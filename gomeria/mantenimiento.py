"""Planes de mantenimiento reutilizables y asignación por unidad."""

GESTORES = {"admin", "encargado"}


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
