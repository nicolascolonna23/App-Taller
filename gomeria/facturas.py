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
import json, re

import lector

# Leer el papel —validarlo, mandárselo al modelo, quedarse con lo que
# contestó— es igual para las tres facturas que entran por foto. Vive en
# lector.py. Acá queda lo único que cambia: qué se le pide.
B64 = lector.B64
MODELO = lector.MODELO
IMAGENES, PDF, TIPOS = lector.IMAGENES, lector.PDF, lector.TIPOS
MAXIMO = lector.MAXIMO

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
                               "indicar '0003-00045'."
            },
            "fecha": {
                "type": ["string", "null"],
                "description": "Fecha de emisión en formato AAAA-MM-DD. En "
                               "Argentina las fechas se escriben día/mes/año."
            },
            "monto": {
                "type": ["number", "null"],
                "description": "El TOTAL a pagar, con IVA incluido, en números. "
                               "Importe sin símbolo de moneda ni separador de miles. "
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
            "unidades": {
                "type": "array",
                "description": "Una entrada por cada unidad de la flota que "
                               "aparece en la factura, con los renglones que "
                               "le corresponden. Una factura puede traer "
                               "trabajos o repuestos de varias unidades: es "
                               "común que al lado de cada renglón esté anotada "
                               "a mano la patente (a veces incompleta). Si toda "
                               "la factura es de una sola unidad, una sola "
                               "entrada. Vacío si no aparece ninguna patente.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "patente": {
                            "type": "string",
                            "description": "La patente como figura en la lista "
                                           "de la flota."
                        },
                        "detalle": {
                            "type": ["string", "null"],
                            "description": "Qué se le hizo o qué se le compró "
                                           "a esta unidad, en una línea."
                        },
                        "importe": {
                            "type": ["number", "null"],
                            "description": "La suma de los importes de los "
                                           "renglones de esta unidad, tal como "
                                           "figuran en la columna de importe "
                                           "(normalmente sin IVA)."
                        },
                    },
                    "required": ["patente", "detalle", "importe"],
                },
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
                     "unidades", "detalle", "moneda", "dudas"],
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
6. Una factura puede ser de más de una unidad: por ejemplo dos
   renglones de cubiertas, uno para cada camión, con la patente anotada a
   mano al lado de cada uno. En ese caso cargá una entrada en 'unidades'
   por cada patente, con sus renglones sumados. Una patente anotada a
   medias ("PIQ", "KSP007") es la de la lista que la contiene, si hay una
   sola que coincide. En 'patente' va la primera.
7. Todo lo que dudes va en 'dudas'. El que carga la factura la tiene en la
   mano y puede mirar; lo que no sirve es que la duda no se vea."""


def _limpiar_patente(valor, patentes):
    """La patente que dijo Claude, si es una de la flota."""
    if not valor:
        return None
    plano = "".join(ch for ch in str(valor).upper() if ch.isalnum())
    return plano if plano in set(patentes or ()) else None


def _buscar_patente(valor, patentes):
    """Como _limpiar_patente, pero acepta la patente anotada a medias.

    En el margen de la factura se escribe "PIQ" por PIQ468 o "AKSP007"
    por KSP007. Se acepta solo si hay UNA patente de la flota que encaje:
    con dos candidatas no se adivina, se deja para que elija la persona.
    """
    exacta = _limpiar_patente(valor, patentes)
    if exacta or not valor:
        return exacta
    plano = "".join(ch for ch in str(valor).upper() if ch.isalnum())
    if len(plano) < 3:
        return None
    candidatas = [p for p in (patentes or ())
                  if plano in p or (len(p) >= 6 and p in plano)]
    return candidatas[0] if len(candidatas) == 1 else None


def _repartir(unidades, total, patentes):
    """Las unidades de la factura, cada una con su parte del total.

    La factura trae un importe por renglón, normalmente sin IVA, y un
    total con IVA y percepciones. Cada unidad se lleva del total la misma
    proporción que sus renglones tienen del subtotal: así la suma de las
    órdenes da exactamente lo que se pagó. La última se queda con los
    centavos del redondeo.
    """
    juntas = {}
    for u in unidades or []:
        patente = _buscar_patente((u or {}).get("patente"), patentes)
        if not patente:
            continue
        item = juntas.setdefault(patente, {"patente": patente, "detalle": [], "importe": 0.0,
                                           "sin_importe": False})
        if u.get("detalle"):
            item["detalle"].append(str(u["detalle"]).strip())
        try:
            item["importe"] += float(u.get("importe"))
        except (TypeError, ValueError):
            item["sin_importe"] = True

    salida = [{"patente": i["patente"], "detalle": "; ".join(d for d in i["detalle"] if d) or None,
               "importe": round(i["importe"], 2) if not i["sin_importe"] else None, "monto": None}
              for i in juntas.values()]
    if len(salida) == 1:
        salida[0]["monto"] = total
        return salida
    suma = sum(i["importe"] or 0 for i in salida)
    if total is None or suma <= 0 or any(i["importe"] is None for i in salida):
        return salida
    acumulado = 0.0
    for n, i in enumerate(salida):
        if n == len(salida) - 1:
            i["monto"] = round(total - acumulado, 2)
        else:
            i["monto"] = round(total * i["importe"] / suma, 2)
            acumulado += i["monto"]
    return salida


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

    contenido = lector.preparar(archivos)

    leido = lector.preguntar(
        contenido, HERRAMIENTA, _instrucciones(patentes),
        "Leé esta factura y cargá el servicio externo.", cliente=cliente)

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

    leido["unidades"] = _repartir(leido.get("unidades"), leido.get("monto"), patentes)
    if not leido["patente"] and leido["unidades"]:
        leido["patente"] = leido["unidades"][0]["patente"]
    if len(leido["unidades"]) > 1 and any(u["monto"] is None for u in leido["unidades"]):
        leido["dudas"].append("No se pudo repartir el total entre las unidades: "
                              "revisar el monto de cada una.")
    return leido
