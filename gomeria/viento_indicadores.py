"""Los indicadores del viento y el viaje en el mapa.

Lo que más importa es el primero: **cuánto combustible cuesta el viento**.
El resto sale solo del viento y sirve para decidir (cuándo salir, qué
tramo cuidar) o para cuidar a la gente (ráfagas y viento cruzado).

El combustible de cada viaje
----------------------------
No hay un número de litros por viaje en ningún lado: hay cargas, con fecha
y patente, en `combustible_cargas`. Se reparten así, que es como se llena un
camión de larga distancia:

  * el camión sale lleno;
  * lo que carga en el camino y al llegar es lo que gastó en ese viaje.

Entonces el viaje se queda con las cargas de esa patente **después del día
de salida y hasta el día siguiente a la llegada**. Si antes de eso la misma
patente vuelve a salir, el viaje corta el día de esa nueva salida: la carga
de ese día es la que repone lo que se gastó en este viaje. La carga del día
de salida es del viaje anterior.

Los km son los del recorrido (~1.120 km): el tramo es siempre el mismo y el
satelital da una lectura por día, que no alcanza para cortar un viaje de
20 horas.

Da mal cuando la carga es parcial o cuando el camión hizo otra cosa en el
medio. Por eso se descartan los viajes con un consumo imposible (fuera de
CONSUMO_MINIMO–CONSUMO_MAXIMO), y la correlación solo se informa con
VIAJES_MINIMOS viajes o más. Con muchos viajes, el ruido de uno se diluye.
"""
import math
import re
from datetime import date, datetime, timedelta

import viento as vto

CONSUMO_MINIMO = 18      # L/100 km: menos que esto, fue una carga parcial
CONSUMO_MAXIMO = 70      # más que esto, se sumaron cargas de otro viaje
VIAJES_MINIMOS = 10      # con menos, una recta es casualidad
RAFAGA_PELIGROSA = 70    # km/h: a esto un semi vacío ya se mueve
CRUZADO_PELIGROSO = 40   # km/h de costado


def _patente(p):
    return re.sub(r"[^A-Z0-9]", "", str(p or "").upper())


def _media(valores):
    valores = [v for v in valores if v is not None]
    return round(sum(valores) / len(valores), 1) if valores else None


# ---------------------------------------------------------------------
# COMBUSTIBLE Y VIENTO
# ---------------------------------------------------------------------
def leer_cargas(cx, patentes, desde, hasta):
    """Las cargas de nuestra planilla de esas patentes, entre dos fechas."""
    if cx is None or not patentes:
        return []
    try:
        filas = cx.execute("""
            select patente, fecha, litros, importe from combustible_cargas
            where origen = 'planilla' and fecha between %s and %s
              and patente = any(%s) and litros > 0""",
            (desde, hasta, sorted(patentes))).fetchall()
    except Exception:
        cx.rollback()
        return None
    return [{"patente": _patente(f["patente"]), "fecha": f["fecha"],
             "litros": float(f["litros"]),
             "importe": None if f["importe"] is None else float(f["importe"])}
            for f in filas]


def litros_por_viaje(viajes, cargas):
    """A cada viaje le pone los litros que le tocan (ver arriba).

    `viajes` son los resúmenes de viento.resumir. Devuelve una lista nueva,
    uno por viaje con patente, con litros, importe, consumo y por qué no
    tiene consumo cuando no lo tiene.
    """
    por_patente = {}
    for c in cargas:
        por_patente.setdefault(c["patente"], []).append(c)
    salida = []
    viajes = sorted((v for v in viajes if _patente(v.get("patente"))),
                    key=lambda v: (_patente(v["patente"]), v["salida"]))
    for i, v in enumerate(viajes):
        pat = _patente(v["patente"])
        desde = v["salida"].date()
        hasta = v["llegada"].date() + timedelta(days=1)
        siguiente = viajes[i + 1] if i + 1 < len(viajes) else None
        if siguiente and _patente(siguiente["patente"]) == pat:
            hasta = min(hasta, siguiente["salida"].date())
        suyas = [c for c in por_patente.get(pat, ())
                 if desde < c["fecha"] <= hasta]
        litros = sum(c["litros"] for c in suyas)
        importes = [c["importe"] for c in suyas if c["importe"]]
        fila = {"hoja": v.get("hoja"), "patente": pat, "chofer": v.get("chofer"),
                "sentido": v["sentido"], "salida": v["salida"],
                "contra_media": v.get("contra_media"), "cargas": len(suyas),
                "litros": round(litros, 1),
                "importe": round(sum(importes), 2) if importes else None,
                "consumo": None, "motivo": None}
        if not suyas:
            fila["motivo"] = "sin cargas después del viaje"
        elif v.get("contra_media") is None:
            fila["motivo"] = "sin viento"
        else:
            consumo = litros * 100 / vto.KM_TOTAL
            if CONSUMO_MINIMO <= consumo <= CONSUMO_MAXIMO:
                fila["consumo"] = round(consumo, 1)
            else:
                fila["motivo"] = (f"{consumo:.0f} L/100 km no es creíble: carga parcial "
                                  "o sumó otro viaje")
        salida.append(fila)
    return salida


