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
                            "description": "Número de fuego de la cubierta, tal cual lo "
                                           "escribió el gomero (ej: 079, 327). Sin la "
                                           "marca. Va SIEMPRE que el texto lo nombre, "
                                           "tanto en la que entra como en la que sale."
                        },
                        "marca": {
                            "type": ["string", "null"],
                            "description": "Marca de esa cubierta si el texto la dice "
                                           "(Michelin, Fate, Bridgestone...)."
                        },
                        "remanente_mm": {
                            "type": ["number", "null"],
                            "description": "Solo para medicion: milímetros de dibujo."
                        },
                        "nota": {"type": ["string", "null"]}
                    },
                    "required": ["tipo", "posicion", "posicion_destino",
                                 "cubierta", "marca", "remanente_mm", "nota"]
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
- "puse", "monté", "calcé", "entra", "entran" = montaje
- "saqué", "bajé", "sale", "salen" = desmontaje
- "la mandé a recapar", "sale para recapar" = recapado
- "la mandé a arreglar", "sale para reparar" = reparacion
- "la tiré", "no va más", "se reventó", "sale de baja" = baja
- "le medí", "tiene X milímetros" = medicion
- "3 eje", "tercer eje", "eje 3" = el eje 3 del mapa
- "recapada", "nueva", "usada" describen a la cubierta, no son un movimiento:
  eso va en la nota, no cambia el tipo.

CÓMO VIENE ESCRITO EL PARTE
Casi siempre llega con la patente en la primera línea y el trabajo abajo:

    Patente: AD 900 UK
    3 eje lado izquierdo entran 2 Michelin 079 y 327 recapadas nuevas..
    salen 2 Fate 380 y 381 para recapar..

Eso se lee así:
- La patente ya está resuelta, es la unidad de arriba. No la vuelvas a mirar.
- Los números sueltos (079, 327, 380, 381) son números de fuego de cubiertas.
  La palabra de al lado (Michelin, Fate) es la marca: va en la nota, nunca
  en el campo cubierta.
- "entran" son las que se montan, "salen" las que se sacan. Las que salen
  liberan justamente las posiciones donde entran las otras.
- Lo que va detrás de "para" es a dónde se van las que salen: "para recapar"
  = recapado, "para arreglar" = reparacion, "para tirar" = baja. Si no dice
  nada, es desmontaje común (van a stock).

REGLAS
1. Usá SOLO códigos de posición que existan en el mapa de arriba.
2. Una rotación es siempre un intercambio completo: si la de 2IE va a 3IE,
   tenés que agregar también la acción de 3IE a 2IE. Nunca dejes una posición
   sin cubierta por una rotación.
3. Si el texto no alcanza para saber qué posición tocó, no inventes: dejá
   acciones vacío y escribí la pregunta concreta en 'pregunta'.
4. Cuando dice un eje y un lado sin aclarar si es la de adentro o la de
   afuera, y en ese eje y lado hay dos posiciones duales, el trabajo es
   sobre las dos: emitilas en orden exterior y después interior (3IE, 3II).
5. Poné el número de fuego en 'cubierta' siempre que el texto lo diga, en la
   que entra y también en la que sale, y la marca en 'marca'.
6. Si el número de una cubierta que sale figura en el mapa de arriba, la
   posición que toca es esa, no la que sugiera el orden del texto.
7. El mapa puede estar incompleto: todavía se están cargando las cubiertas
   que hoy tiene puesta cada unidad. Que una posición figure VACÍA no
   significa que el gomero se haya equivocado. Si él dice que de ahí salió
   una cubierta, registrala igual con su número de fuego; el sistema la da
   de alta y la deja donde corresponde. No preguntes por eso.
8. Cuando entran y salen cubiertas en el mismo lugar, emparejalas en el
   orden en que están escritas: la primera que sale deja libre la posición
   donde va la primera que entra. Y poné SIEMPRE primero las acciones de
   las que salen y después las de las que entran.
9. La cantidad que entra tiene que coincidir con la cantidad que sale. Si no
   coincide, o si hay más cubiertas nombradas que posiciones en ese lugar,
   no inventes: preguntá.
