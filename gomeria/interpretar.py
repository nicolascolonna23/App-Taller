"""
De lo que escribe el gomero a un movimiento concreto.

El gomero escribe "giré las de atrás del lado del acompañante" y esto lo
convierte en una propuesta de movimientos sobre las posiciones reales de
esa unidad. La propuesta NO se aplica: se le muestra y recién cuando
confirma se escribe en la base.

Claude recibe el mapa de la unidad con lo que tiene puesto ahora, así
razona sobre posiciones que existen de verdad y no sobre un modelo
genérico de camión.
"""
import json, os
import anthropic

MODELO = "claude-opus-5"

# Una sola herramienta, obligatoria: la respuesta siempre viene estructurada.
HERRAMIENTA = {
    "name": "registrar",
    "description": "Registra lo que hizo el gomero, traducido a movimientos sobre "
                   "las posiciones de esta unidad.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "resumen": {
                "type": "string",
                "description": "Una frase en castellano de lo que entendiste, "
                               "para que el gomero confirme. Ej: 'Cruzás las dos "
                               "cubiertas del lado izquierdo entre el eje 2 y el 3'."
            },
            "km_unidad": {
                "type": ["number", "null"],
                "description": "Kilometraje de la unidad si el texto lo menciona."
            },
            "acciones": {
                "type": "array",
                "description": "Los movimientos a aplicar. Vacío si no se entiende "
                               "qué hizo o si falta un dato.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "tipo": {
                            "type": "string",
                            "enum": ["rotacion", "montaje", "desmontaje",
                                     "medicion", "recapado", "reparacion", "baja"]
                        },
                        "posicion": {
                            "type": ["string", "null"],
                            "description": "Código de posición afectada: 1I, 2IE, 3DE, AUX."
                        },
                        "posicion_destino": {
                            "type": ["string", "null"],
                            "description": "Solo para rotacion: a dónde va."
                        },
                        "cubierta": {
                            "type": ["string", "null"],
                            "description": "Código de la cubierta. Solo para montaje "
                                           "desde stock, si el texto lo dice."
                        },
                        "remanente_mm": {
                            "type": ["number", "null"],
                            "description": "Solo para medicion: milímetros de dibujo."
                        },
                        "nota": {"type": ["string", "null"]}
                    },
                    "required": ["tipo", "posicion", "posicion_destino",
                                 "cubierta", "remanente_mm", "nota"]
                }
            },
            "pregunta": {
                "type": ["string", "null"],
                "description": "Si falta información para decidir, la pregunta concreta "
                               "que hay que hacerle al gomero. Null si está todo claro."
            }
        },
        "required": ["resumen", "km_unidad", "acciones", "pregunta"]
    }
}


def _mapa_en_texto(mapa):
    filas = []
    for p in mapa:
        que = p["cubierta"] or "VACÍA"
        detalle = ""
        if p["cubierta"]:
            detalle = f" ({p['marca'] or 's/marca'}, {p['medida'] or 's/medida'}"
            if p["remanente_mm"] is not None:
                detalle += f", {p['remanente_mm']}mm"
            detalle += ")"
        lado = {"I": "izquierda", "D": "derecha", "X": "auxilio"}[p["lado"]]
        montaje = {"unica": "rueda simple", "interior": "dual interior",
                   "exterior": "dual exterior"}[p["montaje"]]
        ubicacion = "auxilio" if p["es_auxilio"] else f"eje {p['eje']}, {lado}, {montaje}"
        filas.append(f"  {p['posicion']:<5} {ubicacion:<38} {que}{detalle}")
    return "\n".join(filas)


def instrucciones(unidad, mapa):
    return f"""Sos el que carga los partes de gomería de Expreso Diemar.
El gomero escribe en castellano rioplatense, corto y con modismos de taller.
Tu trabajo es traducir eso a movimientos sobre las posiciones reales de esta
unidad, y nada más.

UNIDAD: {unidad['patente']}{' (interno ' + unidad['interno'] + ')' if unidad.get('interno') else ''}
{'Kilometraje registrado: ' + format(int(unidad['km_actual']), ',').replace(',', '.') if unidad.get('km_actual') else ''}

CÓMO ESTÁ ARMADA Y QUÉ TIENE PUESTO AHORA:
{_mapa_en_texto(mapa)}

CÓMO SE LEEN LOS CÓDIGOS
El número es el eje, contando desde adelante. Después el lado: I izquierda,
D derecha. En los ejes duales se agrega E si es la de afuera e I si es la de
adentro. AUX es el auxilio.

CÓMO HABLA EL GOMERO
- "la de adelante izquierda", "la del lado del chofer" = 1I
- "la del acompañante" = 1D
- "las de atrás", "las traseras" = los ejes duales, no el direccional
- "la de afuera" = exterior, "la de adentro" = interior
- "girar", "rotar", "cruzar", "cambiar de lugar" = rotacion
- "puse", "monté", "calcé" = montaje
- "saqué", "bajé" = desmontaje
- "la mandé a recapar" = recapado, "la mandé a arreglar" = reparacion
- "la tiré", "no va más", "se reventó" = baja
- "le medí", "tiene X milímetros" = medicion

REGLAS
1. Usá SOLO códigos de posición que existan en el mapa de arriba.
2. Una rotación es siempre un intercambio completo: si la de 2IE va a 3IE,
   tenés que agregar también la acción de 3IE a 2IE. Nunca dejes una posición
   sin cubierta por una rotación.
3. Si el texto no alcanza para saber qué posición tocó, no inventes: dejá
   acciones vacío y escribí la pregunta concreta en 'pregunta'.
4. Si menciona un kilometraje, ponelo en km_unidad.
5. El resumen tiene que ser entendible por el gomero que lo escribió, en una
   frase, nombrando las posiciones como las nombra él.

Ante la duda, preguntá. Es mucho peor guardar un movimiento equivocado que
pedir una aclaración."""


