"""Órdenes de trabajo: la hoja de una unidad que entra al taller.

Una orden se abre cuando la unidad entra, se le van cargando los trabajos
y los repuestos mientras está adentro, y se cierra cuando sale. Cerrada
queda como está: es el papel que se imprime y se archiva.

Dos clases, la misma tabla (ver 15_ordenes.sql):

    interna   la hizo el taller propio; se carga renglón por renglón.
    externa   la hizo un tercero y de eso hay una factura; se anota
              patente, fecha, número y monto, y nace cerrada.

Lo importante de acá es el enganche con el stock: cada repuesto que se
carga a una orden escribe una Salida en repuestos_movimientos, que es de
donde sale el stock de todo el sistema. Sacar el renglón borra ese
movimiento. No hay una cuenta del depósito y otra del taller: hay una.
"""
from datetime import date

GESTORES = {"admin", "encargado"}

# Lo que se puede escribir en la cabecera de una orden abierta. Está en un
# solo lugar para que agregar un campo sea agregarlo acá y en el SQL.
CAMPOS = ("km", "chofer", "responsable", "taller",
          "solicitado", "diagnostico", "observaciones")


# =====================================================================
# AYUDAS
# =====================================================================
def puede_gestionar(usuario):
    return (usuario or {}).get("rol") in GESTORES


def _exigir_gestor(usuario, que="tocar las órdenes de trabajo"):
    if not puede_gestionar(usuario):
        raise PermissionError(f"Solo un encargado o administrador puede {que}.")


def _texto(valor, limite=2000):
    texto = str(valor or "").strip()
    return texto[:limite] or None


def _patente(valor):
    """Como la guarda el resto del sistema: sin espacios ni guiones."""
    return "".join(c for c in str(valor or "").upper() if c.isalnum())


def _fecha(valor, campo="la fecha"):
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor).strip()[:10])
    except ValueError:
        raise ValueError(f"No se entiende {campo}: {valor}") from None


def _numero(valor, campo, entero=False):
    if valor in (None, ""):
        return None
    try:
        n = int(valor) if entero else float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"{campo} tiene que ser un número.") from None
    if n < 0:
        raise ValueError(f"{campo} no puede ser negativo.")
    return n


def _orden(cx, orden_id, abierta=False):
    """La orden, o el error de por qué no se puede seguir."""
    try:
        orden_id = int(orden_id)
    except (TypeError, ValueError):
        raise ValueError("No se sabe de qué orden se habla.") from None
    fila = cx.execute("select * from ordenes_trabajo where id = %s",
                      (orden_id,)).fetchone()
    if not fila:
        raise ValueError("Esa orden de trabajo no existe.")
    if abierta and fila["estado"] != "abierta":
        raise ValueError(f"La orden {fila['numero']} está {fila['estado']}: "
                         "hay que reabrirla para poder cambiarla.")
    if abierta and fila["tipo"] == "externa":
        raise ValueError("Un servicio externo no lleva renglones: es la factura del tercero.")
    return fila


# =====================================================================
# LECTURA
# =====================================================================
def listar(cx, usuario):
    """Todo lo que la pantalla dibuja de una."""
    ordenes = cx.execute("""
        select * from v_ordenes
        order by estado = 'abierta' desc, fecha desc, numero desc
    """).fetchall()

    resumen = {"abiertas": 0, "cerradas": 0, "externas": 0, "anuladas": 0}
    for o in ordenes:
        if o["estado"] == "anulada":
            resumen["anuladas"] += 1
        elif o["tipo"] == "externa":
            resumen["externas"] += 1
        elif o["estado"] == "abierta":
            resumen["abiertas"] += 1
        else:
            resumen["cerradas"] += 1

    return {
        "ordenes": [dict(o) for o in ordenes],
        "resumen": resumen,
        "unidades": [dict(u) for u in cx.execute("""
            select id, patente, interno, marca, modelo, sucursal, chofer,
                   chasis, km_actual
            from unidades where activa order by patente""").fetchall()],
        # El catálogo con el stock de hoy: el que carga un repuesto tiene
        # que ver cuántos quedan antes de sacarlo, no después.
        "articulos": [dict(a) for a in cx.execute("""
            select codigo, descripcion, rubro, stock_actual
            from v_repuestos_stock where activo
            order by descripcion, codigo""").fetchall()],
        "puede_gestionar": puede_gestionar(usuario),
    }


