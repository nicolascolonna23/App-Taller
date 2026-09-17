"""Urea: el tacho propio, y lo que sale de él.

Combustible se controla contra un tercero —la estación manda su listado y
el sistema cruza remitos—. La urea no: el tacho es nuestro, así que no hay
nada que cruzar con nadie. Lo que hay que controlar es un stock.

Por eso este módulo no se parece al cruce de combustible, se parece al
depósito de repuestos: **nadie edita el saldo**. El saldo es el resultado
de los movimientos, y son tres:

    entrada   llegó el proveedor y se descargó en el tacho.
    salida    se despachó a una unidad. Un derrame o un préstamo también
              salen del tacho, y también se anotan: con motivo en vez de
              patente, pero se anotan.
    ajuste    alguien midió el tacho y no da. Se anota la diferencia con
              su motivo.

Lo del ajuste es la parte que importa. La merma de un tacho de urea es
real —evaporación, derrames, lo que se carga y no se anota— y corregir el
saldo a mano sería perder justo el dato que la explica.

Quién puede qué:

    despachar          cualquiera que tenga el módulo. Es el acto de todos
                       los días y anotarlo tiene que costar menos que no
                       anotarlo.
    cargar y medir     el que gestiona: son la plata que entró y la
                       diferencia que hubo.
    tocar el tacho     el que gestiona.
"""
from datetime import date

import permisos

# Cuánto mira la pantalla hacia atrás sin que nadie filtre nada.
MOVIMIENTOS_VISIBLES = 300
MESES_POR_UNIDAD = 6

# Lo que se espera de un camión moderno: entre 3% y 6% del gasoil. Fuera
# de esa banda no está mal cargado: está pasando otra cosa, y hay que
# mirarla.
BANDA_GASOIL = (3.0, 6.0)


# =====================================================================
# AYUDAS
# =====================================================================
def _exigir_gestor(usuario, que="tocar el tacho de urea"):
    if not permisos.gestiona(usuario):
        raise PermissionError(f"Solo un encargado o administrador puede {que}.")


def _texto(valor, limite=300):
    texto = str(valor or "").strip()
    return texto[:limite] or None


def _patente(valor):
    """Como la guarda el resto del sistema: sin espacios ni guiones."""
    return "".join(c for c in str(valor or "").upper() if c.isalnum())


def _litros(valor, campo="Los litros", permitir_cero=False):
    if valor in (None, ""):
        raise ValueError(f"Falta{'n' if campo.startswith('Los') else ''} {campo.lower()}.")
    try:
        n = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"{campo} tienen que ser un número.") from None
    if n < 0 or (n == 0 and not permitir_cero):
        raise ValueError(f"{campo} tienen que ser mayores que cero.")
    return round(n, 2)


def _numero(valor, campo):
    if valor in (None, ""):
        return None
    try:
        n = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"{campo} tiene que ser un número.") from None
    if n < 0:
        raise ValueError(f"{campo} no puede ser negativo.")
    return n


def _fecha(valor):
    if not valor:
        return date.today()
    if isinstance(valor, date):
        return valor
    try:
        fecha = date.fromisoformat(str(valor).strip()[:10])
    except ValueError:
        raise ValueError(f"No se entiende la fecha: {valor}") from None
    if fecha > date.today():
        raise ValueError("La fecha no puede ser posterior a hoy.")
    return fecha


def _tanque(cx, tanque_id=None):
    """El tacho pedido, o el único que hay.

    Con un solo tacho nadie tiene que elegirlo: la pantalla no pregunta
    lo que tiene una sola respuesta posible.
    """
    if tanque_id:
        fila = cx.execute("select * from urea_tanques where id = %s",
                          (int(tanque_id),)).fetchone()
        if not fila:
            raise ValueError("Ese tacho no existe.")
        return fila
    filas = cx.execute("select * from urea_tanques where activo order by id").fetchall()
    if not filas:
        raise ValueError("Todavía no hay ningún tacho cargado. "
                         "Ejecutar gomeria/28_urea.sql en Supabase.")
    if len(filas) > 1:
        raise ValueError("Hay más de un tacho: indicar de cuál se trata.")
    return filas[0]


