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
        por_dia = {}
        for unidad, fecha, km in seleccion:
            punto = por_dia.setdefault(fecha, {"km": 0, "unidades": 0})
            punto["km"] += float(km)
            punto["unidades"] += 1
        salida[periodo]["serie"] = [
            {"fecha": (desde + timedelta(days=i)).isoformat(),
             "km": por_dia.get(desde + timedelta(days=i), {}).get("km"),
             "unidades": por_dia.get(desde + timedelta(days=i), {}).get("unidades", 0)}
            for i in range(dias)
        ]
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


# Los tres cortes del mismo dato, con cuántos períodos se muestran atrás.
# El día mira un mes porque una semana de cargas no dice si hoy es mucho o
# poco; el mes, un año entero, que es donde se ve la temporada.
CORTES = (("dia", "day", 30), ("mes", "month", 12), ("anio", "year", 5))


def _litros(cx):
    """Los litros que cargó la flota, por día, por mes y por año.

    Es el mismo dato mirado con tres lupas y no tres consultas parecidas:
    el que abre la portada quiere el total de hoy, el del mes y el del
    año, y la serie de atrás para saber si eso es mucho o poco.

    Sale de las cargas de la planilla —el remito que firma el chofer—, que
    es lo que de verdad se cargó. El listado de la estación no entra acá:
    ese sirve para cruzar y encontrar diferencias, no para sumar dos veces
    el mismo litro.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    hoy = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()

    try:
        total = cx.execute("""
            select coalesce(sum(litros), 0) as litros, count(*)::int as cargas,
                   min(fecha) as desde, max(fecha) as hasta
            from combustible_cargas
            where origen = 'planilla' and fecha is not null and litros is not null
        """).fetchone()
    except Exception:
        cx.rollback()
        return None
    if not total or not total["cargas"]:
        return {"total": 0, "cargas": 0, "desde": None, "hasta": None, "cortes": {}}

    cortes = {}
    for nombre, unidad, cuantos in CORTES:
        filas = cx.execute(f"""
            select date_trunc('{unidad}', fecha)::date as periodo,
                   sum(litros) as litros, count(*)::int as cargas,
                   sum(importe) as importe,
                   count(distinct patente)::int as unidades
            from combustible_cargas
            where origen = 'planilla' and fecha is not null and litros is not null
              and fecha >= date_trunc('{unidad}', %s::date)
                           - make_interval({unidad}s => %s)
            group by 1 order by 1
        """, (hoy, cuantos - 1)).fetchall()
        serie = _rellenar({str(f["periodo"]): dict(f) for f in filas}, unidad, hoy, cuantos)
        cortes[nombre] = {"serie": serie, "actual": serie[-1] if serie else None}

    return {
        "total": float(total["litros"]),
        "cargas": total["cargas"],
        "desde": total["desde"].isoformat() if total["desde"] else None,
        "hasta": total["hasta"].isoformat() if total["hasta"] else None,
        "cortes": cortes,
    }


def _rellenar(cargados, unidad, hoy, cuantos):
    """La serie completa, con los períodos sin cargas en cero.

    Un día sin cargas es un cero de verdad —nadie cargó— y no un hueco:
    saltearlo apretaría el gráfico y haría ver una semana donde hay un mes.
    Que la planilla de los últimos días todavía no esté subida se ve en la
    fecha de la última carga, que la tarjeta muestra aparte.
    """
    from datetime import date, timedelta
    salida = []
    for atras in range(cuantos - 1, -1, -1):
        if unidad == "day":
            periodo = hoy - timedelta(days=atras)
        elif unidad == "month":
            mes = hoy.month - atras
            periodo = date(hoy.year + (mes - 1) // 12, (mes - 1) % 12 + 1, 1)
        else:
            periodo = date(hoy.year - atras, 1, 1)
        fila = cargados.get(periodo.isoformat())
        salida.append({
            "periodo": periodo.isoformat(),
            "litros": float(fila["litros"]) if fila else 0.0,
            "cargas": fila["cargas"] if fila else 0,
            "importe": float(fila["importe"]) if fila and fila["importe"] else None,
            "unidades": fila["unidades"] if fila else 0,
        })
    return salida


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
    datos["litros"] = _litros(cx)
    datos["ordenes_costos"] = _ordenes_costos(cx)
    datos["alertas"] = _alertas(cx)
    return datos


def _ordenes_costos(cx):
    """Lo que cuesta el taller: gasto por patente y pesos por kilómetro.

    Se importa acá adentro, como las alertas: si todavía no se corrió el
    SQL de órdenes, la portada tiene que seguir dibujándose sin el panel.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        import kpi_ordenes
        hoy = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
        return kpi_ordenes.resumen(cx, hoy)
    except Exception:
        cx.rollback()
        return None


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
