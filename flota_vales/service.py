"""Mantenimiento integrado. Todas las escrituras usan la transacción del caller."""
import base64
import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo('America/Argentina/Buenos_Aires')
FINALES = {'CERRADA','CANCELADA','RECHAZADA'}
TRANSICIONES = {
 'BORRADOR': {'PENDIENTE_DE_APROBACION': {'sucursal','admin'}},
 'PENDIENTE_DE_APROBACION': {s:{'mantenimiento','admin'} for s in ('APROBADA','OBSERVADA','RECHAZADA')},
 'OBSERVADA': {'PENDIENTE_DE_APROBACION': {'sucursal','admin'}},
 'APROBADA': {'EN_REPARACION': {'sucursal','mantenimiento','admin'}},
 'EN_REPARACION': {'PENDIENTE_DE_FACTURA': {'sucursal','mantenimiento','admin'}},
 'PENDIENTE_DE_FACTURA': {'PENDIENTE_DE_CIERRE': {'sucursal','admin'}},
 'PENDIENTE_DE_CIERRE': {'CERRADA': {'admin'}},
}
PUBLICOS = ('id','numero','sucursal_id','unidad_id','patente','sucursal','estado','urgencia','condicion','emergencia','creado','actualizado')

def exigir(condicion, mensaje):
    if not condicion: raise ValueError(mensaje)

def permiso(condicion):
    if not condicion: raise PermissionError('No tenés permiso para esta operación.')

def texto(d, k, obligatorio=True):
    v = str(d.get(k) or '').strip()
    exigir(len(v)<=10000 and (v or not obligatorio), f'Completá {k.replace("_"," ")}.')
    return v

def importe(v, requerido=False):
    if v in (None,''):
        exigir(not requerido,'Falta el importe.'); return None
    try: n = Decimal(str(v))
    except InvalidOperation: raise ValueError('Importe inválido.')
    exigir(n.is_finite() and n>=0 and n<=Decimal('999999999999.99'),'Importe inválido.')
    exigir(n==n.quantize(Decimal('.01')),'Usá hasta dos decimales.')
    return n

def perfil(cx,u):
    if u['rol']=='admin': return {**u,'rol':'admin','sucursal_id':None}
    p=cx.execute('select * from mt_accesos where usuario_id=%s',(u['id'],)).fetchone()
    permiso(p is not None)
    return {**u,**p}

def config(cx): return cx.execute('select datos from mt_config where id=true').fetchone()['datos']

def propia(p,r): return p['rol']!='sucursal' or p['sucursal_id']==r['sucursal_id']

def solicitud(cx,p,id):
    r=cx.execute('select * from mt_solicitudes where id=%s for update',(id,)).fetchone()
    exigir(r is not None,'Vale inexistente.'); permiso(propia(p,r)); return r

def unidad(cx,p,id):
    r=cx.execute('''select u.*,c.habilitada from unidades u join mt_categorias c on c.codigo=u.mantenimiento_categoria
                     join mt_sucursales b on b.id=u.mantenimiento_sucursal_id and b.activa where u.id=%s for update of u''',(id,)).fetchone()
    exigir(r and r['activa'] and r['habilitada'],'Unidad fuera del alcance o sin sucursal configurada.')
    permiso(p['rol']!='sucursal' or p['sucursal_id']==r['mantenimiento_sucursal_id']); return r

def actualizar(cx,r,**campos):
    # Nombres exclusivamente internos, nunca procedentes del cliente.
    cx.execute('update mt_solicitudes set '+','.join(k+'=%s' for k in campos)+' where id=%s',(*campos.values(),r['id']))

def notificar(cx,r,evento):
    cx.execute('insert into mt_notificaciones(solicitud_id,sucursal_id,evento) values(%s,%s,%s)',(r['id'],r['sucursal_id'],evento))

def estado_preventivo(km,objetivo,umbral):
    if km is None or objetivo is None: return 'sin_datos',None
    restante=Decimal(str(objetivo))-Decimal(str(km))
    return ('vencido' if restante<=0 else 'proximo' if umbral is not None and restante<=Decimal(str(umbral)) else 'normal'),restante

