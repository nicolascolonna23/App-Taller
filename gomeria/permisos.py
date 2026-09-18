"""Quién entra, con qué rol, y qué abre cada rol.

Tres ideas, y el módulo entero sale de ellas:

  1. El **módulo** es la unidad de permiso. No hay permisos de botón: o se
     abre Combustible o no se abre. Un permiso más fino se explica peor y
     termina mal configurado, que es lo mismo que no tenerlo.

  2. El rol es una **fila**, no una constante del código. Se crea, se le
     marcan módulos y se le asignan usuarios desde la pantalla. Los que
     vienen de fábrica —admin, encargado, operario, sucursal, taller,
     mecánico y chofer— no se borran: hay gente colgando de ellos.

  3. Cuatro permisos no son módulos sino **nivel**, porque atraviesan
     todo:

         repara            carga trabajos y repuestos en una orden
                           abierta. Es el mecánico: hace, no aprueba.
         gestiona          aprueba, cierra y corrige. El responsable de
                           taller y mantenimiento.
         administra        usuarios, roles, parámetros, borrar y reabrir.
         solo_su_sucursal  ve lo de su boca y nada más. El responsable de
                           sucursal y el chofer.

El catálogo de módulos vive acá y no en la base: un módulo es una pantalla
con sus direcciones, y eso lo sabe el código. La base guarda a quién se le
habilitó cada uno.

La lista blanca la revisa el servidor en cada pedido (ver `_exigir_sesion`
en app.py). Esconder el botón en la pantalla es comodidad, no seguridad.
"""
import re

import auth

# (código, nombre, la dirección de la pantalla, para qué es)
MODULOS = (
    ("choferes", "Reportar fallas", "/choferes/", "Fallas y fotos con envío pendiente sin conexión."),
    ("flota",        "Flota y services",   "/flota",
     "Panel general, control de flota y mantenimiento."),
    ("unidades",     "Maestro de unidades", "/unidades",
     "La ficha de cada vehículo: marca, chasis, chofer, sucursal."),
    ("gomeria",      "Gomería",            "/gomeria",
     "Cubiertas: montaje, rotación, desgaste y stock."),
    ("repuestos",    "Repuestos",          "/repuestos",
     "Stock del depósito, movimientos y remitos."),
    ("ordenes",      "Órdenes de trabajo", "/ordenes",
     "La hoja de la unidad que entra al taller y los servicios externos."),
    ("solicitudes",  "Solicitudes de orden de compra", "/solicitudes",
     "Pedir, aprobar y rendir el trabajo de taller. Es el módulo de las sucursales."),
    ("combustible",  "Combustible",        "/combustible",
     "Tickets, cruce con la estación y consumo."),
    ("alertas",      "Alertas",            "/alertas",
     "Todo lo que hay que mirar hoy, de las cuatro fuentes."),
    ("vencimientos", "Vencimientos",       "/vencimientos",
     "Papeles de las unidades y licencias de los choferes."),
    ("asistente",    "Asistente",          "/asistente",
     "Consultas en castellano sobre los datos del sistema."),
    ("usuarios",     "Usuarios y roles",   "/usuarios",
     "Altas, bajas, contraseñas y qué abre cada rol."),
    ("parametros",   "Parámetros",         "/parametros",
     "De dónde salen los kilómetros, los planes de mantenimiento y los umbrales de aviso."),
)

CODIGOS = tuple(m[0] for m in MODULOS)

# Lo que se abre sin permiso de nadie: la portada, la configuración de la
# apariencia —que es de cada uno— y salir. Un sistema donde alguien entra
# y no puede ni ver su nombre no es un sistema con permisos, es una puerta
# cerrada.
LIBRES = ("/", "/configuracion", "/movil", "/salir")

