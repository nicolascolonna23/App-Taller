"""
Acceso a la base de gomería (Supabase / PostgreSQL).

Todas las operaciones que cambian algo corren dentro de una transacción:
o se aplica el movimiento entero o no se aplica nada. Una rotación de
cuatro cubiertas nunca puede quedar por la mitad.
"""
import os, uuid
import psycopg
from psycopg.rows import dict_row

import mapas


def url_conexion():
    """Cadena de conexión a Postgres.

    En Supabase se copia de Project Settings → Database → Connection string
    (modo 'Session'). Se guarda en la variable SUPABASE_DB_URL o en el
    archivo gomeria/conexion.txt.
    """
    url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not url:
        archivo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conexion.txt")
        if os.path.exists(archivo):
            url = open(archivo, encoding="utf-8").read().strip()
    if not url:
        raise SystemExit(
            "Falta la conexión a la base.\n"
            "  Opción 1: export SUPABASE_DB_URL=postgresql://...\n"
            "  Opción 2: guardala en gomeria/conexion.txt")
    return url


def conectar():
    return psycopg.connect(url_conexion(), row_factory=dict_row, autocommit=False)


# =====================================================================
# LECTURA
# =====================================================================
def buscar_unidad(cx, texto):
    """Busca por patente o número interno. La patente se compara sin espacios."""
    limpio = "".join(ch for ch in str(texto).upper() if ch.isalnum())
    return cx.execute("""
        select * from unidades
        where replace(replace(upper(patente),' ',''),'-','') = %s
           or upper(coalesce(interno,'')) = %s
        limit 1""", (limpio, limpio)).fetchone()


def mapa_unidad(cx, unidad_id):
    """El mapa con lo que tiene puesto ahora, ordenado como se dibuja."""
    return cx.execute("""
        select * from v_mapa_unidad where unidad_id = %s order by orden""",
        (unidad_id,)).fetchall()


def posicion_por_codigo(cx, unidad_id, codigo):
    return cx.execute("""
        select p.* from configuracion_posiciones p
        join unidades u on u.configuracion_id = p.configuracion_id
        where u.id = %s and upper(p.codigo) = upper(%s)""",
        (unidad_id, str(codigo).strip())).fetchone()


def buscar_cubierta(cx, codigo):
    return cx.execute("select * from cubiertas where upper(codigo) = upper(%s)",
                      (str(codigo).strip(),)).fetchone()


def stock(cx, medida=None, limite=50):
    if medida:
        return cx.execute("select * from v_stock where medida = %s order by codigo limit %s",
                          (medida, limite)).fetchall()
    return cx.execute("select * from v_stock order by codigo limit %s", (limite,)).fetchall()


def historial_cubierta(cx, cubierta_id, limite=40):
    return cx.execute("""
        select * from v_historial_cubierta where cubierta_id = %s limit %s""",
        (cubierta_id, limite)).fetchall()


# =====================================================================
# ALTAS
# =====================================================================
def crear_configuracion(cx, nombre, spec, descripcion=None):
    """Crea el mapa a partir de un spec tipo 'S-D-D'."""
    posiciones = mapas.expandir(spec)
    fila = cx.execute("""
        insert into configuraciones (nombre, descripcion) values (%s, %s)
        on conflict (nombre) do update set descripcion = excluded.descripcion
        returning id""", (nombre, descripcion or mapas.describir(spec))).fetchone()
    cid = fila["id"]
    for p in posiciones:
        cx.execute("""
            insert into configuracion_posiciones
              (configuracion_id, codigo, eje, lado, montaje, es_auxilio, orden)
            values (%s,%s,%s,%s,%s,%s,%s)
            on conflict (configuracion_id, codigo) do nothing""",
            (cid, p["codigo"], p["eje"], p["lado"], p["montaje"], p["es_auxilio"], p["orden"]))
    return cid


