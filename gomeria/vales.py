"""Vales de taller: el registro nace antes de la reparación, no después.

El preventivo ya estaba procedimentado. El correctivo se hacía y se
rendía como un gasto más de la sucursal: la plata quedaba anotada, la
intervención técnica no. El vale corrige eso con una sola idea: ninguna
compra ni trabajo de taller se hace sin un vale aprobado, y ninguna
factura se rinde sin el número de vale escrito.

El circuito es corto a propósito —pedir, aprobar, reparar, rendir— y son
cuatro estados y un botón por parte del taller:

    SOLICITADO ──aprobar──▶ APROBADO ──iniciar──▶ EN_EJECUCION ──┐
         │                      │                                │
         └──rechazar──▶ RECHAZADO└──────── cerrar ───────────────▶ CERRADO

Dos reglas duras, que son el módulo entero:

  * No se compra ni se repara con el vale en SOLICITADO o RECHAZADO.
  * No se rinde una factura de taller sin un vale CERRADO. Esa validación
    vive en el módulo de gastos —acá, las órdenes externas— y entra por
    `validar_para_gasto`.

El número lo da el sistema y sale de quién pide: `CAT-00001`. Es
correlativo por sucursal e inmutable —el número de un vale rechazado no se
reutiliza—, por eso no hay ningún borrado de vales en este archivo.
"""
from datetime import date, datetime, timedelta, timezone

import alertas

# El taller y mantenimiento aprueban. La sucursal pide, y también puede
# iniciar y cerrar: el que tiene la factura en la mano es el que la carga.
GESTORES = {"admin", "encargado"}

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
# horas y el vale se va arriba de la bandeja.
RESPUESTA_DIAS_HABILES = 1
RESPUESTA_PARADA_HORAS = 2

# La regularización de un arreglo autorizado por teléfono en la ruta: 48
# horas hábiles para cargar el vale.
REGULARIZACION_DIAS_HABILES = 2

# Cuánto mira la pantalla hacia atrás. Lo que no está cerrado se muestra
# siempre, tenga la antigüedad que tenga.
VENTANA_MESES = 12


# =====================================================================
# AYUDAS
# =====================================================================
def puede_aprobar(usuario):
    return (usuario or {}).get("rol") in GESTORES


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

    No conoce los feriados: para lo que se usa —marcar un vale demorado y
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


def demorado(vale, ahora=None):
    """¿El taller se pasó del tiempo que tiene para contestar?"""
    if (vale or {}).get("estado") != "SOLICITADO":
        return False
    creado = vale.get("creado_en")
    if not isinstance(creado, datetime):
        return False
    ahora = ahora or _ahora()
    if creado.tzinfo is None:
        creado = creado.replace(tzinfo=timezone.utc)
    if vale.get("urgencia") == "UNIDAD_PARADA":
        return (ahora - creado) > timedelta(hours=RESPUESTA_PARADA_HORAS)
    return dias_habiles(creado.date(), ahora.date()) > RESPUESTA_DIAS_HABILES


def _evento(cx, vale_id, estado, usuario, comentario=None):
    """El historial. Se escribe siempre, en la misma transacción."""
    cx.execute("""
        insert into vale_eventos (vale_id, estado, usuario, comentario)
        values (%s, %s, %s, %s)
    """, (vale_id, estado, (usuario or {}).get("nombre"), _texto(comentario, 500)))


def _vale(cx, vale_id, bloquear=False):
    """El vale, o el error de por qué no se puede seguir."""
    vale_id = str(vale_id or "").strip().upper()
    if not vale_id:
        raise ValueError("No se sabe de qué vale se habla.")
    fila = cx.execute(
        "select * from vales where id = %s" + (" for update" if bloquear else ""),
        (vale_id,)).fetchone()
    if not fila:
        raise ValueError(f"El vale {vale_id} no existe.")
    return fila


