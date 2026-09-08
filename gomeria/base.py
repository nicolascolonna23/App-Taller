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


def historial_unidad(cx, unidad_id, limite=120, con_deshechos=False):
    return cx.execute("""
        select mv.id, mv.grupo_id, mv.fecha, mv.tipo, mv.cubierta_id,
               c.codigo as cubierta,
               po.codigo as desde_posicion, pd.codigo as hasta_posicion,
               mv.km_unidad, mv.remanente_mm, mv.usuario, mv.nota,
               mv.deshecho, mv.deshecho_por,
               pa.texto as texto_original
        from movimientos mv
        left join cubiertas c on c.id = mv.cubierta_id
        left join configuracion_posiciones po on po.id = mv.posicion_origen_id
        left join configuracion_posiciones pd on pd.id = mv.posicion_destino_id
        left join partes pa on pa.id = mv.parte_id
        where mv.unidad_id = %s
          and (%s or mv.deshecho is null)
        order by mv.fecha desc limit %s
    """, (unidad_id, bool(con_deshechos), limite)).fetchall()


# =====================================================================
# EL HISTORIAL, Y CÓMO SE DESHACE UN MOVIMIENTO
# =====================================================================
# Un parte es un grupo. Una rotación de cuatro cubiertas son cuatro filas
# de un mismo grupo, y en pantalla tienen que ser un solo renglón con un
# solo botón: deshacer media rotación no es deshacer nada.
#
# Todo lo que escribe un grupo se escribe en una sola transacción, y en
# PostgreSQL now() vale lo mismo durante toda la transacción. Por eso el
# montaje que abrió el grupo, el que cerró y la medición que tomó llevan
# los tres exactamente la misma marca de tiempo que sus movimientos: esa
# marca es la que permite encontrarlos después para revertirlos, sin
# tener que haber guardado un puntero en cada tabla.

def _historial_soporta_deshacer(cx):
    fila = cx.execute("""
        select count(*) as n from information_schema.columns
        where table_name = 'movimientos' and column_name = 'deshecho'
    """).fetchone()
    return bool(fila and fila["n"])


def movimientos_unidad(cx, unidad_id, limite=60, con_deshechos=False):
    """El historial de la unidad, un renglón por parte.

    Cada renglón trae el detalle de lo que se hizo y si se puede deshacer.
    No se puede cuando después pasó algo más sobre las mismas cubiertas:
    revertir el anteúltimo movimiento dejaría el mapa peor de lo que está.
    """
    if not _historial_soporta_deshacer(cx):
        # Sin el SQL corrido no hay historial agrupado; la pantalla se
        # arregla con la lista de siempre.
        return []

    grupos = cx.execute("""
        select g.*,
               pa.texto as texto_original,
               exists (
                 select 1 from movimientos m2
                 where m2.cubierta_id = any(g.cubiertas)
                   and m2.deshecho is null
                   and m2.grupo_id <> g.grupo_id
                   and m2.id > g.ultimo_id
               ) as hay_posteriores
        from v_grupos_movimiento g
        left join partes pa on pa.id = g.parte_id
        where g.unidad_id = %s
          and (%s or not g.deshecho_flag)
        order by g.fecha desc, g.ultimo_id desc
        limit %s
    """, (unidad_id, bool(con_deshechos), limite)).fetchall()
    if not grupos:
        return []

    detalle = cx.execute("""
        select mv.grupo_id, mv.id, mv.tipo, mv.fecha,
               c.codigo as cubierta, c.marca,
               po.codigo as desde_posicion, pd.codigo as hasta_posicion,
               mv.km_unidad, mv.remanente_mm, mv.nota
        from movimientos mv
        left join cubiertas c on c.id = mv.cubierta_id
        left join configuracion_posiciones po on po.id = mv.posicion_origen_id
        left join configuracion_posiciones pd on pd.id = mv.posicion_destino_id
        where mv.grupo_id = any(%s)
        order by mv.id
    """, ([g["grupo_id"] for g in grupos],)).fetchall()

    por_grupo = {}
    for fila in detalle:
        por_grupo.setdefault(fila["grupo_id"], []).append(fila)

    for g in grupos:
        g["detalle"] = por_grupo.get(g["grupo_id"], [])
        g["deshecho_flag"] = bool(g["deshecho_flag"])
        g["motivo_bloqueo"] = _por_que_no_se_deshace(g)
        g["se_puede_deshacer"] = g["motivo_bloqueo"] is None
    return grupos


