"""Fluidos: lo que se compra por litro y se despacha por unidad.

Combustible se controla contra un tercero —la estación manda su listado y
el sistema cruza remitos—. Los fluidos no: el envase es nuestro, así que
no hay nada que cruzar con nadie. Lo que hay que controlar es un stock.

Por eso este módulo no se parece al cruce de combustible, se parece al
depósito de repuestos: **nadie edita el saldo**. El saldo es el resultado
de los movimientos, y son tres:

    entrada   llegó el proveedor y se descargó.
    salida    se despachó a una unidad. Un derrame o un préstamo también
              salen, y también se anotan: con motivo en vez de patente,
              pero se anotan.
    ajuste    alguien midió y no da. Se anota la diferencia con su motivo.

Lo del ajuste es la parte que importa. La merma es real —evaporación,
derrames, lo que se carga y no se anota— y corregir el saldo a mano sería
perder justo el dato que la explica.

El envase no es decoración: un bin de 1.000 litros, un tambor de 205 y un
balde de grasa de 20 kilos no se miran igual. El fluido dice en qué viene
y cuánto entra en uno, y de ahí sale el dibujo —el abierto se vacía, los
sellados se cuentan al lado— y el aviso de cuándo hay que pedir.

Quién puede qué:

    despachar          cualquiera que tenga el módulo. Es el acto de todos
                       los días y anotarlo tiene que costar menos que no
                       anotarlo.
    cargar y medir     el que gestiona: son la plata que entró y la
                       diferencia que hubo.
    tocar el catálogo  el que gestiona: fluidos, envases y proveedores.
"""
import os
import re
from datetime import date

import permisos

# Cuánto mira la pantalla hacia atrás sin que nadie filtre nada.
MOVIMIENTOS_VISIBLES = 300
MESES_POR_UNIDAD = 6

# Lo que se espera de un camión moderno: entre 3% y 6% del gasoil. Fuera
# de esa banda no está mal cargado: está pasando otra cosa, y hay que
# mirarla. Vale para la urea; a los demás fluidos no se les mira eso.
BANDA_GASOIL = (3.0, 6.0)

UNIDADES = ("litros", "kilos")
# En qué viene cada uno. El nombre es el del taller, no el del catálogo
# del proveedor: nadie pide "un IBC", pide un bin.
ENVASES = {
    "bin": "Bin", "tambor": "Tambor", "tacho": "Tacho",
    "balde": "Balde", "tanque": "Tanque",
}
RUBROS = ("combustible", "urea", "aceites", "grasa", "repuestos")


# =====================================================================
# AYUDAS
# =====================================================================
def _exigir_gestor(usuario, que="tocar los fluidos"):
    if not permisos.gestiona(usuario):
        raise PermissionError(f"Solo un encargado o administrador puede {que}.")


def _texto(valor, limite=300):
    texto = " ".join(str(valor or "").split())
    return texto[:limite] or None


def _patente(valor):
    """Como la guarda el resto del sistema: sin espacios ni guiones."""
    return "".join(c for c in str(valor or "").upper() if c.isalnum())


def clave_de(nombre):
    """«Aceite 15W40» → «aceite15w40». Es con lo que lo busca el código."""
    return re.sub(r"[^a-z0-9]", "", str(nombre or "").lower())


def _cantidad(valor, campo="La cantidad", permitir_cero=False):
    if valor in (None, ""):
        raise ValueError(f"Falta {campo.lower()}.")
    try:
        n = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"{campo} tiene que ser un número.") from None
    if n < 0 or (n == 0 and not permitir_cero):
        raise ValueError(f"{campo} tiene que ser mayor que cero.")
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


def _entero(valor, campo, minimo=0):
    if valor in (None, ""):
        return None
    try:
        n = int(float(str(valor).replace(",", ".")))
    except (TypeError, ValueError):
        raise ValueError(f"{campo} tiene que ser un número.") from None
    if n < minimo:
        raise ValueError(f"{campo} no puede ser menor que {minimo}.")
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


