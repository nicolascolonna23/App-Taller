"""
Los mapas de las unidades.

Un mapa se escribe en una línea corta, un eje por letra, de adelante hacia
atrás:

    S  eje simple  — una cubierta por lado   (el direccional)
    D  eje dual    — dos cubiertas por lado  (los de tracción y portantes)

Ejemplos:

    S-D-D    1 eje direccional + 2 traseros duales = 10 cubiertas
             (cuatro por lado atrás, que es el caso más común)
    S-D      chasis chico de reparto = 6 cubiertas
    S-S-D-D  con eje delantero doble = 12 cubiertas
    D-D-D    semirremolque de tres ejes = 12 cubiertas

Los códigos de posición salen solos y siguen la forma en que se nombran en
el taller: número de eje, lado, y en los duales si es la de afuera o la de
adentro.

    1I   1D             eje 1, izquierda y derecha
    2IE  2II  2DI  2DE  eje 2: izq exterior, izq interior, der interior, der exterior
    AUX                 el auxilio
"""

LADOS = {"I": "Izquierda", "D": "Derecha"}


def expandir(spec, con_auxilio=True):
    """Convierte 'S-D-D' en la lista de posiciones de esa configuración.

    Devuelve dicts con las columnas de configuracion_posiciones.
    """
    ejes = [e.strip().upper() for e in str(spec).replace(",", "-").split("-") if e.strip()]
    if not ejes:
        raise ValueError(f"Mapa vacío: {spec!r}")
    if any(e not in ("S", "D") for e in ejes):
        raise ValueError(f"Mapa inválido: {spec!r}. Cada eje tiene que ser S o D.")

    posiciones, orden = [], 0
    for n, tipo in enumerate(ejes, start=1):
        # De izquierda a derecha, como se ve la unidad de frente: la exterior
        # izquierda primero y la exterior derecha al final.
        if tipo == "S":
            lugares = [("I", "unica", "I"), ("D", "unica", "D")]
        else:
            lugares = [("I", "exterior", "IE"), ("I", "interior", "II"),
                       ("D", "interior", "DI"), ("D", "exterior", "DE")]
        for lado, montaje, sufijo in lugares:
            orden += 1
            posiciones.append({
                "codigo": f"{n}{sufijo}",
                "eje": n,
                "lado": lado,
                "montaje": montaje,
                "es_auxilio": False,
                "orden": orden,
            })

    if con_auxilio:
        orden += 1
        posiciones.append({"codigo": "AUX", "eje": 0, "lado": "X",
                           "montaje": "unica", "es_auxilio": True, "orden": orden})
    return posiciones


def describir(spec):
    """Texto legible del mapa, para mostrarlo en pantalla y en el prompt."""
    ejes = [e.strip().upper() for e in str(spec).replace(",", "-").split("-") if e.strip()]
    simples = sum(1 for e in ejes if e == "S")
    duales = sum(1 for e in ejes if e == "D")
    partes = []
    if simples:
        partes.append(f"{simples} eje{'s' if simples > 1 else ''} simple{'s' if simples > 1 else ''}")
    if duales:
        partes.append(f"{duales} eje{'s' if duales > 1 else ''} dual{'es' if duales > 1 else ''}")
    total = simples * 2 + duales * 4
    return f"{' + '.join(partes)} · {total} cubiertas"


if __name__ == "__main__":
    for spec in ("S-D-D", "S-D", "D-D-D", "S-S-D-D"):
        pos = expandir(spec)
        print(f"{spec:<9} {describir(spec):<38} {' '.join(p['codigo'] for p in pos)}")
