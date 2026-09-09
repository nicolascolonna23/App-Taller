"""
Los números que la portada muestra en vivo.

La pantalla de inicio no debería ser una lista de enlaces: si el sistema
sabe que hay diecisiete documentos vencidos, eso tiene que verse antes de
entrar a ningún lado.

Cada número se pide por separado y a prueba de balas: los módulos se van
prendiendo de a uno, así que hasta que no esté todo el SQL corrido va a
haber tablas que no existen. Una que falte apaga su número, no la portada.
"""


def _uno(cx, consulta, valores=()):
    """El primer valor de la consulta, o None si la tabla todavía no está."""
    try:
        fila = cx.execute(consulta, valores).fetchone()
    except Exception:
        # La conexión queda inutilizable después de un error, así que se
        # deshace la transacción para que las consultas que siguen anden.
        cx.rollback()
        return None
    if not fila:
        return None
    return list(fila.values())[0] if isinstance(fila, dict) else fila[0]


def _resumir_km(filas, hoy):
    """Diferencias diarias de Hawk. Nunca inventa km para días sin lectura."""
    from datetime import timedelta
    ventanas = {
        "ayer": (hoy - timedelta(days=1), hoy - timedelta(days=1)),
        "semana": (hoy - timedelta(days=7), hoy - timedelta(days=1)),
        "mes": (hoy - timedelta(days=30), hoy - timedelta(days=1)),
        "ayer_previo": (hoy - timedelta(days=2), hoy - timedelta(days=2)),
        "semana_previa": (hoy - timedelta(days=14), hoy - timedelta(days=8)),
        "mes_previo": (hoy - timedelta(days=60), hoy - timedelta(days=31)),
    }
    # La consulta entrega una lectura por unidad/fecha, siempre de Hawk.
    anteriores, tramos = {}, []
    for fila in sorted(filas, key=lambda f: (f["unidad_id"], f["fecha"])):
        unidad, fecha, km = fila["unidad_id"], fila["fecha"], fila["km"]
        anterior = anteriores.get(unidad)
        if anterior:
            dias = (fecha - anterior["fecha"]).days
            delta = km - anterior["km"]
            if dias == 1 and 0 <= delta <= 1200:
                tramos.append((unidad, fecha, delta))
        anteriores[unidad] = fila
    salida, coberturas = {}, {}
    for periodo, (desde, hasta) in ventanas.items():
        seleccion = [(u, f, km) for u, f, km in tramos if desde <= f <= hasta]
        cobertura = {}
        for unidad, fecha, _ in seleccion:
            cobertura.setdefault(unidad, set()).add(fecha)
        dias = (hasta - desde).days + 1
        completas = {u for u, fechas in cobertura.items() if len(fechas) == dias}
        coberturas[periodo] = (completas, set(cobertura))
        salida[periodo] = {
            "km": float(sum(km for _, _, km in seleccion)) if seleccion else None,
            "unidades": len(cobertura),
            "dias": len({f for _, f, _ in seleccion}),
            "dias_esperados": dias,
            "unidades_completas": len(completas),
            "desde": desde.isoformat(), "hasta": hasta.isoformat(),
            "comparar": False,
        }
    for actual, previo in (("ayer", "ayer_previo"), ("semana", "semana_previa"), ("mes", "mes_previo")):
        completas, unidades = coberturas[actual]
        anteriores_completas, anteriores_unidades = coberturas[previo]
        salida[actual]["comparar"] = bool(unidades and completas == unidades ==
                                         anteriores_completas == anteriores_unidades)
    return salida


def _kilometros(cx):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    hoy = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    try:
        filas = cx.execute("""
            select distinct on (unidad_id, fecha) unidad_id, fecha, km
            from odometros
            where unidad_id is not null and fuente = 'hawk'
              and fecha >= %s and fecha < %s
            order by unidad_id, fecha, leido desc, id desc
        """, (hoy - timedelta(days=61), hoy)).fetchall()
    except Exception:
        cx.rollback()
        return {}
    return _resumir_km(filas, hoy)


def _combustible(cx):
    """Último mes calendario cerrado y el inmediatamente anterior."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    primero = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date().replace(day=1)
    ultimo = (primero - timedelta(days=1)).replace(day=1)
    previo = (ultimo - timedelta(days=1)).replace(day=1)
    try:
        filas = cx.execute("""
            select mes, litros, importe, km, litros_100km, pesos_km,
                   cargas, unidades, sin_consumo, litros_sin_consumo
            from v_combustible_mes where mes in (%s, %s)
            order by mes desc
        """, (ultimo, previo)).fetchall()
    except Exception:
        cx.rollback()
        return None
    por_mes = {str(f["mes"])[:10]: dict(f) for f in filas}
    return {"mes": por_mes.get(ultimo.isoformat()),
            "previo": por_mes.get(previo.isoformat()),
            "esperado": ultimo.isoformat()}


def resumen(cx):
    """Lo que se dibuja en la portada. Todo lo que falte viene en None."""
    datos = {
        "unidades": _uno(cx, "select count(*) from unidades where activa"),

        # Gomería
        "cubiertas": _uno(cx, "select count(*) from cubiertas"),
        "montadas": _uno(cx, "select count(*) from montajes where hasta is null"),
        "en_stock": _uno(cx, "select count(*) from v_stock"),

        # Cubiertas al límite: las que hay que bajar y las que están por
        # llegar. Es el aviso que no se puede esperar a que alguien entre
        # a Gomería a buscarlo.
        "cubiertas_al_limite": _uno(cx, """select count(*) from v_alertas_cubiertas
                                           where alerta = 'al_limite'"""),
        "cubiertas_cerca": _uno(cx, """select count(*) from v_alertas_cubiertas
                                       where alerta = 'cerca'"""),

        # Repuestos
        "articulos": _uno(cx, "select count(*) from repuestos_articulos where activo"),
        "reponer": _uno(cx, """select count(*) from v_repuestos_stock
                               where estado in ('REPONER','SIN STOCK')"""),

        # Órdenes de trabajo: las que están abiertas son las unidades que
        # ahora mismo están en el taller.
        "ordenes_abiertas": _uno(cx, """select count(*) from ordenes_trabajo
                                        where estado = 'abierta'"""),

        # Vencimientos
        "vencidos": _uno(cx, "select count(*) from v_vencimientos_hoy where estado = 'vencido'"),
        "por_vencer": _uno(cx, "select count(*) from v_vencimientos_hoy where estado = 'por_vencer'"),
        "controlados": _uno(cx, "select count(*) from v_vencimientos_hoy"),

        # Satelital: cuándo fue la última lectura y cuántas unidades reportaron
        "km_fecha": _uno(cx, "select max(fecha)::text from odometros"),
        "km_unidades": _uno(cx, """select count(*) from odometros
                                   where fecha = (select max(fecha) from odometros)"""),
    }
    datos["recorrido"] = _kilometros(cx)
    datos["combustible"] = _combustible(cx)
    datos["alertas"] = _alertas(cx)
    return datos


def _alertas(cx):
    """Cuántas cosas hay para mirar hoy, de las cuatro fuentes juntas.

    Se importa acá adentro y no arriba: si el módulo de alertas todavía no
    está —o le falta el SQL—, la portada tiene que seguir dibujándose.
    """
    try:
        import alertas
        return alertas.resumen(cx)
    except Exception:
        cx.rollback()
        return None
