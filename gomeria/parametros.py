"""Los parámetros del sistema: lo que antes decidía el código.

Tres cosas se juntan en una sola pantalla, porque las tres son la misma
pregunta —cómo se comporta el sistema— y estaban en tres lugares
distintos o en ninguno:

  1. **De dónde salen los kilómetros.** Automático: los trae el satelital
     todas las mañanas. Manual: los carga una persona y el job no escribe
     nada. Hasta acá era siempre automático, y la unidad sin equipo
     quedaba sin kilómetros, sin consumo y sin services.

  2. **Los planes de mantenimiento.** El preventivo se agenda: cada
     tantos kilómetros o cada tantos días —el aceite se vence aunque el
     camión no ruede—. El correctivo no se agenda, porque una rotura no
     se agenda: es un catálogo de trabajos con lo que deberían llevar de
     tiempo y de plata, para comparar contra lo que salieron.

  3. **Los umbrales de aviso**, que ya vivían en `alertas_reglas`: a
     cuántos kilómetros del service empieza a avisar, cuándo se pone
     urgente, y qué carga de combustible es demasiado grande.
"""
from datetime import datetime, timezone

import alertas
import permisos

ORIGENES = ("automatico", "manual")
CLASES = ("preventivo", "correctivo")


def _exigir_admin(usuario, que="cambiar los parámetros"):
    if not permisos.administra(usuario):
        raise PermissionError(f"Solo un administrador puede {que}.")


def _exigir_gestor(usuario, que="tocar los planes"):
    if not permisos.gestiona(usuario):
        raise PermissionError(f"Solo un encargado o administrador puede {que}.")


def _texto(valor, limite=300):
    texto = " ".join(str(valor or "").split())
    return texto[:limite] or None


def _entero(valor, campo, minimo=1):
    if valor in (None, ""):
        return None
    try:
        n = int(float(str(valor).replace(",", ".")))
    except (TypeError, ValueError):
        raise ValueError(f"{campo} tiene que ser un número.") from None
    if n < minimo:
        raise ValueError(f"{campo} tiene que ser mayor que cero.")
    return n


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


# =====================================================================
# LOS PARÁMETROS
# =====================================================================
def leer(cx):
    """La única fila. Si el SQL no se corrió, los valores de siempre."""
    try:
        fila = cx.execute("select * from parametros").fetchone()
    except Exception:
        cx.rollback()
        return None
    return dict(fila) if fila else None


def km_automatico(cx):
    """¿El satelital puede escribir kilómetros?

    Lo pregunta el job de la mañana antes de subir nada: en manual, el
    que manda es el que carga a mano y una lectura automática le pisaría
    el número.
    """
    p = leer(cx)
    return True if p is None else p["km_origen"] == "automatico"


def guardar(cx, datos, usuario=None):
    _exigir_admin(usuario)
    origen = str(datos.get("km_origen") or "").strip().lower()
    if origen not in ORIGENES:
        raise ValueError("El kilometraje sale del satelital (automático) o se carga "
                         "a mano (manual).")
    hora = _texto(datos.get("km_hora"), 5) or "05:00"
    try:
        datetime.strptime(hora, "%H:%M")
    except ValueError:
        raise ValueError("La hora va en formato 24 horas, por ejemplo 05:00.") from None

    cx.execute("""
        update parametros set km_origen = %s, km_hora = %s,
               actualizado = now(), usuario = %s
        where unica
    """, (origen, hora, (usuario or {}).get("nombre")))
    return {"ok": True, "km_origen": origen, "km_hora": hora}


# =====================================================================
# LOS PLANES
# =====================================================================
def planes(cx):
    return [dict(p) for p in cx.execute("""
        select p.id, p.nombre, p.descripcion, p.clase, p.cada_km, p.cada_dias,
               p.tareas, p.horas_estimadas, p.costo_estimado, p.activo,
               count(u.id)::int as unidades
        from mantenimiento_planes p
        left join unidades u on u.mantenimiento_plan_id = p.id and u.activa
        group by p.id
        order by p.clase, p.activo desc, p.nombre
    """).fetchall()]