def preventivos(cx,p):
    rows=cx.execute('''select u.id,u.patente,u.interno,u.mantenimiento_categoria categoria,b.id sucursal_id,b.nombre sucursal,u.km_actual,
      o.fecha ultima_lectura,s.fecha ultimo_service,s.objetivo,s.km km_service,pl.intervalo,pl.umbral
      from unidades u join mt_sucursales b on b.id=u.mantenimiento_sucursal_id
      join mt_categorias c on c.codigo=u.mantenimiento_categoria and c.habilitada
      left join lateral(select * from odometros where unidad_id=u.id order by fecha desc,leido desc limit 1)o on true
      left join lateral(select * from mt_services where unidad_id=u.id order by fecha desc,id desc limit 1)s on true
      left join lateral(select * from mt_planes where activo and (unidad_id=u.id or categoria=u.mantenimiento_categoria) order by unidad_id nulls last limit 1)pl on true
      where u.activa and (%s::bigint is null or b.id=%s) order by u.patente''',(p['sucursal_id'] if p['rol']=='sucursal' else None,p['sucursal_id'])).fetchall()
    cfg=config(cx)
    for r in rows:
        r['estado'],r['restantes']=estado_preventivo(r['km_actual'],r['objetivo'],r['umbral'] if r['umbral'] is not None else cfg['umbral_km'])
        r['lectura_desactualizada']=r['ultima_lectura'] is None or (cfg['lectura_dias'] is not None and (datetime.now(TZ).date()-r['ultima_lectura']).days>cfg['lectura_dias'])
        r['inconsistente']=r['km_actual'] is not None and r['km_service'] is not None and r['km_actual']<r['km_service']
    return rows

