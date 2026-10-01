"""El circuito de recapado: lo que sale, lo que vuelve y lo que no volvió.

Todas las semanas el gomero se lleva un lote de gomas a recapar y trae el
de la semana anterior. Antes cada mitad se cargaba por separado —estado
'recapado' al salir, desgaste.recapar() al volver— y las dos no se
hablaban. Por eso no se podía contestar la única pregunta que importa: si
se llevó doce y trajo diez, cuáles son las dos que faltan.

Acá el envío es una entidad con sus renglones, así salida y vuelta quedan
emparejadas.

La vida de la cubierta no se cierra al salir: la cierra desgaste.recapar
cuando vuelve, junto con abrir la nueva. Acá solo se mueve el estado.
"""
import uuid

import base
import desgaste
import permisos

TOPE_POR_DEFECTO = 3


def _exigir_gestor(usuario, que="mover el recapado"):
    if not permisos.gestiona(usuario):
        raise PermissionError(f"No tiene permiso para {que}.")


def _texto(valor, limite=120):
    t = " ".join(str(valor or "").split())
    return t[:limite] or None


def tope(cx):
    """Cuántas veces se puede recapar una carcasa."""
    try:
        fila = cx.execute("select recapados_maximo from parametros").fetchone()
        return int(fila["recapados_maximo"]) if fila else TOPE_POR_DEFECTO
    except Exception:
        # Sin 43_recapado.sql corrido se usa el de siempre.
        cx.rollback()
        return TOPE_POR_DEFECTO


# =====================================================================
# LECTURA
# =====================================================================
def listar(cx, usuario=None):
    """Todo lo que la pantalla dibuja de una."""
    return {
        "envios": [dict(e) for e in cx.execute(
            "select * from v_recapado_envios limit 200").fetchall()],
        "afuera": [dict(a) for a in cx.execute(
            "select * from v_recapado_afuera").fetchall()],
        # Las que se pueden mandar: están en el depósito y les queda vida.
        "candidatas": [dict(c) for c in cx.execute("""
            select c.id, c.codigo, c.marca, c.modelo, c.medida, c.recapados,
                   c.remanente_mm, c.codigo_provisorio
            from cubiertas c
            where c.estado = 'stock' and c.recapados < %s
            order by c.remanente_mm nulls last, c.codigo""",
            (tope(cx),)).fetchall()],
        "tope": tope(cx),
        "recapadores": [r["recapador"] for r in cx.execute("""
            select recapador, max(fecha) as ultima from recapado_envios
            where estado <> 'anulado'
            group by recapador order by ultima desc limit 10""").fetchall()],
        "puede_gestionar": permisos.gestiona(usuario),
    }


def uno(cx, envio_id):
    """Un envío con sus renglones. Es lo que se imprime en el remito."""
    envio = cx.execute("select * from v_recapado_envios where id = %s",
                       (envio_id,)).fetchone()
    if not envio:
        raise ValueError("Ese envío no existe.")
    renglones = cx.execute("""
        select r.*, c.codigo, c.marca, c.modelo, c.medida, c.codigo_provisorio
        from recapado_renglones r
        join cubiertas c on c.id = r.cubierta_id
        where r.envio_id = %s
        order by c.codigo""", (envio_id,)).fetchall()
    return {"envio": dict(envio), "renglones": [dict(r) for r in renglones]}


# =====================================================================
# ESCRITURA
# =====================================================================
def _numero(cx):
    """El próximo número, bloqueando el contador.

    No se usa max(numero)+1: sin bloqueo, dos cargas simultáneas leen el
    mismo máximo y escriben el mismo número.
    """
    fila = cx.execute("""
        update recapado_contador set ultimo = ultimo + 1
        where unica returning ultimo""").fetchone()
    if not fila:
        raise ValueError("Falta correr gomeria/43_recapado.sql en la base.")
    return fila["ultimo"]