# Qué módulo protege cada dirección. Las que no están acá —los archivos
# estáticos, el login, /api/yo— no piden módulo.
#
# El orden importa: se busca primero la coincidencia exacta y después por
# prefijo, así `/api/unidades/exportar` cae en el módulo de unidades sin
# tener que nombrarla.
RUTAS = {
    "/fallas": "solicitudes", "/choferes/": "choferes",
    "/flota": "flota", "/control": "flota", "/api/flota": "flota",
    "/unidades": "unidades", "/api/unidades": "unidades",
    "/gomeria": "gomeria", "/api/tablero": "gomeria", "/api/movimiento": "gomeria",
    "/repuestos": "repuestos", "/api/repuestos": "repuestos",
    "/ordenes": "ordenes", "/api/ordenes": "ordenes", "/api/factura": "ordenes",
    "/solicitudes": "solicitudes", "/api/solicitudes": "solicitudes",
    "/combustible": "combustible", "/api/combustible": "combustible",
    # Los fluidos son la solapa del depósito adentro de Combustible: el
    # mismo módulo, porque el que carga gasoil es el que carga urea.
    "/api/fluidos": "combustible",
    "/alertas": "alertas", "/api/alertas": "alertas",
    "/vencimientos": "vencimientos", "/api/vencimientos": "vencimientos",
    "/asistente": "asistente", "/api/asistente": "asistente",
    "/usuarios": "usuarios", "/api/usuarios": "usuarios",
    "/parametros": "parametros", "/api/parametros": "parametros",
    # El catálogo de marcas y medidas no pide módulo: lo leen todas las
    # pantallas de gomería para sus desplegables. Tocarlo exige gestionar,
    # y eso lo revisa marcas.py.
    # El enganche tractor–semi es un submódulo de Flota: se abre desde el
    # maestro de unidades y vive de sus mismos datos.
    "/api/enganches": "unidades",
}

PREFIJOS = (
    ("/api/unidades/", "unidades"),
    ("/api/repuestos/", "repuestos"),
    ("/api/solicitudes/", "solicitudes"),
    ("/gomeria/", "gomeria"),
    ("/u/", "gomeria"),
)


def modulo_de(ruta):
    """El módulo que protege esa dirección, o None si no pide ninguno."""
    ruta = (ruta or "").split("?")[0]
    if ruta in LIBRES:
        return None
    if ruta in RUTAS:
        return RUTAS[ruta]
    for prefijo, modulo in PREFIJOS:
        if ruta.startswith(prefijo):
            return modulo
    return None


# =====================================================================
# LEER LOS PERMISOS
# =====================================================================
def permisos(cx, rol):
    """Lo que puede ese rol. Con la tabla sin crear, devuelve None.

    None no es "no puede nada": es "esta base todavía no corrió
    27_roles.sql". El que llama tiene que dejar pasar, porque hasta ese
    día el sistema no tenía permisos por módulo y nadie tiene por qué
    quedarse afuera por una migración que no se corrió.
    """
    try:
        fila = cx.execute("""
            select r.codigo, r.nombre, r.gestiona, r.administra, r.pide_sucursal,
                   coalesce(r.repara, r.gestiona) as repara,
                   coalesce(r.solo_su_sucursal, false) as solo_su_sucursal,
                   r.activo,
                   coalesce(array_agg(m.modulo) filter (where m.modulo is not null),
                            '{}') as modulos
            from roles r
            left join rol_modulos m on m.rol_codigo = r.codigo
            where r.codigo = %s
            group by r.codigo, r.nombre, r.gestiona, r.administra,
                     r.pide_sucursal, r.repara, r.solo_su_sucursal, r.activo
        """, (str(rol or ""),)).fetchone()
    except Exception:
        cx.rollback()
        return None
    if not fila:
        # El rol no existe: no se le inventan permisos.
        return {"codigo": rol, "nombre": rol, "gestiona": False, "administra": False,
                "repara": False, "solo_su_sucursal": False,
                "pide_sucursal": False, "activo": False, "modulos": []}
    return dict(fila)


