"""De la factura de una compra a los renglones que entran al stock.

Dos facturas distintas con el mismo problema de fondo: lo que dice el
papel no se llama igual que lo que está cargado. «FILTRO ACEITE SCANIA»
en la factura es el «Filtro de aceite R400» del catálogo, y si el sistema
no se da cuenta termina con tres artículos que son el mismo.

Por eso el modelo propone y no crea. De cada renglón sale lo que dice la
factura, y el que lo carga decide: es este, es nuevo, o lo veo después.

En las cubiertas no hay catálogo contra qué comparar —cada goma es una
ficha nueva— pero falta el número de fuego, que el gomero graba cuando la
recibe. Entra con un código provisorio y se completa después.
"""
import difflib
import re
import unicodedata

import lector

# De cuánto para arriba se propone un artículo del catálogo como «este
# puede ser». Abajo de eso, la propuesta sería ruido y el que carga
# termina ignorándolas todas.
PARECIDO_MINIMO = 0.62


def _plano(texto):
    """Para comparar: sin tildes, sin signos y en una sola línea."""
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", t).split())


def parecidos(descripcion, catalogo, cuantos=3):
    """Los artículos del catálogo que más se parecen a lo que dice la factura.

    El código del proveedor manda: si coincide, es ese y no hay nada que
    adivinar. Si no, se compara la descripción palabra por palabra.
    """
    busco = _plano(descripcion)
    if not busco:
        return []
    salida = []
    for a in catalogo:
        puntaje = difflib.SequenceMatcher(
            None, busco, _plano(a.get("descripcion"))).ratio()
        # Las palabras en común valen aparte: «filtro aceite» contra
        # «filtro de aceite scania» tiene todas adentro aunque el largo
        # las separe.
        mias, suyas = set(busco.split()), set(_plano(a.get("descripcion")).split())
        if mias and suyas:
            puntaje = max(puntaje, len(mias & suyas) / len(mias))
        if puntaje >= PARECIDO_MINIMO:
            salida.append({**a, "parecido": round(puntaje, 2)})
    salida.sort(key=lambda x: -x["parecido"])
    return salida[:cuantos]


def emparejar(renglones, catalogo):
    """A cada renglón de la factura, lo que puede llegar a ser.

    El que coincide por código de proveedor sale resuelto. El resto sale
    con candidatos y sin decidir: el alta la decide una persona.
    """
    porcodigo = {}
    for a in catalogo:
        for clave in (a.get("codigo"), a.get("codigo_interno")):
            if clave:
                porcodigo[_plano(clave)] = a

    salida = []
    for r in renglones:
        codigo = _plano(r.get("codigo_proveedor"))
        exacto = porcodigo.get(codigo) if codigo else None
        if exacto:
            salida.append({**r, "articulo": exacto, "por": "codigo",
                           "candidatos": []})
            continue
        candidatos = parecidos(r.get("descripcion"), catalogo)
        salida.append({**r, "articulo": None, "por": None,
                       "candidatos": candidatos})
    return salida


# =====================================================================
# REPUESTOS
# =====================================================================
REPUESTOS = {
    "name": "cargar_repuestos",
    "description": "Los renglones de una factura de compra de repuestos.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "proveedor": {"type": ["string", "null"],
                          "description": "Razón social de quien emitió la factura."},
            "factura": {"type": ["string", "null"],
                        "description": "Número completo: '0001-00012345'."},
            "fecha": {"type": ["string", "null"],
                      "description": "Fecha de la factura en AAAA-MM-DD."},
            "renglones": {
                "type": "array",
                "description": "Un elemento por renglón de la factura. No "
                               "incluir el IVA, los descuentos ni el total.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "descripcion": {"type": "string",
                                        "description": "El texto del renglón, tal "
                                                       "como figura."},
                        "codigo_proveedor": {
                            "type": ["string", "null"],
                            "description": "El código del artículo si el renglón "
                                           "lo trae en una columna aparte."},
                        "cantidad": {"type": ["number", "null"],
                                     "description": "Cuántas unidades."},
                        "costo_unitario": {
                            "type": ["number", "null"],
                            "description": "Precio por unidad sin IVA. Si el "
                                           "renglón trae el total y la cantidad, "
                                           "dividir."},
                    },
                    "required": ["descripcion", "codigo_proveedor", "cantidad",
                                 "costo_unitario"],
                },
            },
            "dudas": {"type": "array", "items": {"type": "string"},
                      "description": "Lo que no se pudo leer con seguridad."},
        },
        "required": ["proveedor", "factura", "fecha", "renglones", "dudas"],
    },
}

