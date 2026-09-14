"""Qué cuesta mantener la flota, según lo que ya se cargó en las órdenes.

El módulo de órdenes sabe lo que se gastó, en qué unidad y si el trabajo
fue preventivo o correctivo. Lo que no dice, mirando el listado, es lo
único que se pregunta cuando hay que decidir: *¿cuánto me sale por
kilómetro este camión, y cuánto de eso es porque se rompió?*

Acá se arma esa cuenta:

    total gastado por patente      la suma de las órdenes de la unidad
    $/km correctivo                lo que se gastó arreglando roturas
    $/km preventivo                lo que se gastó en mantenimiento

Los pesos salen de `v_ordenes` (en las internas, los renglones; en las
externas, la factura). Los kilómetros salen de `v_km_diarios`, la serie
del satelital, que ya descarta los retrocesos y los saltos imposibles.

Dos reglas que hacen que el número no mienta:

  * Las anuladas no cuentan: el trabajo no existió.
  * El peso por kilómetro solo mira las órdenes que caen adentro del
    tramo en que esa unidad tuvo lecturas. Dividir el gasto de un año
    por los kilómetros de dos meses da un número altísimo que no es de
    nadie. Lo que queda afuera se informa como cobertura parcial, no se
    rellena.
"""
from datetime import date

# La ventana que mira la portada: doce meses hacia atrás, contando el mes
# en curso. Un año entero mete los service grandes que se hacen una vez y
# evita que un mes flojo parezca una tendencia.
VENTANA_MESES = 12

# Cuántas unidades entran en el ranking de la portada. El resto se resume
# en una línea: la lista completa está en el módulo de órdenes.
TOPE_RANKING = 8

CLASES = ("correctivo", "preventivo", "sin_clasificar")