def con_permisos(cx, usuario):
    """El usuario de la sesión, con lo que su rol le permite.

    Se le cuelgan tres cosas: `modulos`, `gestiona` y `administra`. El
    resto del sistema pregunta por eso y no por el nombre del rol, así un
    rol nuevo no obliga a tocar cinco archivos.
    """
    if not usuario:
        return usuario
    usuario = dict(usuario)
    p = permisos(cx, usuario.get("rol"))
    if p is None:
        # Sin el módulo de roles corrido: como siempre fue.
        usuario["modulos"] = list(CODIGOS)
        usuario["gestiona"] = usuario.get("rol") in ("admin", "encargado")
        usuario["administra"] = usuario.get("rol") == "admin"
        usuario["repara"] = usuario["gestiona"]
        usuario["solo_su_sucursal"] = False
        usuario["rol_nombre"] = usuario.get("rol")
        return usuario
    usuario["modulos"] = list(p["modulos"])
    usuario["gestiona"] = bool(p["gestiona"])
    usuario["repara"] = bool(p.get("repara")) or bool(p["gestiona"])
    usuario["solo_su_sucursal"] = bool(p.get("solo_su_sucursal"))
    usuario["rol_nombre"] = p["nombre"]
    # El maestro administra siempre, aunque alguien le toque los permisos
    # al rol: es el seguro contra quedarse afuera del propio sistema.
    usuario["administra"] = bool(p["administra"]) or bool(usuario.get("es_maestro"))
    return usuario


def puede_ver(usuario, modulo):
    if not modulo:
        return True
    usuario = usuario or {}
    if usuario.get("administra"):
        return True          # el que administra no se cierra afuera solo
    return modulo in (usuario.get("modulos") or ())


def gestiona(usuario):
    """Nivel taller: aprueba, cierra, corrige.

    Mientras 27_roles.sql no esté corrido, `gestiona` no viene en el
    usuario y se cae al rol de siempre. Así el módulo de órdenes anda
    igual en una base vieja.
    """
    usuario = usuario or {}
    if "gestiona" in usuario:
        return bool(usuario["gestiona"])
    return usuario.get("rol") in ("admin", "encargado")


def repara(usuario):
    """Nivel mecánico: carga en la orden lo que hizo y lo que puso.

    El que gestiona repara también: el que cierra una orden puede cargarle
    un renglón.
    """
    usuario = usuario or {}
    if "repara" in usuario:
        return bool(usuario["repara"]) or gestiona(usuario)
    return gestiona(usuario)


def solo_su_sucursal(usuario):
    """¿Este rol ve solo lo de su boca?

    Sin sucursal cargada no hay nada que recortar: se deja ver todo antes
    que dejar a alguien mirando una pantalla vacía sin entender por qué.
    """
    usuario = usuario or {}
    return bool(usuario.get("solo_su_sucursal")) and bool(usuario.get("sucursal_codigo"))


def sucursal_de(usuario):
    """La sucursal por la que hay que filtrar, o None si ve toda la red."""
    return (usuario or {}).get("sucursal_codigo") if solo_su_sucursal(usuario) else None


def administra(usuario):
    usuario = usuario or {}
    if usuario.get("es_maestro"):
        return True
    if "administra" in usuario:
        return bool(usuario["administra"])
    return usuario.get("rol") == "admin"


# =====================================================================
# ADMINISTRAR — lo que hace la pantalla /usuarios
# =====================================================================
# Un usuario es lo que se escribe para entrar: sin espacios, sin acentos y
# sin mayúsculas, porque la mitad de las veces se tipea en un teléfono.
FORMATO_USUARIO = re.compile(r"^[a-z0-9._-]{3,30}$")


def _exigir_admin(usuario):
    if not administra(usuario):
        raise PermissionError("Solo un administrador puede tocar usuarios y roles.")


def _texto(valor, limite=200):
    texto = str(valor or "").strip()
    return texto[:limite] or None


def _codigo(valor):
    codigo = str(valor or "").strip().lower().replace(" ", "_")
    if not re.match(r"^[a-z0-9_]{3,20}$", codigo):
        raise ValueError("El código del rol va en minúsculas, sin espacios ni acentos "
                         "(entre 3 y 20 caracteres).")
    return codigo


def _modulos(valores):
    pedidos = [str(m).strip().lower() for m in (valores or [])]
    desconocidos = [m for m in pedidos if m not in CODIGOS]
    if desconocidos:
        raise ValueError(f"No existe el módulo {desconocidos[0]}.")
    return sorted(set(pedidos))


