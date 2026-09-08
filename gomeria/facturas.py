"""
De la foto de una factura a los campos del servicio externo.

El encargado saca una foto de la factura del taller de afuera con el
celular, y esto la lee: quién la hizo, qué número tiene, de qué fecha,
cuánto salió, de qué unidad es y qué le hicieron. Después muestra lo que
entendió en el mismo formulario de siempre, para que lo revise antes de
guardar.

Lo que sale de acá NO se guarda solo. Es una propuesta: una factura mal
leída que entra sola al historial de una unidad es peor que no tener la
foto, porque después nadie sabe si el número está bien.

Se le pasa el listado de patentes de la flota. Sin eso, "AD247MQ" escrito
a mano en un remito arrugado sale con la Q por O una de cada tres veces;
con el listado, Claude elige entre las que existen.
"""
import base64, json, os, re
import anthropic

MODELO = "claude-opus-5"

# Lo que se acepta desde el navegador. El PDF entra igual que una foto:
# la mitad de las facturas llegan por mail y nadie las va a imprimir para
# sacarles una foto.
IMAGENES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
PDF = "application/pdf"
TIPOS = IMAGENES | {PDF}

# Una foto de celular ronda los 3 MB. Más que esto es una foto sin
# achicar, y el navegador ya la achica antes de mandarla.
MAXIMO = 12 * 1024 * 1024

HERRAMIENTA = {
    "name": "cargar_servicio",
    "description": "Los datos de la factura de un servicio hecho por un tercero, "
                   "para cargarlo como orden de trabajo externa.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "taller": {
                "type": ["string", "null"],
                "description": "Quién emitió la factura: razón social o nombre "
                               "comercial del taller o proveedor. Sin el CUIT ni "
                               "la dirección."
            },
            "factura": {
                "type": ["string", "null"],
                "description": "Número de comprobante completo, como figura: "
                               "'0001-00012345'. Si dice 'Factura B Nº 0003-00045', "
                               "poné '0003-00045'."
            },
            "fecha": {
                "type": ["string", "null"],
                "description": "Fecha de emisión en formato AAAA-MM-DD. En "
                               "Argentina las fechas se escriben día/mes/año."
            },
            "monto": {
                "type": ["number", "null"],
                "description": "El TOTAL a pagar, con IVA incluido, en números. "
                               "Sin símbolo de moneda ni separador de miles. Ojo "
                               "con la coma decimal: '1.234.567,89' es 1234567.89."
            },
            "patente": {
                "type": ["string", "null"],
                "description": "La patente de la unidad, sin espacios y en "
                               "mayúsculas. Tiene que ser una de las de la flota "
                               "que figuran en las instrucciones. Si lo que se lee "
                               "no coincide con ninguna, dejalo en null y decilo "
                               "en 'dudas'."
            },
            "km": {
                "type": ["number", "null"],
                "description": "Kilometraje de la unidad si la factura lo menciona."
            },
            "detalle": {
                "type": ["string", "null"],
                "description": "Qué trabajo se hizo, en una o dos líneas y en "
                               "castellano. Resumido, no la lista de renglones."
            },
            "moneda": {
                "type": ["string", "null"],
                "description": "'ARS' si son pesos, o el código que corresponda. "
                               "null si no se aclara."
            },
            "dudas": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Qué no se pudo leer con seguridad, un renglón por "
                               "cosa: 'el total está borroso, puede ser 1.250.000 "
                               "o 1.290.000'. Vacío si está todo claro."
            },
        },
        "required": ["taller", "factura", "fecha", "monto", "patente", "km",
                     "detalle", "moneda", "dudas"],
    },
}


def _instrucciones(patentes):
    lista = ", ".join(patentes) if patentes else "(no se pudo cargar el listado)"
    return f"""Leés facturas de talleres y proveedores de una empresa de transporte
argentina, para cargarlas en el sistema de órdenes de trabajo.

Las patentes de la flota son estas, y ninguna otra:
{lista}

Reglas:

1. Copiá lo que dice la factura. No completes lo que no está: un campo que
   no aparece va en null. Un dato inventado se guarda igual que uno bueno y
   después nadie sabe cuál era cuál.
2. El monto es el TOTAL final, el que se paga. No el subtotal, no el neto
   gravado, no el IVA.
3. Los números vienen en formato argentino: el punto separa los miles y la
   coma los decimales. $1.234.567,89 es 1234567.89.
4. Las fechas vienen día/mes/año. 03/11/2026 es el 3 de noviembre.
5. La patente puede estar escrita de cualquier manera —con espacios, con
   guiones, a mano en un margen— o puede no estar. Si la que leés se parece
   a una de la lista, usá la de la lista. Si no se parece a ninguna, es
   null: puede ser el auto de otro cliente del taller.
6. Todo lo que dudes va en 'dudas'. El que carga la factura la tiene en la
   mano y puede mirar; lo que no sirve es que la duda no se vea."""


