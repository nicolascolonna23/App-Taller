#!/usr/bin/env python3
"""
Carga las unidades y sus mapas desde un CSV.

    python3 cargar_unidades.py unidades.csv

Columnas del CSV (el orden no importa, sí el nombre):

    patente    obligatoria
    mapa       obligatoria — S = eje simple, D = eje dual, de adelante hacia atrás
    interno    marca    modelo    sucursal    uso    km_actual

El mapa se escribe con una letra por eje:

    S-D-D    direccional + 2 traseros duales = 10 cubiertas  (tractor típico)
    S-D      chasis de reparto = 6 cubiertas
    D-D-D    semi de 3 ejes = 12 cubiertas

Se puede correr las veces que haga falta: si la unidad ya existe, actualiza
sus datos. Los montajes que ya tenga cargados no se tocan.
"""
import argparse, csv, os, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import base, mapas


def main():
    ap = argparse.ArgumentParser(description="Carga unidades y mapas desde un CSV")
    ap.add_argument("csv", help="Archivo con las unidades")
    ap.add_argument("--simular", action="store_true",
                    help="Muestra qué haría, sin escribir en la base")
    a = ap.parse_args()

    with open(a.csv, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    if not filas:
        raise SystemExit("El CSV está vacío.")

    faltan = {"patente", "mapa"} - {c.strip().lower() for c in filas[0]}
    if faltan:
        raise SystemExit(f"Al CSV le faltan columnas: {', '.join(sorted(faltan))}")

    # Primero se validan todos los mapas: es preferible frenar antes de escribir
    # que dejar media flota cargada y media no.
    limpias, sin_mapa = [], []
    for n, f in enumerate(filas, start=2):
        f = {(k or "").strip().lower(): (v or "").strip() for k, v in f.items()}
        if not f.get("patente"):
            continue
        # Sin mapa no se puede cargar, pero tampoco frena al resto: se avisa
        # al final y se cargan cuando se complete la columna.
        if not f.get("mapa"):
            sin_mapa.append(f["patente"])
            continue
        try:
            mapas.expandir(f["mapa"])
        except ValueError as e:
            raise SystemExit(f"Línea {n} ({f['patente']}): {e}")
        limpias.append(f)

    # Una configuración por cada mapa distinto, no una por unidad.
    distintos = sorted({f["mapa"].upper().replace(",", "-") for f in limpias})
    print(f"{len(limpias)} unidades · {len(distintos)} mapas distintos")
    for spec in distintos:
        cuantas = sum(1 for f in limpias if f["mapa"].upper().replace(",", "-") == spec)
        print(f"  {spec:<10} {mapas.describir(spec):<40} {cuantas} unidades")

    if sin_mapa:
        print(f"\nSin mapa, no se cargan: {', '.join(sin_mapa)}")
    if a.simular:
        print("\n(simulación: no se escribió nada)")
        return

    with base.conectar() as cx:
        configs = {}
        for spec in distintos:
            configs[spec] = base.crear_configuracion(cx, spec, spec, mapas.describir(spec))

        nuevas = 0
        for f in limpias:
            spec = f["mapa"].upper().replace(",", "-")
            km = f.get("km_actual") or None
            base.crear_unidad(cx, f["patente"], configs[spec],
                              interno=f.get("interno") or None,
                              marca=f.get("marca") or None,
                              modelo=f.get("modelo") or None,
                              sucursal=f.get("sucursal") or None,
                              uso=f.get("uso") or None,
                              km_actual=float(str(km).replace(".", "").replace(",", ".")) if km else None)
            nuevas += 1
        cx.commit()

    print(f"\nCargadas {nuevas} unidades.")
    if sin_mapa:
        print(f"Quedaron afuera {len(sin_mapa)} sin mapa: {', '.join(sin_mapa)}")
        print("  Completales la columna 'mapa' en el CSV y volvé a correr esto.")
    print("Las cubiertas se montan después, desde la pantalla de gomería o con un CSV aparte.")


if __name__ == "__main__":
    main()