def interpretar(unidad, mapa, texto, cliente=None):
    """Devuelve la propuesta como dict. No toca la base."""
    cliente = cliente or anthropic.Anthropic()
    r = cliente.messages.create(
        model=MODELO,
        max_tokens=2000,
        system=instrucciones(unidad, mapa),
        thinking={"type": "adaptive"},
        tools=[HERRAMIENTA],
        tool_choice={"type": "tool", "name": "registrar"},
        messages=[{"role": "user", "content": texto}],
    )
    for bloque in r.content:
        if bloque.type == "tool_use" and bloque.name == "registrar":
            return bloque.input
    raise RuntimeError("Claude no devolvió una propuesta estructurada.")


# =====================================================================
# APLICAR LA PROPUESTA (después de que el gomero confirma)
# =====================================================================
def aplicar(cx, unidad, propuesta, parte_id=None, usuario=None, base=None):
    """Escribe la propuesta en la base, entera o nada.

    Devuelve la lista de lo que se hizo, para mostrarlo de vuelta.
    """
    import uuid
    if base is None:
        import base as base_mod
        base = base_mod

    acciones = propuesta.get("acciones") or []
    if not acciones:
        raise ValueError("La propuesta no tiene acciones para aplicar.")

    km = propuesta.get("km_unidad")
    grupo = uuid.uuid4()
    hecho = []

    def posicion(codigo):
        p = base.posicion_por_codigo(cx, unidad["id"], codigo)
        if not p:
            raise ValueError(f"La posición {codigo} no existe en esta unidad.")
        return p["id"]

    # Las rotaciones se juntan y se aplican de una sola vez: si se hicieran
    # de a una, un cruce chocaría contra el índice de posición ocupada.
    pares = [(posicion(a["posicion"]), posicion(a["posicion_destino"]))
             for a in acciones
             if a["tipo"] == "rotacion" and a.get("posicion") and a.get("posicion_destino")]
    if pares:
        base.rotar(cx, unidad["id"], pares, km=km, grupo=grupo,
                   parte_id=parte_id, usuario=usuario)
        hecho += [f"Rotación {a['posicion']} → {a['posicion_destino']}"
                  for a in acciones if a["tipo"] == "rotacion"]

    for a in acciones:
        tipo = a["tipo"]
        if tipo == "rotacion":
            continue

        if tipo == "montaje":
            if not a.get("cubierta"):
                raise ValueError(f"Falta el código de cubierta para montar en {a['posicion']}.")
            c = base.buscar_cubierta(cx, a["cubierta"])
            if not c:
                raise ValueError(f"No existe la cubierta {a['cubierta']}.")
            base.montar(cx, unidad["id"], posicion(a["posicion"]), c["id"], km=km,
                        grupo=grupo, parte_id=parte_id, usuario=usuario, nota=a.get("nota"))
            hecho.append(f"Montada {a['cubierta']} en {a['posicion']}")

        elif tipo in ("desmontaje", "recapado", "reparacion", "baja"):
            destino = {"desmontaje": "stock", "recapado": "recapado",
                       "reparacion": "reparacion", "baja": "baja"}[tipo]
            base.desmontar(cx, unidad["id"], posicion(a["posicion"]), km=km,
                           destino=destino, grupo=grupo, parte_id=parte_id,
                           usuario=usuario, nota=a.get("nota"))
            hecho.append(f"{tipo.capitalize()} de {a['posicion']}")

        elif tipo == "medicion":
            fila = cx.execute("""
                select cubierta_id from v_mapa_unidad
                where unidad_id = %s and posicion = %s""",
                (unidad["id"], a["posicion"])).fetchone()
            if not fila or not fila["cubierta_id"]:
                raise ValueError(f"La posición {a['posicion']} está vacía, no hay qué medir.")
            base.medir(cx, fila["cubierta_id"], a["remanente_mm"], km=km,
                       usuario=usuario, grupo=grupo)
            hecho.append(f"Medida {a['posicion']}: {a['remanente_mm']} mm")

    return hecho