def saldo_de(cx, tanque_id):
    fila = cx.execute("select saldo from v_urea_saldo where tanque_id = %s",
                      (tanque_id,)).fetchone()
    return float(fila["saldo"]) if fila else 0.0


def _unidad(cx, datos):
    """La unidad del despacho, si es a una unidad."""
    unidad_id = datos.get("unidad_id") or None
    patente = _patente(datos.get("patente"))
    if unidad_id:
        fila = cx.execute("select id, patente from unidades where id = %s",
                          (unidad_id,)).fetchone()
        if not fila:
            raise ValueError("Esa unidad no existe.")
        return fila["id"], fila["patente"]
    if patente:
        fila = cx.execute("select id from unidades where patente = %s",
                          (patente,)).fetchone()
        return (fila["id"] if fila else None), patente
    return None, None


def _registrar(cx, tanque, tipo, litros, datos, usuario, **extra):
    campos = {
        "tanque_id": tanque["id"], "tipo": tipo, "fecha": _fecha(datos.get("fecha")),
        "litros": litros, "nota": _texto(datos.get("nota"), 500),
        "usuario_id": (usuario or {}).get("id"),
        "usuario": (usuario or {}).get("nombre"),
    }
    campos.update(extra)
    columnas = ", ".join(campos)
    huecos = ", ".join(["%s"] * len(campos))
    fila = cx.execute(
        f"insert into urea_movimientos ({columnas}) values ({huecos}) returning id",
        list(campos.values())).fetchone()
    return fila["id"]


# =====================================================================
# LECTURA
# =====================================================================
def instalado(cx):
    try:
        cx.execute("select 1 from urea_tanques limit 1").fetchone()
        return True
    except Exception:
        cx.rollback()
        return False


def panel(cx, usuario=None, tanque_id=None):
    """Todo lo que la solapa de urea dibuja de una."""
    tanques = [dict(t) for t in cx.execute("""
        select * from v_urea_saldo order by activo desc, nombre""").fetchall()]

    movimientos = [dict(m) for m in cx.execute("""
        select id, tanque_id, tanque, tipo, fecha, litros, delta, unidad_id, patente,
               interno, km, proveedor, remito, importe, motivo, medido_litros,
               usuario, nota, creado
        from v_urea_movimientos
        order by fecha desc, id desc limit %s""", (MOVIMIENTOS_VISIBLES,)).fetchall()]

    por_unidad = [dict(u) for u in cx.execute("""
        select * from v_urea_unidad
        where mes >= date_trunc('month', current_date) - make_interval(months => %s)
        order by mes desc, litros_urea desc
    """, (MESES_POR_UNIDAD,)).fetchall()]

    return {
        "instalado": True,
        "tanques": tanques,
        "movimientos": movimientos,
        "por_unidad": por_unidad,
        "banda_gasoil": list(BANDA_GASOIL),
        "unidades": [dict(u) for u in cx.execute("""
            select id, patente, interno, marca, modelo, sucursal, chofer, km_actual
            from unidades where activa order by patente""").fetchall()],
        "puede_gestionar": permisos.gestiona(usuario),
    }


def historial(cx, patente=None, unidad_id=None):
    """Toda la urea que cargó una unidad, de lo último a lo primero."""
    patente = _patente(patente)
    if not patente and unidad_id:
        fila = cx.execute("select patente from unidades where id = %s",
                          (unidad_id,)).fetchone()
        patente = fila["patente"] if fila else None
    if not patente:
        raise ValueError("Debe seleccionarse la unidad para ver su historial.")

    movimientos = [dict(m) for m in cx.execute("""
        select fecha, litros, km, motivo, usuario, nota
        from urea_movimientos
        where tipo = 'salida' and patente = %s
        order by fecha desc, id desc""", (patente,)).fetchall()]
    meses = [dict(m) for m in cx.execute("""
        select * from v_urea_unidad where patente = %s order by mes desc
    """, (patente,)).fetchall()]
    return {
        "patente": patente,
        "movimientos": movimientos,
        "meses": meses,
        "litros": round(sum(float(m["litros"]) for m in movimientos), 2),
    }