10. Si menciona un kilometraje, ponelo en km_unidad.
11. El resumen tiene que ser entendible por el gomero que lo escribió, en una
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

    def cubierta_de(a):
        """La cubierta que nombró el gomero. Si no está en la base, se da de alta.

        Mientras se termina de cargar el inventario aparecen números de fuego
        que el sistema no vio nunca. Frenar el parte por eso deja el trabajo
        sin registrar; darla de alta al pasar la incorpora al stock, que es
        justamente lo que hace falta.
        """
        c = base.buscar_cubierta_flexible(cx, a["cubierta"])
        if c:
            return c, False
        codigo = str(a["cubierta"]).strip().upper()
        base.alta_cubierta(cx, codigo, marca=(a.get("marca") or None),
                           usuario=usuario,
                           nota="Alta automática al cargar un parte.")
        return base.buscar_cubierta(cx, codigo), True

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

    # Primero las que salen y después las que entran, sin importar en qué
    # orden las escribió el gomero: si se montara antes de desmontar, montar()
    # mandaría a stock la cubierta que salía, en vez de a recapado. Las
    # mediciones van al final, para poder medir una recién puesta.
    ORDEN = {"desmontaje": 0, "recapado": 0, "reparacion": 0, "baja": 0,
             "montaje": 1, "medicion": 2}
    for a in sorted(acciones, key=lambda a: ORDEN.get(a["tipo"], 1)):
        tipo = a["tipo"]
        if tipo == "rotacion":
            continue

        if tipo == "montaje":
            if not a.get("cubierta"):
                raise ValueError(f"Falta el número de fuego para montar en {a['posicion']}.")
            c, nueva = cubierta_de(a)
            puesta = base.donde_esta(cx, c["id"])
            if puesta and puesta["posicion"] != a["posicion"]:
                raise ValueError(
                    f"La cubierta {c['codigo']} figura montada en "
                    f"{base.fmtPat(puesta['patente'])}, posición {puesta['posicion']}. "
                    f"Sacala de ahí antes de ponerla en {a['posicion']}.")
            base.montar(cx, unidad["id"], posicion(a["posicion"]), c["id"], km=km,
                        grupo=grupo, parte_id=parte_id, usuario=usuario, nota=a.get("nota"))
            hecho.append(f"Montada {c['codigo']} en {a['posicion']}"
                         + (" (alta nueva)" if nueva else ""))

        elif tipo in ("desmontaje", "recapado", "reparacion", "baja"):
            destino = {"desmontaje": "stock", "recapado": "recapado",
                       "reparacion": "reparacion", "baja": "baja"}[tipo]
            donde = {"stock": "stock", "recapado": "recapado",
                     "reparacion": "reparación", "baja": "baja"}[destino]
            pos_id = posicion(a["posicion"])
            puesta = base.montaje_abierto(cx, unidad["id"], pos_id)

            if puesta:
                base.desmontar(cx, unidad["id"], pos_id, km=km, destino=destino,
                               grupo=grupo, parte_id=parte_id, usuario=usuario,
                               nota=a.get("nota"))
                hecho.append(f"Sale de {a['posicion']} a {donde}")
            else:
                # El mapa todavía no tiene cargado lo que la unidad trae puesto,
                # así que el sistema ve la posición vacía aunque el gomero haya
                # sacado una cubierta de ahí. Se asienta igual: lo que importa
                # es dónde queda la cubierta.
                if not a.get("cubierta"):
                    raise ValueError(
                        f"En {a['posicion']} el sistema no tiene ninguna cubierta "
                        f"cargada. Escribí el número de fuego de la que sacaste "
                        f"para poder registrarla.")
                c, nueva = cubierta_de(a)
                base.sacar_de_servicio(cx, c["id"], destino=destino,
                                       unidad_id=unidad["id"], posicion_id=pos_id,
                                       km=km, grupo=grupo, parte_id=parte_id,
                                       usuario=usuario, nota=a.get("nota"))
                hecho.append(f"Sale {c['codigo']} de {a['posicion']} a {donde}"
                             + (" (alta nueva)" if nueva else ""))

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
