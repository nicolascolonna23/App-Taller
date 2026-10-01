"""El viento que le tocó a cada viaje Buenos Aires ↔ Catamarca.

Tres fuentes, y ninguna es nuestra:

  * Los viajes salen de la planilla de hojas de ruta del BI
    (`reporte_hojas.xlsx`). Se baja desde el servidor: el navegador no
    puede leer bi.sistemaexpreso.com.ar (CORS y http mezclado con https).
  * El viento, de Open-Meteo: el reanálisis ERA5, hora por hora, en
    cualquier coordenada. Viene con unos cinco días de atraso, así que un
    viaje de esta semana todavía no tiene viento.
  * El recorrido, de acá abajo: la RN 9 hasta Córdoba capital y de ahí al
    norte por Deán Funes hasta Catamarca.

Dónde estaba el camión a cada hora no se sabe: Hawk da el odómetro, no la
traza. Se supone velocidad pareja entre la salida y la llegada. Con puntos
cada ~50 km y un viento que el modelo ya promedia en celdas de 10 a 25 km,
el error de suponer es menor que el del propio dato.

La planilla no se vio al escribir esto. Las columnas se reconocen por el
nombre (ver COLUMNAS): si alguna no se reconoce, la pantalla dice cuáles
encontró, y el arreglo es agregar el nombre a la lista.
"""
import io
import math
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import json
from datetime import date, datetime, timedelta, time as hora_del_dia

URL_HOJAS = (os.environ.get("VIENTO_HOJAS_URL", "").strip()
             or "http://bi.sistemaexpreso.com.ar/reporte_hojas.xlsx")

# Con clave, el servidor comercial de Open-Meteo; sin clave, el gratuito,
# que es solo para uso no comercial.
CLAVE_METEO = os.environ.get("OPEN_METEO_APIKEY", "").strip()
URL_METEO = ("https://customer-archive-api.open-meteo.com/v1/archive" if CLAVE_METEO
             else "https://archive-api.open-meteo.com/v1/archive")

# ---------------------------------------------------------------------
# EL RECORRIDO
# ---------------------------------------------------------------------
# De Buenos Aires a Catamarca, en el orden en que se pasa. Las coordenadas
# son las de la ciudad; el camión pasa por la circunvalación, a pocos km,
# y a esa distancia el viento del modelo es el mismo.
RUTA = (
    ("Buenos Aires",            -34.603, -58.381),
    ("Zárate",                  -34.098, -59.029),
    ("San Nicolás",             -33.335, -60.227),
    ("Rosario",                 -32.947, -60.639),
    ("Cañada de Gómez",         -32.816, -61.395),
    ("Marcos Juárez",           -32.697, -62.106),
    ("Bell Ville",              -32.626, -62.689),
    ("Villa María",             -32.407, -63.240),
    ("Oncativo",                -31.913, -63.682),
    ("Córdoba",                 -31.420, -64.188),
    ("Jesús María",             -30.981, -64.094),
    ("Deán Funes",              -30.420, -64.350),
    ("Quilino",                 -30.212, -64.500),
    ("San José de las Salinas", -30.005, -64.623),
    ("Recreo",                  -29.281, -65.061),
    ("Chumbicha",               -28.857, -66.237),
    ("Catamarca",               -28.469, -65.779),
)

# La línea recta entre ciudades es algo más corta que la ruta, pero el
# quiebre por Chumbicha ya alarga lo suficiente: la suma da ~1.120 km, lo
# que marca la ruta. Solo cambia los km que se muestran; dónde está el
# camión se calcula en proporción.
FACTOR_RUTA = 1.0
# Entre dos puntos de viento, como mucho esto. Más cerca que la celda del
# modelo no agrega nada.
PASO_KM = 50
# Sin hora de llegada, el viaje se estira a esta velocidad media, con las
# paradas incluidas.
VELOCIDAD_MEDIA = 60
# Un viaje de más de esto tuvo una parada larga en el medio (un fin de
# semana, un taller). Repartirlo parejo pondría al camión en la ruta
# cuando estaba parado, así que se estima con la velocidad media.
HORAS_MAXIMAS = 48
# La hora que se supone cuando la planilla trae solo la fecha.
HORA_SUPUESTA = 8

# Lo que se reconoce como cada punta. Se compara sin tildes y en minúscula.
# Pilar y Avellaneda quedan afuera a propósito: hay una en Córdoba y otra
# en Santa Fe.
BUENOS_AIRES = ("buenos aires", "bs as", "bsas", "bs.as", "caba", "c.a.b.a",
                "capital federal", "cap fed", "cap. fed", "baires", "pacheco",
                "tortuguitas", "escobar", "garin", "barracas", "pompeya",
                "mercado central", "ezeiza")
CATAMARCA = ("catamarca", "san fernando del valle", "sfvc", "valle viejo",
             "fray mamerto esquiu", "ctca")


