#!/usr/bin/env python3
"""
Carga los services desde la planilla, para arrancar con historia.

    python3 gomeria/cargar_services.py services.csv --simular
    python3 gomeria/cargar_services.py services.csv

Hasta ahora los services vivían en la planilla de Google. Esto los trae a
la base de una vez, para que las alertas no dependan de que una planilla
siga compartida. De ahí en más se cargan desde la pantalla de Alertas.

Columnas que entiende. El nombre no tiene que ser exacto: busca parecidos,
sin importar mayúsculas ni acentos.

    patente     obligatoria — el dominio de la unidad
    km          obligatoria — con cuántos kilómetros se le hizo
    fecha       cuándo. Si falta, hoy
    tipo        M6, aceite y filtros, correa…
    cada_km     cada cuántos km le toca de ahí en más. Si falta, 15.000
    taller      quién lo hizo
    nota        observaciones

Se puede correr las veces que haga falta, pero OJO: un service es un hecho,
no una ficha. Correrlo dos veces con el mismo archivo carga los mismos
services dos veces. Por eso se saltea el que ya esté cargado con la misma
unidad, la misma fecha y el mismo kilometraje.

Antes de escribir nada valida el archivo entero: si hay una patente que no
existe o un kilometraje que no se entiende, lo dice y no carga nada.
"""
import argparse, csv, os, re, sys, unicodedata
from datetime import date, datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import base

CADA_KM_POR_DEFECTO = 15000

ALIAS = {
    "patente": ["patente", "dominio", "unidad", "movil", "interno"],
    "km":      ["km", "kilometros", "kilometraje", "kmservice", "odometro"],
    "fecha":   ["fecha", "dia", "fechaservice"],
    "tipo":    ["tipo", "service", "trabajo", "detalle", "quesehizo"],
    "cada_km": ["cadakm", "intervalo", "frecuencia", "cada", "periodicidad"],
    "taller":  ["taller", "proveedor", "donde", "lugar"],
    "nota":    ["nota", "observaciones", "obs", "comentario"],
}


def simplificar(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", t.lower())


def mapear(encabezados):
    """Qué columna del archivo es cada campo nuestro."""
    simples = {simplificar(h): h for h in encabezados if h}
    mapa, usadas = {}, set()
    for pasada in ("exacta", "empieza", "contiene"):
        for campo, formas in ALIAS.items():
            if campo in mapa:
                continue
            for s, original in simples.items():
                if original in usadas:
                    continue
                if pasada == "exacta":
                    coincide = s in formas
                elif pasada == "empieza":
                    coincide = any(s.startswith(x) for x in formas)
                else:
                    # La pasada suelta solo con alias largos: 'km' adentro de
                    # otra palabra engancharía cualquier cosa.
                    coincide = any(x in s for x in formas if len(x) >= 5)
                if coincide:
                    mapa[campo] = original
                    usadas.add(original)
                    break
    return mapa


def leer(ruta):
    if ruta.lower().endswith((".xlsx", ".xlsm", ".xls")):
        import openpyxl
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        it = ws.iter_rows(values_only=True)
        encabezados = [str(c).strip() if c is not None else "" for c in next(it)]
        filas = [dict(zip(encabezados, f)) for f in it]
        wb.close()
        return encabezados, filas
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        return list(lector.fieldnames or []), list(lector)


def numero(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(".", "").replace(" ", "").replace("km", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def fecha_de(v):
    """Acepta lo que suele traer una planilla: 12/03/2026, 2026-03-12, o vacío."""
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    texto = str(v).strip()[:10]
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return "?"      # se entendió que hay algo, pero no qué


def main():
    p = argparse.ArgumentParser(description="Carga los services desde una planilla.")
    p.add_argument("archivo")
    p.add_argument("--simular", action="store_true", help="muestra qué haría y no escribe")
    args = p.parse_args()

    encabezados, filas = leer(args.archivo)
    mapa = mapear(encabezados)
    print("Columnas reconocidas:")
    for campo in ALIAS:
        print(f"  {campo:9} → {mapa.get(campo) or '(no está)'}")
    for obligatoria in ("patente", "km"):
        if obligatoria not in mapa:
            sys.exit(f"\nFalta la columna «{obligatoria}». Sin eso no se puede cargar nada.")

    with base.conectar() as cx:
        unidades = {u["patente"]: u["id"] for u in cx.execute(
            "select id, patente from unidades").fetchall()}
        internos = {str(u["interno"]).strip().upper(): u["id"] for u in cx.execute(
            "select id, interno from unidades where interno is not null").fetchall()}

        listas, problemas, repetidas = [], [], 0
        for n, fila in enumerate(filas, start=2):
            crudo = str(fila.get(mapa["patente"]) or "").strip()
            if not crudo:
                continue
            plano = "".join(c for c in crudo.upper() if c.isalnum())
            unidad_id = unidades.get(plano) or internos.get(crudo.upper())
            if not unidad_id:
                problemas.append(f"fila {n}: no existe la unidad «{crudo}»")
                continue

            km = numero(fila.get(mapa["km"]))
            if km is None or km < 0:
                problemas.append(f"fila {n}: no se entiende el kilometraje "
                                 f"«{fila.get(mapa['km'])}»")
                continue

            f = fecha_de(fila.get(mapa["fecha"])) if "fecha" in mapa else None
            if f == "?":
                problemas.append(f"fila {n}: no se entiende la fecha "
                                 f"«{fila.get(mapa['fecha'])}»")
                continue

            cada = numero(fila.get(mapa["cada_km"])) if "cada_km" in mapa else None
            texto = lambda campo, n=200: (
                str(fila.get(mapa[campo]) or "").strip()[:n] or None) if campo in mapa else None

            ya = cx.execute("""select 1 from services
                               where unidad_id = %s and km = %s
                                 and fecha = coalesce(%s::date, fecha)""",
                            (unidad_id, km, f)).fetchone()
            if ya:
                repetidas += 1
                continue

            listas.append((unidad_id, f, km, texto("tipo", 60),
                           cada or CADA_KM_POR_DEFECTO, texto("taller", 120),
                           texto("nota", 500)))

        print(f"\n{len(listas)} services para cargar · {repetidas} ya estaban")
        if problemas:
            print(f"\n{len(problemas)} filas con problemas:")
            for x in problemas[:20]:
                print("  " + x)
            if len(problemas) > 20:
                print(f"  … y {len(problemas) - 20} más")
            sys.exit("\nNo se cargó nada. Corregí el archivo y volvé a correrlo.")

        if args.simular:
            print("\n(simulación: no se escribió nada)")
            return

        for datos in listas:
            cx.execute("""
                insert into services (unidad_id, fecha, km, tipo, cada_km,
                                      taller, observaciones, usuario)
                values (%s, coalesce(%s, current_date), %s, %s, %s, %s, %s, 'importado')
            """, datos)
        cx.commit()
        print(f"\nListo: {len(listas)} services cargados.")

        print("\nCómo quedó cada unidad:")
        for f in cx.execute("""
                select patente, estado, km_restantes from v_services_hoy
                order by km_restantes nulls last limit 15""").fetchall():
            falta = "—" if f["km_restantes"] is None else f"{float(f['km_restantes']):,.0f}".replace(",", ".")
            print(f"  {f['patente']:10} {f['estado']:13} faltan {falta}")


if __name__ == "__main__":
    main()
