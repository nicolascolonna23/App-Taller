"""Tractor y semi: quién llevó a quién, y los kilómetros que eso deja.

Un semi no tiene satelital. No tiene motor, no reporta, y sin embargo sus
cubiertas se gastan, sus frenos se ajustan y sus papeles vencen. Hasta acá
el sistema sabía de él lo que decía una columna de texto en el tractor
—`unidades.semi`—, que solo puede decir el de hoy y borra el de ayer.

Acá el enganche es una fila con fechas. De eso salen dos cosas:

  * **Qué semi llevó cada tractor y cuándo.** Un historial, no una foto.
  * **Los kilómetros del semi**: los que hizo el tractor mientras lo
    llevaba puesto. Se escriben en `odometros` con fuente `enganche`, así
    el semi entra en services, en cubiertas y en alertas como cualquier
    otra unidad, sin que ningún módulo tenga que enterarse de nada.

El día del enganche no cuenta: el recorrido de una fecha es el tramo
entre la lectura anterior y esa fecha, y ese tramo lo hizo el tractor
solo, o con otro semi atrás.
"""
from datetime import date

import permisos


def _exigir_gestor(usuario, que="enganchar o desenganchar un semi"):
    if not permisos.gestiona(usuario):
        raise PermissionError(f"Solo un encargado o administrador puede {que}.")


def _texto(valor, limite=300):
    texto = " ".join(str(valor or "").split())
    return texto[:limite] or None


def _fecha(valor, campo="la fecha"):
    if not valor:
        return date.today()
    if isinstance(valor, date):
        return valor
    try:
        fecha = date.fromisoformat(str(valor).strip()[:10])
    except ValueError:
        raise ValueError(f"No se entiende {campo}: {valor}") from None
    if fecha > date.today():
        raise ValueError(f"{campo.capitalize()} no puede ser posterior a hoy.")
    return fecha


def _unidad(cx, unidad_id, que):
    try:
        unidad_id = int(unidad_id)
    except (TypeError, ValueError):
        raise ValueError(f"Falta {que}.") from None
    fila = cx.execute("select * from unidades where id = %s", (unidad_id,)).fetchone()
    if not fila:
        raise ValueError(f"Esa unidad no existe ({que}).")
    return fila


# =====================================================================
# LECTURA
# =====================================================================
def panel(cx, usuario=None):
    """Los semis con su tractor de hoy, y con qué engancharlos."""
    sucursal = permisos.sucursal_de(usuario)
    semis = [dict(s) for s in cx.execute("""
        select * from v_semis
        where activa and (%s::text is null or sucursal = %s)
        order by tractor_id is null, patente
    """, (sucursal, sucursal)).fetchall()]

    return {
        "semis": semis,
        # Los tractores libres primero: es lo que se busca al enganchar.
        "tractores": [dict(t) for t in cx.execute("""
            select u.id, u.patente, u.interno, u.marca, u.modelo, u.sucursal,
                   u.chofer, u.km_actual,
                   e.semi_id, s.patente as semi
            from unidades u
            left join lateral (
              select * from enganches e2 where e2.tractor_id = u.id
                and e2.hasta is null limit 1) e on true
            left join unidades s on s.id = e.semi_id
            where u.activa and u.tipo = 'vehiculo' and not u.es_semi
              and (%s::text is null or u.sucursal = %s)
            order by e.semi_id is not null, u.patente
        """, (sucursal, sucursal)).fetchall()],
        "candidatos": [dict(u) for u in cx.execute("""
            select id, patente, interno, marca, modelo, sucursal, es_semi
            from unidades where activa order by es_semi desc, patente""").fetchall()],
        "puede_gestionar": permisos.gestiona(usuario),
    }