def guardar_plan(cx, datos, usuario=None):
    """Crea o corrige un plan. La clase decide qué campos tienen sentido."""
    _exigir_gestor(usuario)
    nombre = _texto(datos.get("nombre"), 60)
    if not nombre:
        raise ValueError("Falta el nombre del plan.")
    clase = str(datos.get("clase") or "preventivo").strip().lower()
    if clase not in CLASES:
        raise ValueError("El plan es preventivo o correctivo.")

    cada_km = _entero(datos.get("cada_km"), "Cada cuántos kilómetros")
    cada_dias = _entero(datos.get("cada_dias"), "Cada cuántos días")
    if clase == "preventivo" and not cada_km and not cada_dias:
        raise ValueError("Un plan preventivo necesita cada cuántos kilómetros "
                         "o cada cuántos días: sin eso no puede avisar.")
    if clase == "correctivo":
        # Un correctivo no se agenda: si trae intervalo, es que se eligió
        # mal la clase. Se limpia en vez de guardar algo que no se usa.
        cada_km = cada_dias = None

    valores = (nombre, _texto(datos.get("descripcion")), clase, cada_km, cada_dias,
               _texto(datos.get("tareas"), 2000),
               _numero(datos.get("horas_estimadas"), "Las horas estimadas"),
               _numero(datos.get("costo_estimado"), "El costo estimado"),
               bool(datos.get("activo", True)))

    plan_id = _entero(datos.get("id"), "El plan", minimo=1)
    if plan_id:
        fila = cx.execute("""
            update mantenimiento_planes
            set nombre=%s, descripcion=%s, clase=%s, cada_km=%s, cada_dias=%s,
                tareas=%s, horas_estimadas=%s, costo_estimado=%s, activo=%s,
                actualizado=now()
            where id=%s returning id""", (*valores, plan_id)).fetchone()
        if not fila:
            raise ValueError("Ese plan no existe.")
        return {"ok": True, "id": plan_id}

    fila = cx.execute("""
        insert into mantenimiento_planes
          (nombre, descripcion, clase, cada_km, cada_dias, tareas,
           horas_estimadas, costo_estimado, activo)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""", valores).fetchone()
    return {"ok": True, "id": fila["id"]}


def borrar_plan(cx, datos, usuario=None):
    """Saca un plan. Las unidades que lo tenían quedan sin plan, no rotas."""
    _exigir_gestor(usuario)
    plan_id = _entero(datos.get("id"), "El plan", minimo=1)
    cuantas = cx.execute("""update unidades set mantenimiento_plan_id = null
                            where mantenimiento_plan_id = %s returning id""",
                         (plan_id,)).fetchall()
    fila = cx.execute("delete from mantenimiento_planes where id = %s returning id",
                      (plan_id,)).fetchone()
    if not fila:
        raise ValueError("Ese plan no existe.")
    return {"ok": True, "unidades": len(cuantas)}


def asignar(cx, datos, usuario=None):
    """Le pone un plan preventivo a una unidad, o se lo saca."""
    _exigir_gestor(usuario)
    unidad_id = _entero(datos.get("unidad_id"), "La unidad", minimo=1)
    plan_id = _entero(datos.get("plan_id"), "El plan", minimo=1)
    if plan_id:
        plan = cx.execute("select clase from mantenimiento_planes where id = %s",
                          (plan_id,)).fetchone()
        if not plan:
            raise ValueError("Ese plan no existe.")
        if plan["clase"] != "preventivo":
            raise ValueError("A una unidad se le asigna un plan preventivo: el "
                             "correctivo es un catálogo de trabajos, no una agenda.")
    fila = cx.execute("""update unidades set mantenimiento_plan_id = %s, actualizado = now()
                         where id = %s returning id""", (plan_id, unidad_id)).fetchone()
    if not fila:
        raise ValueError("Esa unidad no existe.")
    return {"ok": True}


# =====================================================================
# LA PANTALLA
# =====================================================================
def panel(cx, usuario=None):
    """Todo lo que la pantalla de parámetros dibuja de una."""
    p = leer(cx)
    return {
        "parametros": p or {"km_origen": "automatico", "km_hora": "05:00"},
        "instalado": p is not None,
        "planes": planes(cx),
        "asignaciones": [dict(a) for a in cx.execute("""
            select u.id as unidad_id, u.patente, u.interno, u.sucursal,
                   u.mantenimiento_plan_id as plan_id, p.nombre as plan_nombre,
                   p.cada_km, p.cada_dias
            from unidades u
            left join mantenimiento_planes p on p.id = u.mantenimiento_plan_id
            where u.activa and u.tipo = 'vehiculo'
            order by u.patente""").fetchall()],
        "reglas": alertas.reglas(cx),
        # Cuántas lecturas del satelital entraron ayer: es lo que dice si
        # el automático está andando de verdad o quedó colgado.
        "lecturas": _uno(cx, """
            select count(*)::int as ayer, max(fecha) as ultima
            from odometros where fuente = 'hawk'
              and fecha >= current_date - 1"""),
        "puede_gestionar": permisos.gestiona(usuario),
        "puede_administrar": permisos.administra(usuario),
    }


def _uno(cx, consulta):
    try:
        fila = cx.execute(consulta).fetchone()
        return dict(fila) if fila else None
    except Exception:
        cx.rollback()
        return None


def aplicar(cx, datos, usuario=None):
    """Punto de entrada de la API."""
    op = (datos.get("op") or "").strip()
    if op == "guardar":
        return guardar(cx, datos, usuario)
    if op == "plan_guardar":
        return guardar_plan(cx, datos, usuario)
    if op == "plan_borrar":
        return borrar_plan(cx, datos, usuario)
    if op == "asignar":
        return asignar(cx, datos, usuario)
    if op == "reglas":
        _exigir_admin(usuario, "cambiar los umbrales de aviso")
        return {"ok": True, "reglas": alertas.guardar_reglas(cx, datos)}
    raise ValueError("No entiendo qué parámetro hay que cambiar.")