def leer(cx,u,q):
    op=q.get('op','listar')
    if op=='alcance':
        if not cx.execute("select to_regclass('mt_migraciones') t").fetchone()['t']: return []
        return [r['patente'] for r in cx.execute('select u.patente from unidades u join mt_categorias c on c.codigo=u.mantenimiento_categoria where c.habilitada and u.mantenimiento_sucursal_id is not null').fetchall()]
    p=perfil(cx,u)
    if op=='contexto':
        out={'perfil':{k:p.get(k) for k in ('id','nombre','rol','sucursal_id')},'sucursales':cx.execute('select id,nombre from mt_sucursales where activa order by nombre').fetchall(),'unidades':preventivos(cx,p),'transiciones':{s:[t for t,roles in ts.items() if p['rol'] in roles] for s,ts in TRANSICIONES.items()}}
        if p['rol']!='sucursal':
            out['config']=config(cx)
            if p['rol'] in out['config']['roles_cierre'] and 'CERRADA' not in out['transiciones'].get('PENDIENTE_DE_CIERRE',[]): out['transiciones'].setdefault('PENDIENTE_DE_CIERRE',[]).append('CERRADA')
        return out
    if op=='preventivos':
        rows=preventivos(cx,p)
        if q.get('categoria'): rows=[r for r in rows if r['categoria']==q['categoria']]
        if q.get('sucursal'): rows=[r for r in rows if str(r['sucursal_id'])==str(q['sucursal'])]
        if q.get('estado'): rows=[r for r in rows if r['estado']==q['estado']]
        if q.get('buscar'): rows=[r for r in rows if q['buscar'].lower() in r['patente'].lower()]
        return rows
    if op=='planes':
        permiso(p['rol']!='sucursal')
        return {'planes':cx.execute('select * from mt_planes order by id').fetchall(),'categorias':cx.execute('select * from mt_categorias').fetchall()}
    if op=='admin':
        permiso(p['rol']=='admin')
        return {'config':config(cx),'sucursales':cx.execute('select * from mt_sucursales order by nombre').fetchall(),'usuarios':cx.execute('select u.id,u.usuario,u.nombre,a.rol,a.sucursal_id from usuarios u left join mt_accesos a on a.usuario_id=u.id').fetchall(),'unidades':cx.execute('select id,patente,mantenimiento_sucursal_id,mantenimiento_categoria from unidades where activa order by patente').fetchall(),'planes':cx.execute('select * from mt_planes order by id').fetchall(),'categorias':cx.execute('select * from mt_categorias').fetchall()}
    if op=='notificaciones':
        return {'eventos':cx.execute('''select n.* from mt_notificaciones n where (%s or n.sucursal_id=%s) and not exists(select 1 from mt_notificaciones_leidas l where l.notificacion_id=n.id and l.usuario_id=%s) order by n.id desc limit 100''',(p['rol']!='sucursal',p['sucursal_id'],p['id'])).fetchall(),'services':[x for x in preventivos(cx,p) if x['estado'] in ('proximo','vencido')]}
    if op=='detalle':
        r=cx.execute('select r.*,u.patente,b.nombre sucursal from mt_solicitudes r join unidades u on u.id=r.unidad_id join mt_sucursales b on b.id=r.sucursal_id where r.id=%s',(q.get('id'),)).fetchone()
        exigir(r,'Vale inexistente.')
        if not propia(p,r): return {k:r[k] for k in PUBLICOS}
        r['adjuntos']=cx.execute('select id,categoria,nombre,mime,version,eliminado,creado,usuario_id from mt_adjuntos where solicitud_id=%s order by creado',(r['id'],)).fetchall()
        r['factura']=cx.execute('select * from mt_facturas where solicitud_id=%s',(r['id'],)).fetchone()
        r['comentarios']=cx.execute('select * from mt_comentarios where solicitud_id=%s and (%s or not interno) order by creado',(r['id'],p['rol']!='sucursal')).fetchall()
        r['historial']=cx.execute("select id,creado,usuario_id,anterior->>'estado' anterior,nuevo->>'estado' nuevo,motivo from mt_auditoria where entidad='mt_solicitudes' and entidad_id=%s order by id",(str(r['id']),)).fetchall()
        if p['rol']!='sucursal': r['auditoria']=cx.execute("select * from mt_auditoria where (entidad='mt_solicitudes' and entidad_id=%s) or nuevo->>'solicitud_id'=%s order by id",(str(r['id']),str(r['id']))).fetchall()
        return r
    if op=='indicadores_preventivos':
        permiso(p['rol']!='sucursal')
        rows=preventivos(cx,p)
        if q.get('sucursal'):
            ids={x['id'] for x in cx.execute('select id from unidades where mantenimiento_sucursal_id=%s',(q['sucursal'],)).fetchall()}
            rows=[x for x in rows if x['id'] in ids]
        servicios=cx.execute('''select count(*) total,count(*) filter(where cumplido_en_termino) en_termino,
          count(*) filter(where cumplido_en_termino=false) fuera_de_termino from mt_services s join unidades u on u.id=s.unidad_id
          where not importado and (%s::date is null or s.fecha>=%s::date) and (%s::date is null or s.fecha<=%s::date)
          and (%s::bigint is null or u.mantenimiento_sucursal_id=%s::bigint)''',(q.get('desde') or None,q.get('desde') or None,q.get('hasta') or None,q.get('hasta') or None,q.get('sucursal') or None,q.get('sucursal') or None)).fetchone()
        return {'proximos':sum(r['estado']=='proximo' for r in rows),'vencidos':sum(r['estado']=='vencido' for r in rows),**servicios}
    if op=='indicadores': permiso(p['rol']!='sucursal')
    pagina=max(1,int(q.get('pagina',1))); limite=min(100,max(1,int(q.get('limite',30))))
    where=[]; args=[]
    if q.get('acciones')=='1': where.append("r.estado in ('BORRADOR','OBSERVADA','APROBADA','PENDIENTE_DE_FACTURA','PENDIENTE_DE_CIERRE')")
    for key,col in [('sucursal','r.sucursal_id'),('estado','r.estado'),('urgencia','r.urgencia'),('unidad','r.unidad_id')]:
        if q.get(key): where.append(col+'=%s'); args.append(q[key])
    if q.get('desde'): where.append('r.creado >= %s::date'); args.append(date.fromisoformat(q['desde']))
    if q.get('hasta'): where.append("r.creado < %s::date + interval '1 day'"); args.append(date.fromisoformat(q['hasta']))
    if q.get('buscar'): where.append('(r.numero ilike %s or u.patente ilike %s)'); args.extend(['%'+q['buscar']+'%']*2)
    if q.get('mias')=='1' and p['sucursal_id']: where.append('r.sucursal_id=%s'); args.append(p['sucursal_id'])
    sql=' from mt_solicitudes r join unidades u on u.id=r.unidad_id join mt_sucursales b on b.id=r.sucursal_id left join mt_facturas f on f.solicitud_id=r.id where '+(' and '.join(where) or 'true')
    if op=='indicadores':
        return cx.execute('''select b.nombre sucursal,u.patente,r.estado,r.emergencia,r.proveedor,r.tipo_reparacion,count(*) cantidad,
          avg(extract(epoch from(r.primera_respuesta-r.creado))/3600) horas_primera_respuesta,
          avg(extract(epoch from(r.cerrado-r.aprobacion_fecha))/3600) horas_aprobacion_cierre,
          sum(f.total) facturado,sum(f.total-r.aprobado) diferencia'''+sql+' group by b.nombre,u.patente,r.estado,r.emergencia,r.proveedor,r.tipo_reparacion',args).fetchall()
    total=cx.execute('select count(*) n'+sql,args).fetchone()['n']
    orden={'recientes':'r.creado desc','antiguas':'r.creado asc','prioridad':"r.emergencia desc,(r.condicion='inmovilizada') desc,case r.urgencia when 'critica' then 0 when 'alta' then 1 when 'media' then 2 else 3 end,r.creado"}.get(q.get('orden','prioridad'),'r.creado asc')
    rows=cx.execute('select r.*,u.patente,b.nombre sucursal'+sql+' order by '+orden+' limit %s offset %s',(*args,limite,(pagina-1)*limite)).fetchall()
    return {'items':[r if propia(p,r) else {k:r[k] for k in PUBLICOS} for r in rows],'total':total,'pagina':pagina}

