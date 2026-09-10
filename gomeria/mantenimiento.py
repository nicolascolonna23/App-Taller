"""Planes de mantenimiento reutilizables y asignación por unidad."""

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
        unidad = unidades.get(patente)
        if nombre == "SIN DATOS":
            if unidad:
                cx.execute("update unidades set mantenimiento_plan_id=null, actualizado=now() where id=%s",
                           (unidad["id"],))
            else:
                faltan_patentes.append(patente_txt)
            sin_datos.append(patente_txt)
            continue
        plan = planes.get(nombre)
        if not unidad:
            faltan_patentes.append(patente_txt)
        elif not plan:
            faltan_planes.add(plan_txt)
        else:
            cx.execute("update unidades set mantenimiento_plan_id=%s, actualizado=now() where id=%s",
                       (plan["id"], unidad["id"]))
            asignadas += 1
    return {"asignadas": asignadas, "total": len(filas),
            "planes_faltantes": sorted(faltan_planes),
            "patentes_faltantes": faltan_patentes, "sin_datos": sin_datos}


def _gestor(usuario):
    if (usuario or {}).get("rol") not in GESTORES:
        raise PermissionError("Solo un encargado o administrador puede parametrizar services.")


def listar(cx):
    return {
        "planes": cx.execute("""
            select p.id, p.nombre, p.descripcion, p.cada_km, p.activo,
                   count(u.id)::int as unidades
            from mantenimiento_planes p
            left join unidades u on u.mantenimiento_plan_id = p.id and u.activa
            group by p.id order by p.activo desc, p.nombre
        """).fetchall(),
        "asignaciones": cx.execute("""
            select u.id as unidad_id, u.patente, u.interno,
                   u.mantenimiento_plan_id as plan_id, p.nombre as plan_nombre,
                   p.cada_km
            from unidades u
            left join mantenimiento_planes p on p.id = u.mantenimiento_plan_id
            where u.activa and u.tipo = 'vehiculo' order by u.patente
        """).fetchall(),
    }


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
        nombre = " ".join(str(datos.get("nombre") or "").split())[:60]
        descripcion = " ".join(str(datos.get("descripcion") or "").split())[:300] or None
        cada = int(datos.get("cada_km") or 0)
        if not nombre or cada <= 0:
            raise ValueError("Completá el nombre y una frecuencia mayor que cero.")
        plan_id = int(datos.get("id") or 0)
        if plan_id:
            fila = cx.execute("""update mantenimiento_planes
                set nombre=%s, descripcion=%s, cada_km=%s, activo=true, actualizado=now()
                where id=%s returning id""", (nombre, descripcion, cada, plan_id)).fetchone()
            if not fila:
                raise ValueError("Ese plan no existe.")
        else:
            cx.execute("""insert into mantenimiento_planes(nombre,descripcion,cada_km)
                           values (%s,%s,%s)""", (nombre, descripcion, cada))
    elif op == "plan_borrar":
        plan_id = int(datos.get("id") or 0)
        cx.execute("update unidades set mantenimiento_plan_id=null where mantenimiento_plan_id=%s", (plan_id,))
        fila = cx.execute("delete from mantenimiento_planes where id=%s returning id", (plan_id,)).fetchone()
        if not fila:
            raise ValueError("Ese plan no existe.")
    elif op == "asignar":
        unidad_id = int(datos.get("unidad_id") or 0)
        plan_id = int(datos.get("plan_id") or 0) or None
        fila = cx.execute("""update unidades set mantenimiento_plan_id=%s, actualizado=now()
                             where id=%s returning id""", (plan_id, unidad_id)).fetchone()
        if not fila:
            raise ValueError("Esa unidad no existe.")
    else:
        raise ValueError("Operación de mantenimiento desconocida.")
    return listar(cx)