def _por_que_no_se_deshace(grupo):
    """El motivo, en castellano, o None si se puede deshacer."""
    if grupo["deshecho_flag"]:
        return "Ya está deshecho."
    if "alta" in (grupo["tipos"] or []):
        return ("Es el alta de una cubierta. Para sacarla del sistema hay que "
                "darla de baja desde su ficha.")
    if grupo["hay_posteriores"]:
        return ("Después de este movimiento hubo otros sobre las mismas "
                "cubiertas. Deshacé primero el último.")
    return None


def deshacer_grupo(cx, grupo_id, usuario=None, motivo=None):
    """Revierte un movimiento entero y lo deja marcado como deshecho.

    Devuelve un resumen de lo que se revirtió. La cubierta vuelve a donde
    estaba, la medición se borra y el remanente vuelve a la medición
    anterior. Lo único que no se puede reconstruir es de qué estado venía
    una cubierta que no estaba montada —si estaba en reparación o en el
    estante—: esas vuelven al estante, que es donde no molestan.
    """
    if not _historial_soporta_deshacer(cx):
        raise ValueError("Falta correr gomeria/19_historial.sql en Supabase.")

    movs = cx.execute("""
        select * from movimientos where grupo_id = %s order by id
    """, (grupo_id,)).fetchall()
    if not movs:
        raise ValueError("Ese movimiento no existe.")

    grupo = cx.execute("""
        select g.*, exists (
                 select 1 from movimientos m2
                 where m2.cubierta_id = any(g.cubiertas)
                   and m2.deshecho is null
                   and m2.grupo_id <> g.grupo_id
                   and m2.id > g.ultimo_id
               ) as hay_posteriores
        from v_grupos_movimiento g where g.grupo_id = %s
    """, (grupo_id,)).fetchone()
    grupo["deshecho_flag"] = bool(grupo["deshecho_flag"])
    impedimento = _por_que_no_se_deshace(grupo)
    if impedimento:
        raise ValueError(impedimento)

    cubiertas = grupo["cubiertas"] or []
    fecha = movs[0]["fecha"]

    # Los montajes que abrió este grupo se van; los que cerró vuelven a
    # abrirse. Los dos se reconocen por la marca de tiempo de la
    # transacción que los escribió.
    abiertos = cx.execute("""
        delete from montajes
        where cubierta_id = any(%s) and desde = %s
        returning id""", (cubiertas, fecha)).fetchall()
    cerrados = cx.execute("""
        update montajes set hasta = null, km_unidad_desmontaje = null
        where cubierta_id = any(%s) and hasta = %s
        returning id""", (cubiertas, fecha)).fetchall()

    # Las mediciones que tomó, y el remanente vuelve al valor anterior.
    cx.execute("delete from mediciones where cubierta_id = any(%s) and fecha = %s",
               (cubiertas, fecha))

    for cubierta_id in cubiertas:
        anterior = cx.execute("""
            select remanente_mm from mediciones
            where cubierta_id = %s order by fecha desc, id desc limit 1
        """, (cubierta_id,)).fetchone()
        montada = cx.execute("""
            select 1 from montajes where cubierta_id = %s and hasta is null
        """, (cubierta_id,)).fetchone()
        cx.execute("""
            update cubiertas
               set remanente_mm = %s,
                   estado = %s,
                   fecha_baja = null,
                   motivo_baja = null
             where id = %s
        """, (anterior["remanente_mm"] if anterior else None,
              "montada" if montada else "stock", cubierta_id))

    cx.execute("""
        update movimientos set deshecho = now(), deshecho_por = %s, deshecho_motivo = %s
        where grupo_id = %s
    """, (usuario, (str(motivo).strip() or None) if motivo else None, grupo_id))

    # El parte del que salió vuelve a quedar sin aplicar, con el texto
    # original intacto: es la prueba de qué se había escrito.
    if grupo["parte_id"]:
        cx.execute("""
            update partes set estado = 'descartado', resuelto = now(), resuelto_por = %s
            where id = %s""", (usuario, grupo["parte_id"]))

    return {"montajes_borrados": len(abiertos),
            "montajes_reabiertos": len(cerrados),
            "cubiertas": len(cubiertas),
            "renglones": len(movs)}


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


