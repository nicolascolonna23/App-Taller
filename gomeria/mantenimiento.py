"""Planes de mantenimiento: qué service es, cada cuánto, y a quién le toca.

Hasta acá el intervalo vivía suelto en cada service: un número en la fila,
que salió de la planilla al importar. Eso no es un criterio: si el que
carga el service se equivoca en ese número, cambió cuándo le toca a esa
unidad y nadie se entera.

El plan lo separa en dos. El PLAN dice qué service es y cada cuántos
kilómetros se hace, y se define una vez. La UNIDAD tiene los planes que le
corresponden —varios, porque un camión tiene M1, M2 y M3 corriendo en
paralelo— y cada uno cuenta y avisa por su cuenta.
"""

import base64
import io
import re
import zipfile
from xml.etree import ElementTree as ET

GESTORES = {"admin", "encargado"}


def _clave(texto):
    return " ".join(str(texto or "").strip().upper().split())


def _patente(texto):
    return re.sub(r"[^A-Z0-9]", "", str(texto or "").upper())


def _filas_xlsx(contenido):
    """Lee las dos primeras columnas de un XLSX usando solo la librería estándar."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        compartidas = []
        if "xl/sharedStrings.xml" in z.namelist():
            raiz = ET.fromstring(z.read("xl/sharedStrings.xml"))
            compartidas = ["".join(n.text or "" for n in si.findall(".//m:t", ns))
                           for si in raiz.findall("m:si", ns)]
        hojas = sorted(n for n in z.namelist()
                       if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        if not hojas:
            raise ValueError("El Excel no tiene hojas para importar.")
        raiz = ET.fromstring(z.read(hojas[0]))
        filas = []
        for row in raiz.findall(".//m:sheetData/m:row", ns):
            valores = {}
            for celda in row.findall("m:c", ns):
                col = re.match(r"[A-Z]+", celda.get("r", ""))
                if not col or col.group() not in {"A", "B"}:
                    continue
                tipo = celda.get("t")
                if tipo == "inlineStr":
                    valor = "".join(n.text or "" for n in celda.findall(".//m:t", ns))
                else:
                    nodo = celda.find("m:v", ns)
                    valor = nodo.text if nodo is not None else ""
                    if tipo == "s" and valor != "":
                        valor = compartidas[int(valor)]
                valores[col.group()] = valor
            if valores:
                filas.append((valores.get("A", ""), valores.get("B", "")))
    if filas and _clave(filas[0][0]) == "PATENTE":
        filas = filas[1:]
    return filas


def importar(cx, contenido):
    filas = _filas_xlsx(contenido)
    planes = {_clave(p["nombre"]): p for p in cx.execute(
        "select id,nombre from mantenimiento_planes where activo").fetchall()}
    unidades = {_patente(u["patente"]): u for u in cx.execute(
        "select id,patente from unidades where activa and tipo='vehiculo'").fetchall()}
    faltan_planes, faltan_patentes, sin_datos = set(), [], []
    asignadas = 0
    for patente_txt, plan_txt in filas:
        patente, nombre = _patente(patente_txt), _clave(plan_txt)
        if not patente or not nombre:
            continue
        if nombre == "SIN DATOS":
            sin_datos.append(patente_txt)
            continue
        unidad, plan = unidades.get(patente), planes.get(nombre)
        if not unidad:
            faltan_patentes.append(patente_txt)
        elif not plan:
            faltan_planes.add(plan_txt)
        else:
            cx.execute("""insert into unidad_planes (unidad_id, plan_id)
                          values (%s, %s) on conflict (unidad_id, plan_id) do nothing""",
                       (unidad["id"], plan["id"]))
            asignadas += 1
    return {"asignadas": asignadas, "total": len(filas),
            "planes_faltantes": sorted(faltan_planes),
            "patentes_faltantes": faltan_patentes, "sin_datos": sin_datos}


def _gestor(usuario):
    if (usuario or {}).get("rol") not in GESTORES:
        raise PermissionError(
            "Solo un encargado o administrador puede parametrizar services.")


# =====================================================================
# LECTURA
# =====================================================================
def planes(cx):
    """Los planes activos, con cuántas unidades tiene cada uno."""
    return cx.execute("""
        select p.id, p.nombre, p.descripcion, p.cada_km, p.activo,
               count(up.unidad_id)::int as unidades
        from mantenimiento_planes p
        left join unidad_planes up on up.plan_id = p.id
        where p.activo
        group by p.id order by p.nombre
    """).fetchall()


def listar(cx):
    """Los planes, a quién le tocan y qué modelos hay para asignar en bloque."""
    return {
        "planes": planes(cx),
        "asignaciones": cx.execute("""
            select u.id as unidad_id, u.patente, u.interno, u.modelo,
                   coalesce(array_agg(up.plan_id order by up.plan_id)
                            filter (where up.plan_id is not null),
                            '{}')::bigint[] as planes
            from unidades u
            left join unidad_planes up on up.unidad_id = u.id
            where u.activa and u.tipo = 'vehiculo'
            group by u.id order by u.patente
        """).fetchall(),
        # El plan de mantenimiento lo fija la fábrica por modelo, así que
        # asignarlo por modelo es como de verdad se decide.
        "modelos": cx.execute("""
            select modelo, count(*)::int as unidades
            from unidades where activa and coalesce(modelo, '') <> ''
            group by modelo order by modelo
        """).fetchall(),
    }


def planes_por_unidad(cx):
    """unidad_id → [plan_id, …]. Para dibujar la asignación en la ficha."""
    salida = {}
    for f in cx.execute("select unidad_id, plan_id from unidad_planes").fetchall():
        salida.setdefault(f["unidad_id"], []).append(f["plan_id"])
    return salida


# =====================================================================
# ESCRITURA
# =====================================================================
def aplicar(cx, datos, usuario):
    _gestor(usuario)
    op = str(datos.get("op") or "").strip()
    if op == "importar":
        bruto = str(datos.get("archivo_b64") or "")
        try:
            contenido = base64.b64decode(bruto, validate=True)
        except Exception as e:
            raise ValueError("El archivo recibido no es válido.") from e
        if not contenido or len(contenido) > 2 * 1024 * 1024:
            raise ValueError("El Excel está vacío o supera los 2 MB.")
        salida = importar(cx, contenido)
        salida.update(listar(cx))
        return salida
    if op == "plan_guardar":
        _guardar_plan(cx, datos)
    elif op == "plan_borrar":
        _borrar_plan(cx, datos.get("id"))
    elif op == "asignar":
        _asignar(cx, datos.get("unidad_id"), datos.get("planes"), usuario)
    elif op == "asignar_modelo":
        _asignar_modelo(cx, datos.get("modelo"), datos.get("planes"), usuario)
    else:
        raise ValueError("Operación de mantenimiento desconocida.")
    return listar(cx)


def _guardar_plan(cx, datos):
    """Crea o modifica un plan. El nombre lo elige el taller: lo lee el taller."""
    nombre = " ".join(str(datos.get("nombre") or "").split())[:60]
    if not nombre:
        raise ValueError("Ponele un nombre al plan: M1, M2, Service auto…")
    descripcion = " ".join(str(datos.get("descripcion") or "").split())[:300] or None
    try:
        cada = float(datos.get("cada_km"))
    except (TypeError, ValueError):
        raise ValueError("«Cada cuántos km» tiene que ser un número.")
    if cada <= 0:
        raise ValueError("«Cada cuántos km» tiene que ser mayor que cero.")
    # Un cero de más en 45.000 no lo ve nadie hasta que la unidad no avisa
    # nunca más.
    if cada > 1_000_000:
        raise ValueError("Ese intervalo no es de un service. Revisá el número.")

    plan_id = int(datos.get("id") or 0)
    try:
        if plan_id:
            fila = cx.execute("""
                update mantenimiento_planes
                   set nombre = %s, descripcion = %s, cada_km = %s,
                       activo = true, actualizado = now()
                 where id = %s returning id""",
                (nombre, descripcion, cada, plan_id)).fetchone()
            if not fila:
                raise ValueError("Ese plan no existe.")
        else:
            cx.execute("""
                insert into mantenimiento_planes (nombre, descripcion, cada_km)
                values (%s, %s, %s)""", (nombre, descripcion, cada))
    except Exception as e:
        # Dos planes con el mismo nombre serían dos opciones idénticas en la
        # lista, y nadie sabría cuál eligió.
        if "mantenimiento_planes_nombre_key" in str(e):
            cx.rollback()
            raise ValueError(f"Ya hay un plan que se llama «{nombre}».")
        raise


def _borrar_plan(cx, plan_id):
    """Saca un plan de circulación.

    Si nunca se usó, se borra. Si ya tiene services registrados, se marca
    inactivo y desaparece de las listas, pero la historia de lo que se hizo
    bajo ese plan no se toca: borrarla sería perder de qué fue cada service.
    """
    plan_id = int(plan_id or 0)
    if not cx.execute("select 1 from mantenimiento_planes where id = %s",
                      (plan_id,)).fetchone():
        raise ValueError("Ese plan no existe.")
    cx.execute("delete from unidad_planes where plan_id = %s", (plan_id,))
    usado = cx.execute("select 1 from services where plan_id = %s limit 1",
                       (plan_id,)).fetchone()
    if usado:
        cx.execute("""update mantenimiento_planes set activo = false,
                      actualizado = now() where id = %s""", (plan_id,))
        return "inactivado"
    cx.execute("delete from mantenimiento_planes where id = %s", (plan_id,))
    return "borrado"


def _validos(cx, plan_ids):
    """Los planes que existen y están activos, de los que mandaron."""
    pedidos = [int(x) for x in (plan_ids or []) if str(x).strip()]
    if not pedidos:
        return []
    validos = {f["id"] for f in cx.execute(
        "select id from mantenimiento_planes where activo and id = any(%s)",
        (pedidos,)).fetchall()}
    if set(pedidos) - validos:
        raise ValueError("Alguno de los planes elegidos ya no existe.")
    return sorted(validos)


def _asignar(cx, unidad_id, plan_ids, usuario=None):
    """Deja a la unidad exactamente con los planes que se le pasan."""
    unidad_id = int(unidad_id or 0)
    if not cx.execute("select 1 from unidades where id = %s", (unidad_id,)).fetchone():
        raise ValueError("Esa unidad no existe.")
    validos = _validos(cx, plan_ids)
    cx.execute("delete from unidad_planes where unidad_id = %s", (unidad_id,))
    for plan_id in validos:
        cx.execute("""insert into unidad_planes (unidad_id, plan_id, usuario)
                      values (%s, %s, %s)""",
                   (unidad_id, plan_id, (usuario or {}).get("nombre")))
    return len(validos)


def _asignar_modelo(cx, modelo, plan_ids, usuario=None):
    """Le pone los mismos planes a todas las unidades activas de un modelo.

    Con cien unidades, asignarlas de a una es media tarde. El plan lo fija
    la fábrica por modelo, así que es la forma en que de verdad se decide.
    """
    modelo = " ".join(str(modelo or "").split())
    if not modelo:
        raise ValueError("Elegí el modelo.")
    validos = _validos(cx, plan_ids)
    unidades = cx.execute("select id from unidades where activa and modelo = %s",
                          (modelo,)).fetchall()
    if not unidades:
        raise ValueError(f"No hay unidades activas del modelo «{modelo}».")
    for u in unidades:
        cx.execute("delete from unidad_planes where unidad_id = %s", (u["id"],))
        for plan_id in validos:
            cx.execute("""insert into unidad_planes (unidad_id, plan_id, usuario)
                          values (%s, %s, %s)""",
                       (u["id"], plan_id, (usuario or {}).get("nombre")))
    return len(unidades)