def historial(cx, semi_id=None, tractor_id=None):
    """Todos los enganches de un semi —o de un tractor—, con sus km."""
    if not semi_id and not tractor_id:
        raise ValueError("Debe indicarse el semi o el tractor.")
    filas = cx.execute("""
        select e.id, e.desde, e.hasta, e.usuario, e.nota,
               e.semi_id, s.patente as semi, s.interno as semi_interno,
               e.tractor_id, t.patente as tractor, t.interno as tractor_interno,
               round(coalesce(k.km, 0), 0) as km
        from enganches e
        join unidades s on s.id = e.semi_id
        join unidades t on t.id = e.tractor_id
        left join lateral (
          select sum(d.recorrido) as km from v_km_semi_diario d
          where d.semi_id = e.semi_id and d.tractor_id = e.tractor_id
            and d.fecha > e.desde and (e.hasta is null or d.fecha <= e.hasta)
        ) k on true
        where (%s::bigint is null or e.semi_id = %s)
          and (%s::bigint is null or e.tractor_id = %s)
        order by e.desde desc, e.id desc
    """, (semi_id, semi_id, tractor_id, tractor_id)).fetchall()
    return {"enganches": [dict(f) for f in filas],
            "km": round(sum(float(f["km"] or 0) for f in filas), 0)}


# =====================================================================
# ESCRITURA
# =====================================================================
def enganchar(cx, datos, usuario=None):
    """Este semi va atrás de este tractor desde hoy.

    Si alguno de los dos venía enganchado a otro, ese enganche se cierra
    el día anterior: un semi no puede estar en dos lugares, y el
    kilometraje de esos días tiene que ir a uno solo.
    """
    _exigir_gestor(usuario)
    tractor = _unidad(cx, datos.get("tractor_id"), "el tractor")
    semi = _unidad(cx, datos.get("semi_id"), "el semi")
    if tractor["id"] == semi["id"]:
        raise ValueError("Una unidad no se engancha a sí misma.")
    desde = _fecha(datos.get("desde"), "la fecha del enganche")

    abierto = cx.execute("""
        select e.id, e.semi_id, e.tractor_id, e.desde
        from enganches e
        where e.hasta is null and (e.semi_id = %s or e.tractor_id = %s)
    """, (semi["id"], tractor["id"])).fetchall()
    for previo in abierto:
        if previo["semi_id"] == semi["id"] and previo["tractor_id"] == tractor["id"]:
            raise ValueError("Ese semi ya está enganchado a ese tractor.")
        if desde < previo["desde"]:
            raise ValueError("El enganche anterior empezó después de esa fecha. "
                             "Corregí la fecha o cerralo a mano.")
        _cerrar(cx, previo["id"], desde, usuario,
                "Se cerró al enganchar otra unidad.")

    # El semi pasa a estar marcado como tal: de ahí en más la pantalla lo
    # ofrece para enganchar y no para llevar a otro.
    if not semi["es_semi"]:
        cx.execute("update unidades set es_semi = true where id = %s", (semi["id"],))

    fila = cx.execute("""
        insert into enganches (tractor_id, semi_id, desde, usuario, nota)
        values (%s,%s,%s,%s,%s) returning id
    """, (tractor["id"], semi["id"], desde, (usuario or {}).get("nombre"),
          _texto(datos.get("nota")))).fetchone()

    # El maestro sigue diciendo qué semi lleva el tractor: es lo que leen
    # las pantallas que todavía no saben de enganches.
    cx.execute("update unidades set semi = %s where id = %s",
               (semi["patente"], tractor["id"]))

    km = recalcular(cx, semi["id"])
    return {"ok": True, "id": fila["id"], "km": km}


def desenganchar(cx, datos, usuario=None):
    """Bajó el semi. Desde mañana, lo que rode el tractor no es suyo."""
    _exigir_gestor(usuario)
    enganche_id = datos.get("id")
    if not enganche_id:
        semi = _unidad(cx, datos.get("semi_id"), "el semi")
        fila = cx.execute("""select id from enganches
                             where semi_id = %s and hasta is null""",
                          (semi["id"],)).fetchone()
        if not fila:
            raise ValueError("Ese semi no está enganchado a ningún tractor.")
        enganche_id = fila["id"]
    hasta = _fecha(datos.get("hasta"), "la fecha en que se bajó")
    fila = _cerrar(cx, enganche_id, hasta, usuario, _texto(datos.get("nota")))
    km = recalcular(cx, fila["semi_id"])
    return {"ok": True, "id": fila["id"], "km": km}


