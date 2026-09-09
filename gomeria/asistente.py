"""Asistente de consultas: herramientas permitidas, SQL fijo y transacciones de lectura."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import threading
import time
from zoneinfo import ZoneInfo

import anthropic
import base

ROLES = {'admin', 'encargado', 'operario'}
DOMINIOS = ['cubiertas', 'repuestos', 'unidades', 'vencimientos', 'combustible']
FUENTES = {
    'cubiertas': ('Gomería · inventario y montajes actuales', '/gomeria'),
    'repuestos': ('Repuestos · stock central', '/repuestos'),
    'unidades': ('Flota · maestro de unidades', '/unidades'),
    'vencimientos': ('Vencimientos · últimas renovaciones', '/vencimientos'),
    'combustible': ('Combustible · tickets propios', '/combustible#tickets'),
}
HERRAMIENTAS = [{
    'type': 'function', 'name': 'consultar_sistema', 'strict': True,
    'description': ('Consulta datos actuales. Cubiertas: buscar por código exacto o patente; '
                    'repuestos: texto parcial de código/descripcion/rubro (usar singular, p.ej. acople); '
                    'unidades: patente, interno o texto; vencimientos: patente o nombre del tipo '
                    '(VTV/RTO); combustible: patente o remito. Vacío busca todos. '
                    'Incluye agregados completos y hasta 50 registros; jamás contar solo la muestra.'),
    'parameters': {'type': 'object', 'additionalProperties': False,
                   'properties': {
                       'dominio': {'type': 'string', 'enum': DOMINIOS},
                       'buscar': {'type': 'string', 'description': 'Texto de búsqueda; vacío para todos.'},
                       'estado': {'type': 'string', 'description': 'Vacío o estado exacto. Cubiertas: stock, montada, reparacion, recapado, baja. Vencimientos: vencido, por_vencer, vigente. Unidades: activa, inactiva.'},
                       'desde': {'type': 'string', 'description': 'Vacío o YYYY-MM-DD; filtra fecha de carga o de vencimiento.'},
                       'hasta': {'type': 'string', 'description': 'Vacío o YYYY-MM-DD; inclusivo.'}},
                   'required': ['dominio', 'buscar', 'estado', 'desde', 'hasta']}
}]


class NoDisponible(Exception):
    pass


class Ocupado(Exception):
    pass


def habilitado():
    return bool(os.environ.get('ANTHROPIC_API_KEY', '').strip())


def validar_mensajes(datos):
    if not isinstance(datos, dict) or not isinstance(datos.get('mensajes'), list):
        raise ValueError('Enviá una conversación válida.')
    mensajes = datos['mensajes']
    if not 1 <= len(mensajes) <= 13:
        raise ValueError('Iniciá una nueva consulta: se alcanzó el límite de contexto.')
    for i, m in enumerate(mensajes):
        if not isinstance(m, dict) or set(m) != {'role', 'content'}:
            raise ValueError('Mensaje inválido.')
        if m['role'] != ('user' if i % 2 == 0 else 'assistant'):
            raise ValueError('Orden de mensajes inválido.')
        if not isinstance(m['content'], str) or not 1 <= len(m['content'].strip()) <= 6000:
            raise ValueError('Cada mensaje debe tener entre 1 y 6000 caracteres.')
    if mensajes[-1]['role'] != 'user' or sum(len(m['content']) for m in mensajes) > 24000:
        raise ValueError('La conversación es demasiado larga. Iniciá una nueva consulta.')
    return mensajes


def consulta_sql(args):
    """El modelo elige parámetros; nunca entrega código ni nombres de tablas."""
    expected = {'dominio', 'buscar', 'estado', 'desde', 'hasta'}
    if not isinstance(args, dict) or set(args) != expected or any(not isinstance(v, str) for v in args.values()):
        raise ValueError('Parámetros de consulta inválidos.')
    dominio = args['dominio']
    if dominio not in DOMINIOS or any(len(v) > 120 for v in args.values()):
        raise ValueError('Consulta fuera de alcance.')
    fechas = {}
    for k in ('desde', 'hasta'):
        if args[k]:
            fechas[k] = dt.date.fromisoformat(args[k])
    if len(fechas) == 2 and fechas['desde'] > fechas['hasta']:
        raise ValueError('El inicio del período debe ser anterior al final.')
    if fechas and dominio not in ('vencimientos', 'combustible'):
        raise ValueError('Este dominio muestra estado actual, no historial por fechas.')
    q, estado = args['buscar'].strip(), args['estado'].strip()
    normal = re.sub(r'[^A-Z0-9]', '', q.upper())
    # Los comodines ingresados son texto literal, no expanden el alcance.
    like = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    valores, filtros = [], []
    agregados = 'count(*)::int as cantidad'
    if dominio == 'cubiertas':
        sql = '''select c.codigo, c.marca, c.modelo, c.medida, c.estado,
                 c.remanente_mm, u.patente, u.interno, p.codigo as posicion, m.desde as montada_desde
                 from cubiertas c
                 left join montajes m on m.cubierta_id=c.id and m.hasta is null
                 left join unidades u on u.id=m.unidad_id
                 left join configuracion_posiciones p on p.id=m.posicion_id'''
        if q:
            filtros.append('(upper(c.codigo)=upper(%s) or u.patente=%s)'); valores += [q, normal]
        if estado and estado not in {'stock','montada','reparacion','recapado','baja'}:
            raise ValueError('Estado de cubierta no válido.')
        if estado:
            filtros.append('c.estado=%s'); valores.append(estado)
        orden = 'codigo'
    elif dominio == 'repuestos':
        sql = 'select codigo, descripcion, rubro, stock_actual, stock_minimo, estado from v_repuestos_stock'
        filtros.append('activo')
        if q:
            filtros.append('(codigo ilike %s or descripcion ilike %s or rubro ilike %s)'); valores += [like]*3
        if estado and estado not in {'OK','REPONER','REVISAR','SIN STOCK'}:
            raise ValueError('Estado de repuesto no válido: OK, REPONER, REVISAR o SIN STOCK.')
        if estado:
            filtros.append('estado=%s'); valores.append(estado)
        agregados += ', sum(stock_actual) as unidades_en_stock'
        orden = 'descripcion, codigo'
    elif dominio == 'unidades':
        sql = 'select patente, interno, marca, modelo, tipo, semi, sucursal, uso, activa from unidades'
        if q:
            filtros.append('(patente=%s or interno=%s or marca ilike %s or modelo ilike %s or uso ilike %s)')
            valores += [normal, q, like, like, like]
        if estado and estado not in {'activa','inactiva'}:
            raise ValueError('Las unidades tienen estado activa o inactiva; no existe disponibilidad de acoplados.')
        if estado:
            filtros.append('activa=%s'); valores.append(estado == 'activa')
        orden = 'patente'
    elif dominio == 'vencimientos':
        sql = 'select tipo, patente, interno, identificador, desde, vence, dias, estado from v_vencimientos_hoy'
        filtros.append('unidad_id is not null')
        if q:
            if normal in {'VTV','RTO'}:
                filtros.append("(tipo ilike %s or tipo ilike %s)"); valores += ['%VTV%', '%RTO%']
            else:
                filtros.append('(patente=%s or tipo ilike %s)'); valores += [normal, like]
        if estado and estado not in {'vencido','por_vencer','vigente'}:
            raise ValueError('Estado de vencimiento no válido.')
        if estado:
            filtros.append('estado=%s'); valores.append(estado)
        orden = 'vence, patente, tipo'
    else:
        if estado:
            raise ValueError('Los tickets no tienen estado. Para conciliación usá Cruce de remitos.')
        sql = 'select remito, remito_bruto, fecha, patente, litros, importe, estacion from combustible_cargas'
        filtros.append("origen='planilla'")
        if q:
            filtros.append('(patente=%s or remito=%s)'); valores += [normal, q]
        agregados += ', sum(litros) as litros, sum(importe) as importe_informado, count(importe)::int as tickets_con_importe'
        orden = 'fecha desc nulls last, remito'
    for k, op in [('desde', '>='), ('hasta', '<=')]:
        if k in fechas:
            filtros.append(('vence' if dominio == 'vencimientos' else 'fecha') + ' ' + op + ' %s')
            valores.append(fechas[k])
    if filtros:
        sql += ' where ' + ' and '.join(filtros)
    return sql, valores, agregados, orden


def consultar(args):
    sql, valores, agregados, orden = consulta_sql(args)
    # Una conexión por herramienta; nunca se mantiene abierta esperando al modelo.
    with base.conectar() as cx:
        cx.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        cx.execute("SET LOCAL statement_timeout = '5000ms'")
        cx.execute("SET LOCAL TIME ZONE 'America/Argentina/Buenos_Aires'")
        resumen = dict(cx.execute('select ' + agregados + ' from (' + sql + ') datos', valores).fetchone())
        filas = [dict(r) for r in cx.execute(sql + ' order by ' + orden + ' limit 50', valores).fetchall()]
    titulo, url = FUENTES[args['dominio']]
    return {'fuente': titulo, 'url': url, 'consultado': dt.datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).isoformat(),
            'filtros': args, 'resumen': resumen, 'registros': filas, 'truncado': resumen['cantidad'] > len(filas),
            'nota': 'Datos registrados en el sistema. Sin coincidencias no prueba que no exista el bien o documento.'}


def _mensajes_claude(items):
    """Convierte el contexto interno a bloques de la API Messages de Claude."""
    salida = []

    def agregar(rol, bloques):
        if salida and salida[-1]['role'] == rol:
            salida[-1]['content'].extend(bloques)
        else:
            salida.append({'role': rol, 'content': bloques})

    for item in items:
        if item.get('role') in {'user', 'assistant'}:
            agregar(item['role'], [{'type': 'text', 'text': item['content']}])
        elif item.get('type') == 'function_call':
            agregar('assistant', [{'type': 'tool_use', 'id': item['call_id'],
                    'name': item['name'], 'input': json.loads(item['arguments'])}])
        elif item.get('type') == 'function_call_output':
            agregar('user', [{'type': 'tool_result', 'tool_use_id': item['call_id'],
                    'content': item['output']}])
    return salida


def llamar_modelo(payload):
    herramientas = [{'name': h['name'], 'description': h['description'],
                      'input_schema': h['parameters']} for h in payload['tools']]
    opciones = dict(model=payload['model'], system=payload['instructions'],
                    messages=_mensajes_claude(payload['input']),
                    max_tokens=payload['max_output_tokens'])
    eleccion = payload.get('tool_choice', 'auto')
    if eleccion != 'none':
        opciones['tools'] = herramientas
        opciones['tool_choice'] = {'type': 'any' if eleccion == 'required' else 'auto'}
    try:
        respuesta = anthropic.Anthropic(
            api_key=os.environ['ANTHROPIC_API_KEY'], timeout=35.0
        ).messages.create(**opciones)
        bloques_texto, salida = [], []
        for bloque in respuesta.content:
            if bloque.type == 'text':
                bloques_texto.append({'type': 'output_text', 'text': bloque.text})
            elif bloque.type == 'tool_use':
                salida.append({'type': 'function_call', 'name': bloque.name,
                               'arguments': json.dumps(bloque.input, ensure_ascii=False),
                               'call_id': bloque.id})
        if bloques_texto:
            salida.insert(0, {'type': 'message', 'content': bloques_texto})
        estado = 'completed' if respuesta.stop_reason in {'end_turn', 'tool_use'} else 'incomplete'
        return {'status': estado, 'output': salida}
    except anthropic.APIStatusError as e:
        if e.status_code in (401, 403):
            raise NoDisponible('El administrador debe revisar la clave y el acceso al modelo.') from None
        if e.status_code == 429:
            raise NoDisponible('El proveedor alcanzó su límite de uso. Intentá más tarde.') from None
        raise NoDisponible('El proveedor de IA no pudo responder. Intentá más tarde.') from None
    except (anthropic.APIConnectionError, TimeoutError, OSError, ValueError, KeyError):
        raise NoDisponible('No se pudo conectar con el proveedor de IA. Intentá nuevamente.') from None


# Limita costo/concurrencia en este proceso. No se guardan preguntas ni resultados.
_lock = threading.Lock()
_activos = set()
_ultimos = {}
_slots = threading.BoundedSemaphore(4)


def responder(datos, usuario, modelo_call=None, consulta_call=None):
    if not usuario or usuario.get('rol') not in ROLES:
        raise PermissionError('Necesitás una sesión autorizada para consultar.')
    mensajes = validar_mensajes(datos)
    # La identidad no es un dato operativo ni requiere consultar la base.
    import unicodedata
    saludo = ''.join(c for c in unicodedata.normalize('NFD', mensajes[-1]['content'].lower())
                     if c.isalnum() or c.isspace()).strip()
    if saludo in {'hola', 'hola pengui', 'buen dia', 'buenas', 'quien sos', 'como te llamas'}:
        return {'respuesta': '¡Hola! Soy Pengui, el asistente de IA de Diemar. Te ayudo a consultar stock, cubiertas, unidades, vencimientos y combustible. ¿Qué necesitás saber?', 'fuentes': []}
    if not habilitado():
        raise NoDisponible('El asistente todavía no está configurado. El administrador debe agregar ANTHROPIC_API_KEY en el servidor.')
    uid = usuario['id']
    with _lock:
        ahora = time.monotonic()
        for key in list(_ultimos):
            if ahora - _ultimos[key] > 60:
                del _ultimos[key]
        if uid in _activos or ahora - _ultimos.get(uid, -60) < 3:
            raise Ocupado('Esperá unos segundos antes de enviar otra consulta.')
        if not _slots.acquire(blocking=False):
            raise Ocupado('Hay varias consultas en curso. Intentá en unos segundos.')
        _activos.add(uid)
        _ultimos[uid] = ahora
    try:
        return _responder(mensajes, modelo_call or llamar_modelo, consulta_call or consultar)
    finally:
        with _lock:
            _activos.discard(uid)
        _slots.release()


def _responder(mensajes, modelo_call, consulta_call):
    reglas = Path(__file__).with_name('asistente_reglas.md').read_text(encoding='utf-8')
    instrucciones = reglas + '\nFecha actual en Argentina: ' + str(dt.datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date())
    contexto = [dict(m) for m in mensajes]
    fuentes, llamadas = [], 0
    # Hasta 4 rondas y 8 consultas. Los resultados nunca habilitan herramientas nuevas.
    for ronda in range(4):
        respuesta = modelo_call({'model': os.environ.get('ANTHROPIC_MODEL', 'claude-opus-5'),
            'instructions': instrucciones, 'input': contexto, 'tools': HERRAMIENTAS,
            'tool_choice': 'required' if ronda == 0 else ('none' if ronda == 3 or llamadas >= 8 else 'auto'),
            'parallel_tool_calls': False, 'store': False, 'max_output_tokens': 2400})
        if respuesta.get('status') != 'completed':
            raise NoDisponible('La respuesta quedó incompleta. Probá con una pregunta más específica.')
        output = respuesta.get('output', [])
        calls = [o for o in output if o.get('type') == 'function_call']
        if not calls:
            texto = '\n'.join(c['text'] for o in output if o.get('type') == 'message'
                              for c in o.get('content', []) if c.get('type') == 'output_text')
            if not texto or not fuentes:
                raise NoDisponible('No fue posible obtener una respuesta respaldada por datos. Reformulá la consulta.')
            return {'respuesta': texto, 'fuentes': fuentes}
        contexto.extend(output)
        for call in calls:
            llamadas += 1
            if llamadas > 8:
                raise NoDisponible('La consulta requiere demasiados pasos. Dividila en preguntas más concretas.')
            try:
                if call.get('name') != 'consultar_sistema':
                    raise ValueError('Herramienta no permitida.')
                args = json.loads(call['arguments'])
                consulta_sql(args)  # valida incluso con transporte de consulta inyectado en tests
                resultado = consulta_call(args)
                fuentes.append({k: resultado[k] for k in ('fuente', 'url', 'consultado', 'filtros', 'resumen', 'truncado')})
            except (ValueError, KeyError, TypeError):
                resultado = {'error': 'Parámetros inválidos. Revisá dominio, estado y fechas; no hay datos verificados de esta consulta.'}
            except Exception:
                # No filtrar SQL, DSN, secretos ni errores internos al modelo o navegador.
                resultado = {'error': 'Esta fuente no está disponible. No equivale a cero registros. Informá la limitación.'}
            contexto.append({'type': 'function_call_output', 'call_id': call['call_id'],
                             'output': json.dumps(resultado, default=str, ensure_ascii=False)})
    raise NoDisponible('No se pudo completar la consulta en el límite de pasos.')
