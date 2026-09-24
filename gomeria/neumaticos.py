"""
Cambios de neumáticos: cada cuánto se cambia cada eje, y cuándo le toca.

Tres preguntas, la misma mirada desde tres lados:

    ¿a qué eje le toca?                 → panel()["ejes"]
    ¿cada cuánto se cambia cada eje?    → panel()["reglas"], por mapa y eje
    ¿cuánto dura una goma?              → panel()["duraciones"], que la
                                          pantalla agrupa por patente,
                                          marca, modelo o tipo de eje

Todo se apoya en las vistas de ``28_cambios_neumaticos.sql``. Acá no se
recalcula nada: se pide, se valida lo que se escribe y se firma.

Los semis no tienen odómetro. Sus kilómetros son los del tractor que los
llevaba cada día, y eso sale de la tabla ``enganches``, que se llena sola
cuando se cambia el semi en la ficha del tractor.
"""
import datetime

import permisos

TIPOS_EJE = ("direccion", "traccion", "portante", "arrastre")

# Por encima de esto un número está mal escrito: ninguna goma de camión
# llega al millón y medio de kilómetros ni dura veinte años.
TOPE_KM = 1_500_000
TOPE_DIAS = 7300


def instalado(cx):
    """Si ya se corrió el SQL de cambios de neumáticos."""
    fila = cx.execute(
        "select to_regclass('neumaticos_reglas') as t").fetchone()
    return bool(fila and fila["t"])


def _exigir_instalado(cx):
    if not instalado(cx):
        raise ValueError("Todavía no está prendido el aviso de cambios. Hay que "
                         "correr gomeria/28_cambios_neumaticos.sql en Supabase.")


def _gestor(usuario):
    if not permisos.gestiona(usuario):
        raise PermissionError(
            "Solo un encargado o administrador puede hacer ese cambio.")


def _entero(valor, nombre, minimo=0, maximo=None, obligatorio=False):
    """Un número entero, o None si vino vacío. Acepta '150.000'."""
    if valor in (None, ""):
        if obligatorio:
            raise ValueError(f"Falta {nombre}.")
        return None
    texto = str(valor).strip().replace(".", "").replace(",", "")
    try:
        n = int(texto)
    except ValueError:
        raise ValueError(f"{nombre.capitalize()} tiene que ser un número.") from None
    if n < minimo or (maximo is not None and n > maximo):
        raise ValueError(f"{nombre.capitalize()} está fuera de rango.")
    return n


def _fecha(valor, nombre="la fecha", obligatorio=True):
    if valor in (None, ""):
        if obligatorio:
            raise ValueError(f"Falta {nombre}.")
        return None
    try:
        f = datetime.date.fromisoformat(str(valor)[:10])
    except ValueError:
        raise ValueError(f"{nombre.capitalize()} tiene que venir como AAAA-MM-DD.") from None
    if f > datetime.date.today():
        raise ValueError(f"{nombre.capitalize()} no puede ser en el futuro.")
    return f


def _texto(valor, largo=80, mayusculas=False):
    t = " ".join(str(valor or "").split())[:largo]
    return (t.upper() if mayusculas else t) or None


# =====================================================================
# LEER
# =====================================================================
ORDEN_ESTADO = """case estado when 'vencido' then 0 when 'proximo' then 1
                               when 'sin_dato' then 2 when 'ok' then 3 else 4 end"""


def panel(cx):
    """Todo lo que usa la solapa, en un solo pedido."""
    if not instalado(cx):
        return {"instalado": False,
                "aviso": "Falta correr gomeria/28_cambios_neumaticos.sql en Supabase."}

    ejes = cx.execute(f"""
        select * from v_neumaticos_ejes
        order by {ORDEN_ESTADO}, km_restantes nulls last,
                 dias_restantes nulls last, patente, eje
    """).fetchall()
    resumen = {"vencido": 0, "proximo": 0, "sin_dato": 0, "ok": 0, "sin_regla": 0}
    for e in ejes:
        resumen[e["estado"]] = resumen.get(e["estado"], 0) + 1

    return {
        "instalado": True,
        "ejes": ejes,
        "resumen": resumen,
        "posiciones": cx.execute("""
            select unidad_id, eje, posicion, orden, cubierta_id, cubierta,
                   marca, modelo, origen, base_fecha, km, dias, km_parcial,
                   km_restantes, dias_restantes, estado
            from v_neumaticos_posiciones order by unidad_id, orden
        """).fetchall(),
        "reglas": cx.execute("""
            select * from v_neumaticos_mapa_ejes order by mapa, eje
        """).fetchall(),
        "duraciones": cx.execute("""
            select * from v_neumaticos_duraciones order by hasta desc, patente, eje
        """).fetchall(),
        "cambios": cx.execute("""
            select c.id, c.unidad_id, u.patente, u.interno, c.eje, c.fecha,
                   c.km_unidad, c.marca, c.modelo, c.medida, c.nota,
                   c.usuario, c.creado
            from neumaticos_cambios c join unidades u on u.id = c.unidad_id
            where not c.anulado
            order by c.fecha desc, c.id desc limit 300
        """).fetchall(),
        "enganches": cx.execute("""
            select e.id, e.semi_id, s.patente as semi, e.tractor_id,
                   t.patente as tractor, e.desde, e.hasta, e.origen, e.usuario
            from enganches e
            join unidades s on s.id = e.semi_id
            join unidades t on t.id = e.tractor_id
            order by s.patente, e.desde desc
        """).fetchall(),
        "unidades": cx.execute("""
            select u.id, u.patente, u.interno, u.uso, c.nombre as mapa,
                   coalesce((select array_agg(distinct p.eje order by p.eje)
                             from configuracion_posiciones p
                             where p.configuracion_id = u.configuracion_id
                               and not p.es_auxilio and p.eje > 0), '{}') as ejes
            from unidades u
            left join configuraciones c on c.id = u.configuracion_id
            where u.activa order by u.patente
        """).fetchall(),
        "tipos_eje": TIPOS_EJE,
    }