def ficha(cx, orden_id):
    """Una orden con sus renglones: lo que se imprime."""
    cabecera = cx.execute("select * from v_ordenes where id = %s",
                          (orden_id,)).fetchone()
    if not cabecera:
        raise ValueError("Esa orden de trabajo no existe.")
    return {
        "orden": dict(cabecera),
        "tareas": [dict(t) for t in cx.execute("""
            select id, detalle, horas, importe from ordenes_tareas
            where orden_id = %s order by id""", (orden_id,)).fetchall()],
        "repuestos": [dict(r) for r in cx.execute("""
            select id, articulo_id, movimiento_id, codigo, descripcion,
                   cantidad, precio
            from ordenes_repuestos where orden_id = %s order by id
        """, (orden_id,)).fetchall()],
    }


def historial(cx, patente=None, unidad_id=None):
    """Todo lo que se le hizo a una unidad, de lo último a lo primero.

    Va por patente y no por unidad_id: una unidad que se dio de baja y se
    volvió a cargar cambia de id, pero es el mismo camión y su historia
    tiene que seguir junta.
    """
    patente = _patente(patente)
    if not patente and unidad_id:
        fila = cx.execute("select patente from unidades where id = %s",
                          (unidad_id,)).fetchone()
        patente = fila["patente"] if fila else None
    if not patente:
        raise ValueError("Elegí de qué unidad querés ver el historial.")

    ordenes = [dict(o) for o in cx.execute("""
        select * from v_ordenes where patente = %s
        order by fecha desc, numero desc""", (patente,)).fetchall()]

    return {
        "patente": patente,
        "ordenes": ordenes,
        "total": sum(float(o["total"] or 0) for o in ordenes
                     if o["estado"] != "anulada"),
        # Los trabajos de todas juntos: es la pregunta que se hace de
        # verdad —"¿cuándo le cambiamos la bomba?"— y no se puede
        # contestar abriendo orden por orden.
        "trabajos": [dict(t) for t in cx.execute("""
            select o.numero, o.fecha, o.estado, t.detalle
            from ordenes_tareas t
            join ordenes_trabajo o on o.id = t.orden_id
            where o.patente = %s and o.estado <> 'anulada'
            order by o.fecha desc, o.numero desc, t.id
        """, (patente,)).fetchall()],
        "repuestos": [dict(r) for r in cx.execute("""
            select o.numero, o.fecha, r.codigo, r.descripcion, r.cantidad
            from ordenes_repuestos r
            join ordenes_trabajo o on o.id = r.orden_id
            where o.patente = %s and o.estado <> 'anulada'
            order by o.fecha desc, o.numero desc, r.id
        """, (patente,)).fetchall()],
    }


# =====================================================================
# ESCRITURA — la cabecera
# =====================================================================
def _unidad(cx, datos):
    """La unidad de la orden. Devuelve (id, patente, fila o None)."""
    unidad_id = datos.get("unidad_id") or None
    patente = _patente(datos.get("patente"))
    fila = None
    if unidad_id:
        fila = cx.execute("select * from unidades where id = %s",
                          (unidad_id,)).fetchone()
        if not fila:
            raise ValueError("Esa unidad no existe.")
        patente = fila["patente"]
    elif patente:
        fila = cx.execute("select * from unidades where patente = %s",
                          (patente,)).fetchone()
        unidad_id = fila["id"] if fila else None
    if not patente:
        raise ValueError("Falta la patente de la unidad.")
    return unidad_id, patente, fila


def abrir(cx, datos, usuario):
    """Abre una orden interna. La unidad entró al taller."""
    _exigir_gestor(usuario, "abrir una orden de trabajo")
    unidad_id, patente, unidad = _unidad(cx, datos)

    # Una unidad con una orden abierta no puede tener otra: si no, los
    # repuestos de un mismo trabajo terminan repartidos en dos hojas.
    abierta = cx.execute("""
        select numero from ordenes_trabajo
        where patente = %s and estado = 'abierta' and tipo = 'interna'
    """, (patente,)).fetchone()
    if abierta:
        raise ValueError(f"{patente} ya tiene la orden {abierta['numero']} abierta. "
                         "Cerrala antes de abrir otra.")

    km = _numero(datos.get("km"), "El kilometraje")
    if km is None and unidad:
        km = unidad["km_actual"]

    fila = cx.execute("""
        insert into ordenes_trabajo
          (tipo, estado, unidad_id, patente, km, fecha, chofer, responsable,
           solicitado, observaciones, usuario_id, usuario)
        values ('interna','abierta',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        returning id, numero
    """, (unidad_id, patente, km,
          _fecha(datos.get("fecha"), "la fecha de entrada") or date.today(),
          _texto(datos.get("chofer"), 120) or (unidad and unidad["chofer"]),
          _texto(datos.get("responsable"), 120),
          _texto(datos.get("solicitado")),
          _texto(datos.get("observaciones")),
          (usuario or {}).get("id"), (usuario or {}).get("nombre"))).fetchone()
    return {"ok": True, "id": fila["id"], "numero": fila["numero"]}


