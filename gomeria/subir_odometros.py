"""
Sube al Supabase de la app las lecturas de odómetro del satelital.

Quien las consigue es hawk.py, que entra al satelital y le pide la flota.
Este archivo es la otra mitad: las deja en la tabla `odometros`
(ver 05_odometros.sql), una fila por unidad y por día.

Recibe la lista de lecturas del scraper, o un DataFrame de pandas si lo que
se está cargando es un archivo viejo. Eso último es para la carga a mano:

    python gomeria/subir_odometros.py historico.csv

Necesita la variable SUPABASE_DB_URL (secret del repo). Si no está, avisa
y no hace nada, así el scraper se puede probar en cualquier lado sin tocar
la base.
"""
import os
import datetime


def _url():
    return (os.environ.get("SUPABASE_DB_URL") or "").strip()


def _patente(texto):
    """AD 247 MQ, ad-247-mq y AD247MQ son la misma patente.

    El satelital devuelve algunas con un HC pegado atrás (AC538KWHC, que es
    AC538KW). Como una patente argentina tiene 6 o 7 caracteres, cualquier
    cosa más larga terminada en HC es ese sufijo y se saca. Los equipos
    PORTATIL... no son unidades y quedan como están: la lectura se guarda
    igual pero no engancha con ninguna patente, que es lo correcto.
    """
    plano = "".join(ch for ch in str(texto or "").upper() if ch.isalnum())
    if len(plano) > 7 and plano.endswith("HC"):
        plano = plano[:-2]
    return plano


def _fecha_de(valor):
    """El día de la lectura. Viene como '2026-09-01 08:12:33' hora argentina."""
    if isinstance(valor, datetime.datetime):
        return valor.date()
    if isinstance(valor, datetime.date):
        return valor
    texto = str(valor or "").strip()[:10]
    try:
        return datetime.date.fromisoformat(texto)
    except ValueError:
        return datetime.date.today()


def _reporte_de(valor):
    """El 'Ultimo_reporte' del equipo: 29/07/2026 16:06."""
    texto = str(valor or "").strip()
    if not texto or texto.lower() == "nan":
        return None
    for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def filas_de(lecturas):
    """Las lecturas del scraper, quedándose con lo que se puede guardar.

    El scraper devuelve la fila igual cuando el equipo no contesta, con el
    kilometraje vacío, así que hay que filtrarlas. Y como el job se puede
    correr varias veces en el día, de cada unidad y día queda la última
    lectura: es una fila por unidad por día, igual que el índice de la tabla.

    Acepta la lista de diccionarios de hawk.py o un DataFrame de pandas: las
    dos cosas se recorren igual y en las dos la fila responde a .get().
    """
    if hasattr(lecturas, "iterrows"):
        lecturas = (fila for _, fila in lecturas.iterrows())

    porclave = {}
    for r in lecturas:
        patente = _patente(r.get("Patente"))
        if not patente:
            continue
        km = r.get("Kilometraje")
        try:
            km = float(km)
        except (TypeError, ValueError):
            continue
        # NaN es el equipo que no reportó, y cero es lo mismo: no son lecturas.
        if km != km or km <= 0:
            continue
        fecha = _fecha_de(r.get("Fecha_lectura"))
        porclave[(patente, fecha)] = (
            patente,
            fecha,
            round(km, 2),
            _reporte_de(r.get("Ultimo_reporte")),
            str(r.get("idGPS") or "").strip() or None,
        )
    return [porclave[k] for k in sorted(porclave)]


def subir(lecturas, url=None):
    """Guarda las lecturas del día. Devuelve cuántas guardó."""
    url = url or _url()
    if not url:
        print("\n[supabase] sin SUPABASE_DB_URL: no se suben los odometros")
        return 0

    filas = filas_de(lecturas)
    if not filas:
        print("\n[supabase] ninguna lectura utilizable")
        return 0

    import psycopg

    with psycopg.connect(url) as cx:
        # El sistema puede estar en manual: ahí los kilómetros los carga
        # una persona y una lectura automática le pisaría el número. Se
        # pregunta antes de escribir nada (ver parametros.py).
        try:
            fila = cx.execute("select km_origen from parametros").fetchone()
            if fila and fila[0] == "manual":
                print("\n[supabase] el kilometraje está en manual: no se sube nada")
                return 0
        except Exception:
            cx.rollback()      # sin 29_parametros.sql corrido, como siempre

        with cx.cursor() as cur:
            # Cuántas había antes, para poder decir después cuántas son
            # nuevas de verdad. En la corrida de todos los días se manda el
            # histórico entero, así que informar lo enviado no dice nada.
            antes = cx.execute("select count(*) from odometros").fetchone()[0]

            # El día ya cargado se pisa en vez de duplicarse: así el job se
            # puede volver a correr a mano sin ensuciar la serie.
            cur.executemany("""
                insert into odometros (patente, fecha, km, ultimo_reporte, id_gps, fuente)
                values (%s, %s, %s, %s, %s, 'hawk')
                on conflict (patente, fecha, fuente) do update
                   set km             = excluded.km,
                       ultimo_reporte = excluded.ultimo_reporte,
                       id_gps         = excluded.id_gps,
                       leido          = now()
            """, filas)

            despues = cx.execute("select count(*) from odometros").fetchone()[0]
            dias = sorted({f[1] for f in filas})
            sin_unidad = cx.execute("""
                select count(distinct patente) from odometros
                where fecha between %s and %s and unidad_id is null""",
                (dias[0], dias[-1])).fetchone()[0]

    nuevas = despues - antes
    print(f"\n[supabase] {len(filas)} lecturas leidas del archivo")
    print(f"[supabase] {nuevas} nuevas, {len(filas) - nuevas} ya estaban")
    print(f"[supabase] la tabla queda con {despues} lecturas")
    if sin_unidad:
        print(f"[supabase] {sin_unidad} patentes no estan en la tabla unidades "
              f"(la lectura queda guardada igual)")
    return nuevas


if __name__ == "__main__":
    # Carga a mano del histórico que el scraper viene guardando en el repo:
    #   python subir_odometros.py data/historico.csv
    import sys
    import pandas as pd

    if len(sys.argv) < 2:
        raise SystemExit("Uso: python subir_odometros.py data/historico.csv")

    datos = pd.read_csv(sys.argv[1]) if sys.argv[1].endswith(".csv") \
        else pd.read_excel(sys.argv[1])
    print(f"{len(datos)} filas en {sys.argv[1]}")
    print(f"nuevas: {subir(datos)}")