def _km(a, b):
    """Distancia en línea recta, en km, entre dos (lat, lon)."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


def _rumbo(a, b):
    """Hacia dónde se va de a a b: 0 es el norte, 90 el este."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    x = math.sin(lo2 - lo1) * math.cos(la2)
    y = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def puntos():
    """El recorrido de ida en puntos cada PASO_KM como mucho.

    Cada punto: lugar (la ciudad anterior), lat, lon, km desde Buenos Aires
    y el rumbo del camión de ida en ese tramo.
    """
    salida, km = [], 0.0
    for (nombre, la, lo), (_, la2, lo2) in zip(RUTA, RUTA[1:]):
        tramo = _km((la, lo), (la2, lo2))
        rumbo = _rumbo((la, lo), (la2, lo2))
        partes = max(1, math.ceil(tramo / PASO_KM))
        for i in range(partes):
            f = i / partes
            salida.append({"lugar": nombre if i == 0 else f"después de {nombre}",
                           "lat": round(la + (la2 - la) * f, 2),
                           "lon": round(lo + (lo2 - lo) * f, 2),
                           "km": round((km + tramo * f) * FACTOR_RUTA),
                           "rumbo": round(rumbo)})
        km += tramo
    nombre, la, lo = RUTA[-1]
    salida.append({"lugar": nombre, "lat": round(la, 2), "lon": round(lo, 2),
                   "km": round(km * FACTOR_RUTA), "rumbo": salida[-1]["rumbo"]})
    return salida


PUNTOS = puntos()
KM_TOTAL = PUNTOS[-1]["km"]


# ---------------------------------------------------------------------
# LA PLANILLA DE VIAJES
# ---------------------------------------------------------------------
def _norm(texto):
    """Sin tildes, en minúscula, con los separadores como espacios."""
    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# Cada dato con los nombres que puede tener la columna, del más seguro al
# menos. Un nombre suelto se compara con el encabezado entero; los que
# terminan en * alcanza con que el encabezado empiece así.
COLUMNAS = {
    "salida":       ("fecha salida", "fecha de salida", "f salida", "salida",
                     "fecha partida", "partida", "fecha inicio", "inicio",
                     "fecha hora salida", "fecha salida*", "salida*",
                     "fecha hoja", "fecha"),
    "hora_salida":  ("hora salida", "hora de salida", "hs salida", "hora"),
    "llegada":      ("fecha llegada", "fecha de llegada", "f llegada", "llegada",
                     "fecha arribo", "arribo", "fecha fin", "fin",
                     "fecha llegada*", "llegada*"),
    "hora_llegada": ("hora llegada", "hora de llegada", "hs llegada", "hora arribo"),
    "origen":       ("origen", "sucursal origen", "localidad origen", "desde",
                     "origen*"),
    "destino":      ("destino", "sucursal destino", "localidad destino", "hasta",
                     "destino*"),
    "recorrido":    ("recorrido", "ruta", "trayecto", "itinerario", "tramo",
                     "viaje", "descripcion"),
    "patente":      ("patente", "patentes", "dominio", "dominios",
                     "patente tractor", "tractor", "dominio tractor", "unidad",
                     "unidades", "camion", "vehiculo", "vehiculos", "movil",
                     "moviles", "equipo", "equipos", "patente*", "dominio*"),
    "semi":         ("semi", "semirremolque", "acoplado", "patente semi",
                     "dominio semi"),
    "chofer":       ("chofer", "conductor", "chofer*", "conductor*"),
    "hoja":         ("nro hoja", "numero hoja", "hoja", "n hoja", "nro", "numero",
                     "hoja de ruta", "id hoja", "id"),
}


def detectar(encabezados):
    """Qué columna es cada dato: {dato: índice}. Cada columna se usa una vez."""
    normales = [_norm(e) for e in encabezados]
    usadas, mapa = set(), {}
    # Primero todas las coincidencias exactas y recién después las de
    # prefijo: «fecha salida» no le puede robar a nadie la columna «fecha».
    for exacta in (True, False):
        for dato, nombres in COLUMNAS.items():
            if dato in mapa:
                continue
            for nombre in nombres:
                prefijo = nombre.endswith("*")
                if prefijo == exacta:
                    continue
                nombre = nombre.rstrip("*")
                for i, e in enumerate(normales):
                    if i in usadas or not e:
                        continue
                    if (e.startswith(nombre) if prefijo else e == nombre):
                        mapa[dato] = i
                        usadas.add(i)
                        break
                if dato in mapa:
                    break
    return mapa


