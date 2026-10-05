"""
Cómo ve cada uno la aplicación.

Cada usuario elige su tema y su color. Vive en la fila del usuario.
"""
import json

# Las paletas. El color es lo único que cambia entre una y otra: el resto
# de la pantalla sale de ahí. La primera es la de Titán Flota: conserva el
# id "diemar" porque es el que quedó guardado en la fila de cada usuario.
PALETAS = (
    ("diemar",   "Titán (predeterminado)", "#2563eb"),
    ("naranja",  "Naranja",   "#f4791f"),
    ("azul",     "Azul",      "#3d8bfd"),
    ("verde",    "Verde",     "#22a06b"),
    ("violeta",  "Violeta",   "#8b7bf7"),
    ("rojo",     "Rojo",      "#e5484d"),
    ("grafito",  "Grafito",   "#8a94a0"),
)
TEMAS = (("claro", "Claro"), ("oscuro", "Oscuro"), ("auto", "Sistema"))

# El rediseño de Titán Flota estrena el tema claro. Lo guardado antes
# (sin esta marca) arrancaba en oscuro sin que nadie lo eligiera, así que
# no se respeta; lo que se guarde desde ahora sí.
DISENO = 2



def _limpiar(prefs):
    """Deja solo lo que se entiende, con lo de siempre para el resto."""
    prefs = prefs if isinstance(prefs, dict) else {}
    tema = str(prefs.get("tema") or "claro").lower()
    if (prefs.get("diseno") or 0) < DISENO:
        tema = "claro"
    paleta = str(prefs.get("paleta") or "diemar").lower()
    return {
        "tema": tema if tema in {t[0] for t in TEMAS} else "claro",
        "paleta": paleta if paleta in {p[0] for p in PALETAS} else "diemar",
        "diseno": DISENO,
    }


def leer(cx, usuario_id):
    fila = cx.execute("""
        select preferencias from usuarios where id = %s""", (usuario_id,)).fetchone()
    if not fila:
        return _limpiar({})
    prefs = fila["preferencias"]
    if isinstance(prefs, str):
        prefs = json.loads(prefs or "{}")
    return {
        **_limpiar(prefs),
        "paletas": [{"id": p[0], "nombre": p[1], "color": p[2]} for p in PALETAS],
        "temas": [{"id": t[0], "nombre": t[1]} for t in TEMAS],
    }


def guardar(cx, usuario_id, prefs):
    # Lo que llega de la pantalla de Configuración ya es una elección hecha
    # con el diseño nuevo.
    limpias = _limpiar({**(prefs if isinstance(prefs, dict) else {}), "diseno": DISENO})
    cx.execute("update usuarios set preferencias = %s where id = %s",
               (json.dumps(limpias), usuario_id))
    return leer(cx, usuario_id)
