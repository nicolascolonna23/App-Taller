"""Solicitudes de orden de compra: el registro nace antes de la reparación.

El preventivo ya estaba procedimentado. El correctivo que resolvía una
sucursal se hacía y se rendía como un gasto más: la plata quedaba
anotada, la intervención técnica no. La solicitud corrige eso con una
sola idea: una sucursal no manda a hacer un trabajo de taller sin una
solicitud aprobada, y no rinde la factura sin el número escrito.

Lo que manda a hacer mantenimiento queda afuera del circuito: el área que
decide el gasto es la misma que lo controla, y pedirle una solicitud a sí
misma sería papeleo. Eso lo decide la orden externa cuando se carga, con
una sola pregunta: ¿quién lo mandó a hacer?

El circuito es corto a propósito —pedir, aprobar, reparar, rendir— y son
cuatro estados y un botón por parte del taller:

    SOLICITADO ──aprobar──▶ APROBADO ──iniciar──▶ EN_EJECUCION ──┐
         │                      │                                │
         └──rechazar──▶ RECHAZADO└──────── cerrar ───────────────▶ CERRADO

Dos reglas duras, que son el módulo entero:

  * No se compra ni se repara con la solicitud en SOLICITADO o RECHAZADO.
  * Una sucursal no rinde una factura de taller sin una solicitud CERRADA.
    Esa validación vive en el módulo de gastos —acá, las órdenes
    externas— y entra por `validar_para_gasto`.

El número lo da el sistema y sale de quién pide: `CAT-00001`. Es
correlativo por sucursal e inmutable —el número de una solicitud rechazada no se
reutiliza—, por eso no hay ningún borrado de solicitudes en este archivo.
"""
from datetime import date, datetime, timedelta, timezone

import alertas
import permisos

# El taller y mantenimiento aprueban: es el permiso «gestiona» del rol,
# que se marca desde Usuarios y roles (ver permisos.py). La sucursal pide,
# y también puede iniciar y cerrar: el que tiene la factura en la mano es
# el que la carga.

TIPOS = ("PREVENTIVO", "CORRECTIVO", "GOMERIA", "SINIESTRO")
ORIGENES = ("CHECKLIST", "RUTA", "RUTINA_SEMANAL", "PREVENTIVO_KM", "CONTROL_MENSUAL")
URGENCIAS = ("PUEDE_ESPERAR", "OPERA_CON_RIESGO", "UNIDAD_PARADA")

TRANSICIONES = {
    "SOLICITADO":   ("APROBADO", "RECHAZADO"),
    "APROBADO":     ("EN_EJECUCION", "CERRADO"),
    "EN_EJECUCION": ("CERRADO",),
    "CERRADO":      (),
    "RECHAZADO":    (),
}

# Lo que no pasa por el circuito. La lista decide, no el monto: un tope de
# plata se interpreta, se discute y se esquiva. Se resuelve y se informa
# en el control mensual.
LISTA_BLANCA = (
    "Lámparas, fusibles y plumillas",
    "Aceite, agua y refrigerante de reposición",
    "Inflado, parche o auxilio en ruta",
    "Ajuste de tuercas y controles sin repuesto",
)

# El taller tiene 24 horas hábiles para contestar: un día hábil. Con la
# unidad parada la respuesta es inmediata, así que la tolerancia es de
# horas y la solicitud se va arriba de la bandeja.
RESPUESTA_DIAS_HABILES = 1
RESPUESTA_PARADA_HORAS = 2

# La regularización de un arreglo autorizado por teléfono en la ruta: 48
# horas hábiles para cargar la solicitud.
REGULARIZACION_DIAS_HABILES = 2

# Cuánto mira la pantalla hacia atrás. Lo que no está cerrado se muestra
# siempre, tenga la antigüedad que tenga.
VENTANA_MESES = 12


# =====================================================================
# AYUDAS
# =====================================================================
def puede_aprobar(usuario):
    return permisos.gestiona(usuario)


def _texto(valor, limite=2000):
    texto = str(valor or "").strip()
    return texto[:limite] or None


