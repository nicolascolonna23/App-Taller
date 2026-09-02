"""Vencimientos: VTV, licencias, matafuegos y lo que se agregue después.

La tabla es una sola para todos los tipos (ver 06_vencimientos.sql). Acá
está lo que la pantalla necesita: la foto de hoy, el historial de cada
cosa y el alta de una renovación.

Una renovación nunca pisa a la anterior: se inserta una fila nueva y la
vista se queda con la última. Así queda el historial de cuándo se hizo
cada VTV y en qué planta.
"""
from datetime import date, timedelta

GESTORES = {"admin", "encargado"}


def _exigir_gestor(usuario):
    if (usuario or {}).get("rol") not in GESTORES:
        raise PermissionError("Solo un encargado o administrador puede cargar vencimientos.")


def _fecha(valor, campo):
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor).strip()[:10])
    except ValueError:
        raise ValueError(f"La fecha de {campo} no se entiende: {valor}")


def _texto(valor, limite=200):
    texto = str(valor or "").strip()
    return texto[:limite] or None


# =====================================================================
# LECTURA
# =====================================================================
def listar(cx):
    """Todo lo que la pantalla dibuja de una."""
    filas = cx.execute("""
        select id, tipo_id, tipo, ambito, unidad_id, patente, interno,
               persona_id, persona, identificador, detalle,
               desde, vence, dias, estado, donde, observaciones,
               coalesce(sucursal_unidad, sucursal_persona) as sucursal
        from v_vencimientos_hoy
        order by estado = 'vigente', dias, orden, tipo
    """).fetchall()

    resumen = {"vencido": 0, "por_vencer": 0, "vigente": 0}
    for f in filas:
        resumen[f["estado"]] = resumen.get(f["estado"], 0) + 1

    return {
        "vencimientos": [dict(f) for f in filas],
        "resumen": resumen,
        "faltantes": [dict(f) for f in cx.execute(
            "select * from v_vencimientos_faltantes order by tipo, patente, persona").fetchall()],
        "tipos": [dict(t) for t in cx.execute("""
            select id, nombre, ambito, aviso_dias, meses, varios
            from tipos_vencimiento where activo order by orden, nombre""").fetchall()],
        "unidades": [dict(u) for u in cx.execute("""
            select id, patente, interno, sucursal from unidades
            where activa order by patente""").fetchall()],
        "personas": [dict(p) for p in cx.execute("""
            select p.id, p.nombre, p.documento, p.sucursal, p.unidad_id,
                   u.patente as patente_unidad
            from personas p
            left join unidades u on u.id = p.unidad_id
            where p.activa order by p.nombre""").fetchall()],
    }


def historial(cx, tipo_id, unidad_id=None, persona_id=None, identificador=None):
    """Todas las renovaciones de una misma cosa, de la última a la primera."""
    return [dict(f) for f in cx.execute("""
        select v.id, v.desde, v.vence, v.identificador, v.detalle,
               v.donde, v.costo, v.observaciones, v.usuario, v.creado
        from vencimientos v
        where v.tipo_id = %s
          and v.unidad_id is not distinct from %s
          and v.persona_id is not distinct from %s
          and (%s::text is null or v.identificador = %s)
        order by v.vence desc, v.id desc
    """, (tipo_id, unidad_id, persona_id, identificador, identificador)).fetchall()]