def kilometros_por_montaje(cx, cubierta_id):
    """Kilómetros de Hawk recorridos por la cubierta en cada montaje.

    El movimiento aporta solamente ``desde``/``hasta``. Para cada intervalo
    se toma la primera lectura diaria de Hawk dentro del montaje y la última
    lectura anterior al cierre (o a hoy si sigue montada). Así una lectura
    que llega después del parte completa el cálculo sin editar el movimiento.
    """
    existe = cx.execute(
        "select to_regclass('public.odometros') as tabla"
    ).fetchone()
    if not existe or not existe["tabla"]:
        return []

    return cx.execute("""
        select m.id as montaje_id, m.desde, m.hasta, u.patente,
               p.codigo as posicion,
               inicio.fecha as fecha_lectura_desde,
               inicio.km as km_desde,
               fin.fecha as fecha_lectura_hasta,
               fin.km as km_hasta,
               case
                 when inicio.km is null or fin.km is null then null
                 when fin.km < inicio.km then null
                 when fin.km - inicio.km >
                      1200 * greatest(fin.fecha - inicio.fecha, 1) then null
                 else fin.km - inicio.km
               end as km_recorridos,
               case
                 when inicio.km is null or fin.km is null then 'pendiente'
                 when fin.km < inicio.km then 'anomalo'
                 when fin.km - inicio.km >
                      1200 * greatest(fin.fecha - inicio.fecha, 1) then 'anomalo'
                 else 'calculado'
               end as estado_km
        from montajes m
        join unidades u on u.id = m.unidad_id
        join configuracion_posiciones p on p.id = m.posicion_id
        left join lateral (
          select o.fecha, o.km
          from odometros o
          where o.unidad_id = m.unidad_id
            and o.fecha >= m.desde::date
            and o.fecha <= coalesce(m.hasta::date, current_date)
          order by o.fecha asc
          limit 1
        ) inicio on true
        left join lateral (
          select o.fecha, o.km
          from odometros o
          where o.unidad_id = m.unidad_id
            and o.fecha >= m.desde::date
            and o.fecha <= coalesce(m.hasta::date, current_date)
          order by o.fecha desc
          limit 1
        ) fin on true
        where m.cubierta_id = %s
        order by m.desde desc
    """, (cubierta_id,)).fetchall()


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
    montajes_km = kilometros_por_montaje(cx, cubierta_id)
    calculados = [m for m in montajes_km if m["km_recorridos"] is not None]
    cubierta["km_hawk_total"] = float(sum(m["km_recorridos"] for m in calculados))
    cubierta["km_hawk_intervalos_calculados"] = len(calculados)
    cubierta["km_hawk_activo"] = bool(montajes_km)
    actual = next((m for m in montajes_km if m["hasta"] is None), None)
    cubierta["km_montaje_actual"] = (
        float(actual["km_recorridos"])
        if actual and actual["km_recorridos"] is not None else None)
    return {"cubierta": cubierta,
            "historial": historial_cubierta(cx, cubierta_id, limite=120),
            "montajes_km": montajes_km}


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
    _abrir_primera_vida(cx, fila["id"], datos)
    return fila["id"]


def _hay_vidas(cx):
    """Si ya se corrió el SQL de desgaste.

    Se pregunta en vez de intentar y atajar el error: en PostgreSQL una
    consulta que falla ensucia la transacción entera, y deshacerla acá se
    llevaría puesta el alta de la cubierta sin que nadie se entere.
    """
    fila = cx.execute("select to_regclass('public.vidas_cubierta') as t").fetchone()
    return bool(fila and fila["t"])