def _patente(valor):
    """Como la guarda el resto del sistema: sin espacios ni guiones."""
    return "".join(c for c in str(valor or "").upper() if c.isalnum())


def _opcion(valor, validas, campo):
    elegida = str(valor or "").strip().upper()
    if elegida not in validas:
        raise ValueError(f"Falta {campo}.")
    return elegida


def _numero(valor, campo):
    if valor in (None, ""):
        return None
    try:
        n = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{campo} tiene que ser un número.") from None
    if n < 0:
        raise ValueError(f"{campo} no puede ser negativo.")
    return n


def _km(valor):
    km = _numero(valor, "El kilometraje")
    if km is None:
        raise ValueError("Falta el kilometraje de la unidad.")
    return km


def _fecha(valor, campo="la fecha"):
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor).strip()[:10])
    except ValueError:
        raise ValueError(f"No se entiende {campo}: {valor}") from None


def dias_habiles(desde, hasta):
    """Días hábiles enteros entre dos fechas. Sábado y domingo no cuentan.

    No conoce los feriados: para lo que se usa —marcar una solicitud demorado y
    contar una regularización fuera de término— errar por un feriado es
    preferible a mantener un calendario que nadie va a actualizar.
    """
    desde, hasta = _fecha(desde), _fecha(hasta)
    if not desde or not hasta or hasta <= desde:
        return 0
    dias, actual = 0, desde
    while actual < hasta:
        actual += timedelta(days=1)
        if actual.weekday() < 5:
            dias += 1
    return dias


def _ahora():
    return datetime.now(timezone.utc)


def demorado(solicitud, ahora=None):
    """¿El taller se pasó del tiempo que tiene para contestar?"""
    if (solicitud or {}).get("estado") != "SOLICITADO":
        return False
    creado = solicitud.get("creado_en")
    if not isinstance(creado, datetime):
        return False
    ahora = ahora or _ahora()
    if creado.tzinfo is None:
        creado = creado.replace(tzinfo=timezone.utc)
    if solicitud.get("urgencia") == "UNIDAD_PARADA":
        return (ahora - creado) > timedelta(hours=RESPUESTA_PARADA_HORAS)
    return dias_habiles(creado.date(), ahora.date()) > RESPUESTA_DIAS_HABILES


def _evento(cx, solicitud_id, estado, usuario, comentario=None):
    """El historial. Se escribe siempre, en la misma transacción."""
    cx.execute("""
        insert into solicitud_eventos (solicitud_id, estado, usuario, comentario)
        values (%s, %s, %s, %s)
    """, (solicitud_id, estado, (usuario or {}).get("nombre"), _texto(comentario, 500)))


def _solicitud(cx, solicitud_id, bloquear=False):
    """La solicitud, o el error de por qué no se puede seguir."""
    solicitud_id = str(solicitud_id or "").strip().upper()
    if not solicitud_id:
        raise ValueError("No se sabe de qué solicitud se habla.")
    fila = cx.execute(
        "select * from solicitudes_compra where id = %s" + (" for update" if bloquear else ""),
        (solicitud_id,)).fetchone()
    if not fila:
        raise ValueError(f"La solicitud {solicitud_id} no existe.")
    return fila


def _exigir_transicion(solicitud, destino):
    if destino not in TRANSICIONES[solicitud["estado"]]:
        raise ValueError(
            f"La solicitud {solicitud['id']} está {ESTADO_LEGIBLE[solicitud['estado']]}: "
            f"no puede pasar a {ESTADO_LEGIBLE[destino]}.")


# Como se lee en un mensaje: "La solicitud CAT-00001 está rechazada".
ESTADO_LEGIBLE = {
    "SOLICITADO": "solicitada", "APROBADO": "aprobada",
    "EN_EJECUCION": "en ejecución", "CERRADO": "cerrada",
    "RECHAZADO": "rechazada",
}