def resumen(cx):
    """Los números para la portada y las alertas."""
    if not instalado(cx):
        return None
    fila = cx.execute("""
        select count(*) filter (where estado = 'vencido')::int as vencidos,
               count(*) filter (where estado = 'proximo')::int as proximos
        from v_neumaticos_ejes
    """).fetchone()
    return dict(fila) if fila else None


# =====================================================================
# ESCRIBIR
# =====================================================================
def aplicar(cx, datos, usuario):
    _exigir_instalado(cx)
    op = str(datos.get("op") or "").strip()
    firma = (usuario or {}).get("nombre") or (usuario or {}).get("usuario")

    if op == "regla_guardar":
        _gestor(usuario)
        cfg = _entero(datos.get("configuracion_id"), "el mapa", 1, obligatorio=True)
        eje = _entero(datos.get("eje"), "el eje", 1, 20, obligatorio=True)
        existe = cx.execute("""
            select 1 from configuracion_posiciones
            where configuracion_id = %s and eje = %s and not es_auxilio
        """, (cfg, eje)).fetchone()
        if not existe:
            raise ValueError("Ese mapa no tiene ese eje.")
        cada_km = _entero(datos.get("cada_km"), "cada cuántos km", 1, TOPE_KM)
        cada_dias = _entero(datos.get("cada_dias"), "cada cuántos días", 1, TOPE_DIAS)
        if cada_km is None and cada_dias is None:
            raise ValueError("Poné cada cuántos km, cada cuántos días, o las dos cosas.")
        aviso_km = _entero(datos.get("aviso_km"), "el aviso en km", 0, TOPE_KM)
        aviso_dias = _entero(datos.get("aviso_dias"), "el aviso en días", 0, TOPE_DIAS)
        if cada_km and aviso_km is not None and aviso_km >= cada_km:
            raise ValueError("El aviso tiene que ser menor que el intervalo.")
        tipo = str(datos.get("tipo_eje") or "").strip().lower() or None
        if tipo and tipo not in TIPOS_EJE:
            raise ValueError("Tipo de eje desconocido.")
        cx.execute("""
            insert into neumaticos_reglas
              (configuracion_id, eje, tipo_eje, cada_km, cada_dias,
               aviso_km, aviso_dias, nota, actualizado_por)
            values (%s, %s, %s, %s, %s, coalesce(%s, 15000), coalesce(%s, 30), %s, %s)
            on conflict (configuracion_id, eje) do update
               set tipo_eje = excluded.tipo_eje, cada_km = excluded.cada_km,
                   cada_dias = excluded.cada_dias, aviso_km = excluded.aviso_km,
                   aviso_dias = excluded.aviso_dias, nota = excluded.nota,
                   actualizado = now(), actualizado_por = excluded.actualizado_por
        """, (cfg, eje, tipo, cada_km, cada_dias, aviso_km, aviso_dias,
              _texto(datos.get("nota"), 200), firma))

    elif op == "regla_borrar":
        _gestor(usuario)
        cx.execute("delete from neumaticos_reglas where configuracion_id = %s and eje = %s",
                   (_entero(datos.get("configuracion_id"), "el mapa", 1, obligatorio=True),
                    _entero(datos.get("eje"), "el eje", 1, 20, obligatorio=True)))

    elif op == "cambio_registrar":
        # Lo carga el gomero: queda firmado, y si está mal lo anula un
        # encargado. Se pueden marcar varios ejes a la vez, porque es común
        # cambiar tracción y tercer eje en la misma parada.
        unidad = _entero(datos.get("unidad_id"), "la unidad", 1, obligatorio=True)
        ejes = datos.get("ejes") or ([datos.get("eje")] if datos.get("eje") else [])
        ejes = sorted({_entero(e, "el eje", 1, 20, obligatorio=True) for e in ejes})
        if not ejes:
            raise ValueError("Marcá qué eje se cambió.")
        validos = {f["eje"] for f in cx.execute("""
            select distinct p.eje from unidades u
            join configuracion_posiciones p on p.configuracion_id = u.configuracion_id
            where u.id = %s and not p.es_auxilio and p.eje > 0
        """, (unidad,)).fetchall()}
        if not validos:
            raise ValueError("Esa unidad no tiene mapa de ejes asignado.")
        if set(ejes) - validos:
            raise ValueError("Esa unidad no tiene ese eje.")
        fecha = _fecha(datos.get("fecha"))
        km = _entero(datos.get("km_unidad"), "el odómetro", 0, 10_000_000)
        for eje in ejes:
            cx.execute("""
                insert into neumaticos_cambios
                  (unidad_id, eje, fecha, km_unidad, marca, modelo, medida, nota, usuario)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (unidad, eje, fecha, km,
                  _texto(datos.get("marca"), 40, True),
                  _texto(datos.get("modelo"), 40, True),
                  _texto(datos.get("medida"), 30, True),
                  _texto(datos.get("nota"), 300), firma))

    elif op == "cambio_anular":
        _gestor(usuario)
        motivo = _texto(datos.get("motivo"), 300)
        if not motivo:
            raise ValueError("Escribí por qué se anula.")
        fila = cx.execute("""
            update neumaticos_cambios
               set anulado = true, anulado_por = %s, anulado_motivo = %s
             where id = %s and not anulado returning id
        """, (firma, motivo, _entero(datos.get("id"), "el cambio", 1, obligatorio=True))
        ).fetchone()
        if not fila:
            raise ValueError("Ese cambio no existe o ya estaba anulado.")

    elif op == "enganche_cargar":
        # Completar la historia: "antes de marzo, este semi lo llevaba otro
        # tractor". El enganche de hoy lo lleva la ficha; acá solo pasado.
        _gestor(usuario)
        semi = _entero(datos.get("semi_id"), "el semi", 1, obligatorio=True)
        tractor = _entero(datos.get("tractor_id"), "el tractor", 1, obligatorio=True)
        if semi == tractor:
            raise ValueError("El semi y el tractor tienen que ser unidades distintas.")
        desde = _fecha(datos.get("desde"), "la fecha de inicio")
        hasta = _fecha(datos.get("hasta"), "la fecha de fin")
        if hasta <= desde:
            raise ValueError("La fecha de fin tiene que ser posterior a la de inicio.")
        choque = cx.execute("""
            select s.patente as semi, t.patente as tractor, e.desde, e.hasta
            from enganches e
            join unidades s on s.id = e.semi_id join unidades t on t.id = e.tractor_id
            where (e.semi_id = %s or e.tractor_id = %s)
              and e.desde < %s and coalesce(e.hasta, current_date + 1) > %s
            limit 1
        """, (semi, tractor, hasta, desde)).fetchone()
        if choque:
            raise ValueError(
                f"Se superpone con {choque['semi']} enganchado a {choque['tractor']} "
                f"desde {choque['desde']}. Corregí las fechas.")
        cx.execute("""
            insert into enganches (semi_id, tractor_id, desde, hasta, origen, usuario)
            values (%s, %s, %s, %s, 'manual', %s)
        """, (semi, tractor, desde, hasta, firma))

    elif op == "enganche_desde":
        # El enganche inicial se supuso "desde siempre". Si se sabe desde
        # cuándo de verdad, se corrige acá.
        _gestor(usuario)
        eid = _entero(datos.get("id"), "el enganche", 1, obligatorio=True)
        desde = _fecha(datos.get("desde"), "la fecha de inicio")
        actual = cx.execute("select * from enganches where id = %s", (eid,)).fetchone()
        if not actual:
            raise ValueError("Ese enganche no existe.")
        if actual["hasta"] and desde > actual["hasta"]:
            raise ValueError("La fecha de inicio queda después del fin.")
        choque = cx.execute("""
            select 1 from enganches e
            where e.id <> %s and (e.semi_id = %s or e.tractor_id = %s)
              and e.desde < coalesce(%s, current_date + 1)
              and coalesce(e.hasta, current_date + 1) > %s
        """, (eid, actual["semi_id"], actual["tractor_id"], actual["hasta"], desde)
        ).fetchone()
        if choque:
            raise ValueError("Con esa fecha se superpone con otro enganche.")
        cx.execute("update enganches set desde = %s, usuario = %s where id = %s",
                   (desde, firma, eid))

    elif op == "enganche_borrar":
        _gestor(usuario)
        fila = cx.execute("""
            delete from enganches where id = %s and origen = 'manual' returning id
        """, (_entero(datos.get("id"), "el enganche", 1, obligatorio=True),)).fetchone()
        if not fila:
            raise ValueError("Solo se borran los enganches cargados a mano. "
                             "El de hoy se cambia desde la ficha del tractor.")
    else:
        raise ValueError("Operación desconocida.")

    return panel(cx)