# =====================================================================
# ESCRITURA
# =====================================================================
def cargar(cx, datos, usuario=None):
    """Entró urea al tacho: llegó el proveedor y se descargó."""
    _exigir_gestor(usuario, "cargar urea en el tacho")
    tanque = _tanque(cx, datos.get("tanque_id"))
    litros = _litros(datos.get("litros"))

    movimiento_id = _registrar(cx, tanque, "entrada", litros, datos, usuario,
                               proveedor=_texto(datos.get("proveedor"), 120),
                               remito=_texto(datos.get("remito"), 60),
                               importe=_numero(datos.get("importe"), "El importe"))
    saldo = saldo_de(cx, tanque["id"])
    aviso = None
    # Llenarlo de más no se bloquea —el tacho es el que manda— pero se
    # dice: o la capacidad cargada está mal, o entraron menos litros de
    # los que dice el remito.
    if saldo > float(tanque["capacidad_litros"]) * 1.02:
        aviso = (f"El tacho quedó en {saldo:.0f} litros y la capacidad cargada es "
                 f"{float(tanque['capacidad_litros']):.0f}. Revisá la capacidad "
                 "o los litros que entraron.")
    return {"ok": True, "id": movimiento_id, "saldo": saldo, "aviso": aviso}


def despachar(cx, datos, usuario=None):
    """Salió urea del tacho: a una unidad, o a lo que haya pasado."""
    tanque = _tanque(cx, datos.get("tanque_id"))
    litros = _litros(datos.get("litros"))
    unidad_id, patente = _unidad(cx, datos)
    motivo = _texto(datos.get("motivo"), 200)
    if not patente and not motivo:
        raise ValueError("Indicá a qué unidad fue, o el motivo si no fue a "
                         "ninguna (derrame, préstamo, devolución).")

    movimiento_id = _registrar(cx, tanque, "salida", litros, datos, usuario,
                               unidad_id=unidad_id, patente=patente,
                               km=_numero(datos.get("km"), "El kilometraje"),
                               motivo=motivo)

    # El kilometraje que quedó en el despacho es la última lectura que se
    # le hizo a la unidad: si es mayor que el del maestro, lo pone al día.
    # Es el mismo criterio de las órdenes de trabajo.
    km = _numero(datos.get("km"), "El kilometraje")
    if km and unidad_id:
        cx.execute("""update unidades set km_actual = %s
                      where id = %s and (km_actual is null or km_actual < %s)""",
                   (km, unidad_id, km))

    saldo = saldo_de(cx, tanque["id"])
    estado = cx.execute("select * from v_urea_saldo where tanque_id = %s",
                        (tanque["id"],)).fetchone()
    aviso = None
    # Un saldo negativo no se bloquea: el que está despachando tiene la
    # manguera en la mano y lo que pasó, pasó. Lo que sí hace falta es
    # decir que el número dejó de ser creíble y que hay que medir.
    if saldo < 0:
        aviso = (f"El tacho quedó en {saldo:.0f} litros. Hubo una entrada que no se "
                 "anotó: medí el tacho y cargá la medición.")
    elif estado and estado["estado"] in ("vacio", "critico", "aviso"):
        dias = estado["dias_restantes"]
        aviso = (f"Quedan {saldo:.0f} litros"
                 + (f", para unos {dias} días al ritmo de este mes" if dias is not None else "")
                 + ". Hay que pedir urea.")
    return {"ok": True, "id": movimiento_id, "saldo": saldo,
            "estado": estado["estado"] if estado else None, "aviso": aviso}