def _unidad(cx, datos):
    """La unidad de la solicitud. Devuelve (id, patente, fila o None)."""
    unidad_id = datos.get("unidad_id") or None
    patente = _patente(datos.get("patente"))
    fila = None
    if unidad_id:
        fila = cx.execute("select * from unidades where id = %s",
                          (unidad_id,)).fetchone()
        if not fila:
            raise ValueError("Esa unidad no existe.")
        patente = fila["patente"]
    elif patente:
        fila = cx.execute("select * from unidades where patente = %s",
                          (patente,)).fetchone()
        unidad_id = fila["id"] if fila else None
    if not patente:
        raise ValueError("Falta la patente de la unidad.")
    return unidad_id, patente, fila


def _sucursal(cx, datos, usuario):
    """De qué sucursal sale el número.

    Sale de quién pide, no de lo que se elija en la pantalla: si el
    usuario tiene sucursal cargada, esa es y no hay discusión. Al que no
    la tenga —administración, mantenimiento— se le pregunta.
    """
    propia = _texto((usuario or {}).get("sucursal_codigo"), 3)
    pedida = _texto(datos.get("sucursal_codigo") or datos.get("sucursal"), 3)
    codigo = (propia or pedida or "").upper()
    if not codigo:
        raise ValueError("Falta la sucursal que pide la solicitud.")
    fila = cx.execute("select codigo, nombre, activa from sucursales where codigo = %s",
                      (codigo,)).fetchone()
    if not fila:
        raise ValueError(f"No existe la sucursal {codigo}.")
    if not fila["activa"]:
        raise ValueError(f"La sucursal {fila['nombre']} está dada de baja.")
    return fila["codigo"]


def _numerar(cx, codigo):
    """El siguiente número de esa sucursal, con la fila del contador tomada.

    El `for update` es el módulo: dos sucursales cargando en el mismo
    segundo no se estorban —son dos filas—, y dos usuarios de la misma
    sucursal esperan uno al otro en vez de escribir el mismo número.
    """
    fila = cx.execute("""select ultimo from solicitudes_contador
                         where sucursal_codigo = %s for update""",
                      (codigo,)).fetchone()
    if not fila:
        cx.execute("""insert into solicitudes_contador (sucursal_codigo) values (%s)
                      on conflict (sucursal_codigo) do nothing""", (codigo,))
        fila = cx.execute("""select ultimo from solicitudes_contador
                             where sucursal_codigo = %s for update""",
                          (codigo,)).fetchone()
    if not fila:
        raise ValueError(f"No se pudo numerar la solicitud de {codigo}. "
                         "Ejecutar gomeria/26_solicitudes.sql en Supabase.")
    numero = int(fila["ultimo"]) + 1
    cx.execute("update solicitudes_contador set ultimo = %s where sucursal_codigo = %s",
               (numero, codigo))
    return numero, f"{codigo}-{numero:05d}"


# =====================================================================
# LECTURA
# =====================================================================
def listar(cx, usuario=None):
    """Todo lo que la pantalla dibuja de una.

    Es una sola lista para las cuatro vistas —bandeja, mi sucursal, toda
    la red y la ficha de la unidad—: que cada responsable vea el resto no
    es un detalle, es lo que hace que se comparen los tiempos de
    respuesta sin que nadie tenga que pedirlo.
    """
    solicitudes = cx.execute("""
        select * from v_solicitudes
        where estado in ('SOLICITADO','APROBADO','EN_EJECUCION')
           or creado_en >= now() - interval '%s months'
        order by estado in ('SOLICITADO','APROBADO','EN_EJECUCION') desc,
                 creado_en desc
    """ % int(VENTANA_MESES)).fetchall()

    ahora = _ahora()
    salida, resumen = [], {e: 0 for e in TRANSICIONES}
    resumen.update({"demorados": 0, "parados": 0, "sin_rendir": 0})
    for fila in solicitudes:
        solicitud = dict(fila)
        solicitud["demorado"] = demorado(solicitud, ahora)
        solicitud["dias_espera"] = dias_habiles(
            solicitud["creado_en"], ahora) if solicitud["estado"] == "SOLICITADO" else None
        resumen[solicitud["estado"]] = resumen.get(solicitud["estado"], 0) + 1
        if solicitud["demorado"]:
            resumen["demorados"] += 1
        if solicitud["estado"] == "SOLICITADO" and solicitud["urgencia"] == "UNIDAD_PARADA":
            resumen["parados"] += 1
        if solicitud["estado"] == "CERRADO" and not solicitud.get("orden_numero"):
            resumen["sin_rendir"] += 1
        salida.append(solicitud)

    return {
        "solicitudes": salida,
        "resumen": resumen,
        "sucursales": [dict(s) for s in cx.execute("""
            select codigo, nombre, activa from sucursales
            where activa order by orden, codigo""").fetchall()],
        "unidades": [dict(u) for u in cx.execute("""
            select id, patente, interno, marca, modelo, sucursal, chofer, km_actual
            from unidades where activa order by patente""").fetchall()],
        "tipos": TIPOS, "origenes": ORIGENES, "urgencias": URGENCIAS,
        "lista_blanca": list(LISTA_BLANCA),
        "usuario": {
            "nombre": (usuario or {}).get("nombre"),
            "sucursal_codigo": (usuario or {}).get("sucursal_codigo"),
            "puede_aprobar": puede_aprobar(usuario),
        },
        "exigir_solicitud": bool(exigir_solicitud(cx)),
    }


