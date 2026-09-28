"""Marcas y medidas de cubierta: lo que antes era texto libre y archivos.

La marca era un texto que cada uno escribía como quería —"FATE", "Fate",
"fate "— y el logo era un archivo que había que dejar en la carpeta
`marcas/` del repositorio, o sea que sumar una marca era hacer un deploy.

Acá son filas que se editan desde `/parametros`, y el logo se sube desde
la pantalla. Se guarda en la base y no en el disco porque el disco de
Render se borra en cada publicación: un logo subido a mano duraría hasta
el próximo deploy.

Las medidas son la otra mitad: qué medidas se usan y de qué familia es
cada una. La familia es lo que hace que el sistema no ofrezca una goma de
camión para un autoelevador, algo que ya sabía hacer pero lo sabía
escrito en el código.
"""
import base64
import re

import permisos

# Lo que un navegador sabe dibujar y no trae sorpresas. El SVG se acepta
# porque muchos logos de marca vienen así y pesan nada.
TIPOS = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
    "image/svg+xml": ".svg", "image/gif": ".gif",
}

# Un logo es un logo: 300 KB es holgado. Más que eso es una foto subida
# por error, y va a la base de datos de todos.
LOGO_MAXIMO = 300 * 1024

CLASES = ("camion", "autoelevador", "otro")


def _exigir_gestor(usuario, que="tocar las marcas"):
    if not permisos.gestiona(usuario):
        raise PermissionError(f"Solo un encargado o administrador puede {que}.")


def _texto(valor, limite=200):
    texto = " ".join(str(valor or "").split())
    return texto[:limite] or None


def slug_de(nombre):
    """«BF Goodrich» → «bfgoodrich». Es el nombre del archivo del logo."""
    return re.sub(r"[^a-z0-9]", "", str(nombre or "").lower())


def _entero(valor, campo, minimo=0):
    if valor in (None, ""):
        return None
    try:
        n = int(float(str(valor).replace(",", ".")))
    except (TypeError, ValueError):
        raise ValueError(f"{campo} tiene que ser un número.") from None
    if n < minimo:
        raise ValueError(f"{campo} no puede ser menor que {minimo}.")
    return n


def _logo(datos):
    """La imagen que llega de la pantalla: (bytes, tipo) o (None, None).

    Viene como data URL, que es lo que devuelve un `FileReader` en el
    navegador. Se valida acá porque lo que entra por la API no siempre
    pasó por nuestra pantalla.
    """
    crudo = str(datos.get("logo") or "").strip()
    if not crudo:
        return None, None
    m = re.match(r"^data:([\w/+.-]+);base64,(.+)$", crudo, re.S)
    if not m:
        raise ValueError("El logo tiene que llegar como imagen, no como texto.")
    tipo, contenido = m.group(1).lower(), m.group(2)
    if tipo not in TIPOS:
        raise ValueError(f"Ese tipo de imagen no va ({tipo}). "
                         "Sirve PNG, JPG, WEBP, GIF o SVG.")
    try:
        binario = base64.b64decode(contenido, validate=True)
    except Exception:
        raise ValueError("No se pudo leer la imagen.") from None
    if not binario:
        raise ValueError("La imagen llegó vacía.")
    if len(binario) > LOGO_MAXIMO:
        raise ValueError(f"El logo pesa {len(binario)//1024} KB y el máximo es "
                         f"{LOGO_MAXIMO//1024} KB. Guardalo más chico.")
    return binario, tipo


# =====================================================================
# LECTURA
# =====================================================================
def listar(cx, incluir_inactivas=False):
    """Las marcas, con si tienen logo cargado —no el logo, que pesa."""
    return [dict(m) for m in cx.execute(f"""
        select m.id, m.nombre, m.slug, m.activa, m.logo_tipo,
               m.logo is not null as tiene_logo,
               (select count(*) from cubiertas c
                where regexp_replace(lower(c.marca), '[^a-z0-9]', '', 'g') = m.slug
               )::int as cubiertas
        from cubiertas_marcas m
        {'' if incluir_inactivas else 'where m.activa'}
        order by m.activa desc, m.nombre
    """).fetchall()]