_COMUN = (
    "Leés facturas de compra de una empresa de transporte argentina.\n\n"
    "Cada renglón de la factura es un elemento. No incluyas el IVA, los "
    "descuentos, las percepciones ni el total: esos no son artículos.\n\n"
    "Los precios son sin IVA y por unidad. Si el renglón trae cantidad y "
    "total, dividí.\n\n"
    "Lo que no se lee con seguridad va en dudas. Es mejor una duda que un "
    "número inventado: esto lo revisa una persona antes de guardar."
)


def leer_repuestos(archivos, cliente=None):
    leido = lector.preguntar(
        lector.preparar(archivos), REPUESTOS,
        _COMUN + "\n\nCada renglón es un repuesto: un filtro, una correa, un "
                 "juego de pastillas. Copiá la descripción tal como figura, "
                 "sin resumirla: es con lo que se la va a buscar en el "
                 "catálogo.",
        "Leé esta factura y cargá sus renglones.",
        cliente=cliente, max_tokens=8000)
    leido["renglones"] = [
        {"descripcion": " ".join(str(r.get("descripcion") or "").split()),
         "codigo_proveedor": (r.get("codigo_proveedor") or "").strip() or None,
         "cantidad": lector.numero(r.get("cantidad")),
         "costo_unitario": lector.numero(r.get("costo_unitario"))}
        for r in (leido.get("renglones") or [])
        if str(r.get("descripcion") or "").strip()]
    leido["dudas"] = [str(d) for d in (leido.get("dudas") or []) if d]
    return leido


# =====================================================================
# CUBIERTAS
# =====================================================================
CUBIERTAS = {
    "name": "cargar_cubiertas",
    "description": "Los renglones de una factura de compra de cubiertas.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "proveedor": {"type": ["string", "null"]},
            "factura": {"type": ["string", "null"],
                        "description": "Número completo: '0001-00012345'."},
            "fecha": {"type": ["string", "null"],
                      "description": "Fecha de la factura en AAAA-MM-DD."},
            "renglones": {
                "type": "array",
                "description": "Un elemento por renglón. Las cubiertas iguales "
                               "suelen venir en un renglón con cantidad.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "marca": {"type": ["string", "null"],
                                  "description": "MICHELIN, FATE, BRIDGESTONE…"},
                        "modelo": {"type": ["string", "null"],
                                   "description": "El dibujo: 'X MULTI Z', 'R268'."},
                        "medida": {"type": ["string", "null"],
                                   "description": "Como figura: '295/80R22.5', "
                                                  "'1000x20'."},
                        "cantidad": {"type": ["number", "null"]},
                        "costo_unitario": {"type": ["number", "null"],
                                           "description": "Precio por cubierta, "
                                                          "sin IVA."},
                    },
                    "required": ["marca", "modelo", "medida", "cantidad",
                                 "costo_unitario"],
                },
            },
            "dudas": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["proveedor", "factura", "fecha", "renglones", "dudas"],
    },
}


def leer_cubiertas(archivos, cliente=None):
    leido = lector.preguntar(
        lector.preparar(archivos), CUBIERTAS,
        _COMUN + "\n\nCada renglón es una cubierta o un lote de cubiertas "
                 "iguales. La medida es el dato que más importa: copiala tal "
                 "como figura, sin normalizarla. El número de fuego no está "
                 "en la factura —lo graba el gomero cuando la recibe— así "
                 "que no lo busques.",
        "Leé esta factura y cargá sus renglones.",
        cliente=cliente, max_tokens=8000)
    leido["renglones"] = [
        {"marca": (r.get("marca") or "").strip().upper() or None,
         "modelo": (r.get("modelo") or "").strip().upper() or None,
         "medida": (r.get("medida") or "").strip().upper() or None,
         "cantidad": lector.numero(r.get("cantidad")) or 1,
         "costo_unitario": lector.numero(r.get("costo_unitario"))}
        for r in (leido.get("renglones") or [])
        if any((r.get("marca"), r.get("medida")))]
    leido["dudas"] = [str(d) for d in (leido.get("dudas") or []) if d]
    return leido