def _cerrar(cx, enganche_id, hasta, usuario, nota=None):
    fila = cx.execute("select * from enganches where id = %s",
                      (enganche_id,)).fetchone()
    if not fila:
        raise ValueError("Ese enganche no existe.")
    if fila["hasta"] is not None:
        raise ValueError("Ese enganche ya estaba cerrado.")
    if hasta < fila["desde"]:
        raise ValueError("No se puede cerrar un enganche antes de que empezara.")
    cx.execute("""update enganches set hasta = %s,
                  nota = nullif(concat_ws(' · ', nota, %s::text), '')
                  where id = %s""", (hasta, nota, enganche_id))
    # El tractor queda sin semi en el maestro, si era el que llevaba.
    cx.execute("""update unidades set semi = null
                  where id = %s and semi = (select patente from unidades where id = %s)""",
               (fila["tractor_id"], fila["semi_id"]))
    return fila


def borrar(cx, datos, usuario=None):
    """Saca un enganche cargado por error y rehace los km del semi."""
    _exigir_gestor(usuario, "borrar un enganche")
    fila = cx.execute("delete from enganches where id = %s returning semi_id",
                      (datos.get("id"),)).fetchone()
    if not fila:
        raise ValueError("Ese enganche ya no está.")
    return {"ok": True, "km": recalcular(cx, fila["semi_id"])}


# =====================================================================
# LOS KILÓMETROS DEL SEMI
# =====================================================================
def recalcular(cx, semi_id):
    """Rehace la serie de kilómetros del semi y la deja en `odometros`.

    Se rehace entera y no se va sumando: un enganche que se corrige o se
    borra cambia el pasado, y una serie que se fue acumulando a mano
    quedaría diciendo kilómetros que el semi no hizo.

    El punto de partida es el kilometraje que tuviera cargado antes de
    que existiera el primer enganche —el que vino en la chapa o el que
    alguien cargó a mano—, así el número no arranca de cero cuando el
    semi ya tiene medio millón encima.
    """
    semi = cx.execute("select id, patente, km_actual from unidades where id = %s",
                      (semi_id,)).fetchone()
    if not semi:
        return 0

    dias = cx.execute("""
        select fecha, sum(recorrido) as km
        from v_km_semi_diario where semi_id = %s
        group by fecha order by fecha""", (semi_id,)).fetchall()

    base = cx.execute("""
        select max(km) as km from odometros
        where patente = %s and fuente <> 'enganche'""", (semi["patente"],)).fetchone()
    arranque = float(base["km"] or 0)
    if not arranque and semi["km_actual"]:
        # Todavía no hay serie propia: se parte del número del maestro,
        # menos lo que se le va a sumar, para no duplicar lo ya rodado.
        arranque = max(0.0, float(semi["km_actual"])
                       - sum(float(d["km"] or 0) for d in dias))

    cx.execute("delete from odometros where patente = %s and fuente = 'enganche'",
               (semi["patente"],))
    acumulado = arranque
    for dia in dias:
        acumulado += float(dia["km"] or 0)
        cx.execute("""
            insert into odometros (unidad_id, patente, fecha, km, fuente)
            values (%s, %s, %s, %s, 'enganche')
            on conflict (patente, fecha, fuente) do update set km = excluded.km
        """, (semi["id"], semi["patente"], dia["fecha"], round(acumulado, 2)))
    return round(acumulado, 2)


def recalcular_todos(cx):
    """Rehace los kilómetros de todos los semis. Lo usa el job de la mañana."""
    semis = cx.execute("select distinct semi_id from enganches").fetchall()
    return {int(s["semi_id"]): recalcular(cx, s["semi_id"]) for s in semis}


# =====================================================================
def aplicar(cx, datos, usuario=None):
    """Punto de entrada de la API."""
    op = (datos.get("op") or "").strip()
    acciones = {"enganchar": enganchar, "desenganchar": desenganchar, "borrar": borrar}
    if op in acciones:
        return acciones[op](cx, datos, usuario)
    if op == "historial":
        return historial(cx, datos.get("semi_id"), datos.get("tractor_id"))
    if op == "recalcular":
        _exigir_gestor(usuario, "recalcular los kilómetros")
        return {"ok": True, "semis": recalcular_todos(cx)}
    raise ValueError("No entiendo qué hay que hacer con el enganche.")
