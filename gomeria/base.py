"""
Acceso a la base de gomería (Supabase / PostgreSQL).

Todas las operaciones que cambian algo corren dentro de una transacción:
o se aplica el movimiento entero o no se aplica nada. Una rotación de
cuatro cubiertas nunca puede quedar por la mitad.
"""
import os, re, uuid
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
    # Sin esto, un texto vacío entra por la comparación contra interno y
    # devuelve la primera unidad que no tenga interno cargado.
    if not limpio:
        return None
    return cx.execute("""
        select * from unidades
        where replace(replace(upper(patente),' ',''),'-','') = %s
           or upper(coalesce(interno,'')) = %s
        limit 1""", (limpio, limpio)).fetchone()


def fmtPat(p):
    """AD247MQ -> AD 247 MQ, para nombrarla como la lee una persona."""
    m = re.match(r"^([A-Z]{2})(\d{3})([A-Z]{2})$", p or "")
    if m:
        return f"{m[1]} {m[2]} {m[3]}"
    o = re.match(r"^([A-Z]{3})(\d{3})$", p or "")
    return f"{o[1]} {o[2]}" if o else (p or "")


def resolver_unidad(cx, texto):
    """Averigua de qué unidad habla el texto.

    El gomero escribe todo junto: "AD 247 MQ giré las de atrás". La patente se
    busca adentro del texto comparando contra las que existen, así da igual si
    la escribió con espacios, con guiones o pegada.

    Devuelve (unidad, error). Si no la encuentra, unidad es None y error dice
    qué hay que preguntarle.
    """
    plano = "".join(ch for ch in str(texto).upper() if ch.isalnum())
    if not plano:
        return None, "Escribí qué hiciste y en qué unidad."

    todas = cx.execute("select * from unidades where activa").fetchall()
    encontradas = [u for u in todas if u["patente"] and u["patente"] in plano]

    # Una patente puede estar contenida en otra: se queda la más larga, que es
    # la que realmente escribió.
    if len(encontradas) > 1:
        largo = max(len(u["patente"]) for u in encontradas)
        largas = [u for u in encontradas if len(u["patente"]) == largo]
        if len(largas) == 1:
            return largas[0], None
        nombres = ", ".join(fmtPat(u["patente"]) for u in largas)
        return None, f"Nombrás más de una unidad ({nombres}). Cargá una por vez."
    if len(encontradas) == 1:
        return encontradas[0], None

    # Sin patente: probar con el número interno ("interno 12", "int 12").
    m = re.search(r"\bINT(?:ERNO)?\.?\s*[:#]?\s*(\d{1,4})\b", str(texto).upper())
    if m:
        porinterno = [u for u in todas if (u["interno"] or "").strip() == m.group(1)]
        if len(porinterno) == 1:
            return porinterno[0], None
        if len(porinterno) > 1:
            return None, f"Hay más de una unidad con el interno {m.group(1)}. Escribí la patente."

    return None, ("No encontré la unidad. Escribí la patente en el texto, "
                  "por ejemplo: AD 247 MQ giré las de atrás.")


def mapa_unidad(cx, unidad_id):
    """El mapa con lo que tiene puesto ahora, ordenado como se dibuja."""
    return cx.execute("""
        select * from v_mapa_unidad where unidad_id = %s order by orden""",
        (unidad_id,)).fetchall()


def tablero_unidades(cx):
    """Todas las unidades activas con el nivel de ocupacion de su mapa."""
    return cx.execute("""
        select u.id, u.patente, u.interno, u.marca, u.modelo, u.sucursal,
               u.uso, u.km_actual, u.configuracion_id,
               c.nombre as configuracion, c.descripcion as descripcion_mapa,
               count(p.id)::int as posiciones,
               count(m.id)::int as montadas
        from unidades u
        left join configuraciones c on c.id = u.configuracion_id
        left join configuracion_posiciones p on p.configuracion_id = u.configuracion_id
        left join montajes m on m.unidad_id = u.id
                            and m.posicion_id = p.id and m.hasta is null
        where u.activa
        group by u.id, c.id
        order by coalesce(u.sucursal,''), u.patente
    """).fetchall()


def configuraciones(cx):
    return cx.execute("""
        select c.id, c.nombre, c.descripcion, count(p.id)::int as posiciones
        from configuraciones c
        left join configuracion_posiciones p on p.configuracion_id = c.id
        group by c.id order by count(p.id), c.nombre
    """).fetchall()