def _monto(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _clase(valor):
    clase = str(valor or "").strip().lower()
    return clase if clase in ("preventivo", "correctivo") else "sin_clasificar"


def _fecha(valor):
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except (TypeError, ValueError):
        return None


def _por_km(pesos, km):
    """Pesos por kilómetro, o None si no hay kilómetros que dividir."""
    return round(pesos / km, 2) if km and km > 0 else None


def desde_hasta(hoy, meses=VENTANA_MESES):
    """El primer día del mes de hace `meses` meses, y hoy."""
    mes = hoy.month - (meses - 1)
    anio = hoy.year + (mes - 1) // 12
    return date(anio, (mes - 1) % 12 + 1, 1), hoy


def _meses(desde, hasta):
    """Los primeros de mes entre las dos fechas, en orden."""
    salida, anio, mes = [], desde.year, desde.month
    while (anio, mes) <= (hasta.year, hasta.month):
        salida.append(date(anio, mes, 1))
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    return salida


def _vacio():
    return {c: 0.0 for c in CLASES}


def calcular(ordenes, kilometros, desde, hasta, tope=TOPE_RANKING):
    """Los KPI de costo, de las órdenes y los kilómetros ya leídos.

    `ordenes`     filas de v_ordenes: patente, fecha, total, mantenimiento…
    `kilometros`  una fila por unidad: patente, km, desde, hasta.

    Las dos listas van por patente y no por unidad_id: una unidad que se
    dio de baja y se volvió a cargar cambia de id, pero es el mismo camión
    y su costo tiene que seguir junto.
    """
    km_por_patente = {}
    for fila in kilometros or []:
        patente = str(fila["patente"] or "").strip().upper()
        if not patente:
            continue
        km = _monto(fila.get("km"))
        actual = km_por_patente.setdefault(
            patente, {"km": 0.0, "desde": None, "hasta": None, "dias": 0})
        actual["km"] += km
        actual["dias"] += int(fila.get("dias") or 0)
        for campo, cmp_ in (("desde", min), ("hasta", max)):
            valor = _fecha(fila.get(campo))
            if valor:
                actual[campo] = valor if actual[campo] is None else cmp_(actual[campo], valor)

    unidades, gasto, cuantas = {}, _vacio(), 0
    serie = {m.isoformat(): _vacio() for m in _meses(desde, hasta)}

    for o in ordenes or []:
        patente = str(o["patente"] or "").strip().upper()
        if not patente:
            continue
        if str(o.get("estado") or "").strip().lower() == "anulada":
            continue          # el trabajo no existió: no es gasto de nadie
        fecha = _fecha(o.get("fecha"))
        if fecha is None or fecha < desde or fecha > hasta:
            continue
        clase, total = _clase(o.get("mantenimiento")), _monto(o.get("total"))
        cuantas += 1
        gasto[clase] += total

        mes = date(fecha.year, fecha.month, 1).isoformat()
        if mes in serie:
            serie[mes][clase] += total

        u = unidades.setdefault(patente, {
            "patente": patente, "interno": None, "marca": None, "modelo": None,
            "ordenes": 0, "gasto": _vacio(), "medido": _vacio(),
        })
        for campo in ("interno", "marca", "modelo"):
            u[campo] = u[campo] or o.get(campo)
        u["ordenes"] += 1
        u["gasto"][clase] += total

        # Solo lo que cae adentro del tramo con lecturas entra en el peso
        # por kilómetro: es el gasto que esos kilómetros explican.
        km = km_por_patente.get(patente)
        if km and km["desde"] and km["desde"] <= fecha <= km["hasta"]:
            u["medido"][clase] += total

    filas, flota_km, flota = [], 0.0, _vacio()
    for patente, u in unidades.items():
        km = km_por_patente.get(patente) or {}
        recorrido = km.get("km") or 0.0
        medido = km.get("desde") is not None and recorrido > 0
        if medido:
            flota_km += recorrido
            for clase in CLASES:
                flota[clase] += u["medido"][clase]
        filas.append({
            "patente": patente,
            "interno": u["interno"], "marca": u["marca"], "modelo": u["modelo"],
            "ordenes": u["ordenes"],
            "total": round(sum(u["gasto"].values()), 2),
            "correctivo": round(u["gasto"]["correctivo"], 2),
            "preventivo": round(u["gasto"]["preventivo"], 2),
            "sin_clasificar": round(u["gasto"]["sin_clasificar"], 2),
            "km": round(recorrido) if medido else None,
            "km_desde": km["desde"].isoformat() if medido else None,
            "km_hasta": km["hasta"].isoformat() if medido else None,
            "pesos_km": _por_km(sum(u["medido"].values()), recorrido) if medido else None,
            "pesos_km_correctivo": _por_km(u["medido"]["correctivo"], recorrido) if medido else None,
            "pesos_km_preventivo": _por_km(u["medido"]["preventivo"], recorrido) if medido else None,
            # Que el gasto del período no sea todo el que los kilómetros
            # explican se dice, no se esconde.
            "parcial": medido and round(sum(u["medido"].values()), 2)
                       < round(sum(u["gasto"].values()), 2),
        })

    filas.sort(key=lambda f: (-f["total"], f["patente"]))
    total = round(sum(gasto.values()), 2)
    medidas = [f for f in filas if f["km"]]

    return {
        "desde": desde.isoformat(), "hasta": hasta.isoformat(),
        "meses": len(serie),
        "gasto": {
            "total": total,
            "correctivo": round(gasto["correctivo"], 2),
            "preventivo": round(gasto["preventivo"], 2),
            "sin_clasificar": round(gasto["sin_clasificar"], 2),
            "ordenes": cuantas,
            "unidades": len(filas),
        },
        "flota": {
            "km": round(flota_km) or None,
            "gasto_medido": round(sum(flota.values()), 2),
            "pesos_km": _por_km(sum(flota.values()), flota_km),
            "pesos_km_correctivo": _por_km(flota["correctivo"], flota_km),
            "pesos_km_preventivo": _por_km(flota["preventivo"], flota_km),
            "unidades_con_km": len(medidas),
            "unidades_sin_km": len(filas) - len(medidas),
        },
        "unidades": filas[:tope],
        "resto": {
            "unidades": max(0, len(filas) - tope),
            "total": round(sum(f["total"] for f in filas[tope:]), 2),
        },
        "serie": [{"mes": mes,
                   "correctivo": round(v["correctivo"], 2),
                   "preventivo": round(v["preventivo"], 2),
                   "sin_clasificar": round(v["sin_clasificar"], 2),
                   "total": round(sum(v.values()), 2)}
                  for mes, v in sorted(serie.items())],
    }


# =====================================================================
# LO QUE SE LE PIDE A LA BASE
# =====================================================================
# Las anuladas quedan afuera de las dos consultas: el trabajo no existió.
ORDENES = """
    select patente, unidad_id, interno, marca, modelo,
           tipo, estado, mantenimiento, fecha, total
    from v_ordenes
    where estado <> 'anulada' and fecha between %s and %s
"""

# v_km_diarios ya descartó los retrocesos —cambios de equipo— y los saltos
# imposibles, así que sumar de ahí es sumar kilómetros creíbles. El tramo
# empieza en la lectura anterior a la primera diferencia buena: es desde
# ahí que la serie explica kilómetros.
KILOMETROS = """
    select patente,
           sum(recorrido)     as km,
           min(fecha_anterior) as desde,
           max(fecha)          as hasta,
           count(*)::int       as dias
    from v_km_diarios
    where recorrido is not null and fecha between %s and %s
    group by patente
"""


def resumen(cx, hoy=None, meses=VENTANA_MESES, tope=TOPE_RANKING):
    """Los KPI listos para la portada. Sin órdenes cargadas devuelve None."""
    hoy = hoy or date.today()
    desde, hasta = desde_hasta(hoy, meses)
    ordenes = cx.execute(ORDENES, (desde, hasta)).fetchall()
    # Los kilómetros son opcionales: sin satelital cargado el gasto por
    # patente se sigue pudiendo mostrar, y el peso por kilómetro queda en
    # blanco en vez de tirar abajo el resto del panel.
    try:
        kilometros = cx.execute(KILOMETROS, (desde, hasta)).fetchall()
    except Exception:
        cx.rollback()
        kilometros = []
    return calcular([dict(o) for o in ordenes], [dict(k) for k in kilometros],
                    desde, hasta, tope)