def _fecha(v):
    """datetime desde lo que traiga la celda. None si no se entiende."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, (int, float)):
        # Número de serie de Excel: días desde el 30/12/1899.
        if 20000 < v < 80000:
            return datetime(1899, 12, 30) + timedelta(days=float(v))
        return None
    s = str(v).strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%d", "%d-%m-%Y %H:%M", "%d-%m-%Y", "%d/%m/%y %H:%M", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _hora(v):
    """(hora, minuto) desde lo que traiga la celda de hora, o None."""
    if v is None or v == "":
        return None
    if isinstance(v, hora_del_dia):
        return v.hour, v.minute
    if isinstance(v, datetime):
        return v.hour, v.minute
    if isinstance(v, (int, float)) and 0 <= v < 1:
        minutos = round(v * 24 * 60)
        return minutos // 60 % 24, minutos % 60
    m = re.match(r"^\s*(\d{1,2})[:.hH](\d{2})", str(v))
    if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
        return int(m.group(1)), int(m.group(2))
    return None


def _con_hora(fecha, hora):
    """Junta fecha y hora. Devuelve (datetime, si la hora es de verdad)."""
    if fecha is None:
        return None, False
    if hora is not None:
        return fecha.replace(hour=hora[0], minute=hora[1], second=0), True
    if (fecha.hour, fecha.minute, fecha.second) != (0, 0, 0):
        return fecha, True
    return fecha.replace(hour=HORA_SUPUESTA), False


def _es(texto, nombres):
    t = " " + _norm(texto) + " "
    return any(" " + _norm(n) + " " in t for n in nombres)


def sentido(origen, destino, recorrido=None):
    """'ida' (Buenos Aires → Catamarca), 'vuelta', o None si no es el tramo."""
    if origen or destino:
        if _es(origen, BUENOS_AIRES) and _es(destino, CATAMARCA):
            return "ida"
        if _es(origen, CATAMARCA) and _es(destino, BUENOS_AIRES):
            return "vuelta"
    if recorrido:
        # «BS AS - CATAMARCA», «Catamarca / Buenos Aires»: manda cuál
        # aparece primero.
        t = " " + _norm(recorrido) + " "
        def donde(nombres):
            pos = [t.find(" " + _norm(n) + " ") for n in nombres]
            pos = [p for p in pos if p >= 0]
            return min(pos) if pos else None
        ba, ca = donde(BUENOS_AIRES), donde(CATAMARCA)
        if ba is not None and ca is not None:
            return "ida" if ba < ca else "vuelta"
    return None


# Una patente argentina: la del Mercosur (AB 123 CD) o la vieja (ABC 123),
# con o sin espacios adentro, y entera: «Tractor AE123CD» no es «RAE123».
PATENTE = re.compile(r"\b(?:[A-Z]{2} ?\d{3} ?[A-Z]{2}|[A-Z]{3} ?\d{3})\b")


def patentes_de(texto):
    """Todas las patentes de una celda, en el orden en que aparecen.

    La planilla trae en una sola columna el tractor, el semi y a veces
    otra más, separadas por coma, barra o guión: cualquier cosa que no sea
    letra ni número cuenta como separador.
    """
    limpio = re.sub(r"[^A-Z0-9]+", " ", str(texto or "").upper())
    salida = []
    for m in PATENTE.finditer(limpio):
        p = m.group().replace(" ", "")
        if p not in salida:
            salida.append(p)
    return salida


def _texto(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def leer_filas(filas):
    """Los viajes del tramo a partir de las filas de la planilla.

    `filas` es una lista de listas; el encabezado puede no estar en la
    primera (los reportes suelen traer un título arriba): se toma la fila,
    de las primeras diez, en la que se reconocen más columnas.

    Devuelve {"viajes", "columnas", "encabezados", "descartados", "otros"}.
    Levanta ValueError, con los encabezados que vio, si no puede armar un
    viaje con lo que hay.
    """
    mejor, fila_enc = {}, 0
    for i, fila in enumerate(filas[:10]):
        mapa = detectar(fila)
        if len(mapa) > len(mejor):
            mejor, fila_enc = mapa, i
    encabezados = [_texto(e) for e in (filas[fila_enc] if filas else [])]
    mapa = mejor
    falta = []
    if "salida" not in mapa:
        falta.append("la fecha de salida")
    if not ({"origen", "destino"} <= mapa.keys() or "recorrido" in mapa):
        falta.append("el origen y el destino (o una columna de recorrido)")
    if falta:
        raise ValueError(
            "No se reconoce en la planilla " + " ni ".join(falta) + ". "
            "Columnas encontradas: " + ", ".join(e for e in encabezados if e) + ".")

    def celda(fila, dato):
        i = mapa.get(dato)
        return fila[i] if i is not None and i < len(fila) else None

    viajes, descartados, otros = [], 0, 0
    for fila in filas[fila_enc + 1:]:
        if not any(c not in (None, "") for c in fila):
            continue
        sen = sentido(_texto(celda(fila, "origen")), _texto(celda(fila, "destino")),
                      _texto(celda(fila, "recorrido")))
        if not sen:
            otros += 1
            continue
        salida, salida_real = _con_hora(_fecha(celda(fila, "salida")),
                                        _hora(celda(fila, "hora_salida")))
        if salida is None:
            descartados += 1
            continue
        llegada, llegada_real = _con_hora(_fecha(celda(fila, "llegada")),
                                          _hora(celda(fila, "hora_llegada")))
        # Todas las patentes de la columna. Si no hay columna, o viene
        # vacía, se buscan en la fila entera: una patente tiene una forma
        # que no se confunde con una fecha, un número de hoja o un nombre.
        patentes = patentes_de(_texto(celda(fila, "patente")))
        if not patentes:
            patentes = patentes_de(" , ".join(_texto(c) for c in fila))
        viajes.append({
            "hoja": _texto(celda(fila, "hoja")),
            "patentes": patentes,
            # Hasta cruzarla con Flota, la primera. `elegir_patentes` la
            # cambia por la de larga distancia.
            "patente": patentes[0] if patentes else "",
            "semi": _texto(celda(fila, "semi")).upper().replace(" ", ""),
            "chofer": _texto(celda(fila, "chofer")),
            "origen": _texto(celda(fila, "origen")),
            "destino": _texto(celda(fila, "destino")),
            "sentido": sen,
            "salida": salida, "salida_real": salida_real,
            # Una llegada con fecha y sin hora no sirve para ubicar al
            # camión: se estima con la velocidad media.
            "llegada": llegada if llegada_real else None,
            "llegada_real": llegada_real,
        })
    return {"viajes": viajes, "descartados": descartados, "otros": otros,
            "encabezados": encabezados,
            "columnas": {d: encabezados[i] for d, i in mapa.items() if i < len(encabezados)}}


def leer_xlsx(contenido):
    """leer_filas sobre un .xlsx en bytes. Mira la primera hoja."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        filas = [list(f) for f in ws.iter_rows(values_only=True)]
    finally:
        wb.close()
    return leer_filas(filas)


