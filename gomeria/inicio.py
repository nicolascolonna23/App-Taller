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


def _kilometros(cx):
    """Lo que recorrió la flota entera: ayer, la semana y el mes.

    Sale de la serie diaria del satelital. Por unidad se toma la diferencia
    entre la primera y la última lectura del período, que es más robusto que
    sumar día contra día: si un equipo no reportó un día, el tramo se cierra
    igual con la lectura siguiente en vez de perderse.

    Se descartan los retrocesos, que son cambios de módulo GPS y no viajes.
    """
    try:
        filas = cx.execute("""
            -- Cada ventana arranca un día antes del período: para saber cuánto
            -- se recorrió ayer hace falta la lectura de anteayer, que es
            -- contra la que se resta.
            with ventanas as (
              select 'ayer'          as periodo, current_date - 2  as desde, current_date - 1 as hasta
              union all select 'semana',         current_date - 8,  current_date - 1
              union all select 'mes',            current_date - 31, current_date - 1
              union all select 'ayer_previo',    current_date - 3,  current_date - 2
              union all select 'semana_previa',  current_date - 15, current_date - 8
              union all select 'mes_previo',     current_date - 61, current_date - 31
            ),
            tramos as (
              select v.periodo, o.unidad_id,
                     max(o.km) - min(o.km) as recorrido,
                     count(*) as lecturas,
                     count(distinct o.fecha) as dias
              from ventanas v
              join odometros o on o.unidad_id is not null
                              and o.fecha >= v.desde and o.fecha <= v.hasta
              group by v.periodo, o.unidad_id
            )
            select periodo,
                   round(sum(recorrido) filter (where recorrido >= 0))::bigint as km,
                   count(*) filter (where lecturas > 1)::int as unidades,
                   max(dias)::int as dias
            from tramos group by periodo
        """).fetchall()
    except Exception:
        cx.rollback()
        return {}
    # Los días con lecturas se devuelven para poder decidir arriba si tiene
    # sentido comparar: la serie arranca el 29 de julio, así que contra un
    # mes previo con dos días cargados cualquier variación es un espejismo.
    return {f["periodo"]: {"km": int(f["km"] or 0), "unidades": f["unidades"],
                          "dias": f["dias"]}
            for f in filas}


def resumen(cx):
    """Lo que se dibuja en la portada. Todo lo que falte viene en None."""
    datos = {
        "unidades": _uno(cx, "select count(*) from unidades where activa"),

        # Gomería
        "cubiertas": _uno(cx, "select count(*) from cubiertas"),
        "montadas": _uno(cx, "select count(*) from montajes where hasta is null"),
        "en_stock": _uno(cx, "select count(*) from v_stock"),

        # Repuestos
        "articulos": _uno(cx, "select count(*) from repuestos_articulos where activo"),
        "reponer": _uno(cx, """select count(*) from v_repuestos_stock
                               where estado in ('REPONER','SIN STOCK')"""),

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
    return datos
