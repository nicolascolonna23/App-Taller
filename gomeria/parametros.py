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
import base64
import zipfile
from datetime import datetime, timezone

from xml.etree import ElementTree

import alertas
import mantenimiento
import permisos

ORIGENES = ("automatico", "manual")
# El prefiltro es un preventivo más, con su propio plan: una unidad que lo
# lleva tiene dos planes, el de service y el de prefiltro (44_prefiltros.sql).
CLASES = ("preventivo", "correctivo", "prefiltro")
FALTA_PREFILTROS = "Falta correr gomeria/44_prefiltros.sql en el SQL Editor de Supabase."

# Con qué queda cada parámetro cuando se lo restablece. Es lo mismo que
# trae el SQL al crearse la fila: «eliminar» un parámetro no es dejarlo
# vacío —el sistema tiene que seguir andando— sino volverlo a lo de
# fábrica, y para eso hay que saber cuál era.
DE_FABRICA = {
    "km_origen": "automatico",
    "km_hora": "05:00",
    "combustible_origen": "manual",
    "combustible_hora": "06:00",
    "combustible_fuente": None,
    "litros_maximos": 450,
    "service_urgente_km": 5000,
    "service_aviso_km": 15000,
    "combustible_dias": 90,
}

# Cuáles de esos viven en la fila de parámetros. Los otros cuatro son los
# umbrales de aviso, que tienen su propia tabla desde antes.
DEL_SISTEMA = ("km_origen", "km_hora", "combustible_origen", "combustible_hora")


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


def combustible_automatico(cx):
    """¿El combustible entra por archivo, o se anota carga por carga?

    Lo pregunta la pantalla de Combustible para saber si ofrecer las
    zonas de importación. Sin la columna corrida vale lo de siempre, que
    es automático: es como venía funcionando.
    """
    p = leer(cx) or {}
    return (p.get("combustible_origen", DE_FABRICA["combustible_origen"]) == "automatico"
            and bool(p.get("combustible_fuente")))


def combustible_como(cx):
    """Cómo entra el combustible, para la pantalla del módulo.

    Va en la respuesta de Combustible y no en la de Parámetros porque el
    que carga gasoil puede no tener permiso de parámetros: necesita saber
    cómo trabaja el sistema, no poder cambiarlo.
    """
    p = leer(cx) or {}
    return {
        "combustible_origen": p.get("combustible_origen",
                                    DE_FABRICA["combustible_origen"]),
        "combustible_fuente": p.get("combustible_fuente"),
        "combustible_hora": p.get("combustible_hora", DE_FABRICA["combustible_hora"]),
        "combustible_ultima": p.get("combustible_ultima"),
        "combustible_estado": p.get("combustible_estado"),
    }


def km_automatico(cx):
    """¿El satelital puede escribir kilómetros?

    Lo pregunta el job de la mañana antes de subir nada: en manual, el
    que manda es el que carga a mano y una lectura automática le pisaría
    el número.
    """
    p = leer(cx)
    return True if p is None else p["km_origen"] == "automatico"