_HOJAS = {"cuando": 0, "datos": None}
_HOJAS_LOCK = threading.Lock()
MINUTOS_HOJAS = 30


def hojas(forzar=False):
    """La planilla del BI, leída. Se guarda media hora en memoria."""
    with _HOJAS_LOCK:
        if (not forzar and _HOJAS["datos"] is not None
                and time.time() - _HOJAS["cuando"] < MINUTOS_HOJAS * 60):
            return _HOJAS["datos"]
        req = urllib.request.Request(URL_HOJAS, headers={"User-Agent": "app-taller-viento/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                contenido = r.read()
        except Exception as e:
            raise RuntimeError(f"No se pudo bajar la planilla de viajes del BI: {e}")
        if not contenido.startswith(b"PK"):
            raise RuntimeError("El BI no devolvió un Excel: "
                               + contenido[:160].decode("utf-8", "replace"))
        datos = leer_xlsx(contenido)
        _HOJAS.update(cuando=time.time(), datos=datos)
        return datos


# ---------------------------------------------------------------------
# LOS VIAJES GUARDADOS (40_viento_viajes.sql)
# ---------------------------------------------------------------------
# La planilla del BI se trae sola todas las mañanas y se guarda: la
# pantalla abre al instante, y los viajes quedan aunque el reporte deje de
# mostrarlos. Sin la tabla, todo sigue como antes: se baja al abrir.
def guardar_viajes(cx, planilla, estado=None):
    """Guarda los viajes de la planilla. Devuelve cuántos, o None sin tabla.

    La clave es la hoja, el sentido y la salida. Si una hoja cambió de
    salida en el BI (la corrigieron), la versión vieja se borra: la misma
    hoja no puede quedar dos veces.
    """
    unicos = {}
    for v in planilla["viajes"]:
        unicos[(v.get("hoja") or "", v["sentido"], v["salida"])] = v
    filas = list(unicos.values())
    try:
        with cx.cursor() as cur:
            if filas:
                cur.execute("""
                    delete from viento_viajes w
                    using unnest(%s::text[], %s::text[], %s::timestamp[]) as f(hoja, sentido, salida)
                    where w.hoja = f.hoja and w.hoja <> '' and w.sentido = f.sentido
                      and w.salida <> f.salida""",
                    ([v.get("hoja") or "" for v in filas], [v["sentido"] for v in filas],
                     [v["salida"] for v in filas]))
            cur.executemany("""
                insert into viento_viajes (hoja, sentido, salida, salida_real, llegada,
                    llegada_real, origen, destino, patentes, semi, chofer, actualizado)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                on conflict (hoja, sentido, salida) do update set
                  salida_real = excluded.salida_real, llegada = excluded.llegada,
                  llegada_real = excluded.llegada_real, origen = excluded.origen,
                  destino = excluded.destino, patentes = excluded.patentes,
                  semi = excluded.semi, chofer = excluded.chofer, actualizado = now()""",
                [(v.get("hoja") or "", v["sentido"], v["salida"], bool(v.get("salida_real")),
                  v.get("llegada"), bool(v.get("llegada_real")), v.get("origen") or None,
                  v.get("destino") or None,
                  v.get("patentes") or ([v["patente"]] if v.get("patente") else []),
                  v.get("semi") or None, v.get("chofer") or None) for v in filas])
            cur.execute("""
                insert into viento_traidas (unica, cuando, estado, columnas, otros)
                values (true, now(), %s, %s::jsonb, %s)
                on conflict (unica) do update set cuando = now(), estado = excluded.estado,
                  columnas = excluded.columnas, otros = excluded.otros""",
                (estado or f"{len(filas)} viajes Buenos Aires ↔ Catamarca",
                 json.dumps(planilla.get("columnas") or {}, ensure_ascii=False),
                 planilla.get("otros") or 0))
        cx.commit()
    except Exception:
        cx.rollback()
        return None
    return len(filas)


def anotar_traida(cx, estado):
    """Anota que la traída falló, sin tocar los viajes que ya había."""
    try:
        cx.execute("""
            insert into viento_traidas (unica, cuando, estado) values (true, now(), %s)
            on conflict (unica) do update set cuando = now(), estado = excluded.estado""",
            (estado[:300],))
        cx.commit()
    except Exception:
        cx.rollback()


def viajes_guardados(cx):
    """Los viajes guardados, con la misma forma que leer_filas. None sin tabla o vacía."""
    try:
        filas = cx.execute("""
            select hoja, sentido, salida, salida_real, llegada, llegada_real, origen,
                   destino, patentes, semi, chofer from viento_viajes""").fetchall()
        traida = cx.execute("select * from viento_traidas").fetchone()
    except Exception:
        cx.rollback()
        return None
    if not filas:
        return None
    viajes = []
    for f in filas:
        patentes = list(f["patentes"] or [])
        viajes.append({"hoja": f["hoja"], "sentido": f["sentido"], "salida": f["salida"],
                       "salida_real": f["salida_real"], "llegada": f["llegada"],
                       "llegada_real": f["llegada_real"], "origen": f["origen"] or "",
                       "destino": f["destino"] or "", "patentes": patentes,
                       "patente": patentes[0] if patentes else "",
                       "semi": f["semi"] or "", "chofer": f["chofer"] or ""})
    return {"viajes": viajes, "descartados": 0,
            "otros": (traida or {}).get("otros") or 0,
            "columnas": (traida or {}).get("columnas") or {}, "encabezados": [],
            "traida": traida and {"cuando": traida["cuando"], "estado": traida["estado"]}}


def planilla_de(cx):
    """Los viajes guardados en la base.

    La planilla del BI no se baja desde el servidor: pesa mucho y abrirla
    dejaba a la app sin memoria (Render la reiniciaba y daba 502). La trae
    GitHub Actions todas las mañanas (gomeria/traer_viajes.py), y a mano
    con "Run workflow" en la pestaña Actions.
    """
    guardados = viajes_guardados(cx) if cx is not None else None
    if not guardados:
        raise RuntimeError(
            "Todavía no hay viajes guardados. La planilla del BI se trae sola "
            "todas las mañanas a las 06:15; para traerla ahora: GitHub → Actions "
            "→ Planilla de viajes → Run workflow.")
    return guardados


# ---------------------------------------------------------------------
# CUÁL DE LAS PATENTES ES EL CAMIÓN
# ---------------------------------------------------------------------
def unidades_lad(cx):
    """Las patentes de larga distancia de Flota: {patente: es_semi}.

    Larga distancia es lo mismo que en el resto del sistema: la sucursal
    LAD o un uso que diga LARGA. None si no se pudo leer (sin base, o sin
    la tabla): el que llama sigue con la primera patente de la hoja.
    """
    if cx is None:
        return None
    consulta = """
        select patente, {semi} as es_semi from unidades
        where patente is not null
          and (upper(btrim(coalesce(sucursal, ''))) = 'LAD'
               or upper(coalesce(uso, '')) like '%%LARGA%%')"""
    for semi in ("coalesce(es_semi, false) or upper(coalesce(uso, '')) like '%%SEMI%%'",
                 "upper(coalesce(uso, '')) like '%%SEMI%%'"):
        # es_semi llegó con 29_parametros.sql: en una base sin correrlo,
        # alcanza con el uso.
        try:
            filas = cx.execute(consulta.format(semi=semi)).fetchall()
            return {re.sub(r"[^A-Z0-9]", "", str(f["patente"]).upper()): bool(f["es_semi"])
                    for f in filas}
        except Exception:
            cx.rollback()
    return None


def elegir_patentes(viajes, lad):
    """A cada viaje le deja como `patente` la de larga distancia.

    De las patentes de la hoja, la primera que en Flota es de larga
    distancia y no es un semi; si solo el semi es de larga distancia,
    queda vacía, porque el combustible se le carga al tractor. Sin Flota
    (`lad` None) queda la primera, como vino.

    Devuelve las patentes de las hojas que no son de larga distancia en
    Flota, para avisar.
    """
    ajenas = set()
    if lad is None:
        return ajenas
    for v in viajes:
        todas = v.get("patentes") or ([v["patente"]] if v.get("patente") else [])
        tractores = [p for p in todas if p in lad and not lad[p]]
        v["patente"] = tractores[0] if tractores else ""
        if not tractores:
            ajenas.update(todas)
    return ajenas


# ---------------------------------------------------------------------
# DÓNDE ESTABA EL CAMIÓN A CADA HORA
# ---------------------------------------------------------------------
def llegada_estimada(viaje):
    """(llegada, si es la de la planilla). La estima si falta o no cierra."""
    salida, llegada = viaje["salida"], viaje.get("llegada")
    minima = timedelta(hours=KM_TOTAL / 110)          # ni un auto la hace antes
    if llegada and minima <= llegada - salida <= timedelta(hours=HORAS_MAXIMAS):
        return llegada, bool(viaje.get("llegada_real"))
    return salida + timedelta(hours=KM_TOTAL / VELOCIDAD_MEDIA), False


def recorrido_por_hora(salida, llegada, vuelta=False):
    """Un renglón por cada hora en punto del viaje: dónde estaba el camión.

    Cada renglón: la hora, el punto de viento más cercano (índice en
    PUNTOS), los km recorridos y el rumbo del camión en ese momento.
    """
    total = (llegada - salida).total_seconds()
    if total <= 0:
        return []
    h = salida.replace(minute=0, second=0, microsecond=0)
    if h < salida:
        h += timedelta(hours=1)
    salida_ = []
    while h <= llegada:
        hechos = KM_TOTAL * (h - salida).total_seconds() / total
        km_ida = KM_TOTAL - hechos if vuelta else hechos
        i = min(range(len(PUNTOS)), key=lambda j: abs(PUNTOS[j]["km"] - km_ida))
        rumbo = PUNTOS[i]["rumbo"]
        if i == len(PUNTOS) - 1 or (i > 0 and PUNTOS[i]["km"] > km_ida):
            # Entre el punto anterior y este, el rumbo es el del tramo que
            # llega acá.
            rumbo = PUNTOS[i - 1]["rumbo"]
        if vuelta:
            rumbo = (rumbo + 180) % 360
        salida_.append({"hora": h, "punto": i, "km": round(hechos), "rumbo": rumbo})
        h += timedelta(hours=1)
    return salida_


def de_frente(velocidad, desde, rumbo):
    """(componente en contra en km/h, tipo). Negativo es viento de cola.

    `desde` es de dónde viene el viento, como lo da cualquier servicio
    meteorológico: 0 es viento del norte. Un camión que va al norte con
    viento del norte lo tiene de frente.
    """
    dif = abs((desde - rumbo + 180) % 360 - 180)
    contra = velocidad * math.cos(math.radians(dif))
    tipo = "frente" if dif <= 45 else "cola" if dif >= 135 else "costado"
    return round(contra, 1), tipo


def cruzado(velocidad, desde, rumbo):
    """La parte del viento que le pega de costado, en km/h (siempre positiva)."""
    return round(abs(velocidad * math.sin(math.radians(desde - rumbo))), 1)


def calificar(contra_media):
    if contra_media is None:
        return "sin datos"
    if contra_media >= 15:
        return "en contra fuerte"
    if contra_media >= 6:
        return "en contra"
    if contra_media <= -6:
        return "a favor"
    return "neutro"


def resumir(viaje, viento):
    """El viaje con el viento que encontró.

    `viento` es una función (lat, lon, hora) → {velocidad, rafaga,
    direccion} o None.
    """
    llegada, llegada_real = llegada_estimada(viaje)
    horas = []
    for r in recorrido_por_hora(viaje["salida"], llegada, viaje["sentido"] == "vuelta"):
        p = PUNTOS[r["punto"]]
        v = viento(p["lat"], p["lon"], r["hora"])
        donde = {"hora": r["hora"], "lugar": p["lugar"], "km": r["km"],
                 "lat": p["lat"], "lon": p["lon"], "punto": r["punto"]}
        if not v or v.get("velocidad") is None or v.get("direccion") is None:
            horas.append({**donde, "velocidad": None})
            continue
        contra, tipo = de_frente(v["velocidad"], v["direccion"], r["rumbo"])
        horas.append({**donde,
                      "velocidad": round(v["velocidad"], 1),
                      "rafaga": None if v.get("rafaga") is None else round(v["rafaga"], 1),
                      "direccion": round(v["direccion"]), "rumbo": r["rumbo"],
                      "contra": contra, "tipo": tipo,
                      "cruzado": cruzado(v["velocidad"], v["direccion"], r["rumbo"])})
    con = [h for h in horas if h["velocidad"] is not None]
    n = len(con)
    resumen = {
        **{k: viaje.get(k) for k in ("hoja", "patente", "patentes", "semi", "chofer", "origen",
                                     "destino", "sentido", "salida", "salida_real")},
        "llegada": llegada, "llegada_real": llegada_real,
        "horas_viaje": round((llegada - viaje["salida"]).total_seconds() / 3600, 1),
        "horas_con_dato": n, "horas_total": len(horas),
        "estado": "ok" if n and n == len(horas) else "parcial" if n else "sin datos",
        "detalle": horas,
    }
    if n:
        rafagas = [h for h in con if h.get("rafaga") is not None]
        peor = max(rafagas, key=lambda h: h["rafaga"]) if rafagas else None
        contra = sum(h["contra"] for h in con) / n
        resumen.update({
            "velocidad_media": round(sum(h["velocidad"] for h in con) / n, 1),
            "contra_media": round(contra, 1),
            "rafaga_max": peor and peor["rafaga"],
            "rafaga_lugar": peor and peor["lugar"],
            "rafaga_hora": peor and peor["hora"],
            "pct_frente": round(100 * sum(h["tipo"] == "frente" for h in con) / n),
            "pct_cola": round(100 * sum(h["tipo"] == "cola" for h in con) / n),
            "pct_costado": round(100 * sum(h["tipo"] == "costado" for h in con) / n),
            "calificacion": calificar(contra),
        })
    else:
        resumen.update({"velocidad_media": None, "contra_media": None, "rafaga_max": None,
                        "rafaga_lugar": None, "rafaga_hora": None, "pct_frente": None,
                        "pct_cola": None, "pct_costado": None,
                        "calificacion": calificar(None)})
    return resumen


# ---------------------------------------------------------------------
# EL VIENTO: OPEN-METEO, CON LO YA BAJADO GUARDADO EN LA BASE
# ---------------------------------------------------------------------
# Lo ya bajado también queda en memoria: si la tabla no existe (no se
# corrió 39_viento.sql) la pantalla anda igual, solo que pregunta de nuevo
# después de cada reinicio.
_MEMORIA = {}
_MEMORIA_LOCK = threading.Lock()
# Cada hora de cada punto ocupa unos 350 bytes: 150.000 son unos 50 MB,
# más de 6 meses de viajes. Pasado eso se vacía y se vuelve a leer de la
# base, para que la memoria no crezca sin límite.
TOPE_MEMORIA = 150_000
# Open-Meteo tarda con muchos días y muchos puntos a la vez.
DIAS_POR_PEDIDO = 62


def _clave(lat, lon, hora):
    return (round(lat, 2), round(lon, 2), hora.replace(minute=0, second=0, microsecond=0))


def _pedir_meteo(desde, hasta):
    """El viento de todos los PUNTOS entre dos fechas, hora por hora."""
    unicos = sorted({(p["lat"], p["lon"]) for p in PUNTOS})
    params = {
        "latitude": ",".join(f"{la:.2f}" for la, _ in unicos),
        "longitude": ",".join(f"{lo:.2f}" for _, lo in unicos),
        "start_date": desde.isoformat(), "end_date": hasta.isoformat(),
        "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "wind_speed_unit": "kmh",
        "timezone": "America/Argentina/Buenos_Aires",
    }
    if CLAVE_METEO:
        params["apikey"] = CLAVE_METEO
    url = URL_METEO + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "app-taller-viento/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            datos = json.loads(r.read())
    except urllib.error.HTTPError as e:
        cuerpo = e.read()[:300].decode("utf-8", "replace")
        raise RuntimeError(f"Open-Meteo contestó {e.code}: {cuerpo}")
    except Exception as e:
        raise RuntimeError(f"No se pudo consultar Open-Meteo: {e}")
    if isinstance(datos, dict):
        datos = [datos]
    filas = []
    for (la, lo), d in zip(unicos, datos):
        h = d.get("hourly") or {}
        for t, vel, dire, raf in zip(h.get("time", []), h.get("wind_speed_10m", []),
                                     h.get("wind_direction_10m", []),
                                     h.get("wind_gusts_10m", [])):
            if vel is None or dire is None:
                continue        # todavía no publicado: se vuelve a pedir otro día
            filas.append((la, lo, datetime.fromisoformat(t), vel, raf, dire))
    return filas


def _leer_base(cx, desde, hasta):
    try:
        filas = cx.execute("""
            select lat, lon, hora, velocidad, rafaga, direccion from viento_horas
            where hora >= %s and hora < %s""",
            (datetime.combine(desde, hora_del_dia()),
             datetime.combine(hasta + timedelta(days=1), hora_del_dia()))).fetchall()
    except Exception:
        cx.rollback()
        return None
    return [(float(f["lat"]), float(f["lon"]), f["hora"], f["velocidad"],
             f["rafaga"], f["direccion"]) for f in filas]


def _guardar_base(cx, filas):
    if not filas:
        return
    try:
        with cx.cursor() as cur:
            cur.executemany("""
                insert into viento_horas (lat, lon, hora, velocidad, rafaga, direccion)
                values (%s, %s, %s, %s, %s, %s)
                on conflict (lat, lon, hora) do nothing""", filas)
        cx.commit()
    except Exception:
        cx.rollback()


def viento_para(cx, dias, pedir=_pedir_meteo):
    """Una función (lat, lon, hora) → viento, con todo lo de esos días.

    Lo que no está ni en memoria ni en la base se le pide a Open-Meteo en
    pedidos de hasta DIAS_POR_PEDIDO días seguidos. Los días que Open-Meteo
    todavía no publicó (los últimos cinco) quedan sin dato.
    """
    dias = sorted(set(dias))
    avisos = []
    if dias:
        desde, hasta = dias[0], dias[-1]
        n_puntos = len({(p["lat"], p["lon"]) for p in PUNTOS})
        with _MEMORIA_LOCK:
            if len(_MEMORIA) > TOPE_MEMORIA:
                _MEMORIA.clear()
            tenemos = {}
            for k, v in _MEMORIA.items():
                if desde <= k[2].date() <= hasta:
                    tenemos.setdefault(k[2].date(), set()).add((k[0], k[1]))
        de_base = _leer_base(cx, desde, hasta) if cx is not None else None
        if de_base:
            with _MEMORIA_LOCK:
                for la, lo, h, vel, raf, dire in de_base:
                    _MEMORIA[_clave(la, lo, h)] = {"velocidad": vel, "rafaga": raf,
                                                   "direccion": dire}
                    tenemos.setdefault(h.date(), set()).add((round(la, 2), round(lo, 2)))
        # Un día está completo si están todos los puntos (se mira por
        # punto y no por hora: un día a medio publicar se vuelve a pedir).
        ultimo_publicado = date.today() - timedelta(days=5)
        faltan = [d for d in dias
                  if len(tenemos.get(d, ())) < n_puntos and d <= ultimo_publicado]
        if any(d > ultimo_publicado for d in dias):
            avisos.append("Los viajes de los últimos cinco días todavía no tienen viento: "
                          "Open-Meteo lo publica con ese atraso.")
        for tramo in _tramos(faltan):
            try:
                nuevas = pedir(tramo[0], tramo[-1])
            except RuntimeError as e:
                avisos.append(str(e))
                break
            with _MEMORIA_LOCK:
                for la, lo, h, vel, raf, dire in nuevas:
                    _MEMORIA[_clave(la, lo, h)] = {"velocidad": vel, "rafaga": raf,
                                                   "direccion": dire}
            if cx is not None:
                _guardar_base(cx, nuevas)

    def viento(lat, lon, hora):
        return _MEMORIA.get(_clave(lat, lon, hora))
    viento.avisos = avisos
    return viento


def _tramos(dias):
    """Días sueltos → tramos de días seguidos, de a DIAS_POR_PEDIDO."""
    tramos, actual = [], []
    for d in sorted(dias):
        if actual and ((d - actual[-1]).days > 1 or len(actual) >= DIAS_POR_PEDIDO):
            tramos.append(actual)
            actual = []
        actual.append(d)
    if actual:
        tramos.append(actual)
    return tramos


# ---------------------------------------------------------------------
# LO QUE PIDE LA PANTALLA
# ---------------------------------------------------------------------
def _dia(texto, defecto):
    try:
        return date.fromisoformat(str(texto)[:10])
    except (TypeError, ValueError):
        return defecto


def informe(cx, desde=None, hasta=None, leer_hojas=None, pedir=None,
            lad=None):
    """Los viajes del período con su viento. Es la respuesta de /api/viento."""
    hoy = date.today()
    hasta = _dia(hasta, hoy)
    desde = _dia(desde, hasta - timedelta(days=90))
    if desde > hasta:
        desde, hasta = hasta, desde
    if (hasta - desde).days > 400:
        desde = hasta - timedelta(days=400)

    planilla = leer_hojas() if leer_hojas else planilla_de(cx)
    # Una copia de cada viaje: la planilla queda media hora en memoria y la
    # patente elegida no se le puede pegar.
    viajes = [dict(v) for v in planilla["viajes"] if desde <= v["salida"].date() <= hasta]
    viajes.sort(key=lambda v: v["salida"], reverse=True)
    ajenas = elegir_patentes(viajes, unidades_lad(cx) if lad is None else lad)

    dias = set()
    for v in viajes:
        llegada, _ = llegada_estimada(v)
        d = v["salida"].date()
        while d <= llegada.date():
            dias.add(d)
            d += timedelta(days=1)
    viento = viento_para(cx, dias, **({"pedir": pedir} if pedir else {}))
    resumenes = [resumir(v, viento) for v in viajes]

    avisos = list(viento.avisos)
    sin_hora = sum(not v["salida_real"] for v in viajes)
    if sin_hora:
        avisos.append(f"{sin_hora} viaje(s) sin hora de salida: se supuso que salieron "
                      f"a las {HORA_SUPUESTA}:00.")
    estimada = sum(not r["llegada_real"] for r in resumenes)
    if estimada:
        avisos.append(f"{estimada} viaje(s) sin una llegada que cierre: se estimó a "
                      f"{VELOCIDAD_MEDIA} km/h de promedio.")
    sin_patente = sum(not v.get("patente") for v in viajes)
    if sin_patente:
        avisos.append(
            f"{sin_patente} viaje(s) sin ninguna patente de larga distancia en Flota: "
            "no se cruzan con el combustible."
            + (" Patentes de esas hojas: " + ", ".join(sorted(ajenas)[:12])
               + ("…" if len(ajenas) > 12 else "") + "." if ajenas else "")
            + " Si son de larga distancia, en Flota tienen que tener sucursal LAD "
              "o un uso que diga LARGA DISTANCIA.")
    if planilla["descartados"]:
        avisos.append(f"{planilla['descartados']} fila(s) del tramo sin fecha de salida "
                      "legible: no se muestran.")

    return {
        "desde": desde, "hasta": hasta, "viajes": resumenes, "avisos": avisos,
        "columnas": planilla["columnas"], "otros_viajes": planilla["otros"],
        "ruta": [{"lugar": n, "lat": la, "lon": lo} for n, la, lo in RUTA],
        "km_total": KM_TOTAL,
        "fuente": "Open-Meteo (ERA5), viento a 10 m",
        "traida": planilla.get("traida"),
    }