def _usuario(cx, usuario_id):
    try:
        usuario_id = int(usuario_id)
    except (TypeError, ValueError):
        raise ValueError("No se sabe de qué usuario se habla.") from None
    fila = cx.execute("select * from usuarios where id = %s", (usuario_id,)).fetchone()
    if not fila:
        raise ValueError("Ese usuario no existe.")
    return fila


def _rol(cx, codigo):
    fila = cx.execute("select * from roles where codigo = %s", (codigo,)).fetchone()
    if not fila:
        raise ValueError(f"No existe el rol {codigo}.")
    return fila


def _exigir_sucursal(cx, rol, sucursal):
    """Un rol de sucursal sin sucursal no puede pedir nada.

    La solicitud se numera según quién la pide: un responsable de boca sin
    su código cargado abriría la pantalla y no podría usarla.
    """
    fila = _rol(cx, rol)
    if fila["pide_sucursal"] and not sucursal:
        raise ValueError(f"El rol «{fila['nombre']}» necesita que le asignes "
                         "una sucursal al usuario.")
    return fila


def _quedan_administradores(cx, excepto_id=None, rol_nuevo=None):
    """¿Queda alguien que pueda administrar después de este cambio?

    Es la única validación que no protege un dato sino al sistema: una
    base sin administradores activos no se arregla desde la pantalla, se
    arregla con SQL a mano.
    """
    filas = cx.execute("""
        select u.id, u.rol from usuarios u
        join roles r on r.codigo = u.rol
        where u.activo and r.administra
    """).fetchall()
    quedan = [f for f in filas if f["id"] != excepto_id]
    if rol_nuevo is not None and excepto_id is not None:
        rol = cx.execute("select administra from roles where codigo = %s",
                         (rol_nuevo,)).fetchone()
        if rol and rol["administra"]:
            quedan.append({"id": excepto_id})
    return bool(quedan)


# ---------------------------------------------------------------------
# LECTURA
# ---------------------------------------------------------------------
def panel(cx, usuario):
    """Todo lo que dibuja la pantalla de usuarios."""
    _exigir_admin(usuario)
    usuarios = cx.execute("""
        select u.id, u.usuario, u.nombre, u.rol, u.activo, u.creado,
               u.ultimo_ingreso, u.sucursal_codigo,
               coalesce(u.es_maestro, false) as es_maestro,
               coalesce(r.nombre, u.rol) as rol_nombre,
               coalesce(r.administra, false) as administra,
               (select count(*) from sesiones s
                where s.usuario_id = u.id and s.expira > now()) as sesiones
        from usuarios u
        left join roles r on r.codigo = u.rol
        order by u.activo desc, u.usuario
    """).fetchall()

    roles = cx.execute("""
        select r.*,
               coalesce(array_agg(m.modulo) filter (where m.modulo is not null),
                        '{}') as modulos,
               (select count(*) from usuarios u where u.rol = r.codigo) as usuarios
        from roles r
        left join rol_modulos m on m.rol_codigo = r.codigo
        group by r.codigo
        order by r.orden, r.nombre
    """).fetchall()

    try:
        sucursales = [dict(s) for s in cx.execute("""
            select codigo, nombre from sucursales where activa
            order by orden, codigo""").fetchall()]
    except Exception:
        # Sin el módulo de solicitudes corrido no hay sucursales que
        # asignar. La pantalla sigue sirviendo para todo lo demás.
        cx.rollback()
        sucursales = []

    return {
        "usuarios": [dict(u) for u in usuarios],
        "roles": [dict(r) for r in roles],
        "yo_maestro": bool((usuario or {}).get("es_maestro")),
        "modulos": [{"codigo": c, "nombre": n, "ruta": ruta, "detalle": d}
                    for c, n, ruta, d in MODULOS],
        "sucursales": sucursales,
        "yo": (usuario or {}).get("id"),
    }


