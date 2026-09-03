#!/usr/bin/env python3
"""
Carga el maestro de unidades desde la planilla.

    python3 gomeria/importar_unidades.py gomeria/unidades_maestro.tsv --simular
    python3 gomeria/importar_unidades.py gomeria/unidades_maestro.tsv

Lee un TSV (o CSV) con las columnas de la planilla, tal como se copian:

    MODELO · NUMERO DE CHASIS · MARCA · CHOFER · PATENTE · NRO INTERNO
    SEMI ASOCIADO · RESIDENCIA · USO

Se puede correr las veces que haga falta. La unidad que ya existe se
actualiza; la que no, se da de alta. Nada se borra: si una unidad está en
la base y no en el archivo, queda como está y se avisa al final. Sacarla
es una decisión, no un efecto de haber importado.

Los campos que el archivo trae vacíos no pisan lo que ya hay en la base.
Así se puede importar una planilla incompleta sin perder datos cargados a
mano desde la pantalla.
"""
import argparse
import csv
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import base
import unidades as uni

# Cómo se llama cada columna en la planilla. Se compara en mayúsculas y sin
# espacios de más, así "Nro Interno" y "NRO  INTERNO" entran igual.
COLUMNAS = {
    "modelo": "MODELO",
    "chasis": "NUMERO DE CHASIS",
    "marca": "MARCA",
    "chofer": "CHOFER",
    "patente": "PATENTE",
    "interno": "NRO INTERNO",
    "semi": "SEMI ASOCIADO",
    "sucursal": "RESIDENCIA",
    "uso": "USO",
}


def leer(ruta):
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        muestra = f.read(4096)
        f.seek(0)
        # La planilla se copia con tabulaciones; si alguien la exporta como
        # CSV, también entra.
        sep = "\t" if muestra.count("\t") > muestra.count(",") else ","
        filas = list(csv.reader(f, delimiter=sep))

    if not filas:
        raise SystemExit("El archivo está vacío.")

    cabecera = [" ".join((c or "").upper().split()) for c in filas[0]]
    indice = {}
    for campo, titulo in COLUMNAS.items():
        if titulo in cabecera:
            indice[campo] = cabecera.index(titulo)
    if "patente" not in indice:
        raise SystemExit(f"No encuentro la columna PATENTE. Vi: {', '.join(cabecera)}")

    salida = []
    for n, fila in enumerate(filas[1:], start=2):
        dato = {c: (fila[i].strip() if i < len(fila) else "")
                for c, i in indice.items()}
        if not uni.normalizar(dato["patente"]):
            continue                      # fila en blanco al final de la planilla
        dato["linea"] = n
        salida.append(dato)
    return salida


def main():
    ap = argparse.ArgumentParser(description="Importa el maestro de unidades")
    ap.add_argument("archivo", help="TSV o CSV copiado de la planilla")
    ap.add_argument("--simular", action="store_true",
                    help="Dice qué haría, sin escribir nada")
    a = ap.parse_args()

    filas = leer(a.archivo)
    print(f"{len(filas)} unidades en {a.archivo}")

    # Una patente repetida en la planilla es un error de carga y hay que
    # verlo antes de escribir, no después.
    vistas = {}
    for f in filas:
        p = uni.normalizar(f["patente"])
        if p in vistas:
            raise SystemExit(f"La patente {p} está dos veces en el archivo "
                             f"(líneas {vistas[p]} y {f['linea']}).")
        vistas[p] = f["linea"]

    with base.conectar() as cx:
        existentes = {r["patente"]: r for r in
                      cx.execute("select * from unidades").fetchall()}

        altas, cambios, iguales = [], [], 0
        for f in filas:
            patente = uni.normalizar(f["patente"])
            campos = {
                "interno": f.get("interno") or None,
                "marca": (f.get("marca") or "").upper() or None,
                "modelo": f.get("modelo") or None,
                "chasis": f.get("chasis") or None,
                "chofer": (f.get("chofer") or "").upper() or None,
                "semi": uni.normalizar(f.get("semi")) or None,
                "sucursal": (f.get("sucursal") or "").upper() or None,
                "uso": (f.get("uso") or "").upper() or None,
                "tipo": "vehiculo" if uni.es_patente(patente) else "equipo",
            }
            actual = existentes.get(patente)
            if not actual:
                altas.append((patente, campos))
                continue
            # Solo los campos que el archivo trae con algo, y solo si cambian:
            # un valor vacío en la planilla no borra lo que hay cargado.
            distintos = {c: v for c, v in campos.items()
                         if v is not None and (actual.get(c) or None) != v}
            if distintos:
                cambios.append((patente, actual["id"], distintos))
            else:
                iguales += 1

        print(f"  altas: {len(altas)} · cambios: {len(cambios)} · sin tocar: {iguales}")
        for patente, campos in altas:
            print(f"    + {uni.base_fmt(patente)}  {campos['modelo'] or campos['tipo']}")
        for patente, _, distintos in cambios:
            print(f"    ~ {uni.base_fmt(patente)}  {', '.join(sorted(distintos))}")

        sobran = sorted(set(existentes) - set(vistas))
        if sobran:
            print(f"\n  {len(sobran)} en la base que no están en el archivo "
                  f"(se dejan como están): {', '.join(sobran)}")

        if a.simular:
            print("\n(simulación: no se escribió nada)")
            return

        for patente, campos in altas:
            columnas = ", ".join(["patente"] + list(campos))
            huecos = ", ".join(["%s"] * (len(campos) + 1))
            cx.execute(f"insert into unidades ({columnas}) values ({huecos})",
                       [patente] + list(campos.values()))
        for _, unidad_id, distintos in cambios:
            sets = ", ".join(f"{c} = %s" for c in distintos)
            cx.execute(f"update unidades set {sets} where id = %s",
                       list(distintos.values()) + [unidad_id])
        cx.commit()

        total = cx.execute("select count(*) as n from unidades").fetchone()["n"]
        print(f"\nListo. El maestro queda con {total} unidades.")

        pendientes = cx.execute("""
            select problema, count(*) as n from v_unidades_a_revisar
            group by problema order by n desc""").fetchall()
        if pendientes:
            print("\nPara revisar cuando puedas:")
            for p in pendientes:
                print(f"  {p['n']:>3}  {p['problema']}")


if __name__ == "__main__":
    main()