def guardar(cx, datos, usuario=None):
    """Cambia los parámetros del sistema. Lo que no venga, queda como está."""
    _exigir_admin(usuario)
    actual = leer(cx) or dict(DE_FABRICA)
    cambios = {}

    if "km_origen" in datos:
        origen = str(datos.get("km_origen") or "").strip().lower()
        if origen not in ORIGENES:
            raise ValueError("El kilometraje sale del satelital (automático) o se "
                             "carga a mano (manual).")
        cambios["km_origen"] = origen
    if "km_hora" in datos:
        hora = _texto(datos.get("km_hora"), 5) or DE_FABRICA["km_hora"]
        try:
            datetime.strptime(hora, "%H:%M")
        except ValueError:
            raise ValueError("La hora va en formato 24 horas, por ejemplo 05:00.") from None
        cambios["km_hora"] = hora
    if "combustible_origen" in datos:
        origen = str(datos.get("combustible_origen") or "").strip().lower()
        if origen not in ORIGENES:
            raise ValueError("El combustible se trae de un link (automático) o se "
                             "carga a mano (manual).")
        cambios["combustible_origen"] = origen
    if "combustible_fuente" in datos:
        # El link se guarda como lo pegó la persona —así lo reconoce— pero
        # se revisa ahora: un link que no sirve tiene que fallar acá y no
        # a las seis de la mañana, cuando no hay nadie mirando.
        link = _texto(datos.get("combustible_fuente"), 500)
        if link:
            import combustible
            combustible._revisar_link(combustible.link_csv(link))
        cambios["combustible_fuente"] = link
    if "combustible_hora" in datos:
        hora = _texto(datos.get("combustible_hora"), 5) or DE_FABRICA["combustible_hora"]
        try:
            datetime.strptime(hora, "%H:%M")
        except ValueError:
            raise ValueError("La hora va en formato 24 horas, por ejemplo 06:00.") from None
        cambios["combustible_hora"] = hora
    if not cambios:
        raise ValueError("No vino ningún parámetro para cambiar.")
    despues = {**actual, **cambios}
    if (despues.get("combustible_origen") == "automatico"
            and not despues.get("combustible_fuente")):
        raise ValueError("Para traer el combustible solo hace falta el link de la "
                         "planilla. Sin eso no hay de dónde traerlo.")

    sets = ", ".join(f"{campo} = %s" for campo in cambios)
    try:
        cx.execute(f"""update parametros set {sets}, actualizado = now(), usuario = %s
                       where unica""",
                   (*cambios.values(), (usuario or {}).get("nombre")))
    except Exception:
        cx.rollback()
        if any(c.startswith("combustible_") for c in cambios):
            raise ValueError("Faltan las columnas del combustible. Ejecutar "
                             "gomeria/33_combustible_origen.sql en Supabase.") from None
        raise
    return {"ok": True, **{**actual, **cambios}}


def restablecer(cx, datos, usuario=None):
    """Vuelve un parámetro a lo de fábrica.

    Borrarlo no es una opción: el sistema tiene que saber de dónde salen
    los kilómetros aunque nadie lo haya elegido. Restablecer es lo más
    parecido a eliminarlo que puede existir sin dejar al sistema mudo.
    """
    campo = str(datos.get("campo") or "").strip().lower()
    if campo not in DE_FABRICA:
        raise ValueError("Ese parámetro no existe.")
    if campo in DEL_SISTEMA or campo == "combustible_fuente":
        return guardar(cx, {campo: DE_FABRICA[campo]}, usuario)
    _exigir_admin(usuario, "cambiar los umbrales de aviso")
    return {"ok": True, "reglas": alertas.guardar_reglas(
        cx, {campo: DE_FABRICA[campo]})}


# =====================================================================
# LOS PLANES
# =====================================================================
def hay_prefiltros(cx):
    """Si la base ya tiene el segundo plan de la unidad."""
    try:
        fila = cx.execute("""
            select 1 from information_schema.columns
            where table_schema = 'public' and table_name = 'unidades'
              and column_name = 'prefiltro_plan_id'""").fetchone()
    except Exception:
        cx.rollback()
        return False
    return bool(fila)


