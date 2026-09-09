"""
Todo lo que hay que mirar hoy, en una sola lista.

Los avisos estaban repartidos: los vencimientos en su pantalla, los
services en una planilla de Google, las cargas raras de combustible en
ningún lado y las gomas al límite en Gomería. Nadie mira cuatro pantallas
todos los días, así que en la práctica no se miraba ninguna.

Acá entran las cuatro fuentes con la misma forma —qué es, de qué unidad,
cuán urgente y adónde ir a resolverlo— y salen ordenadas por urgencia, no
por fuente. Al que abre la pantalla a la mañana no le importa si lo que
tiene encima es una VTV o un service: le importa cuál lo deja tirado
primero.

Cada fuente se lee por separado y a prueba de balas. Los módulos se van
prendiendo de a uno y el SQL se corre a mano: que falte una tabla apaga
esa fuente y lo dice, no la pantalla entera.
"""

# El orden en que se miran las cosas. Es el de la consecuencia: un papel
# vencido puede parar el camión en un control de ruta hoy, un service
# pasado de kilómetros lo rompe en algún momento, y una carga rara ya
# pasó y lo que queda es entender qué fue.
SEVERIDADES = {"grave": 0, "media": 1, "leve": 2}

# A igual gravedad, qué se mira primero. No se pueden comparar entre sí los
# números de cada fuente —días, kilómetros, milímetros y litros no están en
# la misma escala—, así que dentro de cada nivel manda la consecuencia:
# el papel para el camión hoy, la goma al mínimo puede reventar, el service
# pasado lo rompe en algún momento, y la carga rara ya pasó.
PRIORIDAD = {"vencimiento": 0, "cubierta": 1, "service": 2, "combustible": 3}

FUENTES = ("vencimiento", "service", "combustible", "cubierta")

# Cómo se llama cada fuente en pantalla y adónde manda.
DONDE = {
    "vencimiento": ("Vencimientos", "/vencimientos"),
    "service":     ("Services",     "/alertas#services"),
    "combustible": ("Combustible",  "/combustible"),
    "cubierta":    ("Gomería",      "/gomeria#wear"),
}


def _miles(n):
    """12345.6 → «12.345». Los puntos de mil, como se escriben acá."""
    return f"{float(n):,.0f}".replace(",", ".")


def _existe(cx, tabla):
    fila = cx.execute("select to_regclass(%s) as t", (f"public.{tabla}",)).fetchone()
    return bool(fila and fila["t"])


def instalado(cx):
    return _existe(cx, "alertas_reglas")


def _tabla(cx, consulta, valores=()):
    """La consulta, o None si la vista todavía no está.

    Devuelve None y no una lista vacía a propósito: la pantalla necesita
    distinguir «no hay alertas de combustible» de «el módulo de
    combustible no está instalado».
    """
    try:
        return cx.execute(consulta, valores).fetchall()
    except Exception:
        cx.rollback()
        return None


# =====================================================================
# LAS REGLAS
# =====================================================================
def reglas(cx):
    fila = cx.execute("select * from alertas_reglas where id = 1").fetchone()
    return dict(fila) if fila else None


def guardar_reglas(cx, datos):
    """Cambia los números que definen cuándo algo es una alerta."""
    def numero(clave, minimo=1):
        valor = datos.get(clave)
        if valor in (None, ""):
            return None
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            raise ValueError(f"«{clave}» tiene que ser un número.")
        if valor < minimo:
            raise ValueError(f"«{clave}» no puede ser menor que {minimo}.")
        return valor

    litros = numero("litros_maximos")
    urgente = numero("service_urgente_km")
    aviso = numero("service_aviso_km")
    dias = numero("combustible_dias")
    if urgente is not None and aviso is not None and aviso < urgente:
        raise ValueError("El aviso de service tiene que ser igual o mayor que "
                         "el urgente: es el amarillo antes del rojo.")
    cx.execute("""
        update alertas_reglas set
          litros_maximos     = coalesce(%s, litros_maximos),
          service_urgente_km = coalesce(%s, service_urgente_km),
          service_aviso_km   = coalesce(%s, service_aviso_km),
          combustible_dias   = coalesce(%s, combustible_dias)
        where id = 1
    """, (litros, urgente, aviso, dias))
    return reglas(cx)


# =====================================================================
# SILENCIAR
# =====================================================================
def silenciadas(cx):
    """Lo silenciado que sigue vigente, indexado por fuente y clave."""
    filas = _tabla(cx, """
        select * from alertas_silenciadas
        where hasta is null or hasta >= current_date
    """) or []
    return {(f["fuente"], f["clave"]): dict(f) for f in filas}