def historial_unidad(cx, unidad_id, limite=120):
    return cx.execute("""
        select mv.id, mv.fecha, mv.tipo, mv.cubierta_id, c.codigo as cubierta,
               po.codigo as desde_posicion, pd.codigo as hasta_posicion,
               mv.km_unidad, mv.remanente_mm, mv.usuario, mv.nota,
               pa.texto as texto_original
        from movimientos mv
        left join cubiertas c on c.id = mv.cubierta_id
        left join configuracion_posiciones po on po.id = mv.posicion_origen_id
        left join configuracion_posiciones pd on pd.id = mv.posicion_destino_id
        left join partes pa on pa.id = mv.parte_id
        where mv.unidad_id = %s
        order by mv.fecha desc limit %s
    """, (unidad_id, limite)).fetchall()


def posicion_por_codigo(cx, unidad_id, codigo):
    return cx.execute("""
        select p.* from configuracion_posiciones p
        join unidades u on u.configuracion_id = p.configuracion_id
        where u.id = %s and upper(p.codigo) = upper(%s)""",
        (unidad_id, str(codigo).strip())).fetchone()


def buscar_cubierta(cx, codigo):
    return cx.execute("select * from cubiertas where upper(codigo) = upper(%s)",
                      (str(codigo).strip(),)).fetchone()


def _numero_de_fuego(codigo):
    """079 y 79 son el mismo número de fuego escrito por dos personas."""
    plano = "".join(ch for ch in str(codigo).upper() if ch.isalnum())
    return plano.lstrip("0") or plano


def buscar_cubierta_flexible(cx, codigo):
    """Busca la cubierta como la nombró el gomero en el parte.

    En el parte el número de fuego viene corto y sin ceros a la izquierda
    ("entran 2 Michelin 079 y 327"), mientras que en la base puede estar
    cargado con ceros, con guiones o con un prefijo. Primero se prueba el
    código exacto y recién después el número de fuego suelto.

    Si el número da con más de una cubierta no elige ninguna: avisa cuáles
    son para que lo escriba completo.
    """
    exacta = buscar_cubierta(cx, codigo)
    if exacta:
        return exacta

    buscado = _numero_de_fuego(codigo)
    if not buscado:
        return None

    candidatas = [c for c in cx.execute("select * from cubiertas").fetchall()
                  if _numero_de_fuego(c["codigo"]) == buscado]
    if len(candidatas) == 1:
        return candidatas[0]
    if len(candidatas) > 1:
        cuales = ", ".join(sorted(c["codigo"] for c in candidatas))
        raise ValueError(f"El número {codigo} da con varias cubiertas ({cuales}). "
                         f"Escribí el código completo.")
    return None


def stock(cx, medida=None, limite=50):
    if medida:
        return cx.execute("select * from v_stock where medida = %s order by codigo limit %s",
                          (medida, limite)).fetchall()
    return cx.execute("select * from v_stock order by codigo limit %s", (limite,)).fetchall()


def historial_cubierta(cx, cubierta_id, limite=40):
    return cx.execute("""
        select * from v_historial_cubierta where cubierta_id = %s limit %s""",
        (cubierta_id, limite)).fetchall()


def inventario_cubiertas(cx):
    """Inventario completo, incluida la ubicacion actual si esta montada."""
    return cx.execute("""
        select c.*, u.patente, p.codigo as posicion, m.desde as montada_desde
        from cubiertas c
        left join montajes m on m.cubierta_id = c.id and m.hasta is null
        left join unidades u on u.id = m.unidad_id
        left join configuracion_posiciones p on p.id = m.posicion_id
        order by case c.estado
                   when 'stock' then 1 when 'montada' then 2
                   when 'reparacion' then 3 when 'recapado' then 4 else 5 end,
                 c.codigo
    """).fetchall()


def resumen_cubiertas(cx):
    filas = cx.execute("""
        select estado, count(*)::int as cantidad
        from cubiertas group by estado
    """).fetchall()
    resumen = {estado: 0 for estado in ('stock', 'montada', 'reparacion', 'recapado', 'baja')}
    resumen.update({f["estado"]: f["cantidad"] for f in filas})
    return resumen