def _abrir_primera_vida(cx, cubierta_id, datos):
    """Le abre la vida 0 a la cubierta recién dada de alta.

    Una cubierta sin vida abierta queda afuera del cálculo de costo y
    rendimiento sin que nadie se entere: aparece en el inventario y no
    aparece en el tablero. Por eso el alta la abre sola.

    Si el SQL de desgaste todavía no se corrió, no hace nada: que falte no
    puede impedir dar de alta una goma. Cuando se corra, el propio archivo
    les abre la vida a todas las que ya estén.
    """
    if not _hay_vidas(cx):
        return
    cx.execute("""
        insert into vidas_cubierta (cubierta_id, numero, tipo, marca, banda,
                                    inicial_mm, costo, desde, nota)
        select %s, 0, 'original', %s, %s, %s, %s, current_date, %s
        where not exists (select 1 from vidas_cubierta where cubierta_id = %s)
    """, (cubierta_id, datos.get("marca"), datos.get("modelo"),
          datos.get("remanente_mm"), datos.get("costo_compra"),
          datos.get("nota"), cubierta_id))


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
    if estado == 'baja':
        _cerrar_vida(cx, cubierta_id, nota or 'baja')


def _cerrar_vida(cx, cubierta_id, motivo):
    """Cierra la vida que corría cuando la cubierta se da de baja.

    Sin esto la última vida queda abierta para siempre y sigue sumando
    kilómetros de montajes que ya no existen. El remanente con el que
    terminó se guarda ahora, que es cuando todavía se sabe."""
    if not _hay_vidas(cx):
        return
    cx.execute("""
        update vidas_cubierta v
           set hasta = current_date, motivo_fin = %s,
               remanente_fin_mm = c.remanente_mm
          from cubiertas c
         where c.id = v.cubierta_id and v.cubierta_id = %s and v.hasta is null
    """, (motivo, cubierta_id))


# =====================================================================
# MOVIMIENTOS
# =====================================================================
def _cerrar_montaje(cx, unidad_id, posicion_id, km=None):
    """Cierra el montaje; los km se calculan luego con las lecturas de Hawk."""
    fila = cx.execute("""
        update montajes set hasta = now(), km_unidad_desmontaje = null
        where unidad_id = %s and posicion_id = %s and hasta is null
        returning id, cubierta_id, km_unidad_montaje""",
        (unidad_id, posicion_id)).fetchone()
    return fila


def _abrir_montaje(cx, unidad_id, posicion_id, cubierta_id, km=None, nota=None):
    cx.execute("""
        insert into montajes (unidad_id, posicion_id, cubierta_id, km_unidad_montaje, nota)
        values (%s,%s,%s,null,%s)""", (unidad_id, posicion_id, cubierta_id, nota))
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


def odometro_en(cx, patente, fecha):
    """El kilometraje que tenía esa unidad en esa fecha, según el satelital.

    Se busca la lectura del día y, si no hay (el scraper no corrió, o el
    equipo no reportó), la más cercana: primero hacia atrás, que es la que
    no inventa kilómetros que la unidad todavía no había hecho.

    Devuelve el diccionario de la lectura con la distancia en días, o None
    si de esa unidad no hay ninguna lectura.
    """
    plano = "".join(ch for ch in str(patente or "").upper() if ch.isalnum())
    if not plano:
        return None
    return cx.execute("""
        select patente, fecha, km, ultimo_reporte,
               (fecha - %s::date) as desvio
        from odometros
        where patente = %s
        order by
          case when fecha <= %s::date then 0 else 1 end,   -- antes que después
          abs(fecha - %s::date)
        limit 1
    """, (fecha, plano, fecha, fecha)).fetchone()


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
    """Anota el dibujo que le quedó a una cubierta.

    Si está montada, la medición queda también a nombre de la unidad: es
    algo que pasó sobre ese camión y tiene que verse en su historial, que
    es donde se mira cuando hay que deshacer una carga equivocada.
    """
    grupo = grupo or uuid.uuid4()
    puesta = cx.execute("""
        select unidad_id, posicion_id from montajes
        where cubierta_id = %s and hasta is null""", (cubierta_id,)).fetchone()
    cx.execute("""insert into mediciones (cubierta_id, remanente_mm, km_unidad, usuario)
                  values (%s,%s,%s,%s)""", (cubierta_id, remanente_mm, km, usuario))
    cx.execute("update cubiertas set remanente_mm = %s where id = %s", (remanente_mm, cubierta_id))
    _log(cx, grupo, "medicion", cubierta_id=cubierta_id, km=km,
         remanente_mm=remanente_mm, usuario=usuario,
         unidad_id=puesta["unidad_id"] if puesta else None,
         origen_id=puesta["posicion_id"] if puesta else None)
    return grupo