def recta(pares):
    """Correlación y recta de mínimos cuadrados de (x, y).

    Devuelve n, r, r², pendiente, ordenada y si la relación es firme: con
    VIAJES_MINIMOS o más y un t de Student de 2 o más (≈95%).
    """
    n = len(pares)
    if n < 3:
        return {"n": n, "r": None, "r2": None, "pendiente": None, "ordenada": None,
                "firme": False}
    mx = sum(x for x, _ in pares) / n
    my = sum(y for _, y in pares) / n
    sxx = sum((x - mx) ** 2 for x, _ in pares)
    syy = sum((y - my) ** 2 for _, y in pares)
    sxy = sum((x - mx) * (y - my) for x, y in pares)
    if sxx == 0 or syy == 0:
        return {"n": n, "r": None, "r2": None, "pendiente": None, "ordenada": None,
                "firme": False}
    r = sxy / math.sqrt(sxx * syy)
    b = sxy / sxx
    t = abs(r) * math.sqrt((n - 2) / max(1e-12, 1 - r * r))
    return {"n": n, "r": round(r, 3), "r2": round(r * r, 3),
            "pendiente": round(b, 4), "ordenada": round(my - b * mx, 2),
            "t": round(t, 2), "firme": n >= VIAJES_MINIMOS and t >= 2}


def combustible_y_viento(viajes, cargas):
    """El indicador principal: cuánto consumo explica el viento."""
    filas = litros_por_viaje(viajes, cargas)
    validas = [f for f in filas if f["consumo"] is not None]
    ajuste = recta([(f["contra_media"], f["consumo"]) for f in validas])
    b = ajuste["pendiente"]

    # El consumo según cómo le fue con el viento: sin estadística, para
    # que se entienda de un vistazo.
    grupos = []
    for nombre, cumple in (("a favor", lambda c: c <= -6),
                           ("neutro", lambda c: -6 < c < 6),
                           ("en contra", lambda c: 6 <= c < 15),
                           ("en contra fuerte", lambda c: c >= 15)):
        suyas = [f for f in validas if cumple(f["contra_media"])]
        grupos.append({"grupo": nombre, "viajes": len(suyas),
                       "consumo": _media(f["consumo"] for f in suyas)})

    # Cuánto se gastó por el viento: la recta dice cuántos L/100 km suma
    # cada km/h en contra; por los km del viaje, litros.
    litros, importe = sum(f["litros"] for f in validas), sum(
        f["importe"] or 0 for f in validas)
    precio = importe / litros if litros and importe else None
    costo = None
    if b is not None:
        extra = [b * f["contra_media"] * vto.KM_TOTAL / 100 for f in validas]
        perdidos = sum(e for e in extra if e > 0)
        ganados = -sum(e for e in extra if e < 0)
        costo = {"litros_en_contra": round(perdidos), "litros_a_favor": round(ganados),
                 "litros_neto": round(perdidos - ganados),
                 "pesos_en_contra": round(perdidos * precio) if precio else None,
                 "pesos_neto": round((perdidos - ganados) * precio) if precio else None,
                 "precio_litro": round(precio, 2) if precio else None,
                 "litros_cada_10": round(b * 10 * vto.KM_TOTAL / 100, 1)}

    # El consumo sin el viento: lo que habría gastado cada uno con viento
    # neutro. Es la comparación justa entre choferes y camiones.
    def ajustado(clave):
        tabla = {}
        for f in validas:
            tabla.setdefault(f[clave] or "–", []).append(f)
        salida = []
        for k, fs in tabla.items():
            real = _media(f["consumo"] for f in fs)
            sin = (_media(f["consumo"] - b * f["contra_media"] for f in fs)
                   if b is not None and ajuste["firme"] else None)
            salida.append({"nombre": k, "viajes": len(fs), "consumo": real,
                           "sin_viento": sin,
                           "contra_media": _media(f["contra_media"] for f in fs)})
        return sorted(salida, key=lambda x: (x["sin_viento"] is None,
                                             -(x["sin_viento"] or x["consumo"] or 0)))

    return {
        "ajuste": ajuste,
        "puntos": [{"x": f["contra_media"], "y": f["consumo"], "hoja": f["hoja"],
                    "patente": f["patente"], "sentido": f["sentido"],
                    "salida": f["salida"]} for f in validas],
        "grupos": grupos, "costo": costo,
        "por_patente": ajustado("patente"), "por_chofer": ajustado("chofer"),
        "viajes_con_consumo": len(validas), "viajes_total": len(filas),
        "descartes": _contar(f["motivo"] for f in filas if f["motivo"]),
    }