def ficha_cubierta(cx, cubierta_id):
    cubierta = cx.execute("""
        select c.*, u.patente, p.codigo as posicion, m.desde as montada_desde
        from cubiertas c
        left join montajes m on m.cubierta_id = c.id and m.hasta is null
        left join unidades u on u.id = m.unidad_id
        left join configuracion_posiciones p on p.id = m.posicion_id
        where c.id = %s
    """, (cubierta_id,)).fetchone()
    if not cubierta:
        return None
    return {"cubierta": cubierta,
            "historial": historial_cubierta(cx, cubierta_id, limite=120)}


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


def asignar_configuracion(cx, unidad_id, configuracion_id):
    existe = cx.execute("select id from configuraciones where id = %s",
                        (configuracion_id,)).fetchone()
    if not existe:
        raise ValueError("El mapa elegido no existe.")
    abiertos = cx.execute("""
        select count(*) as n from montajes where unidad_id = %s and hasta is null
    """, (unidad_id,)).fetchone()["n"]
    if abiertos:
        raise ValueError("No se puede cambiar el mapa mientras haya cubiertas montadas.")
    fila = cx.execute("""
        update unidades set configuracion_id = %s where id = %s returning patente
    """, (configuracion_id, unidad_id)).fetchone()
    if not fila:
        raise ValueError("La unidad no existe.")
    return fila["patente"]


def cambiar_estado_cubierta(cx, cubierta_id, estado, usuario=None, nota=None):
    permitidos = {'stock', 'reparacion', 'recapado', 'baja'}
    if estado not in permitidos:
        raise ValueError("Estado de cubierta invalido.")
    cubierta = cx.execute("select * from cubiertas where id = %s",
                          (cubierta_id,)).fetchone()
    if not cubierta:
        raise ValueError("La cubierta no existe.")
    montada = cx.execute("select 1 from montajes where cubierta_id = %s and hasta is null",
                         (cubierta_id,)).fetchone()
    if montada:
        raise ValueError("La cubierta esta montada. Registrá primero el desmontaje.")
    cx.execute("""
        update cubiertas set estado = %s,
          fecha_baja = case when %s = 'baja' then current_date else null end,
          motivo_baja = case when %s = 'baja' then %s else null end
        where id = %s
    """, (estado, estado, estado, nota, cubierta_id))
    tipo = {'reparacion': 'reparacion', 'recapado': 'recapado',
            'baja': 'baja'}.get(estado, 'desmontaje')
    _log(cx, uuid.uuid4(), tipo, cubierta_id=cubierta_id,
         usuario=usuario, nota=nota)


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


def montaje_abierto(cx, unidad_id, posicion_id):
    """La cubierta que el sistema tiene puesta en esa posición, si tiene alguna."""
    return cx.execute("""
        select id, cubierta_id from montajes
        where unidad_id = %s and posicion_id = %s and hasta is null""",
        (unidad_id, posicion_id)).fetchone()


def donde_esta(cx, cubierta_id):
    """Si la cubierta figura montada, en qué unidad y en qué posición."""
    return cx.execute("""
        select u.patente, p.codigo as posicion
        from montajes m
        join unidades u on u.id = m.unidad_id
        join configuracion_posiciones p on p.id = m.posicion_id
        where m.cubierta_id = %s and m.hasta is null""",
        (cubierta_id,)).fetchone()


def sacar_de_servicio(cx, cubierta_id, destino="stock", unidad_id=None,
                      posicion_id=None, km=None, grupo=None, **kw):
    """Asienta la salida de una cubierta que el sistema no tenía montada.

    Pasa mientras los mapas se están cargando: el gomero saca cubiertas que
    nunca se registraron puestas. Rechazar el parte entero por eso sería
    perder el dato que importa, que es dónde queda la cubierta.
    """
    grupo = grupo or uuid.uuid4()
    cx.execute("update cubiertas set estado = %s where id = %s", (destino, cubierta_id))
    if destino == "baja":
        cx.execute("""update cubiertas set fecha_baja = current_date, motivo_baja = %s
                      where id = %s""", (kw.get("nota"), cubierta_id))
    tipo = {"baja": "baja", "recapado": "recapado",
            "reparacion": "reparacion"}.get(destino, "desmontaje")
    _log(cx, grupo, tipo, unidad_id=unidad_id, cubierta_id=cubierta_id,
         origen_id=posicion_id, km=km, **kw)
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