def medidas(cx, incluir_inactivas=False):
    return [dict(m) for m in cx.execute(f"""
        select d.id, d.medida, d.corta, d.clase, d.descripcion, d.activa, d.orden,
               (select count(*) from cubiertas c
                where btrim(c.medida) = d.medida)::int as cubiertas
        from cubiertas_medidas d
        {'' if incluir_inactivas else 'where d.activa'}
        order by d.orden, d.medida
    """).fetchall()]


def catalogo(cx):
    """Lo que necesitan las pantallas de gomería para sus desplegables.

    Va sin logos y sin las de baja: es lo que se ofrece al cargar una
    cubierta, no la parametrización.
    """
    return {"marcas": listar(cx), "medidas": medidas(cx)}


def logo_de(cx, slug):
    """El logo de esa marca, o None si no tiene uno cargado.

    None no es un error: la pantalla que lo pide muestra el nombre en
    texto, y app.py cae al archivo del repositorio si existe.
    """
    fila = cx.execute("""
        select logo, logo_tipo from cubiertas_marcas
        where slug = %s and logo is not null""", (slug_de(slug),)).fetchone()
    if not fila:
        return None
    return bytes(fila["logo"]), fila["logo_tipo"] or "image/png"


# =====================================================================
# ESCRITURA
# =====================================================================
def guardar(cx, datos, usuario=None):
    """Da de alta una marca o le cambia el nombre, el logo o el estado."""
    _exigir_gestor(usuario)
    nombre = _texto(datos.get("nombre"), 60)
    if not nombre:
        raise ValueError("Falta el nombre de la marca.")
    slug = slug_de(nombre)
    if not slug:
        raise ValueError("Ese nombre no tiene ni una letra ni un número.")
    logo, tipo = _logo(datos)
    activa = bool(datos.get("activa", True))
    marca_id = _entero(datos.get("id"), "La marca", minimo=1)

    if marca_id:
        fila = cx.execute("select * from cubiertas_marcas where id = %s",
                          (marca_id,)).fetchone()
        if not fila:
            raise ValueError("Esa marca no existe.")
        repetida = cx.execute("""select 1 from cubiertas_marcas
                                 where slug = %s and id <> %s""",
                              (slug, marca_id)).fetchone()
        if repetida:
            raise ValueError(f"Ya hay otra marca que se llama {nombre}.")
        # El logo solo se pisa si vino uno nuevo: guardar el nombre no
        # tiene por qué borrar la imagen que ya estaba.
        if logo is not None:
            cx.execute("""update cubiertas_marcas
                          set nombre=%s, slug=%s, logo=%s, logo_tipo=%s, activa=%s,
                              actualizado=now() where id=%s""",
                       (nombre, slug, logo, tipo, activa, marca_id))
        else:
            cx.execute("""update cubiertas_marcas
                          set nombre=%s, slug=%s, activa=%s, actualizado=now()
                          where id=%s""", (nombre, slug, activa, marca_id))
        return {"ok": True, "id": marca_id, "slug": slug}

    if cx.execute("select 1 from cubiertas_marcas where slug = %s", (slug,)).fetchone():
        raise ValueError(f"La marca {nombre} ya está cargada.")
    fila = cx.execute("""
        insert into cubiertas_marcas (nombre, slug, logo, logo_tipo, activa)
        values (%s,%s,%s,%s,%s) returning id""",
        (nombre, slug, logo, tipo, activa)).fetchone()
    return {"ok": True, "id": fila["id"], "slug": slug}


def borrar_logo(cx, datos, usuario=None):
    """Saca el logo y deja el nombre. La pantalla vuelve a mostrar texto."""
    _exigir_gestor(usuario)
    fila = cx.execute("""update cubiertas_marcas set logo = null, logo_tipo = null,
                         actualizado = now() where id = %s returning slug""",
                      (_entero(datos.get("id"), "La marca", minimo=1),)).fetchone()
    if not fila:
        raise ValueError("Esa marca no existe.")
    return {"ok": True, "slug": fila["slug"]}