def ficha(cx, solicitud_id):
    """Una solicitud con su historial: lo que se imprime y se firma."""
    solicitud = cx.execute("select * from v_solicitudes where id = %s",
                      (str(solicitud_id or "").strip().upper(),)).fetchone()
    if not solicitud:
        raise ValueError("Esa solicitud no existe.")
    solicitud = dict(solicitud)
    solicitud["demorado"] = demorado(solicitud)
    return {
        "solicitud": solicitud,
        "eventos": [dict(e) for e in cx.execute("""
            select estado, usuario, momento, comentario
            from solicitud_eventos where solicitud_id = %s order by id
        """, (solicitud["id"],)).fetchall()],
    }


def historial(cx, patente=None, unidad_id=None):
    """La ficha de la unidad: todo lo que se le pidió, por patente.

    Va por patente y no por unidad_id, igual que las órdenes: una unidad
    que se dio de baja y se volvió a cargar cambia de id, pero es el mismo
    camión y su historia tiene que seguir junta. Esta es la vista que
    detecta la unidad que entra tres veces por la misma falla.
    """
    patente = _patente(patente)
    if not patente and unidad_id:
        fila = cx.execute("select patente from unidades where id = %s",
                          (unidad_id,)).fetchone()
        patente = fila["patente"] if fila else None
    if not patente:
        raise ValueError("Debe seleccionarse la unidad para ver su historial.")

    solicitudes = [dict(v) for v in cx.execute("""
        select * from v_solicitudes where patente = %s
        order by creado_en desc""", (patente,)).fetchall()]

    gasto = {t: 0.0 for t in TIPOS}
    for v in solicitudes:
        if v["estado"] != "RECHAZADO":
            gasto[v["tipo"]] = gasto.get(v["tipo"], 0.0) + float(v["monto"] or 0)
    return {
        "patente": patente,
        "solicitudes": solicitudes,
        "gasto": gasto,
        "total": round(sum(gasto.values()), 2),
    }


