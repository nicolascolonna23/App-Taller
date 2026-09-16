import csv
import io
import json
import traceback
from urllib.parse import urlparse,parse_qs,quote
import psycopg
from . import service

def atender(h,base,escritura=False):
    if not h._exigir_sesion(): return
    try:
        q={k:v[0] for k,v in parse_qs(urlparse(h.path).query).items()}
        with base.conectar() as cx:
            if escritura:
                origin=h.headers.get('Origin')
                if origin and urlparse(origin).netloc!=h.headers.get('Host'): raise PermissionError('Origen no autorizado.')
                if h.headers.get('Sec-Fetch-Site')=='cross-site': raise PermissionError('Origen no autorizado.')
                if h.headers.get('Content-Type','').split(';')[0]!='application/json': raise ValueError('Se requiere JSON.')
                n=int(h.headers.get('Content-Length','0'))
                if not 0<n<=15*1024*1024: return h._error('Tamaño de pedido inválido.',413)
                d=json.loads(h.rfile.read(n)); service.exigir(isinstance(d,dict),'Pedido inválido.')
                salida=service.escribir(cx,h.usuario,d)
            elif q.get('op')=='descargar':
                p=service.perfil(cx,h.usuario)
                a=cx.execute('select a.*,r.sucursal_id from mt_adjuntos a join mt_solicitudes r on r.id=a.solicitud_id where a.id=%s and not a.eliminado',(q.get('id'),)).fetchone()
                service.exigir(a,'Adjunto inexistente.'); service.permiso(service.propia(p,a))
                b=bytes(a['contenido']); h.send_response(200); h.send_header('Content-Type','application/octet-stream'); h.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(a['nombre'])); h.send_header('Content-Length',str(len(b))); h.send_header('X-Content-Type-Options','nosniff'); h.send_header('Cache-Control','no-store'); h.end_headers(); h.wfile.write(b); return
            else: salida=service.leer(cx,h.usuario,q)
        if q.get('csv')=='1':
            service.permiso(q.get('op')=='indicadores')
            buf=io.StringIO(); rows=salida
            if rows:
                writer=csv.DictWriter(buf,fieldnames=list(rows[0])); writer.writeheader()
                writer.writerows({k:("'"+str(v) if str(v).startswith(('=','+','-','@','\t','\r')) else v) for k,v in r.items()} for r in rows)
            return h._responder('\ufeff'+buf.getvalue(),'text/csv; charset=utf-8')
        return h._responder(json.dumps(salida,ensure_ascii=False,default=str))
    except PermissionError as e: return h._error(str(e),403)
    except (ValueError,KeyError,TypeError,psycopg.errors.CheckViolation,psycopg.errors.ForeignKeyViolation,psycopg.errors.InvalidTextRepresentation) as e:
        return h._error(str(e) if isinstance(e,ValueError) else 'Datos inválidos; revisá los campos.')
    except psycopg.errors.UniqueViolation: return h._error('El registro ya existe. Revisá duplicados o recargá.',409)
    except psycopg.errors.UndefinedTable: return h._error('Falta aplicar la migración de mantenimiento.',503)
    except Exception:
        traceback.print_exc(); return h._error('No se pudo completar la operación. No se guardaron cambios.',500)