def enviar(cx, datos, usuario=None):
    """Arma el envío con las gomas elegidas y las manda al recapador.

    Devuelve el envío listo para imprimir: el remito sale de acá, no se
    carga después. La salida es el único momento del circuito en que el
    dato se tiene antes que el papel, así que el papel lo hace el sistema.
    """
    _exigir_gestor(usuario, "enviar cubiertas a recapar")

    recapador = _texto(datos.get("recapador"))
    if not recapador:
        raise ValueError("Indicar a qué recapador se mandan.")

    ids = [int(x) for x in (datos.get("cubiertas") or []) if str(x).strip()]
    if not ids:
        raise ValueError("Elegir al menos una cubierta.")
    if len(set(ids)) != len(ids):
        raise ValueError("Hay una cubierta repetida en el remito.")

    limite = tope(cx)
    elegidas = cx.execute("""
        select id, codigo, estado, recapados, remanente_mm
        from cubiertas where id = any(%s)""", (ids,)).fetchall()
    porid = {c["id"]: c for c in elegidas}

    for cubierta_id in ids:
        c = porid.get(cubierta_id)
        if not c:
            raise ValueError("Una de las cubiertas elegidas no existe.")
        # Una goma montada está puesta en un camión: no se la puede
        # mandar a recapar sin bajarla primero.
        if c["estado"] != "stock":
            raise ValueError(
                f"La cubierta {c['codigo']} está en «{c['estado']}» y no en el "
                f"depósito. Solo se manda a recapar lo que está en stock.")
        if (c["recapados"] or 0) >= limite:
            raise ValueError(
                f"La cubierta {c['codigo']} ya lleva {c['recapados']} recapados "
                f"y el máximo es {limite}. Esa carcasa no va más.")

    numero = _numero(cx)
    envio_id = f"REC-{numero:05d}"
    cx.execute("""
        insert into recapado_envios (id, numero, recapador, fecha, nota, usuario)
        values (%s, %s, %s, coalesce(%s::date, current_date), %s, %s)""",
        (envio_id, numero, recapador, _texto(datos.get("fecha"), 10),
         _texto(datos.get("nota"), 300), (usuario or {}).get("nombre")))

    grupo = uuid.uuid4()
    for cubierta_id in ids:
        c = porid[cubierta_id]
        cx.execute("""
            insert into recapado_renglones
              (envio_id, cubierta_id, remanente_salida_mm, recapados_al_salir)
            values (%s, %s, %s, %s)""",
            (envio_id, cubierta_id, c["remanente_mm"], c["recapados"] or 0))
        cx.execute("update cubiertas set estado = 'recapado' where id = %s",
                   (cubierta_id,))
        base._log(cx, grupo, "recapado", cubierta_id=cubierta_id,
                  usuario=(usuario or {}).get("nombre"),
                  nota=f"Enviada a recapar a {recapador} · remito {envio_id}")

    return uno(cx, envio_id)


