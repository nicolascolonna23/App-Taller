"""Reportes offline: recepción idempotente y decisión atómica del taller."""
import base64
import binascii
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import ordenes
import permisos


def exigir(condicion, mensaje):
    if not condicion:
        raise ValueError(mensaje)


def gestor(u):
    return permisos.gestiona(u) and permisos.puede_ver(u, 'solicitudes')


def acceso(u):
    if not (permisos.puede_ver(u, 'choferes') or gestor(u)):
        raise PermissionError('Tu rol no tiene acceso a reportes de choferes.')


def contexto(cx, u):
    acceso(u)
    suc = u.get('sucursal_codigo')
    # Choferes sin sucursal no reciben el catálogo de toda la empresa.
    unidades = cx.execute('''select id, patente, interno from unidades where activa
        and (%s or sucursal=%s) order by patente''', (gestor(u) and not bool(u.get('solo_su_sucursal')), suc)).fetchall()
    return {'usuario_id': u['id'], 'nombre': u['nombre'], 'gestiona': gestor(u),
            'unidades': [dict(r) for r in unidades]}


def listar(cx, u):
    acceso(u)
    return [dict(r) for r in cx.execute('''select r.*, u.patente, us.nombre chofer,
        (select count(*) from reporte_fotos f where f.reporte_id=r.id) fotos,
        o.numero orden_numero from reportes_chofer r
        join unidades u on u.id=r.unidad_id join usuarios us on us.id=r.usuario_id
        left join ordenes_trabajo o on o.id=r.orden_id
        where (%s or r.usuario_id=%s) and (%s or u.sucursal=%s or r.usuario_id=%s)
        order by r.recibido_en desc limit 500''',
        (gestor(u), u['id'], not bool(u.get('solo_su_sucursal')), u.get('sucursal_codigo'), u['id'])).fetchall()]


def obtener(cx, u, id, bloquear=False):
    acceso(u)
    r = cx.execute('select r.*, un.sucursal from reportes_chofer r join unidades un on un.id=r.unidad_id where r.id=%s'
                   + (' for update of r' if bloquear else ''), (str(uuid.UUID(str(id))),)).fetchone()
    exigir(r is not None, 'No existe el reporte.')
    if r['usuario_id'] != u['id'] and (not gestor(u) or
            (bool(u.get('solo_su_sucursal')) and r['sucursal'] != u.get('sucursal_codigo'))):
        raise PermissionError('No tenés acceso a ese reporte.')
    return r


def fotos(cx, u, id):
    r = obtener(cx, u, id)
    return [{'mime': f['mime'], 'datos': base64.b64encode(bytes(f['contenido'])).decode()}
            for f in cx.execute('select mime,contenido from reporte_fotos where reporte_id=%s order by posicion', (r['id'],)).fetchall()]


def validar_fotos(fotos):
    exigir(isinstance(fotos, list) and len(fotos) <= 3, 'Se admiten hasta 3 fotos.')
    salida = []
    for f in fotos:
        exigir(isinstance(f, dict), 'Foto inválida.')
        try:
            b = base64.b64decode(f.get('datos', ''), validate=True)
        except (ValueError, TypeError, binascii.Error):
            raise ValueError('Foto inválida.') from None
        mime = f.get('mime')
        firma = (mime == 'image/jpeg' and b.startswith(b'\xff\xd8\xff') or
                 mime == 'image/png' and b.startswith(b'\x89PNG\r\n\x1a\n') or
                 mime == 'image/webp' and b[:4] == b'RIFF' and b[8:12] == b'WEBP')
        exigir(firma and 0 < len(b) <= 2*1024*1024, 'Foto inválida: JPEG, PNG o WebP de hasta 2 MB.')
        salida.append((mime, b))
    return salida