# =====================================================================
# GUARDAR LO QUE SE CONFIRMÓ
# =====================================================================
# Lo que llega acá ya lo decidió una persona en la pantalla: qué renglón
# es qué artículo, cuál se da de alta y cuál se deja para después. Nada
# de esto lo decide el modelo.
# =====================================================================
def guardar_repuestos(cx, datos, usuario=None):
    """Da de alta los artículos nuevos y carga la entrada de cada renglón."""
    import repuestos

    repuestos._exigir_gestor(usuario)
    fecha = " ".join(str(datos.get("fecha") or "").split())[:10]
    if not fecha:
        raise ValueError("Falta la fecha de la factura.")
    factura = " ".join(str(datos.get("factura") or "").split())[:60]
    proveedor = " ".join(str(datos.get("proveedor") or "").split())[:120]

    renglones = [r for r in (datos.get("renglones") or []) if not r.get("omitir")]
    if not renglones:
        raise ValueError("No quedó ningún renglón para cargar.")

    hecho, nuevos = [], 0
    for r in renglones:
        codigo = " ".join(str(r.get("codigo") or "").split())
        if not codigo:
            raise ValueError("Un renglón quedó sin repuesto elegido.")
        # El artículo que no existe se crea acá, con lo que dice la
        # factura. La alternativa era mandar al que carga a otra pantalla
        # y volver, y entonces no lo carga nadie.
        if r.get("nuevo"):
            repuestos.guardar_articulo(cx, {
                "codigo": codigo,
                "descripcion": r.get("descripcion") or codigo,
                "rubro": r.get("rubro") or "Sin rubro",
                "interno": r.get("codigo_proveedor") or "",
                "minimo": 0,
            }, usuario)
            nuevos += 1
        cantidad = int(float(r.get("cantidad") or 0))
        if cantidad <= 0:
            raise ValueError(f"El renglón {codigo} no tiene cantidad.")
        repuestos.crear_movimiento(cx, {
            "codigo": codigo, "tipo": "Entrada", "cantidad": cantidad,
            "fecha": fecha, "costo_unitario": r.get("costo_unitario"),
            "obs": " · ".join(x for x in (proveedor, factura) if x) or None,
        }, usuario)
        hecho.append({"codigo": codigo, "cantidad": cantidad})

    return {"ok": True, "cargados": len(hecho), "nuevos": nuevos,
            "hecho": hecho}


def guardar_cubiertas(cx, datos, usuario=None):
    """Da de alta las cubiertas de la factura, sin número de fuego.

    Una por unidad: si el renglón dice cuatro, son cuatro fichas, porque
    cada goma tiene su vida propia. El código es provisorio —el fuego lo
    graba el gomero cuando la recibe— y la pantalla de stock las junta
    para completarlas después.
    """
    import base as _base

    if not permisos_gestiona(usuario):
        raise PermissionError("No tiene permiso para dar de alta cubiertas.")

    factura = " ".join(str(datos.get("factura") or "").split())[:60]
    if not factura:
        raise ValueError("Falta el número de factura: de ahí sale el código "
                         "provisorio de cada cubierta.")
    # El número de la factura, sin guiones ni espacios. Entero: cortarlo
    # corto se come el punto de venta —0001-00001234 y 0002-00001234
    # quedarían iguales— y entonces la numeración de una factura seguiría
    # la de la otra.
    raiz = "FC-" + re.sub(r"[^A-Z0-9]+", "", factura.upper())[-14:]

    renglones = [r for r in (datos.get("renglones") or []) if not r.get("omitir")]
    if not renglones:
        raise ValueError("No quedó ningún renglón para cargar.")

    # El número sigue desde la última que se cargó de esta misma factura,
    # así cargar la segunda hoja no pisa la primera.
    ya = cx.execute("select count(*) as n from cubiertas where codigo like %s",
                    (raiz + "-%",)).fetchone()["n"]

    hecho = []
    for r in renglones:
        cantidad = int(float(r.get("cantidad") or 1))
        if cantidad <= 0:
            raise ValueError("Un renglón quedó con cantidad cero.")
        for _ in range(cantidad):
            ya += 1
            codigo = f"{raiz}-{ya:02d}"
            _base.alta_cubierta(
                cx, codigo,
                marca=(r.get("marca") or None), modelo=(r.get("modelo") or None),
                medida=(r.get("medida") or None),
                costo_compra=r.get("costo_unitario"),
                codigo_provisorio=True,
                observaciones=f"Alta por factura {factura}",
                usuario=(usuario or {}).get("nombre"),
                nota=f"Alta por factura {factura}")
            hecho.append(codigo)

    return {"ok": True, "cargadas": len(hecho), "codigos": hecho,
            "aviso": f"{len(hecho)} cubiertas entraron sin número de fuego. "
                     f"Se completan desde Stock de cubiertas."}


def permisos_gestiona(usuario):
    import permisos
    return permisos.gestiona(usuario)