# ---------------------------------------------------------------------
# ESCRITURA — usuarios
# ---------------------------------------------------------------------
def crear(cx, datos, usuario):
    """Da de alta a alguien. Nace activo y con su contraseña."""
    _exigir_admin(usuario)
    nombre_usuario = str(datos.get("usuario") or "").strip().lower()
    if not FORMATO_USUARIO.match(nombre_usuario):
        raise ValueError("El usuario va en minúsculas, sin espacios ni acentos "
                         "(entre 3 y 30 caracteres).")
    if cx.execute("select 1 from usuarios where usuario = %s",
                  (nombre_usuario,)).fetchone():
        raise ValueError(f"El usuario «{nombre_usuario}» ya existe.")

    nombre = _texto(datos.get("nombre"), 120)
    if not nombre:
        raise ValueError("Falta el nombre y apellido: es el que firma los partes.")
    rol = _texto(datos.get("rol"), 20) or "operario"
    sucursal = _texto(datos.get("sucursal_codigo"), 3)
    _exigir_sucursal(cx, rol, sucursal)

    clave = str(datos.get("clave") or "")
    problema = auth.revisar_clave(clave)
    if problema:
        raise ValueError(problema)

    nuevo = cx.execute("""
        insert into usuarios (usuario, nombre, hash, rol, sucursal_codigo)
        values (%s,%s,%s,%s,%s) returning id
    """, (nombre_usuario, nombre, auth.hashear(clave), rol,
          (sucursal or "").upper() or None)).fetchone()
    return {"ok": True, "id": nuevo["id"], "usuario": nombre_usuario}


def guardar(cx, datos, usuario):
    """Cambia el nombre, el rol o la sucursal de alguien."""
    _exigir_admin(usuario)
    fila = _usuario(cx, datos.get("id"))
    nombre = _texto(datos.get("nombre"), 120) or fila["nombre"]
    rol = _texto(datos.get("rol"), 20) or fila["rol"]
    sucursal = _texto(datos.get("sucursal_codigo"), 3)
    if "sucursal_codigo" not in datos:
        sucursal = fila["sucursal_codigo"]
    _exigir_sucursal(cx, rol, sucursal)

    # El maestro es el seguro del sistema: su rol no se toca desde la
    # pantalla, ni siquiera él mismo. Se mueve con una línea de SQL, que
    # está escrita en 29_parametros.sql.
    if fila.get("es_maestro") and rol != fila["rol"]:
        raise ValueError("Ese es el usuario maestro: su rol no se cambia desde acá.")

    if not _quedan_administradores(cx, excepto_id=fila["id"], rol_nuevo=rol):
        raise ValueError("Es el único administrador activo. Nombrá otro antes "
                         "de cambiarle el rol a este.")

    cx.execute("""update usuarios set nombre = %s, rol = %s, sucursal_codigo = %s
                  where id = %s""",
               (nombre, rol, (sucursal or "").upper() or None, fila["id"]))
    # Cambiarle el rol a alguien que está adentro tiene que valer ya: si
    # se le sacó un módulo, no puede seguir abriéndolo hasta mañana.
    if rol != fila["rol"]:
        cx.execute("delete from sesiones where usuario_id = %s", (fila["id"],))
    return {"ok": True, "id": fila["id"]}


def estado(cx, datos, usuario):
    """Alta o baja. No se borra a nadie: su firma está en lo que cargó."""
    _exigir_admin(usuario)
    fila = _usuario(cx, datos.get("id"))
    activo = bool(datos.get("activo"))
    if not activo:
        if fila.get("es_maestro"):
            raise ValueError("Ese es el usuario maestro: no se da de baja.")
        if fila["id"] == (usuario or {}).get("id"):
            raise ValueError("No podés darte de baja a vos mismo.")
        if not _quedan_administradores(cx, excepto_id=fila["id"]):
            raise ValueError("Es el único administrador activo. Nombrá otro antes "
                             "de darlo de baja.")
    cx.execute("update usuarios set activo = %s where id = %s", (activo, fila["id"]))
    if not activo:
        # Darlo de baja es que no entre más, no que termine el día.
        cx.execute("delete from sesiones where usuario_id = %s", (fila["id"],))
    return {"ok": True, "id": fila["id"], "activo": activo}


