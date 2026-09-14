"""Los odómetros del satelital, leídos directo de Hawk.

Hasta acá esto llegaba rebotado: el scraper vivía en el repo ServiceDM,
dejaba un `historico.csv` commiteado y este repo se lo bajaba con curl.
Andaba, pero ataba la serie de la app a que el otro repo corriera. ServiceDM
está programado de lunes a viernes, así que sábado y domingo acá no entraba
nada; y el día que allá cambió el orden de las columnas del CSV, de este
lado se guardaron dos campos en blanco sin que nadie se enterara.

Ahora la app entra a Hawk por su cuenta. Hawk no tiene API abierta: hay que
loguearse con un navegador de verdad, y recién con las cookies de esa sesión
se le puede pedir la flota al mismo endpoint que usa su propia página. Por
eso esto necesita Chrome y corre en GitHub Actions, no en el server de la
app.

La planilla de services la sigue escribiendo ServiceDM. Son dos lecturas
distintas del mismo satelital y está bien que así sea: si un día se cae una,
la otra sigue.

Necesita los secrets HAWK_USER, HAWK_PASS y SUPABASE_DB_URL.

    python gomeria/hawk.py
"""
import datetime
import os
import re
import sys
import time

import subir_odometros

BASE = "http://www.hawkgps.com.ar/HawkEyeWeb/"
INDEX = BASE + "Index.aspx"

# Vacío es toda la flota. Las lecturas que no enganchan con ninguna patente
# de `unidades` se guardan igual y quedan sin unidad: no molestan a nadie y
# el día que se da de alta el vehículo, la historia ya está.
SOLO = [s.strip().upper()
        for s in os.environ.get("SOLO_EMPRESAS", "").split(",") if s.strip()]

# Argentina no tiene horario de verano: -3 fijo. La fecha de la lectura es
# la del día argentino, que es el día del que habla el que mira el tablero.
ARG = datetime.timezone(datetime.timedelta(hours=-3))

# La página no avisa cuándo terminó de cargar la lista de móviles, así que
# se la busca por lo único que se reconoce solo: una patente argentina en
# algún renglón corto. Si hay patentes, hay sesión.
JS_PATENTES = r"""
const re = /\b([A-Z]{2}\d{3}[A-Z]{2}|[A-Z]{3}\d{3})\b/;
const out = [], vistos = new Set();
document.querySelectorAll('div,li,td,span,a').forEach(el => {
  if (el.children.length > 2) return;
  const t = (el.innerText || '').trim();
  if (!t || t.length > 60) return;
  const m = t.match(re);
  if (!m || vistos.has(m[1])) return;
  vistos.add(m[1]); out.push(m[1]);
});
return out;
"""

# AE527FA viene mal escrita desde el satelital. Se corrige acá y no en la
# base: es un error de origen y la tabla no tiene por qué saberlo.
ERRATAS = {"AF527AE": "AE527FA", "AE527AE": "AE527FA"}


def _reporte(valor):
    """`/Date(1757601600000)/` es cuándo reportó por última vez el equipo."""
    m = re.search(r"/Date\((\d+)\)/", str(valor or ""))
    if not m:
        return None
    momento = datetime.datetime.fromtimestamp(int(m.group(1)) / 1000, ARG)
    return momento.strftime("%Y-%m-%d %H:%M:%S")


def _patente(texto):
    """'AE 527 FA' y 'AE527FA' son la misma unidad."""
    plano = re.sub(r"[^A-Z0-9]", "", str(texto or "").upper())
    return ERRATAS.get(plano, plano)


# ------------------------------------------------------------------ sesión

def _navegador():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--window-size=1600,1000")
    o.add_argument("--no-sandbox")
    o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--disable-gpu")
    # El sitio es http y mezcla contenido: sin esto Chrome bloquea medio login.
    o.add_argument("--ignore-certificate-errors")
    o.add_argument("--allow-running-insecure-content")
    return webdriver.Chrome(options=o)