# =====================================================================
# ESCRITURA — el circuito
# =====================================================================
def crear(cx, datos, usuario):
    """Un pedido nuevo. Seis campos: patente, km, tipo, origen, urgencia y detalle.

    La sucursal no elige el número ni el estado: los dos los pone el
    sistema. Nace SOLICITADO y con su primer evento.
    """
    codigo = _sucursal(cx, datos, usuario)
    unidad_id, patente, unidad = _unidad(cx, datos)
    km = _km(datos.get("km") if datos.get("km") not in (None, "")
             else (unidad and unidad["km_actual"]))
    tipo = _opcion(datos.get("tipo"), TIPOS, "el tipo de trabajo")
    origen = _opcion(datos.get("origen"), ORIGENES, "de dónde sale el pedido")
    urgencia = _opcion(datos.get("urgencia") or "PUEDE_ESPERAR", URGENCIAS,
                       "la urgencia")
    detalle = _texto(datos.get("detalle"))
    if not detalle:
        raise ValueError("Falta el detalle de la falla o la tarea.")

    # La excepción de ruta: se autorizó por teléfono con la unidad parada
    # fuera de la sucursal y la solicitud se carga después. La fecha del hecho
    # puede ser anterior a la de carga; la de mañana no existe.
    regularizacion = bool(datos.get("regularizacion_ruta"))
    hecho = _fecha(datos.get("fecha_hecho"), "la fecha del hecho") or date.today()
    if hecho > date.today():
        raise ValueError("La fecha del hecho no puede ser posterior a hoy.")
    if hecho < date.today() and not regularizacion:
        raise ValueError("Una solicitud con fecha anterior a hoy es una regularización "
                         "de ruta: marcala para poder cargarlo.")

    anterior = _texto(datos.get("solicitud_anterior"), 20)
    if anterior:
        previo = _solicitud(cx, anterior)
        if previo["patente"] != patente:
            raise ValueError(f"La solicitud {previo['id']} es de otra unidad.")
        anterior = previo["id"]

    numero, solicitud_id = _numerar(cx, codigo)
    cx.execute("""
        insert into solicitudes_compra
          (id, sucursal_codigo, numero, unidad_id, patente, km, tipo, origen,
           urgencia, detalle, taller_sugerido, monto_estimado, estado,
           solicitante, solicitante_id, fecha_hecho, regularizacion_ruta,
           solicitud_anterior)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'SOLICITADO',%s,%s,%s,%s,%s)
    """, (solicitud_id, codigo, numero, unidad_id, patente, km, tipo, origen,
          urgencia, detalle, _texto(datos.get("taller_sugerido"), 120),
          _numero(datos.get("monto_estimado"), "El monto estimado"),
          (usuario or {}).get("nombre"), (usuario or {}).get("id"),
          hecho, regularizacion, anterior))

    comentario = _texto(datos.get("comentario"), 500)
    if regularizacion and not comentario:
        comentario = (f"Regularización de ruta: el hecho fue el "
                      f"{hecho.isoformat()} y se autorizó verbalmente.")
    _evento(cx, solicitud_id, "SOLICITADO", usuario, comentario)
    return {"ok": True, "id": solicitud_id, "numero": numero, "sucursal_codigo": codigo,
            "fuera_de_termino": bool(
                regularizacion and dias_habiles(hecho, date.today())
                > REGULARIZACION_DIAS_HABILES)}


def aprobar(cx, datos, usuario):
    """El taller dice que sí. Recién acá se puede comprar o reparar."""
    if not puede_aprobar(usuario):
        raise PermissionError("Solo el taller o mantenimiento puede aprobar una solicitud.")
    solicitud = _solicitud(cx, datos.get("id"), bloquear=True)
    _exigir_transicion(solicitud, "APROBADO")

    monto = _numero(datos.get("monto_autorizado"), "El monto autorizado")
    taller = _texto(datos.get("taller"), 120) or solicitud["taller_sugerido"]
    nota = _texto(datos.get("nota"), 500)
    cx.execute("""
        update solicitudes_compra set estado = 'APROBADO', monto_autorizado = coalesce(%s, monto_autorizado),
               taller = %s, nota = %s, aprobado_en = now(), aprobado_por = %s
        where id = %s
    """, (monto, taller, nota, (usuario or {}).get("nombre"), solicitud["id"]))
    _evento(cx, solicitud["id"], "APROBADO", usuario, nota)
    return {"ok": True, "id": solicitud["id"], "estado": "APROBADO"}


def rechazar(cx, datos, usuario):
    """El taller dice que no, y dice por qué. De acá no se vuelve."""
    if not puede_aprobar(usuario):
        raise PermissionError("Solo el taller o mantenimiento puede rechazar una solicitud.")
    solicitud = _solicitud(cx, datos.get("id"), bloquear=True)
    _exigir_transicion(solicitud, "RECHAZADO")

    nota = _texto(datos.get("nota"), 500)
    if not nota:
        raise ValueError("Un rechazo sin motivo no le sirve a la sucursal: "
                         "escribí por qué no va.")
    cx.execute("""update solicitudes_compra set estado = 'RECHAZADO', nota = %s
                  where id = %s""", (nota, solicitud["id"]))
    _evento(cx, solicitud["id"], "RECHAZADO", usuario, nota)
    return {"ok": True, "id": solicitud["id"], "estado": "RECHAZADO"}