def medir(cx, datos, usuario=None):
    """Se midió el tacho. La diferencia se anota; el saldo no se pisa."""
    _exigir_gestor(usuario, "cargar una medición del tacho")
    tanque = _tanque(cx, datos.get("tanque_id"))
    medido = _litros(datos.get("medido_litros") or datos.get("litros"),
                     "Los litros medidos", permitir_cero=True)
    saldo = saldo_de(cx, tanque["id"])
    diferencia = round(medido - saldo, 2)
    if diferencia == 0:
        return {"ok": True, "id": None, "saldo": saldo, "diferencia": 0,
                "aviso": "El tacho da exacto: no hay nada que ajustar."}

    motivo = _texto(datos.get("motivo"), 200)
    if not motivo:
        raise ValueError("Falta el motivo de la diferencia. Sin eso, el ajuste "
                         "tapa el problema en vez de explicarlo.")

    movimiento_id = _registrar(cx, tanque, "ajuste", diferencia, datos, usuario,
                               motivo=motivo, medido_litros=medido)
    return {"ok": True, "id": movimiento_id, "saldo": medido,
            "diferencia": diferencia,
            "aviso": (f"Se anotó una diferencia de {diferencia:+.0f} litros. "
                      "El saldo queda en lo que se midió.")}


def borrar(cx, datos, usuario=None):
    """Saca un movimiento cargado por error. El saldo se corrige solo."""
    _exigir_gestor(usuario, "borrar un movimiento de urea")
    fila = cx.execute("delete from urea_movimientos where id = %s returning tanque_id",
                      (datos.get("id"),)).fetchone()
    if not fila:
        raise ValueError("Ese movimiento ya no está.")
    return {"ok": True, "saldo": saldo_de(cx, fila["tanque_id"])}


def guardar_tanque(cx, datos, usuario=None):
    """El nombre, la capacidad y el mínimo del tacho."""
    _exigir_gestor(usuario)
    nombre = _texto(datos.get("nombre"), 80)
    capacidad = _litros(datos.get("capacidad_litros"), "La capacidad")
    minimo = _numero(datos.get("minimo_litros"), "El mínimo")
    if minimo is not None and minimo > capacidad:
        raise ValueError("El mínimo no puede ser mayor que la capacidad del tacho.")
    sucursal = (_texto(datos.get("sucursal_codigo"), 3) or "").upper() or None

    if datos.get("id"):
        tanque = _tanque(cx, datos["id"])
        cx.execute("""update urea_tanques
                      set nombre = coalesce(%s, nombre), capacidad_litros = %s,
                          minimo_litros = %s, sucursal_codigo = %s, activo = %s
                      where id = %s""",
                   (nombre, capacidad, minimo, sucursal,
                    bool(datos.get("activo", True)), tanque["id"]))
        return {"ok": True, "id": tanque["id"]}

    if not nombre:
        raise ValueError("Falta el nombre del tacho.")
    fila = cx.execute("""
        insert into urea_tanques (nombre, capacidad_litros, minimo_litros, sucursal_codigo)
        values (%s,%s,%s,%s) returning id""",
        (nombre, capacidad, minimo, sucursal)).fetchone()
    return {"ok": True, "id": fila["id"]}


# =====================================================================
# LO QUE MIRA LA PANTALLA DE ALERTAS
# =====================================================================
def alertas(cx):
    """Los tachos que se están quedando sin urea.

    Dos formas de quedarse sin: el tacho bajo y el consumo alto. Las dos
    miran el mismo saldo desde distintos lados, y por eso las dos avisan.
    Un tacho de 1.000 litros con 200 está bien en Catamarca y es una
    urgencia en Córdoba.
    """
    return [dict(f) for f in cx.execute("""
        select * from v_urea_saldo
        where activo and estado <> 'ok'
        order by case estado when 'vacio' then 0 when 'critico' then 1 else 2 end,
                 dias_restantes nulls last, saldo
    """).fetchall()]


# =====================================================================
def aplicar(cx, datos, usuario=None):
    """Punto de entrada de la API."""
    op = (datos.get("op") or "").strip()
    acciones = {"cargar": cargar, "despachar": despachar, "medir": medir,
                "borrar": borrar, "tanque": guardar_tanque}
    if op in acciones:
        return acciones[op](cx, datos, usuario)
    if op == "historial":
        return historial(cx, datos.get("patente"), datos.get("unidad_id"))
    raise ValueError("No entiendo qué hay que hacer con la urea.")