def _fluido(cx, fluido_id=None, clave=None):
    """El fluido pedido. Sin decir cuál, el único que haya activo."""
    if fluido_id:
        fila = cx.execute("select * from fluidos where id = %s",
                          (int(fluido_id),)).fetchone()
        if not fila:
            raise ValueError("Ese fluido no existe.")
        return fila
    if clave:
        fila = cx.execute("select * from fluidos where clave = %s",
                          (clave_de(clave),)).fetchone()
        if not fila:
            raise ValueError(f"No hay ningún fluido {clave}.")
        return fila
    filas = cx.execute("select * from fluidos where activo order by orden, id").fetchall()
    if not filas:
        raise ValueError("Todavía no hay fluidos cargados. "
                         "Ejecutar gomeria/32_fluidos.sql en Supabase.")
    if len(filas) > 1:
        raise ValueError("Indicá de qué fluido se trata.")
    return filas[0]


def _como(fluido, cantidad):
    """«140 litros», «12 kilos». Lo que se escribe en los avisos."""
    return f"{cantidad:,.0f}".replace(",", ".") + " " + (fluido["unidad"] or "litros")


def saldo_de(cx, fluido_id):
    fila = cx.execute("select saldo from v_fluidos_saldo where fluido_id = %s",
                      (fluido_id,)).fetchone()
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


def _proveedor(cx, datos):
    """(id, nombre). Se acepta el id de la lista o un nombre escrito."""
    proveedor_id = _entero(datos.get("proveedor_id"), "El proveedor", minimo=1)
    if proveedor_id:
        fila = cx.execute("select id, nombre from proveedores where id = %s",
                          (proveedor_id,)).fetchone()
        if not fila:
            raise ValueError("Ese proveedor no existe.")
        return fila["id"], fila["nombre"]
    nombre = _texto(datos.get("proveedor"), 120)
    if not nombre:
        return None, None
    # Lo escrito a mano se engancha con el que ya está cargado, si está:
    # así "YPF" y "ypf" suman para el mismo.
    fila = cx.execute("select id, nombre from proveedores where lower(nombre) = lower(%s)",
                      (nombre,)).fetchone()
    return (fila["id"], fila["nombre"]) if fila else (None, nombre)


def _registrar(cx, fluido, tipo, cantidad, datos, usuario, **extra):
    campos = {
        "fluido_id": fluido["id"], "tipo": tipo, "fecha": _fecha(datos.get("fecha")),
        "cantidad": cantidad, "nota": _texto(datos.get("nota"), 500),
        "usuario_id": (usuario or {}).get("id"),
        "usuario": (usuario or {}).get("nombre"),
    }
    campos.update(extra)
    columnas = ", ".join(campos)
    huecos = ", ".join(["%s"] * len(campos))
    fila = cx.execute(
        f"insert into fluido_movimientos ({columnas}) values ({huecos}) returning id",
        list(campos.values())).fetchone()
    return fila["id"]


# =====================================================================
# LECTURA
# =====================================================================
# Todo lo que crea 32_fluidos.sql, en el orden en que lo crea. Sirve para
# decir qué falta cuando falta: el error más común no es olvidarse de
# correr el script, es pegarlo cortado y que queden las primeras tablas
# sin las vistas. "Faltan las tablas" no ayuda a ver eso; decir cuáles, sí.
OBJETOS = ("proveedores", "fluidos", "fluido_movimientos",
           "v_fluido_movimientos", "v_fluidos_saldo", "v_fluidos_unidad")


def falta(cx):
    """Los objetos del script que todavía no están. Vacío es que está todo."""
    faltan = []
    for nombre in OBJETOS:
        try:
            cx.execute(f"select 1 from {nombre} limit 1").fetchone()
        except Exception:
            cx.rollback()
            faltan.append(nombre)
    return faltan


def porque_falta(cx):
    """El aviso para la pantalla: qué falta y qué hacer con eso."""
    faltan = falta(cx)
    if not faltan:
        return None
    if len(faltan) == len(OBJETOS):
        return ("Faltan las tablas de fluidos. Ejecutar gomeria/32_fluidos.sql "
                "en el SQL Editor de Supabase.")
    # Algunas están y otras no: el script entró a medias.
    return (f"El script de fluidos entró a medias: falta crear "
            f"{', '.join(faltan)}. Casi siempre es que se cortó al pegarlo. "
            f"Volvé a pegar gomeria/32_fluidos.sql entero{_largo_del_script()} y "
            "corrélo de nuevo: se puede correr las veces que haga falta, "
            "no borra nada.")