def borrar(cx, datos, usuario=None):
    """Saca una marca que no usa ninguna cubierta.

    La que sí se usa no se borra: se da de baja. Borrarla dejaría fichas
    de cubierta apuntando a una marca que no existe, y el nombre en la
    ficha es texto: quedaría escrito sin poder explicarse.
    """
    _exigir_gestor(usuario)
    marca_id = _entero(datos.get("id"), "La marca", minimo=1)
    fila = cx.execute("select nombre, slug from cubiertas_marcas where id = %s",
                      (marca_id,)).fetchone()
    if not fila:
        raise ValueError("Esa marca no existe.")
    usadas = cx.execute("""
        select count(*) as n from cubiertas
        where regexp_replace(lower(marca), '[^a-z0-9]', '', 'g') = %s
    """, (fila["slug"],)).fetchone()["n"]
    if usadas:
        raise ValueError(f"Hay {usadas} cubierta(s) de {fila['nombre']}. "
                         "Se puede dar de baja, no borrar.")
    cx.execute("delete from cubiertas_marcas where id = %s", (marca_id,))
    return {"ok": True}


def guardar_medida(cx, datos, usuario=None):
    """Da de alta una medida o la corrige."""
    _exigir_gestor(usuario, "tocar las medidas")
    medida = _texto(datos.get("medida"), 40)
    if not medida:
        raise ValueError("Falta la medida.")
    # El primer número identifica a la familia: 295/80R22.5 es una 295.
    corta = _texto(datos.get("corta"), 10)
    if not corta:
        encontrado = re.search(r"\d+", medida)
        corta = encontrado.group(0) if encontrado else None
    clase = str(datos.get("clase") or "otro").strip().lower()
    if clase not in CLASES:
        raise ValueError("La familia es camión, autoelevador u otro.")

    valores = (medida, corta, clase, _texto(datos.get("descripcion")),
               bool(datos.get("activa", True)),
               _entero(datos.get("orden"), "El orden") or 50)
    medida_id = _entero(datos.get("id"), "La medida", minimo=1)
    if medida_id:
        fila = cx.execute("""update cubiertas_medidas
                             set medida=%s, corta=%s, clase=%s, descripcion=%s,
                                 activa=%s, orden=%s
                             where id=%s returning id""",
                          (*valores, medida_id)).fetchone()
        if not fila:
            raise ValueError("Esa medida no existe.")
        return {"ok": True, "id": medida_id}

    if cx.execute("select 1 from cubiertas_medidas where medida = %s",
                  (medida,)).fetchone():
        raise ValueError(f"La medida {medida} ya está cargada.")
    fila = cx.execute("""
        insert into cubiertas_medidas (medida, corta, clase, descripcion, activa, orden)
        values (%s,%s,%s,%s,%s,%s) returning id""", valores).fetchone()
    return {"ok": True, "id": fila["id"]}


def borrar_medida(cx, datos, usuario=None):
    _exigir_gestor(usuario, "tocar las medidas")
    medida_id = _entero(datos.get("id"), "La medida", minimo=1)
    fila = cx.execute("select medida from cubiertas_medidas where id = %s",
                      (medida_id,)).fetchone()
    if not fila:
        raise ValueError("Esa medida no existe.")
    usadas = cx.execute("select count(*) as n from cubiertas where btrim(medida) = %s",
                        (fila["medida"],)).fetchone()["n"]
    if usadas:
        raise ValueError(f"Hay {usadas} cubierta(s) de {fila['medida']}. "
                         "Se puede dar de baja, no borrar.")
    cx.execute("delete from cubiertas_medidas where id = %s", (medida_id,))
    return {"ok": True}


# =====================================================================
def aplicar(cx, datos, usuario=None):
    """Punto de entrada de la API."""
    op = (datos.get("op") or "").strip()
    acciones = {"guardar": guardar, "borrar": borrar, "borrar_logo": borrar_logo,
                "medida_guardar": guardar_medida, "medida_borrar": borrar_medida}
    if op in acciones:
        return acciones[op](cx, datos, usuario)
    raise ValueError("No entiendo qué hay que hacer con la marca.")
