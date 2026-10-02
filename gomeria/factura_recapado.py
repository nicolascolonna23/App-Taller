"""De la factura del recapador a las gomas que volvieron.

El recapador factura por goma, con el número de fuego grabado en cada
renglón. Eso es lo que hace que esto se pueda verificar: no hay que
creerle al modelo, porque lo que leyó se cruza contra lo que el sistema
sabe que mandó.

    · fuego que está en la factura y en un envío abierto → volvió
    · fuego en la factura que no salió nunca            → algo está mal
    · fuego que salió y no está en la factura           → ésa no volvió

El último es el que importa y el que no existía. Si se mandaron doce y la
factura trae diez, las dos que faltan quedan señaladas.

Se le pasa la lista de números de fuego que están afuera, igual que a la
factura de servicios se le pasan las patentes. Sin eso, un 4521 grabado a
fuego y después fotografiado sale 4S21 una de cada tres veces; con la
lista, el modelo elige entre los que existen.
"""
import lector

HERRAMIENTA = {
    "name": "cargar_recapados",
    "description": "Los renglones de una factura de recapado: qué cubierta se "
                   "recapó y cuánto salió cada una.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "factura": {
                "type": ["string", "null"],
                "description": "Número de comprobante completo, como figura: "
                               "'0001-00012345'."
            },
            "fecha": {
                "type": ["string", "null"],
                "description": "Fecha de la factura en AAAA-MM-DD."
            },
            "renglones": {
                "type": "array",
                "description": "Un elemento por cubierta facturada. Si un "
                               "renglón dice cantidad 2 con un solo número de "
                               "fuego, es un renglón.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "codigo_fuego": {
                            "type": ["string", "null"],
                            "description": "El número de fuego de la cubierta, "
                                           "como figura en el renglón. Es el que "
                                           "la identifica. Si el renglón no lo "
                                           "trae, dejarlo en null."
                        },
                        "costo": {
                            "type": ["number", "null"],
                            "description": "Lo que salió recapar esa cubierta, "
                                           "sin IVA. Si la factura trae un total "
                                           "por renglón y una cantidad, el costo "
                                           "es el unitario."
                        },
                        "banda": {
                            "type": ["string", "null"],
                            "description": "La banda o dibujo que le pusieron, si "
                                           "el renglón lo dice: 'BDR-HT', 'R250'."
                        },
                    },
                    "required": ["codigo_fuego", "costo", "banda"],
                },
            },
            "dudas": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lo que no se pudo leer con seguridad. Una frase "
                               "por cosa, en castellano."
            },
        },
        "required": ["factura", "fecha", "renglones", "dudas"],
    },
}


def _instrucciones(codigos):
    lista = ", ".join(codigos[:400]) if codigos else "(no hay ninguna afuera)"
    return (
        "Leés facturas de recapado de una empresa de transporte argentina.\n\n"
        "El recapador factura por cubierta: cada renglón es una goma, "
        "identificada por su número de fuego —el número grabado en el "
        "flanco—, con lo que salió recaparla.\n\n"
        "Estos son los números de fuego de las cubiertas que la empresa "
        "mandó a recapar y todavía no volvieron. El de cada renglón "
        "debería ser uno de estos:\n"
        f"{lista}\n\n"
        "Si lo que leés se parece mucho a uno de la lista, usá el de la "
        "lista: están grabados a fuego y fotografiados, y el 5 se confunde "
        "con el S y el 0 con el O. Si no se parece a ninguno, escribí lo "
        "que ves tal cual y anotalo en dudas: puede ser una goma que entró "
        "por otro lado.\n\n"
        "El costo es sin IVA y por cubierta. Si el renglón trae cantidad y "
        "total, dividí. Si la factura trae un único total para todo, dejá "
        "los costos en null y anotalo en dudas: no inventes un prorrateo.\n\n"
        "Lo que no se lee con seguridad va en dudas. Es mejor una duda que "
        "un número inventado: esto lo revisa una persona antes de guardar."
    )


def leer(archivos, codigos_afuera=None, cliente=None):
    """Lo que dice la factura. No toca la base ni decide nada."""
    contenido = lector.preparar(archivos)
    leido = lector.preguntar(
        contenido, HERRAMIENTA, _instrucciones(list(codigos_afuera or [])),
        "Leé esta factura de recapado y cargá sus renglones.",
        cliente=cliente, max_tokens=8000)

    renglones = []
    for r in (leido.get("renglones") or []):
        codigo = " ".join(str(r.get("codigo_fuego") or "").split()).upper()
        renglones.append({"codigo_fuego": codigo or None,
                          "costo": lector.numero(r.get("costo")),
                          "banda": (r.get("banda") or "").strip().upper() or None})
    leido["renglones"] = renglones
    leido["dudas"] = [str(d) for d in (leido.get("dudas") or []) if d]
    return leido