def guardar(cx, datos, usuario):
    """Cambia la cabecera de una orden abierta."""
    _exigir_gestor(usuario, "cambiar una orden de trabajo")
    orden = _orden(cx, datos.get("id"), abierta=True)

    valores = {
        "km": _numero(datos.get("km"), "El kilometraje"),
        "chofer": _texto(datos.get("chofer"), 120),
        "responsable": _texto(datos.get("responsable"), 120),
        "taller": _texto(datos.get("taller"), 120),
        "solicitado": _texto(datos.get("solicitado")),
        "diagnostico": _texto(datos.get("diagnostico")),
        "observaciones": _texto(datos.get("observaciones")),
    }
    # Solo lo que vino en el pedido: la pantalla puede mandar un campo o
    # todos, y lo que no manda no se borra.
    cambios = {c: v for c, v in valores.items() if c in datos}
    if not cambios:
        return {"ok": True}
    sets = ", ".join(f"{c} = %s" for c in cambios)
    cx.execute(f"update ordenes_trabajo set {sets} where id = %s",
               (*cambios.values(), orden["id"]))
    return {"ok": True}


def cerrar(cx, datos, usuario):
    """La unidad sale del taller. De acá en más la orden no se toca."""
    _exigir_gestor(usuario, "cerrar una orden de trabajo")
    orden = _orden(cx, datos.get("id"))
    if orden["estado"] == "cerrada":
        raise ValueError(f"La orden {orden['numero']} ya está cerrada.")
    if orden["estado"] == "anulada":
        raise ValueError(f"La orden {orden['numero']} está anulada.")

    vacia = not cx.execute("""
        select 1 from ordenes_tareas where orden_id = %s
        union all
        select 1 from ordenes_repuestos where orden_id = %s limit 1
    """, (orden["id"], orden["id"])).fetchone()
    if vacia and not orden["diagnostico"]:
        raise ValueError("La orden no tiene ni un trabajo ni un repuesto cargado. "
                         "Cargá lo que se hizo antes de cerrarla.")

    cierre = _fecha(datos.get("fecha_cierre"), "la fecha de cierre") or date.today()
    if cierre < orden["fecha"]:
        raise ValueError("La orden no puede cerrarse antes de la fecha en que se abrió.")

    cx.execute("""
        update ordenes_trabajo
        set estado = 'cerrada', fecha_cierre = %s, cerrada_por = %s
        where id = %s
    """, (cierre, (usuario or {}).get("nombre"), orden["id"]))

    # El kilometraje que quedó en la orden es el último que se le leyó a la
    # unidad: si es mayor que el del maestro, el maestro se pone al día.
    if orden["km"] and orden["unidad_id"]:
        cx.execute("""
            update unidades set km_actual = %s
            where id = %s and (km_actual is null or km_actual < %s)
        """, (orden["km"], orden["unidad_id"], orden["km"]))

    return {"ok": True, "numero": orden["numero"], "fecha_cierre": cierre.isoformat()}


def reabrir(cx, datos, usuario):
    """Se cerró de más. Solo un admin, y nunca una externa."""
    if (usuario or {}).get("rol") != "admin":
        raise PermissionError("Solo un administrador puede reabrir una orden cerrada.")
    orden = _orden(cx, datos.get("id"))
    if orden["tipo"] == "externa":
        raise ValueError("Un servicio externo no se reabre: se anula y se carga de nuevo.")
    if orden["estado"] != "cerrada":
        raise ValueError("Esa orden no está cerrada.")
    cx.execute("""update ordenes_trabajo
                  set estado = 'abierta', fecha_cierre = null, cerrada_por = null
                  where id = %s""", (orden["id"],))
    return {"ok": True}