def iniciar(cx, datos, usuario):
    """La unidad entró al taller. El trabajo empezó."""
    solicitud = _solicitud(cx, datos.get("id"), bloquear=True)
    _exigir_transicion(solicitud, "EN_EJECUCION")
    cx.execute("update solicitudes_compra set estado = 'EN_EJECUCION' where id = %s", (solicitud["id"],))
    _evento(cx, solicitud["id"], "EN_EJECUCION", usuario, _texto(datos.get("comentario"), 500))
    return {"ok": True, "id": solicitud["id"], "estado": "EN_EJECUCION"}


def cerrar(cx, datos, usuario):
    """El trabajo se hizo y está la factura. La solicitud queda como está.

    Una solicitud preventiva cerrada es además el último service de la unidad:
    se registra acá para que el próximo service se recalcule solo. Si la
    unidad no tiene plan de mantenimiento asignado la solicitud se cierra
    igual y se avisa: la sucursal que tiene la factura en la mano no
    puede quedar trabada por una parametrización que no depende de ella.
    """
    solicitud = _solicitud(cx, datos.get("id"), bloquear=True)
    _exigir_transicion(solicitud, "CERRADO")

    factura = _texto(datos.get("factura_numero") or datos.get("factura"), 60)
    if not factura:
        raise ValueError("Falta el número de factura: sin eso la solicitud no cierra.")
    monto = _numero(datos.get("monto_autorizado"), "El monto")

    cx.execute("""
        update solicitudes_compra
        set estado = 'CERRADO', factura_numero = %s,
            monto_autorizado = coalesce(%s, monto_autorizado),
            cerrado_en = now(), cerrado_por = %s
        where id = %s
    """, (factura, monto, (usuario or {}).get("nombre"), solicitud["id"]))
    _evento(cx, solicitud["id"], "CERRADO", usuario,
            _texto(datos.get("comentario"), 500) or f"Factura {factura}.")

    service_id, aviso = _registrar_preventivo(cx, solicitud, usuario)
    return {"ok": True, "id": solicitud["id"], "estado": "CERRADO",
            "service_id": service_id, "aviso": aviso}


def _registrar_preventivo(cx, solicitud, usuario):
    """Hace que una solicitud preventiva cerrada sea también el último service."""
    if solicitud["tipo"] != "PREVENTIVO" or not solicitud["unidad_id"]:
        return None, None
    existente = cx.execute("select id from services where solicitud_id = %s",
                           (solicitud["id"],)).fetchone()
    if existente:
        return existente["id"], None
    try:
        service_id = alertas.guardar_service(cx, {
            "unidad_id": solicitud["unidad_id"],
            "fecha": date.today().isoformat(),
            "km": solicitud["km"],
            "tipo": (solicitud["detalle"] or "Mantenimiento preventivo")[:60],
            "taller": solicitud["taller"] or solicitud["taller_sugerido"],
            "observaciones": f"Registrado desde la solicitud {solicitud['id']}.",
        }, usuario=(usuario or {}).get("nombre"))
    except ValueError as e:
        return None, (f"La solicitud cerró, pero el service no se pudo registrar: {e}")
    cx.execute("update services set solicitud_id = %s where id = %s",
               (solicitud["id"], service_id))
    return service_id, None


# =====================================================================
# LA REGLA QUE MIRA EL MÓDULO DE GASTOS
# =====================================================================
def exigir_solicitud(cx):
    """¿Le exigimos solicitud a la factura que rinde una sucursal?

    Por regla sí. Nunca a la que rinde mantenimiento: eso lo separa la
    orden externa con su campo `gestion`, no este interruptor.

    Devuelve None cuando el módulo todavía no se corrió en esta base. No
    es lo mismo que "no exigir": sin las tablas no hay ni circuito ni
    columna donde anotar quién mandó a hacer el trabajo, así que el que
    carga una factura tiene que poder seguir como antes.
    """
    try:
        fila = cx.execute("select exigir_solicitud from solicitudes_ajustes").fetchone()
    except Exception:
        cx.rollback()
        return None
    return bool(fila["exigir_solicitud"]) if fila else True