def clave(cx, datos, usuario):
    """Le pone una contraseña nueva. Corta lo que tenga abierto."""
    _exigir_admin(usuario)
    fila = _usuario(cx, datos.get("id"))
    auth.cambiar_clave(cx, fila["id"], str(datos.get("clave") or ""))
    return {"ok": True, "id": fila["id"]}


# ---------------------------------------------------------------------
# ESCRITURA — roles
# ---------------------------------------------------------------------
def guardar_rol(cx, datos, usuario):
    """Crea un rol o le cambia el nombre, el nivel y sus módulos."""
    _exigir_admin(usuario)
    codigo = _codigo(datos.get("codigo"))
    nombre = _texto(datos.get("nombre"), 60)
    if not nombre:
        raise ValueError("Falta el nombre del rol: es lo que se lee en la pantalla.")
    modulos = _modulos(datos.get("modulos"))
    existente = cx.execute("select * from roles where codigo = %s", (codigo,)).fetchone()

    administra_nuevo = bool(datos.get("administra"))
    if existente and existente["administra"] and not administra_nuevo:
        # Sacarle la administración al rol que la tiene puede dejar el
        # sistema sin nadie que entre a arreglarlo.
        otros = cx.execute("""
            select 1 from usuarios u join roles r on r.codigo = u.rol
            where u.activo and r.administra and u.rol <> %s limit 1""",
            (codigo,)).fetchone()
        if not otros:
            raise ValueError("Es el único rol que administra y hay gente usándolo. "
                             "Creá otro rol que administre antes de sacarle esto.")

    cx.execute("""
        insert into roles (codigo, nombre, descripcion, gestiona, administra,
                           pide_sucursal, orden)
        values (%s,%s,%s,%s,%s,%s,%s)
        on conflict (codigo) do update set
          nombre = excluded.nombre, descripcion = excluded.descripcion,
          gestiona = excluded.gestiona, administra = excluded.administra,
          pide_sucursal = excluded.pide_sucursal
    """, (codigo, nombre, _texto(datos.get("descripcion"), 300),
          bool(datos.get("gestiona")), administra_nuevo,
          bool(datos.get("pide_sucursal")),
          int(datos.get("orden") or 99)))

    # Los módulos se escriben enteros: la pantalla manda la lista final y
    # acá se deja exactamente eso. Sumar y restar renglones sueltos deja
    # permisos que nadie recuerda haber dado.
    cx.execute("delete from rol_modulos where rol_codigo = %s", (codigo,))
    for modulo in modulos:
        cx.execute("insert into rol_modulos (rol_codigo, modulo) values (%s,%s)",
                   (codigo, modulo))

    # Al que está adentro con ese rol le cambian los permisos ahora, no
    # cuando se le venza la sesión.
    if existente:
        cx.execute("""delete from sesiones where usuario_id in
                      (select id from usuarios where rol = %s)""", (codigo,))
    return {"ok": True, "codigo": codigo, "modulos": modulos}


def borrar_rol(cx, datos, usuario):
    """Saca un rol que no se usa. Los de fábrica no se tocan."""
    _exigir_admin(usuario)
    fila = _rol(cx, _codigo(datos.get("codigo")))
    if fila["de_sistema"]:
        raise ValueError(f"El rol «{fila['nombre']}» es de los que trae el sistema: "
                         "se puede editar, no borrar.")
    cuantos = cx.execute("select count(*) as n from usuarios where rol = %s",
                         (fila["codigo"],)).fetchone()["n"]
    if cuantos:
        raise ValueError(f"Hay {cuantos} usuario(s) con el rol «{fila['nombre']}». "
                         "Cambialos de rol antes de borrarlo.")
    cx.execute("delete from roles where codigo = %s", (fila["codigo"],))
    return {"ok": True, "codigo": fila["codigo"]}


# =====================================================================
def aplicar(cx, datos, usuario):
    """Punto de entrada de la API."""
    op = (datos.get("op") or "").strip()
    acciones = {"crear": crear, "guardar": guardar, "estado": estado, "clave": clave,
                "guardar_rol": guardar_rol, "borrar_rol": borrar_rol}
    if op in acciones:
        return acciones[op](cx, datos, usuario)
    raise ValueError("No entiendo qué hay que hacer con el usuario.")