def silenciar(cx, fuente, clave, motivo, usuario=None, hasta=None):
    """Saca una alerta de la lista, dejando anotado quién y por qué.

    El motivo es obligatorio. Dentro de seis meses, «alguien la ocultó» no
    le sirve a nadie: lo que sirve es «el tanque de este camión es de 600
    litros, la carga estaba bien».
    """
    if fuente not in FUENTES:
        raise ValueError("Esa fuente de alerta no existe.")
    clave = str(clave or "").strip()
    if not clave:
        raise ValueError("Falta la alerta a silenciar.")
    motivo = str(motivo or "").strip()
    if len(motivo) < 3:
        raise ValueError("Escribí por qué se silencia. Sin el motivo, dentro de "
                         "seis meses nadie va a saber si estaba bien ocultarla.")
    cx.execute("""
        insert into alertas_silenciadas (fuente, clave, motivo, hasta, usuario)
        values (%s,%s,%s,%s,%s)
        on conflict (fuente, clave) do update
          set motivo = excluded.motivo, hasta = excluded.hasta,
              usuario = excluded.usuario, creado = now()
    """, (fuente, clave, motivo[:500], hasta or None, usuario))


def reactivar(cx, fuente, clave):
    cx.execute("delete from alertas_silenciadas where fuente = %s and clave = %s",
               (fuente, str(clave)))


# =====================================================================
# LAS CUATRO FUENTES
# =====================================================================
def _vencimientos(cx):
    filas = _tabla(cx, """
        select id, tipo, ambito, patente, interno, persona, identificador,
               detalle, vence, dias, estado,
               coalesce(sucursal_unidad, sucursal_persona) as sucursal
        from v_vencimientos_hoy
        where estado in ('vencido', 'por_vencer')
        order by dias
    """)
    if filas is None:
        return None
    salida = []
    for f in filas:
        dias = int(f["dias"] or 0)
        de = f["patente"] and f"{f['patente']}" or f["persona"] or "—"
        cuando = ("venció hace %d día%s" % (-dias, "" if dias == -1 else "s")) if dias < 0 \
            else ("vence hoy" if dias == 0
                  else "vence en %d día%s" % (dias, "" if dias == 1 else "s"))
        salida.append({
            "fuente": "vencimiento",
            "clave": str(f["id"]),
            "severidad": "grave" if f["estado"] == "vencido" else "media",
            "titulo": f["tipo"],
            "detalle": cuando,
            "patente": f["patente"],
            "interno": f["interno"],
            "sucursal": f["sucursal"],
            "de_quien": f["persona"],
            "fecha": f["vence"],
            "orden": dias,
            "extra": " · ".join(x for x in (f["identificador"], f["detalle"]) if x),
        })
    return salida


def _services(cx):
    filas = _tabla(cx, """
        select * from v_services_hoy
        where estado in ('vencido', 'urgente', 'proximo', 'km_dudoso')
        order by km_restantes
    """)
    if filas is None:
        return None
    salida = []
    for f in filas:
        base_alerta = {
            "fuente": "service",
            "clave": str(f["unidad_id"]),
            "titulo": f"Service{' ' + f['tipo'] if f['tipo'] else ''}",
            "patente": f["patente"],
            "interno": f["interno"],
            "sucursal": f["sucursal"],
            "de_quien": None,
            "fecha": f["ultimo_fecha"],
        }

        if f["estado"] == "km_dudoso":
            # No se puede saber si le toca: el satelital marca menos
            # kilómetros de los que tenía en su último service. Se avisa
            # igual, porque una unidad de la que no se sabe si está pasada
            # de service no puede desaparecer de la lista.
            salida.append({
                **base_alerta,
                "severidad": "leve",
                "titulo": "No se sabe cuándo le toca el service",
                "detalle": (f"el satelital marca {_miles(f['km_actual'])} km y su "
                            f"último service fue a los {_miles(f['ultimo_km'])}"),
                "orden": 0,
                "extra": ("le cambiaron el equipo de GPS, o dejó de reportar. "
                          "Hasta que no se arregle, esta unidad no avisa."),
            })
            continue

        faltan = float(f["km_restantes"])
        dias = f["dias_restantes"]
        detalle = (f"pasado por {_miles(abs(faltan))} km" if faltan < 0
                   else f"faltan {_miles(faltan)} km")
        if faltan >= 0 and dias is not None:
            detalle += f" · unos {int(dias)} días"
        salida.append({
            **base_alerta,
            "severidad": "grave" if f["estado"] == "vencido"
                         else "media" if f["estado"] == "urgente" else "leve",
            "detalle": detalle,
            "orden": faltan,
            "extra": (f"último a los {_miles(f['ultimo_km'])} km, "
                      f"cada {_miles(f['cada_km'])}"),
        })
    return salida