def validar_para_gasto(cx, solicitud_id, patente, orden_id=None):
    """La solicitud con la que se rinde una factura, o el error que corresponde.

    Lo llama el módulo de órdenes antes de guardar un servicio externo.
    Una solicitud sirve para rendir si está CERRADA, es de esa unidad y no
    se usó en otra factura.
    """
    solicitud = _solicitud(cx, solicitud_id)
    if solicitud["estado"] != "CERRADO":
        raise ValueError(
            f"La solicitud {solicitud['id']} está {ESTADO_LEGIBLE[solicitud['estado']]}: "
            "una factura de taller solo se rinde con la solicitud cerrada.")
    if patente and solicitud["patente"] != _patente(patente):
        raise ValueError(f"La solicitud {solicitud['id']} es de {solicitud['patente']}, "
                         f"no de {_patente(patente)}.")
    usado = cx.execute("""
        select numero from ordenes_trabajo
        where solicitud_id = %s and estado <> 'anulada' and (%s::bigint is null or id <> %s)
    """, (solicitud["id"], orden_id, orden_id)).fetchone()
    if usado:
        raise ValueError(f"La solicitud {solicitud['id']} ya se rindió en la orden "
                         f"{usado['numero']}.")
    return solicitud


def para_rendir(cx):
    """Las solicitudes cerradas que todavía no tienen factura cargada.

    Es lo que ofrece el formulario de servicio externo: rendir es elegir
    de esta lista, no tipear un número de solicitud que puede no existir.
    """
    return [dict(v) for v in cx.execute("""
        select id, patente, tipo, detalle, taller, factura_numero,
               coalesce(monto_autorizado, monto_estimado) as monto, cerrado_en
        from v_solicitudes
        where estado = 'CERRADO' and orden_id is null
        order by cerrado_en desc, id desc
    """).fetchall()]