def _entrar(d, usuario, clave):
    """Deja la sesión abierta en el navegador. Explota si no puede."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    d.get(INDEX)
    time.sleep(4)

    clave_campo, hasta = None, time.time() + 45
    while time.time() < hasta:
        visibles = [e for e in d.find_elements(By.CSS_SELECTOR, "input[type='password']")
                    if e.is_displayed()]
        if visibles:
            clave_campo = visibles[0]
            break
        if d.execute_script(JS_PATENTES):
            return            # ya había sesión abierta
        time.sleep(1)
    if clave_campo is None:
        raise SystemExit("Hawk: no aparece el campo de contraseña.")

    textos = [e for e in d.find_elements(By.CSS_SELECTOR, "input[type='text'],input:not([type])")
              if e.is_displayed()]
    if not textos:
        raise SystemExit("Hawk: no aparece el campo de usuario.")
    textos[0].clear()
    textos[0].send_keys(usuario)
    clave_campo.clear()
    clave_campo.send_keys(clave)

    # El botón de ingresar no tiene un id estable, así que se lo busca por lo
    # que dice. Si no aparece ninguno, Enter sobre la contraseña hace lo mismo.
    apretado = False
    for selector in ("input[type='submit']", "button[type='submit']", "button", "a[id*='ogin']"):
        for boton in d.find_elements(By.CSS_SELECTOR, selector):
            etiqueta = (boton.text or "") + " " + (boton.get_attribute("value") or "")
            if boton.is_displayed() and re.search(r"ingres|entrar|login|acceder|aceptar",
                                                  etiqueta, re.I):
                boton.click()
                apretado = True
                break
        if apretado:
            break
    if not apretado:
        clave_campo.send_keys(Keys.ENTER)

    hasta = time.time() + 60
    while time.time() < hasta:
        time.sleep(2)
        if d.execute_script(JS_PATENTES):
            return
    raise SystemExit("Hawk: entró pero nunca cargó la lista de móviles.")


def _sesion(d):
    """Las cookies del navegador, pasadas a requests para hablarle a la API."""
    import requests

    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": d.execute_script("return navigator.userAgent"),
        "Referer": INDEX,
        "Origin": "http://www.hawkgps.com.ar",
    })
    for c in d.get_cookies():
        s.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path", "/"))
    return s


def _flota(s):
    r = s.post(BASE + "JsonMoviles.aspx/ObtenerTodos",
               json={"idEmpresa": 0, "ListaID": 0, "idTipoMovil": 0}, timeout=30)
    r.raise_for_status()
    datos = r.json()
    return datos.get("d", datos) if isinstance(datos, dict) else datos


def _movil(s, id_gps):
    """El detalle de un móvil, que es donde está el odómetro."""
    r = s.post(BASE + "JsonMoviles.aspx/ObtenerMovil", json={"idGPS": id_gps}, timeout=30)
    if r.status_code != 200:
        return None
    return r.json().get("d")


# ------------------------------------------------------------------ lectura

def lecturas(usuario, clave):
    """Una fila por móvil, con las claves que espera subir_odometros."""
    d = _navegador()
    try:
        _entrar(d, usuario, clave)
        s = _sesion(d)
    finally:
        try:
            d.quit()
        except Exception:
            pass

    flota = _flota(s)
    if not isinstance(flota, list):
        raise SystemExit(f"Hawk: ObtenerTodos devolvió algo raro: {str(flota)[:200]}")
    print(f"flota: {len(flota)} móviles")

    if SOLO:
        flota = [m for m in flota
                 if any(x in (str(m.get("NombreEmpresa", "")) +
                              str(m.get("NombreFlota", ""))).upper() for x in SOLO)]
        print(f"a leer: {len(flota)} (filtro {SOLO})")

    hoy = datetime.datetime.now(ARG).strftime("%Y-%m-%d %H:%M:%S")
    filas, fallados = [], []
    for i, m in enumerate(flota, 1):
        # El detalle se pide de a uno y arranca en None en cada vuelta: si una
        # lectura falla, el km del móvil anterior no puede quedar pegado a
        # esta patente.
        detalle = km = reporte = falla = None
        try:
            detalle = _movil(s, m.get("idGPS"))
        except Exception as e:
            falla = type(e).__name__
        if detalle:
            km = detalle.get("Kilometraje")
            reporte = _reporte(detalle.get("FechaServer"))

        patente = (detalle or {}).get("Descripcion") or m.get("Patente") or m.get("Descripcion")

        # Lo que decide no es si el pedido salió bien sino si trajo odómetro:
        # el equipo que contesta con el kilometraje vacío tampoco es una
        # lectura. Se clasifica acá para que los que no entraron y los que sí
        # sumen la flota completa; si no, hay móviles que no aparecen en
        # ninguna de las dos cuentas y el resumen no cierra.
        if not isinstance(km, (int, float)):
            fallados.append(f"{_patente(patente) or m.get('idGPS')}: "
                            f"{falla or ('sin datos' if detalle is None else 'sin kilometraje')}")

        filas.append({
            "Patente": _patente(patente),
            "Kilometraje": km,
            "Ultimo_reporte": reporte,
            "idGPS": m.get("idGPS"),
            "Fecha_lectura": hoy,
        })
        if i % 20 == 0:
            print(f"  {i}/{len(flota)}")

    con_km = sum(1 for f in filas if isinstance(f["Kilometraje"], (int, float)))
    print(f"\nleídos {con_km}/{len(filas)} con kilometraje")
    if fallados:
        print(f"sin lectura ({len(fallados)}): " + ", ".join(fallados[:10]) +
              (" …" if len(fallados) > 10 else ""))
    return filas


def main():
    usuario = os.environ.get("HAWK_USER", "").strip()
    clave = os.environ.get("HAWK_PASS", "").strip()
    if not usuario or not clave:
        raise SystemExit("Faltan los secrets HAWK_USER / HAWK_PASS")

    filas = lecturas(usuario, clave)

    # Que Hawk conteste pero sin un solo kilometraje no es un día sin viajes:
    # es la sesión caída o la API cambiada. Tiene que fallar y avisar, no
    # terminar en verde sin datos.
    if not any(isinstance(f["Kilometraje"], (int, float)) and f["Kilometraje"] > 0
               for f in filas):
        raise SystemExit("Hawk contestó pero ningún móvil trajo kilometraje.")

    nuevas = subir_odometros.subir(filas)
    print(f"nuevas: {nuevas}")


if __name__ == "__main__":
    sys.exit(main())