def _combustible(cx):
    filas = _tabla(cx, """
        select * from v_cargas_grandes order by litros desc, fecha desc
    """)
    if filas is None:
        return None
    salida = []
    for f in filas:
        litros = float(f["litros"])
        salida.append({
            "fuente": "combustible",
            "clave": str(f["carga_id"]),
            # Una sola carga grande es algo para mirar, no una emergencia:
            # ya pasó. Lo que la vuelve grave es cuánto se pasó.
            "severidad": "grave" if litros >= float(f["litros_maximos"]) * 1.5 else "media",
            "titulo": f"Carga de {_miles(litros)} litros",
            "detalle": f"{_miles(f['litros_de_mas'])} litros por encima del máximo",
            "patente": f["patente"],
            "interno": f["interno"],
            "sucursal": None,
            "de_quien": f["chofer"],
            "fecha": f["fecha"],
            "orden": -litros,
            "extra": " · ".join(str(x) for x in (
                f"remito {f['remito_bruto'] or f['remito']}", f["estacion"]) if x),
        })
    return salida


def _cubiertas(cx):
    filas = _tabla(cx, """
        select cubierta_id, codigo, patente, interno, posicion, funcion,
               remanente_mm, minimo_mm, alerta, km_restantes, dias_restantes
        from v_alertas_cubiertas
        where alerta in ('al_limite', 'cerca')
        order by remanente_mm - minimo_mm
    """)
    if filas is None:
        return None
    salida = []
    for f in filas:
        al_limite = f["alerta"] == "al_limite"
        detalle = (f"{float(f['remanente_mm']):.1f} mm, el mínimo es "
                   f"{float(f['minimo_mm']):.1f}").replace(".", ",")
        if not al_limite and f["km_restantes"] is not None:
            detalle += f" · llega en {_miles(f['km_restantes'])} km"
        salida.append({
            "fuente": "cubierta",
            "clave": str(f["cubierta_id"]),
            "severidad": "grave" if al_limite else "media",
            "titulo": f"Cubierta {f['codigo']} en {f['posicion']}",
            "detalle": detalle,
            "patente": f["patente"],
            "interno": f["interno"],
            "sucursal": None,
            "de_quien": None,
            "fecha": None,
            "orden": float(f["remanente_mm"]) - float(f["minimo_mm"]),
            "extra": f["funcion"],
        })
    return salida


LECTORES = {"vencimiento": _vencimientos, "service": _services,
            "combustible": _combustible, "cubierta": _cubiertas}


# =====================================================================
# LA LISTA
# =====================================================================
def listar(cx, incluir_silenciadas=False):
    """Las cuatro fuentes juntas, ordenadas por urgencia."""
    if not instalado(cx):
        return {"instalado": False,
                "aviso": "Falta correr gomeria/20_alertas.sql en Supabase."}

    calladas = silenciadas(cx)
    alertas, apagadas, dormidas = [], [], []

    for fuente, leer in LECTORES.items():
        filas = leer(cx)
        if filas is None:
            # La tabla de esa fuente todavía no existe. Se dice cuál, para
            # que se sepa qué SQL falta correr en vez de creer que no hay
            # nada que mirar.
            apagadas.append(DONDE[fuente][0])
            continue
        for a in filas:
            a["modulo"], a["enlace"] = DONDE[a["fuente"]]
            callada = calladas.get((a["fuente"], a["clave"]))
            if callada:
                a["silenciada"] = {"motivo": callada["motivo"],
                                   "hasta": callada["hasta"],
                                   "usuario": callada["usuario"]}
                dormidas.append(a)
            else:
                alertas.append(a)

    def urgencia(a):
        return (SEVERIDADES.get(a["severidad"], 9),
                PRIORIDAD.get(a["fuente"], 9),
                a["orden"])

    alertas.sort(key=urgencia)
    dormidas.sort(key=urgencia)

    resumen = {"grave": 0, "media": 0, "leve": 0, "total": len(alertas),
               "silenciadas": len(dormidas)}
    por_fuente = {f: 0 for f in FUENTES}
    for a in alertas:
        resumen[a["severidad"]] += 1
        por_fuente[a["fuente"]] += 1

    return {"instalado": True,
            "alertas": alertas,
            "silenciadas": dormidas if incluir_silenciadas else [],
            "resumen": resumen,
            "por_fuente": por_fuente,
            "fuentes_apagadas": apagadas,
            "reglas": reglas(cx)}