def anular(cx, datos, usuario):
    """La orden no va. Los repuestos vuelven al estante."""
    _exigir_gestor(usuario, "anular una orden de trabajo")
    orden = _orden(cx, datos.get("id"))
    if orden["estado"] == "anulada":
        return {"ok": True}

    # Anular sin devolver el stock dejaría repuestos descontados por un
    # trabajo que no existió.
    devueltos = _devolver_stock(cx, orden["id"])
    cx.execute("""update ordenes_trabajo set estado = 'anulada',
                  observaciones = coalesce(observaciones || ' · ', '') || %s
                  where id = %s""",
               (f"Anulada por {(usuario or {}).get('nombre') or 'alguien'} "
                f"el {date.today().isoformat()}.", orden["id"]))
    return {"ok": True, "devueltos": devueltos}


def borrar(cx, datos, usuario):
    """Saca del medio una orden cargada por error. Solo un admin."""
    if (usuario or {}).get("rol") != "admin":
        raise PermissionError("Solo un administrador puede borrar una orden.")
    orden = _orden(cx, datos.get("id"))
    _devolver_stock(cx, orden["id"])
    cx.execute("delete from ordenes_trabajo where id = %s", (orden["id"],))
    return {"ok": True}


# =====================================================================
# ESCRITURA — los renglones
# =====================================================================
def tarea_agregar(cx, datos, usuario):
    _exigir_gestor(usuario, "cargar trabajos")
    orden = _orden(cx, datos.get("id"), abierta=True)
    detalle = _texto(datos.get("detalle"), 500)
    if not detalle:
        raise ValueError("Escribí qué se le hizo.")
    fila = cx.execute("""
        insert into ordenes_tareas (orden_id, detalle, horas, importe)
        values (%s,%s,%s,%s) returning id
    """, (orden["id"], detalle,
          _numero(datos.get("horas"), "Las horas"),
          _numero(datos.get("importe"), "El importe"))).fetchone()
    return {"ok": True, "id": fila["id"]}


def tarea_borrar(cx, datos, usuario):
    _exigir_gestor(usuario, "sacar trabajos")
    orden = _orden(cx, datos.get("id"), abierta=True)
    fila = cx.execute("""delete from ordenes_tareas
                         where id = %s and orden_id = %s returning id""",
                      (datos.get("tarea_id"), orden["id"])).fetchone()
    if not fila:
        raise ValueError("Ese trabajo ya no está en la orden.")
    return {"ok": True}


def repuesto_agregar(cx, datos, usuario):
    """Carga un repuesto a la orden y lo saca del depósito.

    Las dos cosas son una sola: el renglón de la orden y la Salida de
    stock se escriben juntos, y el renglón se queda con el número del
    movimiento para poder deshacerlo entero.
    """
    _exigir_gestor(usuario, "cargar repuestos")
    orden = _orden(cx, datos.get("id"), abierta=True)

    cantidad = _numero(datos.get("cantidad"), "La cantidad", entero=True)
    if not cantidad:
        raise ValueError("La cantidad tiene que ser mayor que cero.")
    precio = _numero(datos.get("precio"), "El precio")

    codigo = str(datos.get("codigo") or "").strip()
    articulo_id = movimiento_id = None
    descripcion = _texto(datos.get("descripcion"), 300)

    if codigo:
        articulo = cx.execute("""
            select a.id, a.codigo, a.descripcion, a.activo,
                   coalesce(v.stock_actual, 0) as stock
            from repuestos_articulos a
            left join v_repuestos_stock v on v.id = a.id
            where a.codigo = %s""", (codigo,)).fetchone()
        if not articulo:
            raise ValueError(f"No existe el repuesto {codigo}.")
        if not articulo["activo"]:
            raise ValueError(f"El repuesto {codigo} está dado de baja.")
        articulo_id = articulo["id"]
        descripcion = descripcion or articulo["descripcion"]

        # La Salida de stock. Va con la patente y el número de orden en las
        # observaciones para que en la pantalla de repuestos se entienda de
        # dónde salió sin tener que venir hasta acá.
        fila = cx.execute("""
            insert into repuestos_movimientos
              (articulo_id, fecha, tipo, cantidad, patente, observaciones, usuario_id)
            values (%s, current_date, 'Salida', %s, %s, %s, %s)
            returning id
        """, (articulo_id, cantidad, orden["patente"],
              f"OT {orden['numero']}", (usuario or {}).get("id"))).fetchone()
        movimiento_id = fila["id"]
        quedan = int(articulo["stock"]) - cantidad
    else:
        # Sin código: algo que se compró para este trabajo y no está en el
        # depósito. Se anota en la orden pero no toca el stock.
        if not descripcion:
            raise ValueError("Elegí un repuesto del depósito o escribí qué se puso.")
        quedan = None

    renglon = cx.execute("""
        insert into ordenes_repuestos
          (orden_id, articulo_id, movimiento_id, codigo, descripcion, cantidad, precio)
        values (%s,%s,%s,%s,%s,%s,%s) returning id
    """, (orden["id"], articulo_id, movimiento_id, codigo or None,
          descripcion, cantidad, precio)).fetchone()
    return {"ok": True, "id": renglon["id"], "stock": quedan}