def _largo_del_script():
    """«—son 400 líneas—», leído del archivo para que no envejezca."""
    try:
        camino = os.path.join(os.path.dirname(__file__), "32_fluidos.sql")
        with open(camino, encoding="utf-8") as archivo:
            return f" —son {sum(1 for _ in archivo)} líneas—"
    except Exception:
        return ""


def instalado(cx):
    try:
        cx.execute("select 1 from v_fluidos_saldo limit 1").fetchone()
        return True
    except Exception:
        cx.rollback()
        return False


def listar(cx, incluir_inactivos=False):
    return [dict(f) for f in cx.execute(f"""
        select * from v_fluidos_saldo
        {'' if incluir_inactivos else 'where activo'}
        order by orden, nombre""").fetchall()]


def proveedores(cx, incluir_inactivos=False):
    return [dict(p) for p in cx.execute(f"""
        select p.id, p.nombre, p.cuit, p.contacto, p.telefono, p.email,
               p.rubros, p.activo, p.nota,
               (select count(*) from fluido_movimientos m
                where m.proveedor_id = p.id)::int as compras
        from proveedores p
        {'' if incluir_inactivos else 'where p.activo'}
        order by p.activo desc, p.nombre""").fetchall()]


def panel(cx, usuario=None, todo=False):
    """Todo lo que la solapa de fluidos dibuja de una."""
    movimientos = [dict(m) for m in cx.execute("""
        select id, fluido_id, fluido, clave, unidad, envase, tipo, fecha, cantidad,
               delta, unidad_id, patente, interno, km, proveedor_id, proveedor,
               remito, importe, motivo, medido, usuario, nota, creado
        from v_fluido_movimientos
        order by fecha desc, id desc limit %s""", (MOVIMIENTOS_VISIBLES,)).fetchall()]

    por_unidad = [dict(u) for u in cx.execute("""
        select * from v_fluidos_unidad
        where mes >= date_trunc('month', current_date) - make_interval(months => %s)
        order by mes desc, cantidad desc
    """, (MESES_POR_UNIDAD,)).fetchall()]

    return {
        "instalado": True,
        "fluidos": listar(cx, todo),
        "proveedores": proveedores(cx, todo),
        "movimientos": movimientos,
        "por_unidad": por_unidad,
        "banda_gasoil": list(BANDA_GASOIL),
        "envases": ENVASES,
        "rubros": list(RUBROS),
        "unidades": [dict(u) for u in cx.execute("""
            select id, patente, interno, marca, modelo, sucursal, chofer, km_actual
            from unidades where activa order by patente""").fetchall()],
        "puede_gestionar": permisos.gestiona(usuario),
    }


def historial(cx, patente=None, unidad_id=None):
    """Todo lo que cargó una unidad, de lo último a lo primero."""
    patente = _patente(patente)
    if not patente and unidad_id:
        fila = cx.execute("select patente from unidades where id = %s",
                          (unidad_id,)).fetchone()
        patente = fila["patente"] if fila else None
    if not patente:
        raise ValueError("Debe seleccionarse la unidad para ver su historial.")

    movimientos = [dict(m) for m in cx.execute("""
        select m.fecha, m.cantidad, m.km, m.motivo, m.usuario, m.nota,
               f.nombre as fluido, f.clave, f.unidad
        from fluido_movimientos m
        join fluidos f on f.id = m.fluido_id
        where m.tipo = 'salida' and m.patente = %s
        order by m.fecha desc, m.id desc""", (patente,)).fetchall()]
    meses = [dict(m) for m in cx.execute("""
        select * from v_fluidos_unidad where patente = %s order by mes desc, fluido
    """, (patente,)).fetchall()]
    totales = {}
    for m in movimientos:
        totales[m["fluido"]] = round(totales.get(m["fluido"], 0) + float(m["cantidad"]), 2)
    return {"patente": patente, "movimientos": movimientos,
            "meses": meses, "totales": totales}


