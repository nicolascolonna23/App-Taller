"""Estanterías del depósito de repuestos y la ubicación de cada repuesto.

El plano se arma con estanterías: rectángulos en centímetros, vistos desde
arriba, con pisos y módulos por dentro. Ver 47_estanterias.sql.

Armar el depósito (crear, mover, borrar estanterías) es del permiso
«gestiona». Ubicar un repuesto lo puede hacer cualquiera que entre al
módulo, igual que cargar un movimiento.
"""

import repuestos

FRENTES = ("norte", "sur", "este", "oeste")
# Topes del plano. Un depósito de 200 m de lado ya es mucho; el tope está
# para que un número mal escrito no arme un plano de kilómetros.
MAX_CM = 20000

# Lo que se puede tocar de una estantería, con sus límites. Los mismos que
# pone la base, para contestar con un mensaje y no con un error de Postgres.
LIMITES = {
    "x_cm": (0, MAX_CM, "La posición"),
    "y_cm": (0, MAX_CM, "La posición"),
    "largo_cm": (25, 2000, "El largo"),
    "profundidad_cm": (20, 300, "La profundidad"),
    "alto_cm": (30, 1000, "El alto"),
    "pisos": (1, 15, "La cantidad de pisos"),
    "modulos": (1, 20, "La cantidad de módulos"),
}
POR_DEFECTO = {"x_cm": 0, "y_cm": 0, "largo_cm": 200, "profundidad_cm": 50,
               "alto_cm": 200, "pisos": 4, "modulos": 3}
MAX_LOTE = 60


def _exigir_gestor(usuario):
    if not repuestos.puede_gestionar(usuario):
        raise PermissionError("Solo un encargado o administrador puede armar el depósito.")


def _entero(datos, campo):
    minimo, maximo, nombre = LIMITES[campo]
    valor = datos.get(campo, POR_DEFECTO[campo])
    try:
        valor = int(round(float(valor)))
    except (TypeError, ValueError):
        raise ValueError(f"{nombre} tiene que ser un número.") from None
    if not minimo <= valor <= maximo:
        raise ValueError(f"{nombre} tiene que estar entre {minimo} y {maximo}.")
    return valor