# =====================================================================
# ESCRITURA
# =====================================================================
def guardar(cx, datos, usuario):
    """Carga un vencimiento o su renovación. Devuelve lo que quedó."""
    _exigir_gestor(usuario)

    tipo_id = datos.get("tipo_id")
    tipo = cx.execute("select * from tipos_vencimiento where id = %s and activo",
                      (tipo_id,)).fetchone()
    if not tipo:
        raise ValueError("Elegí qué vence.")

    vence = _fecha(datos.get("vence"), "vencimiento")
    desde = _fecha(datos.get("desde"), "emisión")
    if not vence:
        # Con la periodicidad del tipo alcanza con la fecha de emisión.
        if desde and tipo["meses"]:
            vence = _sumar_meses(desde, tipo["meses"])
        else:
            raise ValueError("Falta la fecha de vencimiento.")

    unidad_id = datos.get("unidad_id") or None
    persona_id = datos.get("persona_id") or None
    if tipo["ambito"] == "unidad":
        persona_id = None
        if not unidad_id:
            raise ValueError(f"{tipo['nombre']} es de una unidad: elegí la patente.")
    elif tipo["ambito"] == "persona":
        unidad_id = None
        if not persona_id:
            raise ValueError(f"{tipo['nombre']} es de una persona: elegí quién.")
    else:
        unidad_id = persona_id = None

    identificador = _texto(datos.get("identificador"), 60)
    if tipo["varios"] and not identificador:
        raise ValueError(
            f"De {tipo['nombre']} puede haber más de uno por unidad, "
            f"así que hace falta el número para saber cuál es.")

    fila = cx.execute("""
        insert into vencimientos
          (tipo_id, unidad_id, persona_id, identificador, detalle,
           desde, vence, costo, donde, observaciones, usuario)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        returning id
    """, (tipo_id, unidad_id, persona_id, identificador,
          _texto(datos.get("detalle")), desde, vence,
          _numero(datos.get("costo")), _texto(datos.get("donde")),
          _texto(datos.get("observaciones"), 500),
          (usuario or {}).get("usuario"))).fetchone()

    return {"ok": True, "id": fila["id"], "vence": vence.isoformat()}


def borrar(cx, venc_id, usuario):
    """Saca una carga equivocada. La renovación anterior vuelve a mandar."""
    _exigir_gestor(usuario)
    fila = cx.execute("delete from vencimientos where id = %s returning id",
                      (venc_id,)).fetchone()
    if not fila:
        raise ValueError("Ese vencimiento ya no está.")
    return {"ok": True}


def alta_persona(cx, datos, usuario):
    _exigir_gestor(usuario)
    nombre = _texto(datos.get("nombre"), 120)
    if not nombre:
        raise ValueError("Falta el nombre.")
    fila = cx.execute("""
        insert into personas (nombre, documento, legajo, sucursal, telefono)
        values (%s,%s,%s,%s,%s) returning id
    """, (nombre, _texto(datos.get("documento"), 20), _texto(datos.get("legajo"), 20),
          _texto(datos.get("sucursal"), 60), _texto(datos.get("telefono"), 40))).fetchone()
    return {"ok": True, "id": fila["id"]}


# =====================================================================
def _numero(valor):
    if valor in (None, ""):
        return None
    try:
        n = float(valor)
    except (TypeError, ValueError):
        raise ValueError("El costo tiene que ser un número.")
    if n < 0:
        raise ValueError("El costo no puede ser negativo.")
    return n


def _sumar_meses(desde, meses):
    """La misma fecha, tantos meses después. El 31 cae al último día del mes."""
    año = desde.year + (desde.month - 1 + meses) // 12
    mes = (desde.month - 1 + meses) % 12 + 1
    dia = desde.day
    while True:
        try:
            return date(año, mes, dia)
        except ValueError:
            dia -= 1


def aplicar(cx, datos, usuario):
    """Punto de entrada de la API."""
    op = (datos.get("op") or "").strip()
    if op == "guardar":
        return guardar(cx, datos, usuario)
    if op == "borrar":
        return borrar(cx, datos.get("id"), usuario)
    if op == "persona":
        return alta_persona(cx, datos, usuario)
    if op == "historial":
        return {"historial": historial(cx, datos.get("tipo_id"),
                                       datos.get("unidad_id") or None,
                                       datos.get("persona_id") or None,
                                       datos.get("identificador") or None)}
    raise ValueError("No entiendo qué hay que hacer.")