def resumen(cx):
    """Los dos números que van a la portada."""
    if not instalado(cx):
        return None
    datos = listar(cx)
    return {"total": datos["resumen"]["total"],
            "graves": datos["resumen"]["grave"]}


# =====================================================================
# LOS SERVICES
# =====================================================================
def services(cx):
    """Una fila por unidad activa, con lo que le falta para el próximo."""
    filas = _tabla(cx, """
        select * from v_services_hoy
        order by case estado
                   when 'vencido' then 0 when 'urgente' then 1
                   when 'proximo' then 2 when 'ok' then 3
                   when 'sin_odometro' then 4 else 5 end,
                 km_restantes nulls last, patente
    """)
    return filas if filas is not None else []


def historial_services(cx, unidad_id, limite=30):
    return _tabla(cx, """
        select * from services where unidad_id = %s
        order by km desc, fecha desc limit %s
    """, (int(unidad_id), limite)) or []


def guardar_service(cx, datos, usuario=None):
    """Anota un service hecho. No pisa el anterior: se suma al historial."""
    unidad_id = int(datos.get("unidad_id") or 0)
    if not unidad_id:
        raise ValueError("Elegí la unidad.")
    unidad = cx.execute("select id, patente, km_actual from unidades where id = %s",
                        (unidad_id,)).fetchone()
    if not unidad:
        raise ValueError("Esa unidad no existe.")

    km = datos.get("km")
    if km in (None, ""):
        km = unidad["km_actual"]
    if km in (None, ""):
        raise ValueError("Falta el kilometraje del service.")
    km = float(km)
    if km < 0:
        raise ValueError("El kilometraje no puede ser negativo.")

    cada = datos.get("cada_km")
    if cada in (None, ""):
        # Primero manda el plan asignado. El service conserva una foto de
        # esa frecuencia para que el historial no cambie si luego se reasigna.
        previo = cx.execute("""select p.cada_km from unidades u
            join mantenimiento_planes p on p.id=u.mantenimiento_plan_id and p.activo
            where u.id=%s""", (unidad_id,)).fetchone()
        if not previo:
            previo = cx.execute("""select cada_km from services where unidad_id = %s
                                   order by km desc limit 1""", (unidad_id,)).fetchone()
        cada = float(previo["cada_km"]) if previo else 15000
    cada = float(cada)
    if cada <= 0:
        raise ValueError("«Cada cuántos km» tiene que ser mayor que cero.")

    fecha = str(datos.get("fecha") or "").strip() or None
    limpio = lambda x, n=200: (str(x).strip()[:n] or None) if x else None
    orden_id = int(datos.get("orden_id") or 0) or None
    valores = (unidad_id, fecha, km, limpio(datos.get("tipo"), 60), cada,
               limpio(datos.get("taller"), 120),
               limpio(datos.get("observaciones"), 500), usuario)
    if orden_id:
        existente = cx.execute("select id from services where orden_id = %s",
                               (orden_id,)).fetchone()
        if existente:
            cx.execute("""
                update services set unidad_id = %s, fecha = coalesce(%s::date, current_date),
                    km = %s, tipo = %s, cada_km = %s, taller = %s,
                    observaciones = %s, usuario = %s
                where id = %s
            """, (*valores, existente["id"]))
            fila = existente
        else:
            fila = cx.execute("""
                insert into services (unidad_id, fecha, km, tipo, cada_km, taller,
                                      observaciones, usuario, orden_id)
                values (%s, coalesce(%s::date, current_date), %s, %s, %s, %s, %s, %s, %s)
                returning id
            """, (*valores, orden_id)).fetchone()
    else:
        fila = cx.execute("""
            insert into services (unidad_id, fecha, km, tipo, cada_km, taller,
                                  observaciones, usuario)
            values (%s, coalesce(%s::date, current_date), %s, %s, %s, %s, %s, %s)
            returning id
        """, valores).fetchone()

    # Un service nuevo es una alerta nueva: lo que se había silenciado del
    # anterior ya no aplica.
    reactivar(cx, "service", str(unidad_id))
    return fila["id"]


def borrar_service(cx, service_id):
    fila = cx.execute("delete from services where id = %s returning unidad_id",
                      (int(service_id),)).fetchone()
    if not fila:
        raise ValueError("Ese service no existe.")
    return fila["unidad_id"]
