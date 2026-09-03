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
    return datos