# =====================================================================
# INDICADORES
# =====================================================================
def indicadores(cx, meses=VENTANA_MESES, hoy=None):
    """Por sucursal y por mes, lo que dice si el circuito se está usando.

    La rendición se mide sobre las facturas que necesitan solicitud: las
    que mandó a hacer una sucursal. Las de mantenimiento se cuentan
    aparte, para saber por dónde pasa el gasto, no para exigirles nada.

    El indicador de correctivos sin anomalía previa se calcula con lo que
    hay: un correctivo cuyo origen no es el check list del chofer es un
    correctivo que el control diario no vio venir. Cuando exista el
    módulo de check list se podrá cruzar contra el ítem concreto.
    """
    hoy = hoy or date.today()
    mes = hoy.month - (meses - 1)
    desde = date(hoy.year + (mes - 1) // 12, (mes - 1) % 12 + 1, 1)

    por_sucursal = cx.execute("""
        select v.sucursal_codigo, s.nombre as sucursal,
               count(*)::int as solicitudes,
               count(*) filter (where v.estado = 'RECHAZADO')::int as rechazados,
               count(*) filter (where v.regularizacion_ruta)::int as regularizaciones,
               count(*) filter (where v.tipo = 'CORRECTIVO')::int as correctivos,
               count(*) filter (where v.tipo = 'CORRECTIVO'
                                  and v.origen <> 'CHECKLIST')::int as correctivos_sin_aviso,
               avg(extract(epoch from (v.aprobado_en - v.creado_en)) / 3600.0)
                 filter (where v.aprobado_en is not null) as horas_respuesta,
               coalesce(sum(coalesce(v.monto_autorizado, v.monto_estimado))
                 filter (where v.estado = 'CERRADO'), 0) as gastado
        from solicitudes_compra v join sucursales s on s.codigo = v.sucursal_codigo
        where v.creado_en >= %s
        group by v.sucursal_codigo, s.nombre
        order by s.nombre
    """, (desde,)).fetchall()

    por_mes = cx.execute("""
        select date_trunc('month', creado_en)::date as mes,
               count(*)::int as solicitudes,
               count(*) filter (where regularizacion_ruta)::int as regularizaciones,
               avg(extract(epoch from (aprobado_en - creado_en)) / 3600.0)
                 filter (where aprobado_en is not null) as horas_respuesta
        from solicitudes_compra where creado_en >= %s
        group by 1 order by 1
    """, (desde,)).fetchall()

    # La rendición: cuántas facturas de taller entraron con solicitud y cuántas
    # sin él. Es el indicador que dice si el circuito se está esquivando.
    rendicion = cx.execute("""
        select count(*)::int as facturas,
               count(*) filter (where gestion = 'mantenimiento')::int as de_mantenimiento,
               count(*) filter (where gestion is distinct from 'mantenimiento')::int as de_sucursal,
               count(*) filter (where gestion is distinct from 'mantenimiento'
                                  and solicitud_id is not null)::int as con_solicitud
        from ordenes_trabajo
        where tipo = 'externa' and estado <> 'anulada' and fecha >= %s
    """, (desde,)).fetchone()
    facturas = int(rendicion["facturas"] or 0)
    de_sucursal = int(rendicion["de_sucursal"] or 0)
    con_solicitud = int(rendicion["con_solicitud"] or 0)

    # El gasto de correctivo por cada mil kilómetros. Los kilómetros son
    # los del satelital; sin lecturas la unidad no entra en la cuenta, no
    # se rellena con un número inventado.
    try:
        km = cx.execute("""
            select patente, sum(recorrido) as km from v_km_diarios
            where recorrido is not null and fecha >= %s
            group by patente
        """, (desde,)).fetchall()
    except Exception:
        cx.rollback()
        km = []
    km_por_patente = {k["patente"]: float(k["km"] or 0) for k in km}

    gasto = cx.execute("""
        select patente, sum(coalesce(monto_autorizado, monto_estimado)) as pesos
        from solicitudes_compra
        where tipo = 'CORRECTIVO' and estado = 'CERRADO' and creado_en >= %s
        group by patente
    """, (desde,)).fetchall()

    unidades = []
    for fila in gasto:
        recorrido = km_por_patente.get(fila["patente"])
        pesos = float(fila["pesos"] or 0)
        unidades.append({
            "patente": fila["patente"], "pesos": round(pesos, 2),
            "km": round(recorrido, 0) if recorrido else None,
            "por_mil_km": round(pesos / recorrido * 1000, 2)
                          if recorrido and recorrido > 0 else None,
        })
    unidades.sort(key=lambda u: u["pesos"], reverse=True)

    return {
        "desde": desde.isoformat(),
        "sucursales": [dict(s) for s in por_sucursal],
        "meses": [dict(m) for m in por_mes],
        # El porcentaje se mide contra las facturas que necesitan
        # solicitud —las de sucursal— y no contra todas: meter adentro lo
        # que manda a hacer mantenimiento bajaría el número sin que nadie
        # haya esquivado nada.
        "rendicion": {
            "facturas": facturas,
            "de_mantenimiento": int(rendicion["de_mantenimiento"] or 0),
            "de_sucursal": de_sucursal,
            "con_solicitud": con_solicitud,
            "sin_solicitud": de_sucursal - con_solicitud,
            "porcentaje": round(con_solicitud / de_sucursal * 100, 1) if de_sucursal else None,
        },
        "correctivo_por_unidad": unidades,
    }


# =====================================================================
def aplicar(cx, datos, usuario):
    """Punto de entrada de la API."""
    op = (datos.get("op") or "").strip()
    acciones = {"crear": crear, "aprobar": aprobar, "rechazar": rechazar,
                "iniciar": iniciar, "cerrar": cerrar}
    if op in acciones:
        return acciones[op](cx, datos, usuario)
    if op == "ficha":
        return ficha(cx, datos.get("id"))
    if op == "historial":
        return historial(cx, datos.get("patente"), datos.get("unidad_id"))
    if op == "indicadores":
        return indicadores(cx)
    raise ValueError("No entiendo qué hay que hacer con la solicitud.")