def planes(cx):
    # Un plan de prefiltro cuenta las unidades por su propia columna.
    usa = ("(u.mantenimiento_plan_id = p.id or u.prefiltro_plan_id = p.id)"
           if hay_prefiltros(cx) else "u.mantenimiento_plan_id = p.id")
    return [dict(p) for p in cx.execute(f"""
        select p.id, p.nombre, p.descripcion, p.clase, p.cada_km, p.cada_dias,
               p.tareas, p.horas_estimadas, p.costo_estimado, p.activo,
               count(u.id)::int as unidades
        from mantenimiento_planes p
        left join unidades u on {usa} and u.activa
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
        raise ValueError("El plan es preventivo, correctivo o de prefiltro.")
    if clase == "prefiltro" and not hay_prefiltros(cx):
        raise ValueError(FALTA_PREFILTROS)

    cada_km = _entero(datos.get("cada_km"), "Cada cuántos kilómetros")
    cada_dias = _entero(datos.get("cada_dias"), "Cada cuántos días")
    if clase == "prefiltro":
        # El prefiltro se controla por kilómetros, como el filtro en el
        # tablero: los días no entran en la cuenta.
        if not cada_km:
            raise ValueError("Un plan de prefiltro necesita cada cuántos kilómetros "
                             "se cambia: sin eso no puede avisar.")
        cada_dias = None
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
    if hay_prefiltros(cx):
        cuantas += cx.execute("""update unidades set prefiltro_plan_id = null
                                 where prefiltro_plan_id = %s returning id""",
                              (plan_id,)).fetchall()
    fila = cx.execute("delete from mantenimiento_planes where id = %s returning id",
                      (plan_id,)).fetchone()
    if not fila:
        raise ValueError("Ese plan no existe.")
    return {"ok": True, "unidades": len(cuantas)}


def asignar(cx, datos, usuario=None):
    """Le pone un plan preventivo (o de prefiltro) a una unidad, o se lo saca.

    Son dos lugares distintos: el plan de service y el de prefiltro. Poner
    uno no toca el otro.
    """
    _exigir_gestor(usuario)
    prefiltro = datos.get("campo") == "prefiltro"
    if prefiltro and not hay_prefiltros(cx):
        raise ValueError(FALTA_PREFILTROS)
    unidad_id = _entero(datos.get("unidad_id"), "La unidad", minimo=1)
    plan_id = _entero(datos.get("plan_id"), "El plan", minimo=1)
    if plan_id:
        plan = cx.execute("select clase from mantenimiento_planes where id = %s",
                          (plan_id,)).fetchone()
        if not plan:
            raise ValueError("Ese plan no existe.")
        if prefiltro and plan["clase"] != "prefiltro":
            raise ValueError("Como prefiltro se asigna un plan de prefiltro.")
        if not prefiltro and plan["clase"] != "preventivo":
            raise ValueError("A una unidad se le asigna un plan preventivo: el "
                             "correctivo es un catálogo de trabajos, no una agenda, "
                             "y el de prefiltro va en su propia columna.")
    columna = "prefiltro_plan_id" if prefiltro else "mantenimiento_plan_id"
    fila = cx.execute(f"""update unidades set {columna} = %s, actualizado = now()
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
        "parametros": {**{k: DE_FABRICA[k] for k in DEL_SISTEMA}, **(p or {})},
        "de_fabrica": DE_FABRICA,
        "instalado": p is not None,
        "planes": planes(cx),
        "prefiltros": hay_prefiltros(cx),
        "asignaciones": _asignaciones(cx),
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


def _asignaciones(cx):
    prefiltro = hay_prefiltros(cx)
    return [dict(a) for a in cx.execute(f"""
        select u.id as unidad_id, u.patente, u.interno, u.sucursal,
               u.mantenimiento_plan_id as plan_id, p.nombre as plan_nombre,
               p.cada_km, p.cada_dias,
               {"u.prefiltro_plan_id" if prefiltro else "null::bigint"} as prefiltro_id,
               {"pf.cada_km" if prefiltro else "null::numeric"} as prefiltro_cada_km
        from unidades u
        left join mantenimiento_planes p on p.id = u.mantenimiento_plan_id
        {"left join mantenimiento_planes pf on pf.id = u.prefiltro_plan_id" if prefiltro else ""}
        where u.activa and u.tipo = 'vehiculo'
        order by u.patente""").fetchall()]


def importar(cx, datos, usuario=None):
    """Asigna planes por patente desde un Excel (PATENTE · TIPO DE SERVICE)."""
    _exigir_gestor(usuario)
    prefiltro = datos.get("campo") == "prefiltro"
    if prefiltro and not hay_prefiltros(cx):
        raise ValueError(FALTA_PREFILTROS)
    try:
        contenido = base64.b64decode(str(datos.get("archivo_b64") or ""), validate=True)
    except Exception:
        raise ValueError("El archivo recibido no es válido.") from None
    if not contenido or len(contenido) > 2 * 1024 * 1024:
        raise ValueError("El Excel está vacío o supera los 2 MB.")
    try:
        salida = mantenimiento.importar(cx, contenido, prefiltro=prefiltro)
    except (zipfile.BadZipFile, ElementTree.ParseError, KeyError, IndexError):
        raise ValueError("No se pudo leer el Excel. Tiene que ser un .xlsx con las "
                         "columnas PATENTE y TIPO DE SERVICE.") from None
    return {"ok": True, **salida}


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
    if op == "importar":
        return importar(cx, datos, usuario)
    if op == "restablecer":
        return restablecer(cx, datos, usuario)
    if op == "reglas":
        _exigir_admin(usuario, "cambiar los umbrales de aviso")
        return {"ok": True, "reglas": alertas.guardar_reglas(cx, datos)}
    raise ValueError("No entiendo qué parámetro hay que cambiar.")