def recibir(cx, datos, usuario=None):
    """Registra lo que volvió del recapador.

    Cada goma que vuelve pasa por desgaste.recapar(), que es quien cierra
    la vida anterior y abre la nueva con su banda y su costo. Acá no se
    duplica nada de eso: se emparejan los renglones y se llama.
    """
    _exigir_gestor(usuario, "recibir cubiertas del recapador")

    envio_id = _texto(datos.get("envio_id"), 20)
    envio = cx.execute("select * from recapado_envios where id = %s",
                       (envio_id,)).fetchone()
    if not envio:
        raise ValueError("Ese envío no existe.")
    if envio["estado"] == "anulado":
        raise ValueError("Ese envío está anulado.")

    vueltas = datos.get("vueltas") or []
    if not vueltas:
        raise ValueError("Marcar al menos una cubierta.")

    abiertos = {r["cubierta_id"]: r for r in cx.execute("""
        select * from recapado_renglones
        where envio_id = %s and estado = 'enviada'""", (envio_id,)).fetchall()}

    hecho = []
    for v in vueltas:
        cubierta_id = int(v.get("cubierta_id") or 0)
        renglon = abiertos.get(cubierta_id)
        if not renglon:
            raise ValueError("Esa cubierta no está pendiente en este envío.")

        if v.get("rechazada"):
            # El recapador dice que la carcasa no va. No vuelve al stock:
            # se da de baja con el motivo, que es lo que pasó de verdad.
            motivo = _texto(v.get("motivo"), 300) or "Rechazada por el recapador"
            cx.execute("""update recapado_renglones
                             set estado = 'rechazada', fecha_vuelta = current_date,
                                 motivo = %s
                           where id = %s""", (motivo, renglon["id"]))
            base.cambiar_estado_cubierta(
                cx, cubierta_id, "baja",
                usuario=(usuario or {}).get("nombre"),
                nota=f"{motivo} · remito {envio_id}")
            hecho.append({"cubierta_id": cubierta_id, "estado": "rechazada"})
            continue

        # Vuelve con banda nueva: empieza una vida.
        desgaste.recapar(
            cx, cubierta_id,
            marca=v.get("marca") or envio["recapador"],
            banda=v.get("banda"),
            proveedor=envio["recapador"],
            costo=v.get("costo"),
            inicial_mm=v.get("inicial_mm"),
            usuario=(usuario or {}).get("nombre"),
            nota=f"Remito {envio_id}")
        costo = v.get("costo")
        cx.execute("""update recapado_renglones
                         set estado = 'volvio', fecha_vuelta = current_date,
                             costo = %s
                       where id = %s""",
                   (float(costo) if costo not in (None, "") else None,
                    renglon["id"]))
        hecho.append({"cubierta_id": cubierta_id, "estado": "volvio"})

    # La factura del recapador se anota en el envío, no en cada goma: es
    # una sola factura para todo el lote.
    factura = _texto(datos.get("factura"), 60)
    if factura:
        cx.execute("update recapado_envios set factura = %s where id = %s",
                   (factura, envio_id))

    # El envío se cierra solo cuando no queda nada pendiente. Mientras
    # falte una goma, sigue abierto y aparece en «qué hay afuera»: es lo
    # que hace que lo que no volvió no se pierda de vista.
    quedan = cx.execute("""
        select count(*) as n from recapado_renglones
        where envio_id = %s and estado = 'enviada'""", (envio_id,)).fetchone()["n"]
    if not quedan:
        cx.execute("""update recapado_envios
                         set estado = 'cerrado', fecha_vuelta = current_date
                       where id = %s""", (envio_id,))

    return {"ok": True, "hecho": hecho, "pendientes": quedan,
            **uno(cx, envio_id)}


def anular(cx, datos, usuario=None):
    """Deshace un envío que se cargó mal. Las gomas vuelven al depósito.

    Solo se puede si no volvió ninguna: una vez que una goma se recapó,
    su vida nueva ya está abierta y deshacer el envío no la desharía.
    """
    _exigir_gestor(usuario, "anular un envío")

    envio_id = _texto(datos.get("envio_id"), 20)
    envio = cx.execute("select * from recapado_envios where id = %s",
                       (envio_id,)).fetchone()
    if not envio:
        raise ValueError("Ese envío no existe.")
    if envio["estado"] == "anulado":
        return {"ok": True, "ya": True}

    movidas = cx.execute("""
        select count(*) as n from recapado_renglones
        where envio_id = %s and estado <> 'enviada'""", (envio_id,)).fetchone()["n"]
    if movidas:
        raise ValueError(
            f"En el remito {envio_id} ya volvieron {movidas} cubiertas. "
            f"No se puede anular: habría que deshacer esos recapados.")

    grupo = uuid.uuid4()
    motivo = _texto(datos.get("motivo"), 300) or "Envío anulado"
    for r in cx.execute("select * from recapado_renglones where envio_id = %s",
                        (envio_id,)).fetchall():
        cx.execute("update cubiertas set estado = 'stock' where id = %s",
                   (r["cubierta_id"],))
        base._log(cx, grupo, "recapado", cubierta_id=r["cubierta_id"],
                  usuario=(usuario or {}).get("nombre"),
                  nota=f"{motivo} · remito {envio_id} anulado")

    # El número no se reutiliza: el correlativo es inmutable y el papel
    # con ese número puede estar dando vueltas.
    cx.execute("""update recapado_envios set estado = 'anulado', nota = %s
                   where id = %s""",
               (motivo, envio_id))
    return {"ok": True}


def aplicar(cx, datos, usuario=None):
    """Punto de entrada de la API."""
    op = str(datos.get("op") or "").strip()
    acciones = {"enviar": enviar, "recibir": recibir, "anular": anular}
    if op not in acciones:
        raise ValueError("Operación de recapado inválida.")
    return acciones[op](cx, datos, usuario)