def _contar(motivos):
    cuenta = {}
    for m in motivos:
        clave = "consumo no creíble" if "no es creíble" in m else m
        cuenta[clave] = cuenta.get(clave, 0) + 1
    return [{"motivo": k, "viajes": v} for k, v in sorted(cuenta.items(), key=lambda x: -x[1])]


# ---------------------------------------------------------------------
# LOS QUE SALEN SOLO DEL VIENTO
# ---------------------------------------------------------------------
def _ciudad(lugar):
    return lugar[len("después de "):] if lugar.startswith("después de ") else lugar


def por_mes(viajes):
    """El viento en contra promedio de cada mes, de ida y de vuelta."""
    meses = {}
    for v in viajes:
        if v.get("contra_media") is None:
            continue
        m = meses.setdefault(v["salida"].strftime("%Y-%m"), {"ida": [], "vuelta": []})
        m[v["sentido"]].append(v)
    return [{"mes": k,
             **{s: {"viajes": len(vs), "contra": _media(x["contra_media"] for x in vs),
                    "fuertes": sum(x["calificacion"] == "en contra fuerte" for x in vs)}
                for s, vs in m.items()}}
            for k, m in sorted(meses.items())]


def por_tramo(viajes):
    """Qué tramo de la ruta pega más, de ida y de vuelta.

    Cada hora de cada viaje cae en el tramo de la ciudad por la que iba.
    """
    orden = [n for n, _, _ in vto.RUTA]
    tramos = {n: {"ida": [], "vuelta": []} for n in orden}
    for v in viajes:
        for h in v.get("detalle", ()):
            if h.get("velocidad") is None:
                continue
            tramos.setdefault(_ciudad(h["lugar"]), {"ida": [], "vuelta": []})[v["sentido"]].append(h)
    salida = []
    for nombre in orden:
        t = tramos[nombre]
        fila = {"tramo": nombre}
        for s in ("ida", "vuelta"):
            hs = t[s]
            fila[s] = {"horas": len(hs), "contra": _media(h["contra"] for h in hs),
                       "velocidad": _media(h["velocidad"] for h in hs),
                       "rafaga": max((h["rafaga"] for h in hs if h.get("rafaga") is not None),
                                     default=None)}
        salida.append(fila)
    return salida


