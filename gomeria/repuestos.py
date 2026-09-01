"""Persistencia del módulo de repuestos en PostgreSQL."""

from datetime import date


GESTORES = {"admin", "encargado"}
TIPOS = {"Entrada", "Salida", "Ajuste"}


def puede_gestionar(usuario):
    return usuario.get("rol") in GESTORES


def _exigir_gestor(usuario):
    if not puede_gestionar(usuario):
        raise PermissionError("Solo un encargado o administrador puede hacer ese cambio.")


def listar(cx, usuario):
    articulos = cx.execute("""
        select codigo, descripcion, rubro, codigo_interno, stock_minimo, activo
        from repuestos_articulos
        order by descripcion, codigo
    """).fetchall()
    movimientos = cx.execute("""
        select m.id, m.fecha, m.tipo, m.cantidad, m.patente, m.observaciones,
               extract(epoch from m.creado_en) * 1000 as ts,
               a.codigo, a.descripcion
        from repuestos_movimientos m
        join repuestos_articulos a on a.id = m.articulo_id
        order by m.fecha desc, m.id desc
    """).fetchall()
    return {
        "arts": [{
            "codigo": a["codigo"],
            "descripcion": a["descripcion"],
            "rubro": a["rubro"],
            "interno": a["codigo_interno"] or "",
            "anterior": "",
            "minimo": a["stock_minimo"],
            "activo": a["activo"],
        } for a in articulos],
        "movs": [{
            "id": m["id"],
            "ts": int(m["ts"] or 0),
            "fecha": str(m["fecha"]),
            "codigo": m["codigo"],
            "desc": m["descripcion"],
            "patente": m["patente"] or "",
            "tipo": m["tipo"],
            "cantidad": m["cantidad"],
            "obs": m["observaciones"] or "",
        } for m in movimientos],
        "puede_gestionar": puede_gestionar(usuario),
        "modo": "Supabase",
    }


def _texto(datos, campo, obligatorio=False):
    valor = str(datos.get(campo) or "").strip()
    if obligatorio and not valor:
        raise ValueError(f"Falta {campo}.")
    return valor


def crear_movimiento(cx, datos, usuario):
    codigo = _texto(datos, "codigo", True)
    tipo = _texto(datos, "tipo", True)
    if tipo not in TIPOS:
        raise ValueError("El tipo de movimiento no es válido.")
    try:
        cantidad = int(datos.get("cantidad"))
    except (TypeError, ValueError):
        raise ValueError("La cantidad tiene que ser un número entero.") from None
    if not cantidad:
        raise ValueError("La cantidad tiene que ser distinta de cero.")
    if tipo != "Ajuste" and cantidad < 0:
        raise ValueError("En entradas y salidas la cantidad va en positivo.")

    fecha = _texto(datos, "fecha", True)
    try:
        date.fromisoformat(fecha)
    except ValueError:
        raise ValueError("La fecha no es válida.") from None
    patente = "".join(ch for ch in _texto(datos, "patente").upper() if ch.isalnum())
    if tipo == "Salida" and not patente:
        raise ValueError("Cargá la patente de la unidad que recibe el repuesto.")

    articulo = cx.execute(
        "select id, activo from repuestos_articulos where codigo = %s", (codigo,)
    ).fetchone()
    if not articulo:
        raise ValueError(f"No existe el repuesto {codigo}.")
    if not articulo["activo"]:
        raise ValueError("Ese repuesto está dado de baja.")

    fila = cx.execute("""
        insert into repuestos_movimientos
          (articulo_id, fecha, tipo, cantidad, patente, observaciones, usuario_id)
        values (%s,%s,%s,%s,%s,%s,%s)
        returning id
    """, (articulo["id"], fecha, tipo, cantidad, patente or None,
          _texto(datos, "obs") or None, usuario["id"])).fetchone()
    return fila["id"]


def guardar_articulo(cx, datos, usuario):
    _exigir_gestor(usuario)
    original = _texto(datos, "original")
    codigo = _texto(datos, "codigo", True)
    descripcion = _texto(datos, "descripcion", True)
    rubro = _texto(datos, "rubro") or "Sin rubro"
    interno = _texto(datos, "interno") or None
    try:
        minimo = int(datos.get("minimo") or 0)
    except (TypeError, ValueError):
        raise ValueError("El stock mínimo tiene que ser un número entero.") from None
    if minimo < 0:
        raise ValueError("El stock mínimo no puede ser negativo.")

    if original:
        fila = cx.execute("""
            update repuestos_articulos
            set codigo=%s, descripcion=%s, rubro=%s, codigo_interno=%s,
                stock_minimo=%s, actualizado_en=now()
            where codigo=%s returning id
        """, (codigo, descripcion, rubro, interno, minimo, original)).fetchone()
        if not fila:
            raise ValueError(f"No existe el repuesto {original}.")
    else:
        cx.execute("""
            insert into repuestos_articulos
              (codigo, descripcion, rubro, codigo_interno, stock_minimo)
            values (%s,%s,%s,%s,%s)
        """, (codigo, descripcion, rubro, interno, minimo))


def cambiar_estado(cx, datos, usuario):
    _exigir_gestor(usuario)
    codigo = _texto(datos, "codigo", True)
    activo = datos.get("activo") is True
    fila = cx.execute("""
        update repuestos_articulos set activo=%s, actualizado_en=now()
        where codigo=%s returning id
    """, (activo, codigo)).fetchone()
    if not fila:
        raise ValueError(f"No existe el repuesto {codigo}.")


def borrar_articulo(cx, datos, usuario):
    _exigir_gestor(usuario)
    codigo = _texto(datos, "codigo", True)
    fila = cx.execute("""
        delete from repuestos_articulos a
        where a.codigo=%s
          and not exists (select 1 from repuestos_movimientos m where m.articulo_id=a.id)
        returning id
    """, (codigo,)).fetchone()
    if not fila:
        raise ValueError("No se puede eliminar: el repuesto no existe o tiene movimientos.")


def borrar_movimiento(cx, datos, usuario):
    _exigir_gestor(usuario)
    try:
        movimiento_id = int(datos.get("id"))
    except (TypeError, ValueError):
        raise ValueError("El movimiento no es válido.") from None
    fila = cx.execute(
        "delete from repuestos_movimientos where id=%s returning id", (movimiento_id,)
    ).fetchone()
    if not fila:
        raise ValueError("No existe ese movimiento.")


def aplicar(cx, datos, usuario):
    op = datos.get("op")
    if op == "movimiento_crear":
        return {"id": crear_movimiento(cx, datos.get("movimiento") or {}, usuario)}
    if op == "movimientos_crear":
        movimientos = datos.get("movimientos") or []
        if not isinstance(movimientos, list) or not movimientos:
            raise ValueError("No hay movimientos para guardar.")
        if len(movimientos) > 200:
            raise ValueError("La carga no puede superar los 200 movimientos.")
        return {"ids": [crear_movimiento(cx, m, usuario) for m in movimientos]}
    if op == "movimiento_borrar":
        borrar_movimiento(cx, datos, usuario)
        return {"ok": True}
    if op == "articulo_guardar":
        guardar_articulo(cx, datos.get("articulo") or {}, usuario)
        return {"ok": True}
    if op == "articulo_estado":
        cambiar_estado(cx, datos, usuario)
        return {"ok": True}
    if op == "articulo_borrar":
        borrar_articulo(cx, datos, usuario)
        return {"ok": True}
    raise ValueError("Operación de repuestos desconocida.")