def recibir(cx, u, d):
    acceso(u)
    exigir(str(d.get('usuario_id')) == str(u['id']), 'El pendiente pertenece a otra cuenta. Iniciá sesión con la cuenta original.')
    id = str(uuid.UUID(str(d.get('id'))))
    # Serializa reintentos incluso si se perdió la respuesta tras el commit.
    cx.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))', (id,))
    existente = cx.execute('select usuario_id from reportes_chofer where id=%s', (id,)).fetchone()
    if existente:
        if existente['usuario_id'] != u['id']:
            raise PermissionError('Identificador ya utilizado.')
        return {'ok': True, 'id': id}
    unidad = cx.execute('select id,sucursal from unidades where id=%s and activa', (d.get('unidad_id'),)).fetchone()
    exigir(unidad is not None, 'Seleccioná una unidad activa.')
    if not gestor(u) and (not u.get('sucursal_codigo') or unidad['sucursal'] != u['sucursal_codigo']):
        raise PermissionError('La unidad no pertenece a tu sucursal.')
    descripcion = str(d.get('descripcion') or '').strip()
    exigir(0 < len(descripcion) <= 2000, 'Describí la falla (hasta 2000 caracteres).')
    urgencia = d.get('urgencia')
    exigir(urgencia in ('PUEDE_ESPERAR','OPERA_CON_RIESGO','UNIDAD_PARADA'), 'Urgencia inválida.')
    try:
        ocurrido = datetime.fromisoformat(str(d.get('ocurrido_en')).replace('Z','+00:00'))
        exigir(ocurrido.tzinfo is not None and ocurrido <= datetime.now(timezone.utc), 'Fecha del reporte inválida.')
    except (TypeError, ValueError):
        raise ValueError('Fecha del reporte inválida.') from None
    adjuntos = validar_fotos(d.get('fotos', []))
    cx.execute('''insert into reportes_chofer(id,usuario_id,unidad_id,descripcion,urgencia,ocurrido_en)
        values(%s,%s,%s,%s,%s,%s)''', (id,u['id'],unidad['id'],descripcion,urgencia,ocurrido))
    for pos, (mime, b) in enumerate(adjuntos):
        cx.execute('insert into reporte_fotos(reporte_id,posicion,mime,contenido) values(%s,%s,%s,%s)', (id,pos,mime,b))
    return {'ok': True, 'id': id}


def resolver(cx, u, d):
    if not gestor(u):
        raise PermissionError('Solo el taller puede resolver reportes.')
    r = obtener(cx, u, d.get('id'), bloquear=True)
    if r['estado'] == 'ORDEN_CREADA' and d['op'] == 'crear_orden':
        return {'ok': True, 'orden_id': r['orden_id']}
    exigir(r['estado'] == 'PENDIENTE', 'El reporte ya está resuelto.')
    orden_id, motivo = None, None
    if d['op'] == 'desestimar':
        motivo = str(d.get('motivo') or '').strip()
        exigir(0 < len(motivo) <= 2000, 'Indicá el motivo (hasta 2000 caracteres).')
        estado = 'DESESTIMADA'
    else:
        if not permisos.puede_ver(u, 'ordenes'):
            raise PermissionError('Falta permiso para órdenes de trabajo.')
        km = str(d.get('km', ''))
        exigir(km.isdigit() and 0 <= int(km) <= 99999999, 'Indicá un kilometraje entero válido.')
        # ordenes.abrir serializa por patente, también con altas manuales.
        salida = ordenes.abrir(cx, {'unidad_id':r['unidad_id'], 'km':d.get('km'),
            'fecha':datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date().isoformat(),
            'mantenimiento':'correctivo', 'solicitado':r['descripcion'],
            'observaciones':f"Reporte de chofer {r['id']}"}, u)
        orden_id, estado = salida['id'], 'ORDEN_CREADA'
    cx.execute('''update reportes_chofer set estado=%s,motivo=%s,orden_id=%s,
        resuelto_por=%s,resuelto_en=now() where id=%s''', (estado,motivo,orden_id,u['id'],r['id']))
    return {'ok':True, 'orden_id':orden_id}