def por_hora_salida(viajes):
    """El viento en contra según a qué hora salió: de a tres horas.

    Solo los viajes con hora de salida de verdad: la supuesta los juntaría
    todos en la misma franja.
    """
    franjas = {h: {"ida": [], "vuelta": []} for h in range(0, 24, 3)}
    for v in viajes:
        if v.get("contra_media") is None or not v.get("salida_real"):
            continue
        franjas[v["salida"].hour // 3 * 3][v["sentido"]].append(v["contra_media"])
    return [{"desde": h, "hasta": h + 3,
             **{s: {"viajes": len(c), "contra": _media(c)} for s, c in f.items()}}
            for h, f in franjas.items()]


def seguridad(viajes):
    """Los viajes que tuvieron ráfagas o viento cruzado peligrosos."""
    lista = []
    horas_rafaga = horas_cruzado = 0
    for v in viajes:
        rafagas = [h for h in v.get("detalle", ())
                   if (h.get("rafaga") or 0) >= RAFAGA_PELIGROSA]
        cruzados = [h for h in v.get("detalle", ())
                    if (h.get("cruzado") or 0) >= CRUZADO_PELIGROSO]
        horas_rafaga += len(rafagas)
        horas_cruzado += len(cruzados)
        if rafagas or cruzados:
            peor_r = max(rafagas, key=lambda h: h["rafaga"], default=None)
            peor_c = max(cruzados, key=lambda h: h["cruzado"], default=None)
            lista.append({"hoja": v.get("hoja"), "patente": v.get("patente"),
                          "chofer": v.get("chofer"), "sentido": v["sentido"],
                          "salida": v["salida"],
                          "rafaga": peor_r and peor_r["rafaga"],
                          "rafaga_lugar": peor_r and peor_r["lugar"],
                          "cruzado": peor_c and peor_c["cruzado"],
                          "cruzado_lugar": peor_c and peor_c["lugar"],
                          "horas": len({h["hora"] for h in rafagas + cruzados})})
    lista.sort(key=lambda x: -max(x["rafaga"] or 0, x["cruzado"] or 0))
    return {"umbral_rafaga": RAFAGA_PELIGROSA, "umbral_cruzado": CRUZADO_PELIGROSO,
            "viajes": len(lista), "horas_rafaga": horas_rafaga,
            "horas_cruzado": horas_cruzado, "lista": lista[:50]}


# ---------------------------------------------------------------------
# LO QUE PIDE LA PANTALLA
# ---------------------------------------------------------------------
def indicadores(cx, desde=None, hasta=None, forzar=False, leer_hojas=None, pedir=None,
                cargas=None):
    """Todo lo de la solapa Indicadores. Es la respuesta de /api/viento/indicadores."""
    base = vto.informe(cx, desde, hasta, forzar=forzar, leer_hojas=leer_hojas, pedir=pedir)
    viajes = base["viajes"]
    avisos = list(base["avisos"])
    patentes = {_patente(v.get("patente")) for v in viajes} - {""}
    if cargas is None:
        cargas = leer_cargas(cx, patentes, base["desde"], base["hasta"] + timedelta(days=5))
        if cargas is None:
            avisos.append("No se pudieron leer las cargas de combustible: falta correr "
                          "gomeria/10_combustible.sql.")
            cargas = []
    if not patentes:
        avisos.append("La planilla de viajes no trae la patente: sin ella no se puede "
                      "cruzar con el combustible.")
    return {
        "desde": base["desde"], "hasta": base["hasta"], "avisos": avisos,
        "viajes": len(viajes), "km_total": vto.KM_TOTAL,
        "combustible": combustible_y_viento(viajes, cargas),
        "por_mes": por_mes(viajes), "por_tramo": por_tramo(viajes),
        "por_hora_salida": por_hora_salida(viajes), "seguridad": seguridad(viajes),
        "criterios": {"consumo_minimo": CONSUMO_MINIMO, "consumo_maximo": CONSUMO_MAXIMO,
                      "viajes_minimos": VIAJES_MINIMOS},
    }


def _hoja(texto):
    return str(texto or "").strip().lstrip("0").upper()


def viaje_en_mapa(cx, hoja, leer_hojas=None, pedir=None):
    """El viaje de esa hoja de ruta, con el viento de toda la ruta a cada hora.

    Para el mapa no alcanza con el viento donde estaba el camión: se ve el
    de todos los puntos del recorrido, así se entiende qué tenía adelante.
    Devuelve una lista: la misma hoja puede ser la ida y la vuelta.
    """
    buscada = _hoja(hoja)
    if not buscada:
        raise ValueError("Escribí el número de hoja de ruta.")
    planilla = leer_hojas() if leer_hojas else vto.hojas()
    viajes = [v for v in planilla["viajes"] if _hoja(v.get("hoja")) == buscada]
    if not viajes:
        raise ValueError(f"La hoja {hoja} no es un viaje Buenos Aires ↔ Catamarca "
                         "en la planilla, o no existe.")
    dias = set()
    for v in viajes:
        llegada, _ = vto.llegada_estimada(v)
        d = v["salida"].date()
        while d <= llegada.date():
            dias.add(d)
            d += timedelta(days=1)
    viento = vto.viento_para(cx, dias, **({"pedir": pedir} if pedir else {}))
    salida = []
    for v in sorted(viajes, key=lambda x: x["salida"]):
        r = vto.resumir(v, viento)
        vuelta = v["sentido"] == "vuelta"
        campo = []
        for h in r["detalle"]:
            fila = []
            for i, p in enumerate(vto.PUNTOS):
                w = viento(p["lat"], p["lon"], h["hora"])
                if not w:
                    fila.append(None)
                    continue
                rumbo = vto.PUNTOS[max(0, i - 1)]["rumbo"] if i == len(vto.PUNTOS) - 1 else p["rumbo"]
                if vuelta:
                    rumbo = (rumbo + 180) % 360
                contra, _ = vto.de_frente(w["velocidad"], w["direccion"], rumbo)
                fila.append([round(w["velocidad"]), round(w["direccion"]),
                             None if w.get("rafaga") is None else round(w["rafaga"]),
                             contra])
            campo.append(fila)
        salida.append({**r, "campo": campo})
    return {"viajes": salida, "avisos": list(viento.avisos),
            "puntos": [{"lugar": p["lugar"], "lat": p["lat"], "lon": p["lon"],
                        "km": p["km"]} for p in vto.PUNTOS],
            "ruta": [{"lugar": n, "lat": la, "lon": lo} for n, la, lo in vto.RUTA]}