def _exigir_transicion(vale, destino):
    if destino not in TRANSICIONES[vale["estado"]]:
        raise ValueError(
            f"El vale {vale['id']} está {ESTADO_LEGIBLE[vale['estado']]}: "
            f"no puede pasar a {ESTADO_LEGIBLE[destino]}.")


ESTADO_LEGIBLE = {
    "SOLICITADO": "solicitado", "APROBADO": "aprobado",
    "EN_EJECUCION": "en ejecución", "CERRADO": "cerrado",
    "RECHAZADO": "rechazado",
}


def _unidad(cx, datos):
    """La unidad del vale. Devuelve (id, patente, fila o None)."""
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
        raise ValueError("Falta la sucursal que pide el vale.")
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
    fila = cx.execute("""select ultimo from vales_contador
                         where sucursal_codigo = %s for update""",
                      (codigo,)).fetchone()
    if not fila:
        cx.execute("""insert into vales_contador (sucursal_codigo) values (%s)
                      on conflict (sucursal_codigo) do nothing""", (codigo,))
        fila = cx.execute("""select ultimo from vales_contador
                             where sucursal_codigo = %s for update""",
                          (codigo,)).fetchone()
    if not fila:
        raise ValueError(f"No se pudo numerar el vale de {codigo}. "
                         "Ejecutar gomeria/26_vales.sql en Supabase.")
    numero = int(fila["ultimo"]) + 1
    cx.execute("update vales_contador set ultimo = %s where sucursal_codigo = %s",
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
    vales = cx.execute("""
        select * from v_vales
        where estado in ('SOLICITADO','APROBADO','EN_EJECUCION')
           or creado_en >= now() - interval '%s months'
        order by estado in ('SOLICITADO','APROBADO','EN_EJECUCION') desc,
                 creado_en desc
    """ % int(VENTANA_MESES)).fetchall()

    ahora = _ahora()
    salida, resumen = [], {e: 0 for e in TRANSICIONES}
    resumen.update({"demorados": 0, "parados": 0, "sin_rendir": 0})
    for fila in vales:
        vale = dict(fila)
        vale["demorado"] = demorado(vale, ahora)
        vale["dias_espera"] = dias_habiles(
            vale["creado_en"], ahora) if vale["estado"] == "SOLICITADO" else None
        resumen[vale["estado"]] = resumen.get(vale["estado"], 0) + 1
        if vale["demorado"]:
            resumen["demorados"] += 1
        if vale["estado"] == "SOLICITADO" and vale["urgencia"] == "UNIDAD_PARADA":
            resumen["parados"] += 1
        if vale["estado"] == "CERRADO" and not vale.get("orden_numero"):
            resumen["sin_rendir"] += 1
        salida.append(vale)

    return {
        "vales": salida,
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
        "exigir_vale": exigir_vale(cx),
    }


def ficha(cx, vale_id):
    """Un vale con su historial: lo que se imprime y se firma."""
    vale = cx.execute("select * from v_vales where id = %s",
                      (str(vale_id or "").strip().upper(),)).fetchone()
    if not vale:
        raise ValueError("Ese vale no existe.")
    vale = dict(vale)
    vale["demorado"] = demorado(vale)
    return {
        "vale": vale,
        "eventos": [dict(e) for e in cx.execute("""
            select estado, usuario, momento, comentario
            from vale_eventos where vale_id = %s order by id
        """, (vale["id"],)).fetchall()],
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

    vales = [dict(v) for v in cx.execute("""
        select * from v_vales where patente = %s
        order by creado_en desc""", (patente,)).fetchall()]

    gasto = {t: 0.0 for t in TIPOS}
    for v in vales:
        if v["estado"] != "RECHAZADO":
            gasto[v["tipo"]] = gasto.get(v["tipo"], 0.0) + float(v["monto"] or 0)
    return {
        "patente": patente,
        "vales": vales,
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
    # fuera de la sucursal y el vale se carga después. La fecha del hecho
    # puede ser anterior a la de carga; la de mañana no existe.
    regularizacion = bool(datos.get("regularizacion_ruta"))
    hecho = _fecha(datos.get("fecha_hecho"), "la fecha del hecho") or date.today()
    if hecho > date.today():
        raise ValueError("La fecha del hecho no puede ser posterior a hoy.")
    if hecho < date.today() and not regularizacion:
        raise ValueError("Un vale con fecha anterior a hoy es una regularización "
                         "de ruta: marcala para poder cargarlo.")

    anterior = _texto(datos.get("vale_anterior"), 20)
    if anterior:
        previo = _vale(cx, anterior)
        if previo["patente"] != patente:
            raise ValueError(f"El vale {previo['id']} es de otra unidad.")
        anterior = previo["id"]

    numero, vale_id = _numerar(cx, codigo)
    cx.execute("""
        insert into vales
          (id, sucursal_codigo, numero, unidad_id, patente, km, tipo, origen,
           urgencia, detalle, taller_sugerido, monto_estimado, estado,
           solicitante, solicitante_id, fecha_hecho, regularizacion_ruta,
           vale_anterior)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'SOLICITADO',%s,%s,%s,%s,%s)
    """, (vale_id, codigo, numero, unidad_id, patente, km, tipo, origen,
          urgencia, detalle, _texto(datos.get("taller_sugerido"), 120),
          _numero(datos.get("monto_estimado"), "El monto estimado"),
          (usuario or {}).get("nombre"), (usuario or {}).get("id"),
          hecho, regularizacion, anterior))

    comentario = _texto(datos.get("comentario"), 500)
    if regularizacion and not comentario:
        comentario = (f"Regularización de ruta: el hecho fue el "
                      f"{hecho.isoformat()} y se autorizó verbalmente.")
    _evento(cx, vale_id, "SOLICITADO", usuario, comentario)
    return {"ok": True, "id": vale_id, "numero": numero, "sucursal_codigo": codigo,
            "fuera_de_termino": bool(
                regularizacion and dias_habiles(hecho, date.today())
                > REGULARIZACION_DIAS_HABILES)}


def aprobar(cx, datos, usuario):
    """El taller dice que sí. Recién acá se puede comprar o reparar."""
    if not puede_aprobar(usuario):
        raise PermissionError("Solo el taller o mantenimiento puede aprobar un vale.")
    vale = _vale(cx, datos.get("id"), bloquear=True)
    _exigir_transicion(vale, "APROBADO")

    monto = _numero(datos.get("monto_autorizado"), "El monto autorizado")
    taller = _texto(datos.get("taller"), 120) or vale["taller_sugerido"]
    nota = _texto(datos.get("nota"), 500)
    cx.execute("""
        update vales set estado = 'APROBADO', monto_autorizado = coalesce(%s, monto_autorizado),
               taller = %s, nota = %s, aprobado_en = now(), aprobado_por = %s
        where id = %s
    """, (monto, taller, nota, (usuario or {}).get("nombre"), vale["id"]))
    _evento(cx, vale["id"], "APROBADO", usuario, nota)
    return {"ok": True, "id": vale["id"], "estado": "APROBADO"}


def rechazar(cx, datos, usuario):
    """El taller dice que no, y dice por qué. De acá no se vuelve."""
    if not puede_aprobar(usuario):
        raise PermissionError("Solo el taller o mantenimiento puede rechazar un vale.")
    vale = _vale(cx, datos.get("id"), bloquear=True)
    _exigir_transicion(vale, "RECHAZADO")

    nota = _texto(datos.get("nota"), 500)
    if not nota:
        raise ValueError("Un rechazo sin motivo no le sirve a la sucursal: "
                         "escribí por qué no va.")
    cx.execute("""update vales set estado = 'RECHAZADO', nota = %s
                  where id = %s""", (nota, vale["id"]))
    _evento(cx, vale["id"], "RECHAZADO", usuario, nota)
    return {"ok": True, "id": vale["id"], "estado": "RECHAZADO"}


def iniciar(cx, datos, usuario):
    """La unidad entró al taller. El trabajo empezó."""
    vale = _vale(cx, datos.get("id"), bloquear=True)
    _exigir_transicion(vale, "EN_EJECUCION")
    cx.execute("update vales set estado = 'EN_EJECUCION' where id = %s", (vale["id"],))
    _evento(cx, vale["id"], "EN_EJECUCION", usuario, _texto(datos.get("comentario"), 500))
    return {"ok": True, "id": vale["id"], "estado": "EN_EJECUCION"}


def cerrar(cx, datos, usuario):
    """El trabajo se hizo y está la factura. El vale queda como está.

    Un vale preventivo cerrado es además el último service de la unidad:
    se registra acá para que el próximo service se recalcule solo. Si la
    unidad no tiene plan de mantenimiento asignado el vale se cierra
    igual y se avisa: la sucursal que tiene la factura en la mano no
    puede quedar trabada por una parametrización que no depende de ella.
    """
    vale = _vale(cx, datos.get("id"), bloquear=True)
    _exigir_transicion(vale, "CERRADO")

    factura = _texto(datos.get("factura_numero") or datos.get("factura"), 60)
    if not factura:
        raise ValueError("Falta el número de factura: sin eso el vale no cierra.")
    monto = _numero(datos.get("monto_autorizado"), "El monto")

    cx.execute("""
        update vales
        set estado = 'CERRADO', factura_numero = %s,
            monto_autorizado = coalesce(%s, monto_autorizado),
            cerrado_en = now(), cerrado_por = %s
        where id = %s
    """, (factura, monto, (usuario or {}).get("nombre"), vale["id"]))
    _evento(cx, vale["id"], "CERRADO", usuario,
            _texto(datos.get("comentario"), 500) or f"Factura {factura}.")

    service_id, aviso = _registrar_preventivo(cx, vale, usuario)
    return {"ok": True, "id": vale["id"], "estado": "CERRADO",
            "service_id": service_id, "aviso": aviso}


def _registrar_preventivo(cx, vale, usuario):
    """Hace que un vale preventivo cerrado sea también el último service."""
    if vale["tipo"] != "PREVENTIVO" or not vale["unidad_id"]:
        return None, None
    existente = cx.execute("select id from services where vale_id = %s",
                           (vale["id"],)).fetchone()
    if existente:
        return existente["id"], None
    try:
        service_id = alertas.guardar_service(cx, {
            "unidad_id": vale["unidad_id"],
            "fecha": date.today().isoformat(),
            "km": vale["km"],
            "tipo": (vale["detalle"] or "Mantenimiento preventivo")[:60],
            "taller": vale["taller"] or vale["taller_sugerido"],
            "observaciones": f"Registrado desde el vale {vale['id']}.",
        }, usuario=(usuario or {}).get("nombre"))
    except ValueError as e:
        return None, (f"El vale cerró, pero el service no se pudo registrar: {e}")
    cx.execute("update services set vale_id = %s where id = %s",
               (vale["id"], service_id))
    return service_id, None


# =====================================================================
# LA REGLA QUE MIRA EL MÓDULO DE GASTOS
# =====================================================================
def exigir_vale(cx):
    """¿Se puede rendir una factura de taller sin vale? Por regla, no."""
    try:
        fila = cx.execute("select exigir_vale from vales_ajustes").fetchone()
    except Exception:
        # Sin el módulo instalado no se le puede exigir a nadie un vale.
        cx.rollback()
        return False
    return bool(fila["exigir_vale"]) if fila else True


def validar_para_gasto(cx, vale_id, patente, orden_id=None):
    """El vale con el que se rinde una factura, o el error que corresponde.

    Lo llama el módulo de órdenes antes de guardar un servicio externo.
    Un vale sirve para rendir si está CERRADO, es de esa unidad y no se
    usó en otra factura.
    """
    vale = _vale(cx, vale_id)
    if vale["estado"] != "CERRADO":
        raise ValueError(
            f"El vale {vale['id']} está {ESTADO_LEGIBLE[vale['estado']]}: "
            "una factura de taller solo se rinde con el vale cerrado.")
    if patente and vale["patente"] != _patente(patente):
        raise ValueError(f"El vale {vale['id']} es de {vale['patente']}, "
                         f"no de {_patente(patente)}.")
    usado = cx.execute("""
        select numero from ordenes_trabajo
        where vale_id = %s and estado <> 'anulada' and (%s::bigint is null or id <> %s)
    """, (vale["id"], orden_id, orden_id)).fetchone()
    if usado:
        raise ValueError(f"El vale {vale['id']} ya se rindió en la orden "
                         f"{usado['numero']}.")
    return vale


def para_rendir(cx):
    """Los vales cerrados que todavía no tienen factura cargada.

    Es lo que ofrece el formulario de servicio externo: rendir es elegir
    de esta lista, no tipear un número de vale que puede no existir.
    """
    return [dict(v) for v in cx.execute("""
        select id, patente, tipo, detalle, taller, factura_numero,
               coalesce(monto_autorizado, monto_estimado) as monto, cerrado_en
        from v_vales
        where estado = 'CERRADO' and orden_id is null
        order by cerrado_en desc, id desc
    """).fetchall()]


# =====================================================================
# INDICADORES
# =====================================================================
def indicadores(cx, meses=VENTANA_MESES, hoy=None):
    """Por sucursal y por mes, lo que dice si el circuito se está usando.

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
               count(*)::int as vales,
               count(*) filter (where v.estado = 'RECHAZADO')::int as rechazados,
               count(*) filter (where v.regularizacion_ruta)::int as regularizaciones,
               count(*) filter (where v.tipo = 'CORRECTIVO')::int as correctivos,
               count(*) filter (where v.tipo = 'CORRECTIVO'
                                  and v.origen <> 'CHECKLIST')::int as correctivos_sin_aviso,
               avg(extract(epoch from (v.aprobado_en - v.creado_en)) / 3600.0)
                 filter (where v.aprobado_en is not null) as horas_respuesta,
               coalesce(sum(coalesce(v.monto_autorizado, v.monto_estimado))
                 filter (where v.estado = 'CERRADO'), 0) as gastado
        from vales v join sucursales s on s.codigo = v.sucursal_codigo
        where v.creado_en >= %s
        group by v.sucursal_codigo, s.nombre
        order by s.nombre
    """, (desde,)).fetchall()

    por_mes = cx.execute("""
        select date_trunc('month', creado_en)::date as mes,
               count(*)::int as vales,
               count(*) filter (where regularizacion_ruta)::int as regularizaciones,
               avg(extract(epoch from (aprobado_en - creado_en)) / 3600.0)
                 filter (where aprobado_en is not null) as horas_respuesta
        from vales where creado_en >= %s
        group by 1 order by 1
    """, (desde,)).fetchall()

    # La rendición: cuántas facturas de taller entraron con vale y cuántas
    # sin él. Es el indicador que dice si el circuito se está esquivando.
    rendicion = cx.execute("""
        select count(*)::int as facturas,
               count(*) filter (where vale_id is not null)::int as con_vale
        from ordenes_trabajo
        where tipo = 'externa' and estado <> 'anulada' and fecha >= %s
    """, (desde,)).fetchone()
    facturas = int(rendicion["facturas"] or 0)
    con_vale = int(rendicion["con_vale"] or 0)

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
        from vales
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
        "rendicion": {
            "facturas": facturas, "con_vale": con_vale,
            "sin_vale": facturas - con_vale,
            "porcentaje": round(con_vale / facturas * 100, 1) if facturas else None,
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
    raise ValueError("No entiendo qué hay que hacer con el vale.")