def validar_archivo(d,max_mb):
    try: b=base64.b64decode(d.get('contenido',''),validate=True)
    except Exception: raise ValueError('Archivo inválido.')
    nombre=texto(d,'nombre'); ext=nombre.rsplit('.',1)[-1].lower()
    tipos={'pdf':('application/pdf',b'%PDF-'),'png':('image/png',b'\x89PNG\r\n\x1a\n'),'jpg':('image/jpeg',b'\xff\xd8\xff'),'jpeg':('image/jpeg',b'\xff\xd8\xff'),'webp':('image/webp',b'RIFF')}
    exigir(ext in tipos,'Sólo PDF, PNG, JPEG y WebP.'); mime,firma=tipos[ext]
    exigir(0<len(b)<=int(max_mb)*1024*1024,'Tamaño de archivo no permitido.')
    exigir(d.get('mime')==mime and b.startswith(firma) and (ext!='webp' or b[8:12]==b'WEBP'),'El contenido no coincide con el tipo de archivo.')
    exigir('/' not in nombre and '\\' not in nombre and '\r' not in nombre and '\n' not in nombre,'Nombre inválido.')
    return b,mime,nombre

def cierre_valido(r,f,cfg):
    exigir(r['aprobacion_id'],'Falta aprobación formal.')
    exigir(f is not None,'Falta factura con archivo y datos fiscales.')
    exigir(r['validacion_id'],'Falta validación técnica.')
    exigir(not r['emergencia'] or (r['regularizacion_id'] and r['motivo_emergencia']),'Falta regularización de emergencia.')
    exigir(r['aprobado'] is not None,'Falta importe aprobado.')
    exigir(cfg['tolerancia_pct'] is not None,'Administración debe configurar la tolerancia.')
    exceso=Decimal(str(f['total']))>Decimal(str(r['aprobado']))*(1+Decimal(str(cfg['tolerancia_pct']))/100)
    exigir(not exceso or (r['diferencia_id'] and r['diferencia_motivo']),'La diferencia requiere justificación y nueva autorización.')