def crear_unidad(cx, patente, configuracion_id, **datos):
    limpia = "".join(ch for ch in str(patente).upper() if ch.isalnum())
    return cx.execute("""
        insert into unidades (patente, interno, marca, modelo, sucursal, uso,
                              configuracion_id, km_actual)
        values (%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (patente) do update set
          interno = excluded.interno, marca = excluded.marca,
          modelo = excluded.modelo, sucursal = excluded.sucursal,
          uso = excluded.uso, configuracion_id = excluded.configuracion_id
        returning id""",
        (limpia, datos.get("interno"), datos.get("marca"), datos.get("modelo"),
         datos.get("sucursal"), datos.get("uso"), configuracion_id,
         datos.get("km_actual"))).fetchone()["id"]


def alta_cubierta(cx, codigo, **datos):
    fila = cx.execute("""
        insert into cubiertas (codigo, marca, modelo, medida, costo_compra, remanente_mm, observaciones)
        values (%s,%s,%s,%s,%s,%s,%s)
        on conflict (codigo) do update set marca = excluded.marca
        returning id""",
        (str(codigo).strip(), datos.get("marca"), datos.get("modelo"), datos.get("medida"),
         datos.get("costo_compra"), datos.get("remanente_mm"),
         datos.get("observaciones"))).fetchone()
    cx.execute("""insert into movimientos (tipo, cubierta_id, nota, usuario)
                  values ('alta', %s, %s, %s)""",
               (fila["id"], datos.get("nota"), datos.get("usuario")))
    return fila["id"]


# =====================================================================
# MOVIMIENTOS
# =====================================================================
def _cerrar_montaje(cx, unidad_id, posicion_id, km=None):
    """Cierra el montaje abierto de esa posición y devuelve la cubierta que salió."""
    fila = cx.execute("""
        update montajes set hasta = now(), km_unidad_desmontaje = %s
        where unidad_id = %s and posicion_id = %s and hasta is null
        returning id, cubierta_id, km_unidad_montaje""",
        (km, unidad_id, posicion_id)).fetchone()
    if fila and km is not None and fila["km_unidad_montaje"] is not None:
        # Los km que rodó en esa posición se acumulan en la ficha de la cubierta.
        recorridos = float(km) - float(fila["km_unidad_montaje"])
        if recorridos > 0:
            cx.execute("update cubiertas set km_acumulados = km_acumulados + %s where id = %s",
                       (recorridos, fila["cubierta_id"]))
    return fila


def _abrir_montaje(cx, unidad_id, posicion_id, cubierta_id, km=None, nota=None):
    cx.execute("""
        insert into montajes (unidad_id, posicion_id, cubierta_id, km_unidad_montaje, nota)
        values (%s,%s,%s,%s,%s)""", (unidad_id, posicion_id, cubierta_id, km, nota))
    cx.execute("update cubiertas set estado = 'montada' where id = %s", (cubierta_id,))


def _log(cx, grupo, tipo, **kw):
    cx.execute("""
        insert into movimientos
          (grupo_id, parte_id, tipo, unidad_id, cubierta_id,
           posicion_origen_id, posicion_destino_id, km_unidad, remanente_mm, usuario, nota)
        values (%(g)s,%(parte)s,%(tipo)s,%(unidad)s,%(cubierta)s,%(origen)s,%(destino)s,
                %(km)s,%(rem)s,%(usuario)s,%(nota)s)""",
        {"g": grupo, "parte": kw.get("parte_id"), "tipo": tipo,
         "unidad": kw.get("unidad_id"), "cubierta": kw.get("cubierta_id"),
         "origen": kw.get("origen_id"), "destino": kw.get("destino_id"),
         "km": kw.get("km"), "rem": kw.get("remanente_mm"),
         "usuario": kw.get("usuario"), "nota": kw.get("nota")})