# =====================================================================
# ESCRITURA
# =====================================================================
def cargar(cx, datos, usuario=None):
    """Entró fluido: llegó el proveedor y se descargó."""
    fluido = _fluido(cx, datos.get("fluido_id"), datos.get("clave"))
    _exigir_gestor(usuario, f"cargar {fluido['nombre']}")
    cantidad = _cantidad(datos.get("cantidad") or datos.get("litros"))
    proveedor_id, proveedor = _proveedor(cx, datos)

    movimiento_id = _registrar(cx, fluido, "entrada", cantidad, datos, usuario,
                               proveedor_id=proveedor_id, proveedor=proveedor,
                               remito=_texto(datos.get("remito"), 60),
                               importe=_numero(datos.get("importe"), "El importe"))
    saldo = saldo_de(cx, fluido["id"])
    return {"ok": True, "id": movimiento_id, "saldo": saldo, "aviso": None}


def despachar(cx, datos, usuario=None):
    """Salió fluido: a una unidad, o a lo que haya pasado."""
    fluido = _fluido(cx, datos.get("fluido_id"), datos.get("clave"))
    cantidad = _cantidad(datos.get("cantidad") or datos.get("litros"))
    unidad_id, patente = _unidad(cx, datos)
    motivo = _texto(datos.get("motivo"), 200)
    if not patente and not motivo:
        raise ValueError("Indicá a qué unidad fue, o el motivo si no fue a "
                         "ninguna (derrame, préstamo, devolución).")

    movimiento_id = _registrar(cx, fluido, "salida", cantidad, datos, usuario,
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

    saldo = saldo_de(cx, fluido["id"])
    estado = cx.execute("select * from v_fluidos_saldo where fluido_id = %s",
                        (fluido["id"],)).fetchone()
    aviso = None
    # Un saldo negativo no se bloquea: el que está despachando tiene la
    # manguera en la mano y lo que pasó, pasó. Lo que sí hace falta es
    # decir que el número dejó de ser creíble y que hay que medir.
    if saldo < 0:
        aviso = (f"Quedaron {_como(fluido, saldo)}. Hubo una entrada que no se "
                 "anotó: medí y cargá la medición.")
    elif estado and estado["estado"] in ("vacio", "critico", "aviso"):
        dias = estado["dias_restantes"]
        aviso = (f"Quedan {_como(fluido, saldo)}"
                 + (f", para unos {dias} días al ritmo de este mes" if dias is not None else "")
                 + f". Hay que pedir {fluido['nombre']}.")
    return {"ok": True, "id": movimiento_id, "saldo": saldo,
            "estado": estado["estado"] if estado else None, "aviso": aviso}


def medir(cx, datos, usuario=None):
    """Se midió lo que hay. La diferencia se anota; el saldo no se pisa."""
    fluido = _fluido(cx, datos.get("fluido_id"), datos.get("clave"))
    _exigir_gestor(usuario, "cargar una medición")
    medido = _cantidad(datos.get("medido") or datos.get("medido_litros"),
                       "Lo medido", permitir_cero=True)
    saldo = saldo_de(cx, fluido["id"])
    diferencia = round(medido - saldo, 2)
    if diferencia == 0:
        return {"ok": True, "id": None, "saldo": saldo, "diferencia": 0,
                "aviso": "Da exacto: no hay nada que ajustar."}

    motivo = _texto(datos.get("motivo"), 200)
    if not motivo:
        raise ValueError("Falta el motivo de la diferencia. Sin eso, el ajuste "
                         "tapa el problema en vez de explicarlo.")

    movimiento_id = _registrar(cx, fluido, "ajuste", diferencia, datos, usuario,
                               motivo=motivo, medido=medido)
    return {"ok": True, "id": movimiento_id, "saldo": medido,
            "diferencia": diferencia,
            "aviso": (f"Se anotó una diferencia de {diferencia:+.0f}. "
                      "El saldo queda en lo que se midió.")}


def borrar(cx, datos, usuario=None):
    """Saca un movimiento cargado por error. El saldo se corrige solo."""
    _exigir_gestor(usuario, "borrar un movimiento")
    fila = cx.execute("delete from fluido_movimientos where id = %s returning fluido_id",
                      (_entero(datos.get("id"), "El movimiento", minimo=1),)).fetchone()
    if not fila:
        raise ValueError("Ese movimiento ya no está.")
    return {"ok": True, "saldo": saldo_de(cx, fila["fluido_id"])}


# =====================================================================
# EL CATÁLOGO: FLUIDOS Y PROVEEDORES
# =====================================================================
def guardar_fluido(cx, datos, usuario=None):
    """Da de alta un fluido o le corrige el envase, la capacidad o el mínimo."""
    _exigir_gestor(usuario)
    nombre = _texto(datos.get("nombre"), 80)
    if not nombre:
        raise ValueError("Falta el nombre del fluido.")
    clave = clave_de(nombre)
    if not clave:
        raise ValueError("Ese nombre no tiene ni una letra ni un número.")
    unidad = (datos.get("unidad") or "litros").strip().lower()
    if unidad not in UNIDADES:
        raise ValueError("Se mide en litros o en kilos.")
    envase = (datos.get("envase") or "tambor").strip().lower()
    if envase not in ENVASES:
        raise ValueError("El envase es bin, tambor, tacho, balde o tanque.")
    capacidad = _cantidad(datos.get("capacidad"), "La capacidad del envase")
    minimo = _numero(datos.get("minimo"), "El mínimo")
    if minimo is not None and minimo > capacidad * 100:
        raise ValueError("Ese mínimo es más grande que cien envases: revisalo.")
    proveedor_id = _entero(datos.get("proveedor_id"), "El proveedor", minimo=1)
    sucursal = (_texto(datos.get("sucursal_codigo"), 3) or "").upper() or None
    activo = bool(datos.get("activo", True))
    orden = _entero(datos.get("orden"), "El orden") or 50
    fluido_id = _entero(datos.get("id"), "El fluido", minimo=1)

    if fluido_id:
        repetido = cx.execute("select 1 from fluidos where clave = %s and id <> %s",
                              (clave, fluido_id)).fetchone()
        if repetido:
            raise ValueError(f"Ya hay otro fluido que se llama {nombre}.")
        fila = cx.execute("""
            update fluidos set nombre=%s, clave=%s, unidad=%s, envase=%s, capacidad=%s,
                   minimo=%s, proveedor_id=%s, sucursal_codigo=%s, activo=%s, orden=%s,
                   nota=%s, actualizado=now()
            where id=%s returning id""",
            (nombre, clave, unidad, envase, capacidad, minimo, proveedor_id, sucursal,
             activo, orden, _texto(datos.get("nota"), 300), fluido_id)).fetchone()
        if not fila:
            raise ValueError("Ese fluido no existe.")
        return {"ok": True, "id": fluido_id}

    if cx.execute("select 1 from fluidos where clave = %s", (clave,)).fetchone():
        raise ValueError(f"{nombre} ya está cargado.")
    fila = cx.execute("""
        insert into fluidos (nombre, clave, unidad, envase, capacidad, minimo,
                             proveedor_id, sucursal_codigo, activo, orden, nota)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
        (nombre, clave, unidad, envase, capacidad, minimo, proveedor_id, sucursal,
         activo, orden, _texto(datos.get("nota"), 300))).fetchone()
    return {"ok": True, "id": fila["id"]}


def borrar_fluido(cx, datos, usuario=None):
    """Saca un fluido que no tiene movimientos.

    El que sí tiene no se borra: se da de baja. Borrarlo dejaría los
    movimientos sin de qué son, y el saldo de un mes pasado sin explicar.
    """
    _exigir_gestor(usuario)
    fluido_id = _entero(datos.get("id"), "El fluido", minimo=1)
    fila = cx.execute("select nombre from fluidos where id = %s", (fluido_id,)).fetchone()
    if not fila:
        raise ValueError("Ese fluido no existe.")
    usados = cx.execute("select count(*) as n from fluido_movimientos where fluido_id = %s",
                        (fluido_id,)).fetchone()["n"]
    if usados:
        raise ValueError(f"{fila['nombre']} tiene {usados} movimiento(s). "
                         "Se puede dar de baja, no borrar.")
    cx.execute("delete from fluidos where id = %s", (fluido_id,))
    return {"ok": True}


def guardar_proveedor(cx, datos, usuario=None):
    """Da de alta un proveedor o lo corrige."""
    _exigir_gestor(usuario, "tocar los proveedores")
    nombre = _texto(datos.get("nombre"), 120)
    if not nombre:
        raise ValueError("Falta el nombre del proveedor.")
    rubros = [r.strip().lower() for r in (datos.get("rubros") or []) if str(r).strip()]
    raros = [r for r in rubros if r not in RUBROS]
    if raros:
        raise ValueError(f"No conozco el rubro {raros[0]}.")
    valores = (nombre, _texto(datos.get("cuit"), 20), _texto(datos.get("contacto"), 120),
               _texto(datos.get("telefono"), 40), _texto(datos.get("email"), 120),
               rubros, bool(datos.get("activo", True)), _texto(datos.get("nota"), 300))
    proveedor_id = _entero(datos.get("id"), "El proveedor", minimo=1)

    if proveedor_id:
        repetido = cx.execute("""select 1 from proveedores
                                 where lower(nombre) = lower(%s) and id <> %s""",
                              (nombre, proveedor_id)).fetchone()
        if repetido:
            raise ValueError(f"Ya hay otro proveedor que se llama {nombre}.")
        fila = cx.execute("""
            update proveedores set nombre=%s, cuit=%s, contacto=%s, telefono=%s,
                   email=%s, rubros=%s, activo=%s, nota=%s
            where id=%s returning id""", (*valores, proveedor_id)).fetchone()
        if not fila:
            raise ValueError("Ese proveedor no existe.")
        return {"ok": True, "id": proveedor_id}

    if cx.execute("select 1 from proveedores where lower(nombre) = lower(%s)",
                  (nombre,)).fetchone():
        raise ValueError(f"{nombre} ya está cargado.")
    fila = cx.execute("""
        insert into proveedores (nombre, cuit, contacto, telefono, email, rubros,
                                 activo, nota)
        values (%s,%s,%s,%s,%s,%s,%s,%s) returning id""", valores).fetchone()
    return {"ok": True, "id": fila["id"]}


def borrar_proveedor(cx, datos, usuario=None):
    """Saca un proveedor al que no se le compró nada."""
    _exigir_gestor(usuario, "tocar los proveedores")
    proveedor_id = _entero(datos.get("id"), "El proveedor", minimo=1)
    fila = cx.execute("select nombre from proveedores where id = %s",
                      (proveedor_id,)).fetchone()
    if not fila:
        raise ValueError("Ese proveedor no existe.")
    compras = cx.execute("""select count(*) as n from fluido_movimientos
                            where proveedor_id = %s""", (proveedor_id,)).fetchone()["n"]
    if compras:
        raise ValueError(f"A {fila['nombre']} se le compró {compras} vez(ces). "
                         "Se puede dar de baja, no borrar.")
    cx.execute("update fluidos set proveedor_id = null where proveedor_id = %s",
               (proveedor_id,))
    cx.execute("delete from proveedores where id = %s", (proveedor_id,))
    return {"ok": True}


# =====================================================================
# LO QUE MIRA LA PANTALLA DE ALERTAS
# =====================================================================
def alertas(cx):
    """Los fluidos que se están por terminar.

    Dos formas de quedarse sin: el saldo bajo y el consumo alto. Las dos
    miran el mismo número desde distintos lados, y por eso las dos avisan.
    Un tambor con 40 litros está bien si se usan dos por mes y es una
    urgencia si se usan dos por semana.

    El que nunca se cargó no avisa: no está vacío, está sin estrenar.
    """
    return [dict(f) for f in cx.execute("""
        select * from v_fluidos_saldo
        where activo and estado not in ('ok', 'sin_cargar')
        order by case estado when 'vacio' then 0 when 'critico' then 1 else 2 end,
                 dias_restantes nulls last, saldo
    """).fetchall()]


# =====================================================================
def aplicar(cx, datos, usuario=None):
    """Punto de entrada de la API."""
    op = (datos.get("op") or "").strip()
    acciones = {"cargar": cargar, "despachar": despachar, "medir": medir,
                "borrar": borrar,
                "fluido": guardar_fluido, "fluido_borrar": borrar_fluido,
                "proveedor": guardar_proveedor, "proveedor_borrar": borrar_proveedor}
    if op in acciones:
        return acciones[op](cx, datos, usuario)
    if op == "historial":
        return historial(cx, datos.get("patente"), datos.get("unidad_id"))
    raise ValueError("No entiendo qué hay que hacer con el fluido.")