def repuesto_borrar(cx, datos, usuario):
    """Saca el renglón y devuelve el repuesto al estante."""
    _exigir_gestor(usuario, "sacar repuestos")
    orden = _orden(cx, datos.get("id"), abierta=True)
    fila = cx.execute("""delete from ordenes_repuestos
                         where id = %s and orden_id = %s
                         returning movimiento_id""",
                      (datos.get("repuesto_id"), orden["id"])).fetchone()
    if not fila:
        raise ValueError("Ese repuesto ya no está en la orden.")
    if fila["movimiento_id"]:
        cx.execute("delete from repuestos_movimientos where id = %s",
                   (fila["movimiento_id"],))
    return {"ok": True}


def _devolver_stock(cx, orden_id):
    """Borra las salidas de stock de una orden. Devuelve cuántas eran."""
    filas = cx.execute("""
        select movimiento_id from ordenes_repuestos
        where orden_id = %s and movimiento_id is not null""",
        (orden_id,)).fetchall()
    for f in filas:
        cx.execute("delete from repuestos_movimientos where id = %s",
                   (f["movimiento_id"],))
    cx.execute("update ordenes_repuestos set movimiento_id = null where orden_id = %s",
               (orden_id,))
    return len(filas)


# =====================================================================
# SERVICIOS EXTERNOS
# =====================================================================
def externa(cx, datos, usuario):
    """El trabajo lo hizo un tercero: queda la factura.

    Nace cerrada porque no hay nada que ir cargando: lo que pasó ya pasó y
    lo único que importa es que quede en la historia de la unidad.
    """
    _exigir_gestor(usuario, "cargar un servicio externo")
    unidad_id, patente, unidad = _unidad(cx, datos)

    fecha = _fecha(datos.get("fecha"), "la fecha del servicio") or date.today()
    monto = _numero(datos.get("monto"), "El monto")
    if monto is None:
        raise ValueError("Falta el monto de la factura.")
    factura = _texto(datos.get("factura"), 60)
    if not factura:
        raise ValueError("Falta el número de factura.")

    # La misma factura dos veces es un error de carga, no dos servicios.
    repetida = cx.execute("""
        select numero from ordenes_trabajo
        where tipo = 'externa' and factura = %s and patente = %s
              and estado <> 'anulada'""", (factura, patente)).fetchone()
    if repetida:
        raise ValueError(f"La factura {factura} de {patente} ya está cargada "
                         f"en la orden {repetida['numero']}.")

    km = _numero(datos.get("km"), "El kilometraje")
    if km is None and unidad:
        km = unidad["km_actual"]

    fila = cx.execute("""
        insert into ordenes_trabajo
          (tipo, estado, unidad_id, patente, km, fecha, fecha_cierre,
           taller, factura, monto, solicitado, observaciones,
           usuario_id, usuario, cerrada_por)
        values ('externa','cerrada',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        returning id, numero
    """, (unidad_id, patente, km, fecha, fecha,
          _texto(datos.get("taller"), 120), factura, monto,
          _texto(datos.get("solicitado")), _texto(datos.get("observaciones")),
          (usuario or {}).get("id"), (usuario or {}).get("nombre"),
          (usuario or {}).get("nombre"))).fetchone()
    return {"ok": True, "id": fila["id"], "numero": fila["numero"]}


# =====================================================================
def aplicar(cx, datos, usuario):
    """Punto de entrada de la API."""
    op = (datos.get("op") or "").strip()
    acciones = {
        "abrir": abrir, "guardar": guardar, "cerrar": cerrar,
        "reabrir": reabrir, "anular": anular, "borrar": borrar,
        "tarea_agregar": tarea_agregar, "tarea_borrar": tarea_borrar,
        "repuesto_agregar": repuesto_agregar, "repuesto_borrar": repuesto_borrar,
        "externa": externa,
    }
    if op in acciones:
        return acciones[op](cx, datos, usuario)
    if op == "ficha":
        return ficha(cx, datos.get("id"))
    if op == "historial":
        return historial(cx, datos.get("patente"), datos.get("unidad_id"))
    raise ValueError("No entiendo qué hay que hacer con la orden.")