def montar(cx, unidad_id, posicion_id, cubierta_id, km=None, grupo=None, **kw):
    """Pone una cubierta en una posición. Si había otra puesta, la baja a stock."""
    grupo = grupo or uuid.uuid4()
    anterior = _cerrar_montaje(cx, unidad_id, posicion_id, km)
    if anterior:
        cx.execute("update cubiertas set estado = 'stock' where id = %s", (anterior["cubierta_id"],))
        _log(cx, grupo, "desmontaje", unidad_id=unidad_id, cubierta_id=anterior["cubierta_id"],
             origen_id=posicion_id, km=km, **kw)
    _abrir_montaje(cx, unidad_id, posicion_id, cubierta_id, km, kw.get("nota"))
    _log(cx, grupo, "montaje", unidad_id=unidad_id, cubierta_id=cubierta_id,
         destino_id=posicion_id, km=km, **kw)
    return grupo


def desmontar(cx, unidad_id, posicion_id, km=None, destino="stock", grupo=None, **kw):
    """Saca la cubierta de una posición. destino: stock, reparacion, recapado o baja."""
    grupo = grupo or uuid.uuid4()
    fila = _cerrar_montaje(cx, unidad_id, posicion_id, km)
    if not fila:
        raise ValueError("Esa posición ya estaba vacía.")
    cx.execute("update cubiertas set estado = %s where id = %s", (destino, fila["cubierta_id"]))
    if destino == "baja":
        cx.execute("""update cubiertas set fecha_baja = current_date, motivo_baja = %s
                      where id = %s""", (kw.get("nota"), fila["cubierta_id"]))
    tipo = {"baja": "baja", "recapado": "recapado", "reparacion": "reparacion"}.get(destino, "desmontaje")
    _log(cx, grupo, tipo, unidad_id=unidad_id, cubierta_id=fila["cubierta_id"],
         origen_id=posicion_id, km=km, **kw)
    return grupo


def rotar(cx, unidad_id, pares, km=None, grupo=None, **kw):
    """Mueve varias cubiertas de una posición a otra en un solo acto.

    pares: [(posicion_origen_id, posicion_destino_id), ...]

    Primero se levantan todas las cubiertas involucradas y recién después se
    vuelven a poner. Si se hiciera de a una, un cruce simple (la de adelante
    va atrás y la de atrás adelante) chocaría contra el índice que impide dos
    cubiertas en la misma posición.
    """
    grupo = grupo or uuid.uuid4()
    levantadas = {}
    for origen, _ in pares:
        fila = _cerrar_montaje(cx, unidad_id, origen, km)
        if not fila:
            raise ValueError("Una de las posiciones a rotar estaba vacía.")
        levantadas[origen] = fila["cubierta_id"]
    for origen, destino in pares:
        cubierta = levantadas[origen]
        # Si el destino tenía algo que no se levantó, esto avisa en vez de pisarlo.
        ocupada = cx.execute("""select 1 from montajes
                                where unidad_id = %s and posicion_id = %s and hasta is null""",
                             (unidad_id, destino)).fetchone()
        if ocupada:
            raise ValueError("El destino de la rotación está ocupado por una cubierta que no se movió.")
        _abrir_montaje(cx, unidad_id, destino, cubierta, km, kw.get("nota"))
        _log(cx, grupo, "rotacion", unidad_id=unidad_id, cubierta_id=cubierta,
             origen_id=origen, destino_id=destino, km=km, **kw)
    return grupo


def medir(cx, cubierta_id, remanente_mm, km=None, usuario=None, grupo=None):
    grupo = grupo or uuid.uuid4()
    cx.execute("""insert into mediciones (cubierta_id, remanente_mm, km_unidad, usuario)
                  values (%s,%s,%s,%s)""", (cubierta_id, remanente_mm, km, usuario))
    cx.execute("update cubiertas set remanente_mm = %s where id = %s", (remanente_mm, cubierta_id))
    _log(cx, grupo, "medicion", cubierta_id=cubierta_id, km=km,
         remanente_mm=remanente_mm, usuario=usuario)
    return grupo