def escribir(cx,u,d):
    p=perfil(cx,u); op=d.get('op'); cfg=config(cx)
    cx.execute("select set_config('mt.usuario',%s,true),set_config('mt.motivo',%s,true)",(str(p['id']),str(d.get('motivo') or '')))
    if op=='usuario':
        permiso(p['rol']=='admin'); texto(d,'motivo')
        import auth
        id=auth.crear_usuario(cx,texto(d,'usuario'),texto(d,'nombre'),texto(d,'clave'),'operario')
        cx.execute("insert into mt_auditoria(entidad,entidad_id,accion,usuario_id,nuevo,motivo) values('usuarios',%s,'CREAR',%s,%s,%s)",(str(id),p['id'],json.dumps({'usuario':d['usuario'],'nombre':d['nombre']}),d['motivo']))
        return {'id':id}
    if op in ('sucursal','acceso','config','asignar'):
        permiso(p['rol']=='admin'); texto(d,'motivo')
        if op=='sucursal':
            if d.get('id'): cx.execute('update mt_sucursales set nombre=%s,prefijo=%s,activa=%s where id=%s',(texto(d,'nombre'),texto(d,'prefijo').upper(),bool(d.get('activa',True)),d['id']))
            else: cx.execute('insert into mt_sucursales(nombre,prefijo) values(%s,%s)',(texto(d,'nombre'),texto(d,'prefijo').upper()))
        if op=='acceso':
            exigir(d.get('rol') in ('sucursal','mantenimiento','admin'),'Rol inválido.')
            cx.execute('insert into mt_accesos(usuario_id,rol,sucursal_id) values(%s,%s,%s) on conflict(usuario_id) do update set rol=excluded.rol,sucursal_id=excluded.sucursal_id',(d['usuario_id'],d['rol'],d.get('sucursal_id') or None))
        if op=='asignar':
            old=cx.execute('select mantenimiento_sucursal_id,mantenimiento_categoria from unidades where id=%s for update',(d['unidad_id'],)).fetchone()
            cx.execute('update unidades set mantenimiento_sucursal_id=%s,mantenimiento_categoria=%s where id=%s',(d['sucursal_id'],d['categoria'],d['unidad_id']))
            cx.execute("insert into mt_auditoria(entidad,entidad_id,accion,usuario_id,anterior,nuevo,motivo) values('unidades',%s,'ASIGNAR',%s,%s,%s,%s)",(str(d['unidad_id']),p['id'],json.dumps(old,default=str),json.dumps(d),d['motivo']))
        if op=='config':
            nuevo=d['datos']; exigir(isinstance(nuevo,dict) and set(nuevo)<=set(cfg),'Configuración inválida.')
            cfg.update(nuevo)
            for k in ('umbral_km','lectura_dias','tolerancia_pct'):
                if cfg[k] is not None: importe(cfg[k],True)
            exigir(cfg['duplicados'] in ('bloquear','advertir'),'Política inválida.')
            exigir(isinstance(cfg['max_adjunto_mb'],int) and 1<=cfg['max_adjunto_mb']<=10,'Máximo entre 1 y 10 MB.')
            for k in ('roles_emergencia','roles_diferencia','roles_cierre'): exigir(isinstance(cfg[k],list) and cfg[k] and set(cfg[k])<={'admin','mantenimiento'},'Roles inválidos.')
            cx.execute('update mt_config set datos=%s where id=true',(json.dumps(cfg),))
        return {'ok':True}
    if op=='leida':
        n=cx.execute('select * from mt_notificaciones where id=%s',(d['id'],)).fetchone(); exigir(n,'Aviso inexistente.'); permiso(propia(p,n))
        cx.execute('insert into mt_notificaciones_leidas values(%s,%s) on conflict do nothing',(d['id'],p['id'])); return {'ok':True}
    if op=='corregir_km':
        permiso(p['rol']=='admin'); texto(d,'motivo'); v=unidad(cx,p,d.get('unidad_id')); km=importe(d.get('km'),True)
        cx.execute('insert into odometros(unidad_id,patente,fecha,km,fuente) values(%s,%s,%s,%s,%s)',(v['id'],v['patente'],datetime.now(TZ).date(),km,'correccion:'+str(uuid.uuid4())))
        cx.execute('update unidades set km_actual=%s where id=%s',(km,v['id'])); return {'ok':True}
    if op=='plan':
        permiso(p['rol'] in ('admin','mantenimiento'))
        exigir(importe(d.get('intervalo'),True)>0,'Intervalo debe ser positivo.')
        if d.get('id'):
            texto(d,'motivo')
            cx.execute('update mt_planes set activo=false where id=%s',(d['id'],))
        cx.execute('insert into mt_planes(nombre,categoria,unidad_id,intervalo,umbral) values(%s,%s,%s,%s,%s)',(texto(d,'nombre'),d.get('categoria') or None,d.get('unidad_id') or None,d['intervalo'],importe(d.get('umbral')))); return {'ok':True}
    if op in ('crear','checklist','lectura','service','importar_service'):
        v=unidad(cx,p,d.get('unidad_id'))
        if op=='lectura':
            km=importe(d.get('km'),True); exigir(v['km_actual'] is None or km>=v['km_actual'],'Lectura inferior al valor actual: requiere revisión administrativa.')
            cx.execute('insert into odometros(unidad_id,patente,fecha,km,fuente) values(%s,%s,%s,%s,%s)',(v['id'],v['patente'],datetime.now(TZ).date(),km,'mantenimiento:'+str(uuid.uuid4()))); return {'ok':True}
        if op in ('service','importar_service'):
            permiso(p['rol'] in ('admin','mantenimiento')); km=importe(d.get('km'),True); fecha=date.fromisoformat(texto(d,'fecha')); exigir(fecha<=datetime.now(TZ).date(),'Fecha futura.')
            anterior=cx.execute('select * from mt_services where unidad_id=%s order by fecha desc,id desc limit 1',(v['id'],)).fetchone()
            exigir(not anterior or (fecha>=anterior['fecha'] and km>=anterior['km']),'Service anterior al último registro.')
            plan=cx.execute('select * from mt_planes where activo and (unidad_id=%s or categoria=%s) order by unidad_id nulls last limit 1',(v['id'],v['mantenimiento_categoria'])).fetchone()
            if op=='importar_service':
                exigir(not anterior,'La importación inicial ya fue realizada.'); texto(d,'motivo'); objetivo=importe(d.get('objetivo'),True)
            else: exigir(plan,'Configurá un plan antes de registrar el service.'); objetivo=km+plan['intervalo']
            exigir(objetivo>km,'Objetivo debe superar km del service.')
            cx.execute('insert into mt_services(unidad_id,plan_id,fecha,km,objetivo,usuario_id,importado,cumplido_en_termino) values(%s,%s,%s,%s,%s,%s,%s,%s)',(v['id'],plan['id'] if plan else None,fecha,km,objetivo,p['id'],op=='importar_service',km<=anterior['objetivo'] if anterior else None)); return {'ok':True}
        if op=='checklist':
            exigir(d.get('resultado') in ('sin_novedad','novedad'),'Resultado inválido.')
            exigir(isinstance(d.get('respuestas'),dict),'Completá el checklist.')
            id=cx.execute('insert into mt_checklists(unidad_id,sucursal_id,usuario_id,respuestas,resultado,descripcion) values(%s,%s,%s,%s,%s,%s) returning id',(v['id'],v['mantenimiento_sucursal_id'],p['id'],json.dumps(d['respuestas']),d['resultado'],texto(d,'descripcion',d['resultado']=='novedad'))).fetchone()['id']; return {'id':id}
        permiso(p['rol'] in ('sucursal','admin'))
        exigir(not any(k in d for k in ('numero','sucursal_id','solicitante_id','aprobado')),'La identidad y la aprobación son automáticas.')
        if d.get('checklist_id'):
            ch=cx.execute('select * from mt_checklists where id=%s',(d['checklist_id'],)).fetchone()
            exigir(ch and ch['unidad_id']==v['id'] and ch['sucursal_id']==v['mantenimiento_sucursal_id'] and ch['resultado']=='novedad','Checklist inválido.'); d={**d,'descripcion':ch['descripcion']}
        emergencia=bool(d.get('emergencia')); motivo=texto(d,'motivo_emergencia',emergencia)
        estado='BORRADOR' if d.get('borrador',False) else 'PENDIENTE_DE_APROBACION'
        r=cx.execute('''insert into mt_solicitudes(unidad_id,sucursal_id,solicitante_id,descripcion,sintomas,urgencia,condicion,ubicacion,km,proveedor,estimado,emergencia,motivo_emergencia,estado,checklist_id,tipo_reparacion)
          values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning *''',(v['id'],v['mantenimiento_sucursal_id'],p['id'],texto(d,'descripcion'),texto(d,'sintomas',False),d.get('urgencia','media'),d.get('condicion','operativa'),texto(d,'ubicacion'),importe(d.get('km')),texto(d,'proveedor',False),importe(d.get('estimado')),emergencia,motivo,estado,d.get('checklist_id'),texto(d,'tipo_reparacion',False))).fetchone()
        notificar(cx,r,'Emergencia en ruta' if emergencia else estado); return {'id':r['id'],'numero':r['numero']}
    r=solicitud(cx,p,d.get('id'))
    if op=='reabrir':
        permiso(p['rol']=='admin'); exigir(r['estado'] in FINALES,'Sólo estados finales.'); texto(d,'motivo')
        actualizar(cx,r,estado='PENDIENTE_DE_APROBACION',aprobacion_id=None,aprobacion_fecha=None,regularizacion_id=None,diferencia_id=None,validacion_id=None,cerrado=None)
        notificar(cx,r,'Reapertura excepcional'); return {'ok':True}
    exigir(r['estado'] not in FINALES,'El vale está finalizado.')
    if op=='editar':
        permiso(p['rol'] in ('sucursal','admin')); exigir(r['estado'] in ('BORRADOR','OBSERVADA'),'Sólo borradores u observadas.')
        actualizar(cx,r,descripcion=texto(d,'descripcion'),sintomas=texto(d,'sintomas',False),ubicacion=texto(d,'ubicacion'),estimado=importe(d.get('estimado')))
    elif op=='comentario':
        interno=bool(d.get('interno')); permiso(not interno or p['rol']!='sucursal')
        cx.execute('insert into mt_comentarios(solicitud_id,usuario_id,interno,texto) values(%s,%s,%s,%s)',(r['id'],p['id'],interno,texto(d,'texto')))
    elif op=='adjunto':
        exigir(d.get('categoria') in ('presupuesto','fotografia','factura','diagnostico','otro'),'Categoría inválida.')
        b,mime,nombre=validar_archivo(d,cfg['max_adjunto_mb']); id=str(uuid.uuid4()); version=1
        if d.get('reemplaza'):
            previo=cx.execute('select * from mt_adjuntos where id=%s and solicitud_id=%s',(d['reemplaza'],r['id'])).fetchone(); exigir(previo,'Adjunto inexistente.'); version=previo['version']+1
        cx.execute('insert into mt_adjuntos(id,solicitud_id,categoria,nombre,mime,contenido,sha256,usuario_id,version,reemplaza) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(id,r['id'],d['categoria'],nombre,mime,b,hashlib.sha256(b).hexdigest(),p['id'],version,d.get('reemplaza'))); return {'id':id}
    elif op=='eliminar_adjunto':
        texto(d,'motivo')
        exigir(not cx.execute('select 1 from mt_facturas where adjunto_id=%s union all select 1 from mt_solicitudes where presupuesto_id=%s',(d['adjunto_id'],d['adjunto_id'])).fetchone(),'Adjunto vinculado a factura o aprobación.')
        cx.execute('update mt_adjuntos set eliminado=true where id=%s and solicitud_id=%s',(d['adjunto_id'],r['id']))
    elif op=='reparacion':
        exigir(r['estado']=='EN_REPARACION','Primero iniciá la reparación.')
        trabajo={k:texto(d,k,k in ('proveedor','diagnostico','trabajos','inicio')) for k in ('proveedor','diagnostico','trabajos','repuestos','inicio','fin')}
        inicio=date.fromisoformat(trabajo['inicio']); exigir(inicio<=datetime.now(TZ).date(),'Inicio futuro.')
        if trabajo['fin']: exigir(inicio<=date.fromisoformat(trabajo['fin'])<=datetime.now(TZ).date(),'Fecha de finalización inválida.')
        trabajo['real']=str(importe(d.get('real'),True)); actualizar(cx,r,reparacion=json.dumps(trabajo),proveedor=trabajo['proveedor'],validacion_id=None)
    elif op=='factura':
        exigir(r['estado'] in ('PENDIENTE_DE_FACTURA','PENDIENTE_DE_CIERRE'),'Factura fuera de etapa.')
        a=cx.execute("select id from mt_adjuntos where id=%s and solicitud_id=%s and categoria='factura' and not eliminado",(d['adjunto_id'],r['id'])).fetchone(); exigir(a,'Adjuntá la factura al vale.')
        fiscal=''.join(c for c in texto(d,'fiscal').upper() if c.isalnum()); tipo=texto(d,'tipo').upper(); numero=texto(d,'numero').upper().replace(' ',''); total=importe(d.get('total'),True); exigir(total>0,'Total debe ser positivo.')
        # Serializa por identidad fiscal para advertir incluso con cargas simultáneas.
        cx.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))',(fiscal+'|'+tipo+'|'+numero,))
        dup=cx.execute('select id from mt_facturas where fiscal=%s and tipo=%s and numero=%s and total=%s and solicitud_id<>%s',(fiscal,tipo,numero,total,r['id'])).fetchone()
        if dup:
            exigir(cfg['duplicados']=='advertir','Comprobante duplicado: carga bloqueada.')
            exigir(d.get('confirmar_duplicado') and texto(d,'duplicado_motivo'),'Posible duplicado: confirmá con motivo.')
        fecha=date.fromisoformat(texto(d,'fecha')); exigir(fecha<=datetime.now(TZ).date(),'Fecha de emisión futura.')
        cx.execute('''insert into mt_facturas(solicitud_id,proveedor,fiscal,tipo,numero,fecha,total,adjunto_id,duplicado_motivo) values(%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict(solicitud_id) do update set proveedor=excluded.proveedor,fiscal=excluded.fiscal,tipo=excluded.tipo,numero=excluded.numero,fecha=excluded.fecha,total=excluded.total,adjunto_id=excluded.adjunto_id,duplicado_motivo=excluded.duplicado_motivo''',(r['id'],texto(d,'proveedor'),fiscal,tipo,numero,fecha,total,d['adjunto_id'],d.get('duplicado_motivo')))
        actualizar(cx,r,estado='PENDIENTE_DE_FACTURA',diferencia_id=None,diferencia_motivo=None); notificar(cx,r,'Factura cargada: revisar diferencia y cierre')
    elif op=='validar':
        permiso(p['rol'] in ('mantenimiento','admin')); exigir(r['estado'] in ('PENDIENTE_DE_FACTURA','PENDIENTE_DE_CIERRE'),'El trabajo no finalizó.'); texto(d,'motivo'); actualizar(cx,r,validacion_id=p['id'])
    elif op=='regularizar':
        permiso(p['rol'] in cfg['roles_emergencia']); exigir(r['emergencia'] and r['estado'] in ('EN_REPARACION','PENDIENTE_DE_FACTURA','PENDIENTE_DE_CIERRE'),'No corresponde regularización.'); texto(d,'motivo')
        actualizar(cx,r,regularizacion_id=p['id'],aprobacion_id=p['id'],aprobacion_fecha=datetime.now(TZ),primera_respuesta=r['primera_respuesta'] or datetime.now(TZ),aprobado=importe(d.get('aprobado'),True),diferencia_id=None,diferencia_motivo=None,estado='PENDIENTE_DE_FACTURA' if r['estado']=='PENDIENTE_DE_CIERRE' else r['estado'])
    elif op=='autorizar_diferencia':
        permiso(p['rol'] in cfg['roles_diferencia']); exigir(cx.execute('select id from mt_facturas where solicitud_id=%s',(r['id'],)).fetchone(),'Primero cargá la factura.')
        actualizar(cx,r,diferencia_id=p['id'],diferencia_motivo=texto(d,'motivo'))
    elif op=='transicion':
        destino=d.get('estado'); motivo=texto(d,'motivo'); permitido=p['rol'] in TRANSICIONES.get(r['estado'],{}).get(destino,set())
        if destino=='CANCELADA': permitido=p['rol']=='admin' or (p['rol']=='sucursal' and r['estado'] in ('BORRADOR','OBSERVADA','PENDIENTE_DE_APROBACION'))
        if destino=='CERRADA': permitido=r['estado']=='PENDIENTE_DE_CIERRE' and p['rol'] in cfg['roles_cierre']
        if destino=='EN_REPARACION' and r['emergencia'] and r['estado']=='PENDIENTE_DE_APROBACION':
            permitido=p['rol'] in ('sucursal','admin','mantenimiento')
            exigir(cx.execute("select id from mt_adjuntos where solicitud_id=%s and not eliminado and categoria in ('fotografia','diagnostico','otro')",(r['id'],)).fetchone(),'La emergencia requiere evidencia adjunta.')
        permiso(permitido)
        cambios={'estado':destino}
        if destino in ('APROBADA','OBSERVADA','RECHAZADA') and not r['primera_respuesta']: cambios['primera_respuesta']=datetime.now(TZ)
        if destino=='APROBADA':
            cambios.update(aprobacion_id=p['id'],aprobacion_fecha=datetime.now(TZ),aprobado=importe(d.get('aprobado'),True))
            if d.get('presupuesto_id'):
                exigir(cx.execute("select id from mt_adjuntos where id=%s and solicitud_id=%s and categoria='presupuesto' and not eliminado",(d['presupuesto_id'],r['id'])).fetchone(),'Presupuesto inválido.'); cambios['presupuesto_id']=d['presupuesto_id']
            if r['emergencia']:
                permiso(p['rol'] in cfg['roles_emergencia'])
                exigir(cx.execute("select id from mt_adjuntos where solicitud_id=%s and not eliminado and categoria in ('fotografia','diagnostico','otro')",(r['id'],)).fetchone(),'La emergencia requiere evidencia adjunta.')
                cambios['regularizacion_id']=p['id']
        if destino=='PENDIENTE_DE_FACTURA': exigir(r['reparacion'].get('fin') and r['reparacion'].get('trabajos'),'Completá la ejecución y fecha de finalización.')
        if destino in ('PENDIENTE_DE_CIERRE','CERRADA'):
            f=cx.execute('select f.* from mt_facturas f join mt_adjuntos a on a.id=f.adjunto_id and not a.eliminado where f.solicitud_id=%s',(r['id'],)).fetchone(); cierre_valido(r,f,cfg)
        if destino=='CERRADA': cambios['cerrado']=datetime.now(TZ)
        actualizar(cx,r,**cambios); notificar(cx,r,destino)
    else: raise ValueError('Operación desconocida.')
    return {'ok':True}
