"""Leer un papel con la IA: la parte que es igual para todos.

Hay tres papeles que entran por foto —la factura de un servicio externo,
la del recapador y la de una compra— y los tres hacen lo mismo antes y
después: validar lo que subió el navegador, armárselo al modelo, pedirle
una herramienta y quedarse con lo que contestó. Lo único distinto es qué
se le pide.

Nada de lo que sale de acá se guarda solo. Es una propuesta: un papel mal
leído que entra solo es peor que no tener la foto, porque después nadie
sabe si el número está bien.
"""
import os
import re

import ia

MODELO = "claude-opus-5"

# Lo que puede tener un base64 y nada más. Se mira con fullmatch, que
# recorre la cadena sin copiarla: con un archivo de 12 MB eso importa.
B64 = re.compile(r"(?:[A-Za-z0-9+/]{4})+(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")

# El PDF entra igual que una foto: la mitad de las facturas llegan por
# mail y nadie las va a imprimir para sacarles una foto.
IMAGENES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
PDF = "application/pdf"
TIPOS = IMAGENES | {PDF}

# Una foto de celular ronda los 3 MB. Más que esto es una foto sin
# achicar, y el navegador ya la achica antes de mandarla.
MAXIMO = 12 * 1024 * 1024
HOJAS = 4


def preparar(archivos, que="La factura"):
    """Los archivos del navegador, listos para mandárselos al modelo.

    El archivo se manda tal como llegó. Abrirlo y volver a cerrarlo
    —b64decode y enseguida b64encode— dejaba tres copias del mismo archivo
    en memoria, y con cuatro hojas de 12 MB eran 233 MB para un solo
    pedido: el servidor se quedaba sin memoria y lo reiniciaban.
    """
    if not archivos:
        raise ValueError("No llegó ninguna imagen.")
    if len(archivos) > HOJAS:
        raise ValueError(f"Son {HOJAS} archivos como mucho por factura.")

    contenido = []
    for archivo in archivos:
        tipo = (archivo.get("tipo") or "").split(";")[0].strip().lower()
        if tipo not in TIPOS:
            raise ValueError(f"{que} tiene que ser una foto (.jpg, .png o "
                             ".webp) o un PDF.")
        limpio = archivo.get("contenido") or ""
        if not limpio:
            raise ValueError("El archivo llegó vacío.")
        if not B64.fullmatch(limpio):
            # La pantalla manda el base64 pelado, pero un cliente puede
            # mandar el data URI entero o cortarlo en líneas. Se arregla
            # solo si hace falta: hacerlo siempre sería otra copia del
            # archivo al pedo, que es justo lo que se vino a evitar.
            limpio = "".join(limpio.split())
            if limpio.startswith("data:"):
                limpio = limpio.partition(",")[2]
            if not limpio:
                raise ValueError("El archivo llegó vacío.")
            if not B64.fullmatch(limpio):
                raise ValueError("El archivo llegó cortado. Debe reintentarse.")
        # Cuánto pesa, sin abrirlo: cada 4 caracteres de base64 son 3
        # bytes, menos el relleno del final. Así el archivo grande se
        # rechaza antes de gastar la memoria, y no después.
        pesa = len(limpio) // 4 * 3 - limpio[-2:].count("=")
        if pesa > MAXIMO:
            raise ValueError(f"El archivo pesa {pesa // (1024*1024)} MB y el "
                             f"máximo son {MAXIMO // (1024*1024)}.")
        clase = "document" if tipo == PDF else "image"
        contenido.append({"type": clase,
                          "source": {"type": "base64", "media_type": tipo,
                                     "data": limpio}})
    return contenido


def hay_clave():
    return bool(os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def preguntar(contenido, herramienta, sistema, pedido, cliente=None,
              max_tokens=4000):
    """Le muestra el papel al modelo y devuelve lo que llenó en la herramienta.

    La herramienta va forzada: no se le pide que conteste en texto y
    después parsearlo. O llena los campos o no se pudo leer.
    """
    contenido = list(contenido) + [{"type": "text", "text": pedido}]

    # Se revisa después de validar los archivos: si el problema es la
    # foto, que lo diga la foto y no la clave.
    if cliente is None and not hay_clave():
        raise ValueError("Falta la clave de la API de Claude: sin eso no se "
                         "pueden leer facturas. Cargar los datos a mano.")

    cliente = cliente or ia.cliente()
    r = cliente.messages.create(
        model=MODELO,
        max_tokens=max_tokens,
        system=sistema,
        thinking={"type": "adaptive"},
        tools=[herramienta],
        tool_choice={"type": "tool", "name": herramienta["name"]},
        messages=[{"role": "user", "content": contenido}],
    )
    for bloque in r.content:
        if bloque.type == "tool_use" and bloque.name == herramienta["name"]:
            return dict(bloque.input)
    raise ValueError("No se pudo leer la factura. Cargarla a mano.")


def numero(valor):
    """Lo que el modelo devolvió como plata o cantidad, o None."""
    if valor in (None, ""):
        return None
    try:
        n = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None
