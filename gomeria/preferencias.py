"""
Cómo ve cada uno la aplicación.

Cada usuario elige su tema, su color y su foto de portada. No es de la
empresa: uno la usa de noche en el taller y otro de día en la oficina, y
no tienen por qué verla igual.

Todo vive en la fila del usuario. La foto también: son unas pocas fotos
de unos pocos usuarios, y guardarlas en la base es una pieza menos que
pueda fallar un domingo.
"""
import json

# Las paletas. El color es lo único que cambia entre una y otra: el resto
# de la pantalla sale de ahí. La primera es la de la empresa.
PALETAS = (
    ("diemar",   "Diemar",    "#ff7a1a"),
    ("azul",     "Azul",      "#3d8bfd"),
    ("verde",    "Verde",     "#22a06b"),
    ("violeta",  "Violeta",   "#8b7bf7"),
    ("rojo",     "Rojo",      "#e5484d"),
    ("grafito",  "Grafito",   "#8a94a0"),
)
TEMAS = (("oscuro", "Oscuro"), ("claro", "Claro"), ("auto", "El del sistema"))

# Lo que pesa como mucho una foto de portada. Una foto de celular ronda
# los 3 MB; más que esto es una foto sin achicar, y tarda en cargar cada
# vez que se abre la portada.
FONDO_MAXIMO = 6 * 1024 * 1024
TIPOS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _limpiar(prefs):
    """Deja solo lo que se entiende, con lo de siempre para el resto."""
    prefs = prefs if isinstance(prefs, dict) else {}
    tema = str(prefs.get("tema") or "oscuro").lower()
    paleta = str(prefs.get("paleta") or "diemar").lower()
    return {
        "tema": tema if tema in {t[0] for t in TEMAS} else "oscuro",
        "paleta": paleta if paleta in {p[0] for p in PALETAS} else "diemar",
        # Si subió una foto, se usa; el interruptor es para volver a la de
        # la empresa sin tener que borrarla.
        "fondo_propio": bool(prefs.get("fondo_propio", True)),
    }


def leer(cx, usuario_id):
    fila = cx.execute("""
        select preferencias, fondo is not null as tiene_fondo, fondo_desde
          from usuarios where id = %s""", (usuario_id,)).fetchone()
    if not fila:
        return {**_limpiar({}), "tiene_fondo": False, "fondo_version": None}
    prefs = fila["preferencias"]
    if isinstance(prefs, str):
        prefs = json.loads(prefs or "{}")
    return {
        **_limpiar(prefs),
        "tiene_fondo": fila["tiene_fondo"],
        # Para que el navegador no siga mostrando la foto anterior después
        # de cambiarla.
        "fondo_version": (fila["fondo_desde"].isoformat()
                          if fila["fondo_desde"] else None),
        "paletas": [{"id": p[0], "nombre": p[1], "color": p[2]} for p in PALETAS],
        "temas": [{"id": t[0], "nombre": t[1]} for t in TEMAS],
    }


def guardar(cx, usuario_id, prefs):
    limpias = _limpiar(prefs)
    cx.execute("update usuarios set preferencias = %s where id = %s",
               (json.dumps(limpias), usuario_id))
    return leer(cx, usuario_id)


def guardar_fondo(cx, usuario_id, cuerpo, tipo):
    """La foto que subió. Devuelve las preferencias ya actualizadas."""
    if not cuerpo:
        raise ValueError("No llegó ninguna imagen.")
    if len(cuerpo) > FONDO_MAXIMO:
        raise ValueError(
            f"La imagen pesa {len(cuerpo) // (1024 * 1024)} MB y el máximo son "
            f"{FONDO_MAXIMO // (1024 * 1024)}. Achicala y volvé a subirla.")
    tipo = (tipo or "").split(";")[0].strip().lower()
    if tipo not in TIPOS:
        raise ValueError("La imagen tiene que ser .jpg, .png o .webp.")
    cx.execute("""update usuarios
                     set fondo = %s, fondo_tipo = %s, fondo_desde = now()
                   where id = %s""", (cuerpo, tipo, usuario_id))
    return leer(cx, usuario_id)


def borrar_fondo(cx, usuario_id):
    cx.execute("""update usuarios
                     set fondo = null, fondo_tipo = null, fondo_desde = null
                   where id = %s""", (usuario_id,))
    return leer(cx, usuario_id)


def fondo(cx, usuario_id):
    """La foto y su tipo, o (None, None) si no subió ninguna."""
    fila = cx.execute("select fondo, fondo_tipo from usuarios where id = %s",
                      (usuario_id,)).fetchone()
    if not fila or not fila["fondo"]:
        return None, None
    return bytes(fila["fondo"]), fila["fondo_tipo"] or "image/jpeg"