def _id(valor, que="La estantería"):
    try:
        valor = int(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{que} no es válida.") from None
    if valor <= 0:
        raise ValueError(f"{que} no es válida.")
    return valor


def limpiar(datos):
    """La estantería tal como se guarda, o ValueError si algo no cierra."""
    nombre = str(datos.get("nombre") or "").strip()
    if not nombre:
        raise ValueError("Falta el nombre de la estantería.")
    if len(nombre) > 40:
        raise ValueError("El nombre de la estantería es demasiado largo.")
    frente = str(datos.get("frente") or "sur").strip().lower()
    if frente not in FRENTES:
        raise ValueError("El frente tiene que ser norte, sur, este u oeste.")
    limpia = {"nombre": nombre,
              "pasillo": str(datos.get("pasillo") or "").strip()[:40],
              "frente": frente}
    for campo in LIMITES:
        limpia[campo] = _entero(datos, campo)
    return limpia


def listar(cx, usuario):
    estanterias = cx.execute("""
        select id, nombre, pasillo, x_cm, y_cm, largo_cm, profundidad_cm,
               alto_cm, pisos, modulos, frente
        from repuestos_estanterias
        order by pasillo, nombre
    """).fetchall()
    ubicaciones = cx.execute("""
        select a.codigo, u.estanteria_id, u.piso, u.modulo
        from repuestos_ubicaciones u
        join repuestos_articulos a on a.id = u.articulo_id
    """).fetchall()
    return {
        "estanterias": [dict(e) for e in estanterias],
        "ubicaciones": [dict(u) for u in ubicaciones],
        "puede_gestionar": repuestos.puede_gestionar(usuario),
    }


def _insertar(cx, e):
    return cx.execute("""
        insert into repuestos_estanterias
          (nombre, pasillo, x_cm, y_cm, largo_cm, profundidad_cm, alto_cm,
           pisos, modulos, frente)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        returning id
    """, (e["nombre"], e["pasillo"], e["x_cm"], e["y_cm"], e["largo_cm"],
          e["profundidad_cm"], e["alto_cm"], e["pisos"], e["modulos"],
          e["frente"])).fetchone()["id"]


def guardar(cx, datos, usuario):
    _exigir_gestor(usuario)
    e = limpiar(datos)
    if not datos.get("id"):
        return _insertar(cx, e)
    estanteria_id = _id(datos.get("id"))
    # Achicarla no puede dejar repuestos en un casillero que ya no existe.
    fuera = cx.execute("""
        select count(*) as n from repuestos_ubicaciones
        where estanteria_id = %s and (piso > %s or modulo > %s)
    """, (estanteria_id, e["pisos"], e["modulos"])).fetchone()["n"]
    if fuera:
        raise ValueError(f"Hay {fuera} repuesto(s) en pisos o módulos que se "
                         "quitan. Moverlos antes de achicar la estantería.")
    fila = cx.execute("""
        update repuestos_estanterias
        set nombre=%s, pasillo=%s, x_cm=%s, y_cm=%s, largo_cm=%s,
            profundidad_cm=%s, alto_cm=%s, pisos=%s, modulos=%s, frente=%s,
            actualizado_en=now()
        where id=%s returning id
    """, (e["nombre"], e["pasillo"], e["x_cm"], e["y_cm"], e["largo_cm"],
          e["profundidad_cm"], e["alto_cm"], e["pisos"], e["modulos"],
          e["frente"], estanteria_id)).fetchone()
    if not fila:
        raise ValueError("Esa estantería ya no existe.")
    return estanteria_id


def crear_lote(cx, lista, usuario):
    """Un pasillo entero de una vez: todas o ninguna."""
    _exigir_gestor(usuario)
    if not isinstance(lista, list) or not lista:
        raise ValueError("No hay estanterías para crear.")
    if len(lista) > MAX_LOTE:
        raise ValueError(f"No se pueden crear más de {MAX_LOTE} estanterías juntas.")
    limpias = [limpiar(d) for d in lista]
    nombres = [e["nombre"].lower() for e in limpias]
    if len(set(nombres)) != len(nombres):
        raise ValueError("Hay nombres de estantería repetidos.")
    return [_insertar(cx, e) for e in limpias]


def mover(cx, datos, usuario):
    """Solo la posición y el frente: lo que cambia al arrastrar o girar."""
    _exigir_gestor(usuario)
    estanteria_id = _id(datos.get("id"))
    x = _entero(datos, "x_cm")
    y = _entero(datos, "y_cm")
    frente = str(datos.get("frente") or "").strip().lower()
    if frente not in FRENTES:
        raise ValueError("El frente tiene que ser norte, sur, este u oeste.")
    fila = cx.execute("""
        update repuestos_estanterias
        set x_cm=%s, y_cm=%s, frente=%s, actualizado_en=now()
        where id=%s returning id
    """, (x, y, frente, estanteria_id)).fetchone()
    if not fila:
        raise ValueError("Esa estantería ya no existe.")


def borrar(cx, datos, usuario):
    """Borrarla deja sin ubicación a lo que tenía: los repuestos no se tocan."""
    _exigir_gestor(usuario)
    estanteria_id = _id(datos.get("id"))
    fila = cx.execute("delete from repuestos_estanterias where id=%s returning id",
                      (estanteria_id,)).fetchone()
    if not fila:
        raise ValueError("Esa estantería ya no existe.")


def ubicar(cx, datos, usuario):
    codigo = str(datos.get("codigo") or "").strip()
    if not codigo:
        raise ValueError("Falta el repuesto.")
    estanteria_id = _id(datos.get("estanteria_id"))
    try:
        piso = int(datos.get("piso"))
        modulo = int(datos.get("modulo"))
    except (TypeError, ValueError):
        raise ValueError("El piso y el módulo tienen que ser números.") from None

    articulo = cx.execute(
        "select id, activo from repuestos_articulos where codigo=%s", (codigo,)
    ).fetchone()
    if not articulo:
        raise ValueError(f"No existe el repuesto {codigo}.")
    if not articulo["activo"]:
        raise ValueError("Ese repuesto está dado de baja.")
    estanteria = cx.execute(
        "select pisos, modulos from repuestos_estanterias where id=%s",
        (estanteria_id,)).fetchone()
    if not estanteria:
        raise ValueError("Esa estantería ya no existe.")
    if not 1 <= piso <= estanteria["pisos"] or not 1 <= modulo <= estanteria["modulos"]:
        raise ValueError("Ese casillero no existe en la estantería.")

    cx.execute("""
        insert into repuestos_ubicaciones
          (articulo_id, estanteria_id, piso, modulo, usuario_id)
        values (%s,%s,%s,%s,%s)
        on conflict (articulo_id) do update
          set estanteria_id=excluded.estanteria_id, piso=excluded.piso,
              modulo=excluded.modulo, usuario_id=excluded.usuario_id,
              actualizado_en=now()
    """, (articulo["id"], estanteria_id, piso, modulo, usuario["id"]))


def desubicar(cx, datos, usuario):
    codigo = str(datos.get("codigo") or "").strip()
    if not codigo:
        raise ValueError("Falta el repuesto.")
    cx.execute("""
        delete from repuestos_ubicaciones u
        using repuestos_articulos a
        where a.id = u.articulo_id and a.codigo = %s
    """, (codigo,))


def aplicar(cx, datos, usuario):
    op = datos.get("op")
    if op == "estanteria_guardar":
        return {"id": guardar(cx, datos.get("estanteria") or {}, usuario)}
    if op == "estanterias_crear":
        return {"ids": crear_lote(cx, datos.get("estanterias"), usuario)}
    if op == "estanteria_mover":
        mover(cx, datos, usuario)
        return {"ok": True}
    if op == "estanteria_borrar":
        borrar(cx, datos, usuario)
        return {"ok": True}
    if op == "ubicar":
        ubicar(cx, datos, usuario)
        return {"ok": True}
    if op == "desubicar":
        desubicar(cx, datos, usuario)
        return {"ok": True}
    raise ValueError("Operación de estanterías desconocida.")