def _limpiar_patente(valor, patentes):
    """La patente que dijo Claude, si es una de la flota."""
    if not valor:
        return None
    plano = "".join(ch for ch in str(valor).upper() if ch.isalnum())
    return plano if plano in set(patentes or ()) else None


def _limpiar_fecha(valor):
    if not valor:
        return None
    texto = str(valor).strip()[:10]
    return texto if re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto) else None


def leer(archivos, patentes=None, cliente=None):
    """Devuelve lo que se entendió de la factura. No toca la base.

    'archivos' es la lista de lo que subió el navegador: cada uno con su
    tipo y el contenido en base64. Van todos en el mismo pedido porque una
    factura de dos hojas es una sola factura.
    """
    if not archivos:
        raise ValueError("No llegó ninguna imagen.")
    if len(archivos) > 4:
        raise ValueError("Son cuatro archivos como mucho por factura.")

    contenido = []
    for archivo in archivos:
        tipo = (archivo.get("tipo") or "").split(";")[0].strip().lower()
        if tipo not in TIPOS:
            raise ValueError("La factura tiene que ser una foto (.jpg, .png o "
                             ".webp) o un PDF.")
        try:
            crudo = base64.b64decode(archivo.get("contenido") or "", validate=False)
        except Exception:
            raise ValueError("El archivo llegó cortado. Probá de nuevo.")
        if not crudo:
            raise ValueError("El archivo llegó vacío.")
        if len(crudo) > MAXIMO:
            raise ValueError(f"El archivo pesa {len(crudo) // (1024*1024)} MB y el "
                             f"máximo son {MAXIMO // (1024*1024)}.")
        limpio = base64.b64encode(crudo).decode()
        if tipo == PDF:
            contenido.append({"type": "document",
                              "source": {"type": "base64", "media_type": PDF,
                                         "data": limpio}})
        else:
            contenido.append({"type": "image",
                              "source": {"type": "base64", "media_type": tipo,
                                         "data": limpio}})

    contenido.append({"type": "text",
                      "text": "Leé esta factura y cargá el servicio externo."})

    # Se revisa después de validar los archivos: si el problema es la foto,
    # que lo diga la foto y no la clave.
    if cliente is None and not (os.environ.get("ANTHROPIC_API_KEY")
                                or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise ValueError("Falta la clave de la API de Claude: sin eso no se "
                         "pueden leer facturas. Cargá los datos a mano.")

    cliente = cliente or anthropic.Anthropic()
    r = cliente.messages.create(
        model=MODELO,
        max_tokens=4000,
        system=_instrucciones(patentes),
        thinking={"type": "adaptive"},
        tools=[HERRAMIENTA],
        tool_choice={"type": "tool", "name": "cargar_servicio"},
        messages=[{"role": "user", "content": contenido}],
    )
    for bloque in r.content:
        if bloque.type == "tool_use" and bloque.name == "cargar_servicio":
            leido = dict(bloque.input)
            break
    else:
        raise ValueError("No se pudo leer la factura. Cargala a mano.")

    # La patente se valida contra la flota: es el campo del que cuelga todo
    # lo demás —la orden va a parar al historial de esa unidad— y el único
    # donde equivocarse manda el gasto al camión de otro.
    leido["patente"] = _limpiar_patente(leido.get("patente"), patentes)
    leido["fecha"] = _limpiar_fecha(leido.get("fecha"))
    if leido.get("monto") is not None:
        try:
            leido["monto"] = float(leido["monto"])
        except (TypeError, ValueError):
            leido["monto"] = None
    leido["dudas"] = [str(d) for d in (leido.get("dudas") or []) if d]
    return leido
