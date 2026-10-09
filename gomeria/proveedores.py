"""El proveedor del catálogo que corresponde a lo que dice una factura.

La factura dice «FRENOS CATAMARCA S.R.L.», el catálogo «Frenos Catamarca»,
y otro día alguien la fotografió torcida y salió «FRENOS CATAMRCA». Las
tres son el mismo proveedor. Se busca en este orden:

  1. El CUIT. Si coincide, es ese y no hay nada que discutir.
  2. El nombre que eligió el modelo de la lista que se le pasó.
  3. El nombre parecido: sin mayúsculas, acentos, puntuación ni la forma
     societaria (S.A., S.R.L., …), y tolerando letras de más o de menos.

Si dos proveedores se parecen igual, no se elige ninguno: lo decide la
persona que carga. Un proveedor mal elegido manda el gasto a la cuenta de
otro.
"""
from difflib import SequenceMatcher
import re
import unicodedata

# Formas societarias y palabras que no distinguen a un proveedor de otro.
_RELLENO = {"sa", "srl", "sas", "sca", "sh", "saic", "saci", "sacif", "sociedad",
            "anonima", "responsabilidad", "limitada", "de", "del", "la", "el", "los",
            "las", "y", "e", "hnos", "hermanos", "cia", "compania", "ltda"}
# Palabras del rubro: que dos proveedores digan «taller» no los hace el mismo.
_GENERICAS = {"taller", "talleres", "gomeria", "frenos", "servicio", "servicios",
              "repuestos", "transporte", "transportes", "lubricentro", "mecanica",
              "electricidad", "neumaticos", "cubiertas", "camiones", "automotor",
              "automotores", "comercial", "industrial", "argentina", "norte", "sur"}
UMBRAL = 0.82


def solo_digitos(valor):
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def normalizar(nombre):
    """'FRENOS CATAMARCA S.R.L.' -> 'frenos catamarca'."""
    texto = unicodedata.normalize("NFD", str(nombre or "").lower())
    texto = "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")
    # S.R.L. y S.A. se escriben con puntos: se juntan antes de separar.
    texto = re.sub(r"\b([a-z])\.(?=[a-z]\.)", r"\1", texto)
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    palabras = [p for p in texto.split() if p not in _RELLENO]
    return " ".join(palabras)


def parecido(a, b):
    """Qué tanto se parecen dos nombres, de 0 a 1."""
    x, y = normalizar(a), normalizar(b)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    # Uno contiene al otro entero: «Morandi» y «Gomería Morandi».
    corto, largo = sorted((x, y), key=len)
    if len(corto) >= 4 and (f" {corto} " in f" {largo} "):
        return 0.9
    # Una palabra propia en común: «Gomería Morandi» y «Morandi Carlos
    # Ezequiel», el nombre de fantasía y la razón social del mismo taller.
    propias = {w for w in x.split() if len(w) >= 5 and w not in _GENERICAS}
    if propias & {w for w in y.split() if len(w) >= 5 and w not in _GENERICAS}:
        return 0.85
    juntos = SequenceMatcher(None, x, y).ratio()
    # Las mismas palabras en otro orden: «Carlos Morandi» y «Morandi Carlos».
    ordenados = SequenceMatcher(None, " ".join(sorted(x.split())),
                                " ".join(sorted(y.split()))).ratio()
    return max(juntos, ordenados)


def emparejar(nombre, cuit, catalogo, elegido=None):
    """El proveedor del catálogo y cómo se lo encontró.

    Devuelve (proveedor o None, 'cuit' | 'nombre' | 'parecido' | None).
    'catalogo' es una lista de diccionarios con id, nombre y cuit.
    """
    catalogo = [p for p in (catalogo or []) if p.get("nombre")]
    digitos = solo_digitos(cuit)
    if len(digitos) == 11:
        for p in catalogo:
            if solo_digitos(p.get("cuit")) == digitos:
                return p, "cuit"

    if elegido:
        for p in catalogo:
            if normalizar(p["nombre"]) == normalizar(elegido):
                return p, "nombre"

    puntajes = sorted(((max(parecido(nombre, p["nombre"]),
                            parecido(elegido, p["nombre"]) if elegido else 0), p)
                       for p in catalogo), key=lambda x: -x[0])
    if not puntajes or puntajes[0][0] < UMBRAL:
        return None, None
    # Empate: dos proveedores igual de parecidos no se adivinan.
    if len(puntajes) > 1 and puntajes[0][0] - puntajes[1][0] < 0.03:
        return None, None
    return puntajes[0][1], "parecido"


def catalogo(cx, rubros=None):
    """Los proveedores activos, opcionalmente de ciertos rubros.

    Un proveedor sin rubros cargados se ofrece en todo. Sin la tabla
    devuelve una lista vacía: la carga sigue andando como antes.
    """
    try:
        filas = cx.execute("""select id, nombre, cuit, rubros from proveedores
                              where activo order by nombre""").fetchall()
    except Exception:
        cx.rollback()
        return []
    filas = [dict(f) for f in filas]
    if rubros:
        filas = [f for f in filas if not f.get("rubros") or set(f["rubros"]) & set(rubros)]
    return filas


def resolver(cx, proveedor_id=None, nombre=None):
    """(id, nombre) a guardar en una carga: el del catálogo si se eligió."""
    if proveedor_id:
        try:
            fila = cx.execute("select id, nombre from proveedores where id = %s",
                              (int(proveedor_id),)).fetchone()
        except (TypeError, ValueError):
            raise ValueError("El proveedor no es válido.") from None
        if not fila:
            raise ValueError("Ese proveedor no existe.")
        return fila["id"], fila["nombre"]
    nombre = " ".join(str(nombre or "").split())[:120] or None
    return None, nombre
