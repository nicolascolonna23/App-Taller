#!/usr/bin/env python3
"""
Carga los services desde las planillas del taller.

    python3 gomeria/cargar_services.py ServicesLAD.csv ServicesBUE.csv --simular
    python3 gomeria/cargar_services.py ServicesLAD.csv ServicesBUE.csv

Se le pasan todos los archivos juntos: una planilla por residencia es lo
normal, y validarlas de a una obliga a acordarse de cuál ya se cargó.

Está hecho para leer las planillas COMO SON, no como habría que
escribirlas. Las de Diemar traen arriba un título y la fecha de la última
carga antes de la tabla, encabezados repetidos, números con puntos de mil
y fechas de un dígito. Nada de eso hay que corregir a mano.

Columnas que entiende. El nombre no tiene que ser exacto: busca parecidos,
sin importar mayúsculas ni acentos.

    patente     obligatoria — el dominio de la unidad
    km          obligatoria — con cuántos km se le hizo el último service
    proximo_km  con cuántos km le toca el próximo
    fecha       cuándo se le hizo. Si falta, hoy
    cada_km     cada cuántos km le toca. Ver abajo
    tipo        M6, aceite y filtros, correa…
    taller      quién lo hizo
    nota        observaciones

CADA CUÁNTOS KILÓMETROS. Es el dato del que sale la alerta y casi ninguna
planilla lo tiene como columna, pero sí tiene el próximo service. El
intervalo se saca de ahí: próximo menos último. En las planillas de Diemar
da 40.000 y 45.000 km según el camión, que es justo lo que un valor fijo
por defecto se comería.

Se puede correr las veces que haga falta: se saltea el service que ya esté
cargado con la misma unidad, la misma fecha y el mismo kilometraje. Pero
un service es un hecho y no una ficha: dos archivos distintos con el mismo
service cargan dos veces si las fechas no coinciden.

Antes de escribir nada valida TODOS los archivos. Si una patente no existe
en el maestro, no carga nada de ningún archivo: una patente que no está es
señal de que el maestro quedó viejo, y cargar el resto lo taparía.
"""
import argparse, csv, os, re, sys, unicodedata
from datetime import date, datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import base

CADA_KM_POR_DEFECTO = 15000

# El orden importa: se resuelve de arriba hacia abajo, y el primero que
# engancha se queda con la columna. 'proximo_km' va antes que 'tipo' porque
# en estas planillas la columna se llama "FECHA/KM PROXIMO SERVICE" y, si
# 'tipo' la agarrara primero, el tipo de service sería una fecha.
ALIAS = {
    "patente":    ["patente", "dominio", "unidad", "movil", "interno"],
    "km":         ["kmultimoservice", "kmultimo", "km", "kilometros",
                   "kilometraje", "odometro"],
    "proximo_km": ["proximo", "proximokm", "kmproximo", "proximoservice"],
    "fecha":      ["fechaultimoservice", "fechaultimo", "fecha", "dia"],
    "cada_km":    ["cadakm", "intervalo", "frecuencia", "periodicidad", "cada"],
    "tipo":       ["tipodeservice", "tipo", "trabajo", "quesehizo", "descripcion"],
    "taller":     ["taller", "proveedor", "donde", "lugar"],
    "nota":       ["nota", "observaciones", "obs", "comentario"],
}

OBLIGATORIAS = ("patente", "km")


def simplificar(t):
    """'Nro. de Fuego' → 'nrodefuego'. También saca los saltos de línea que
    Google mete adentro de una celda de encabezado."""
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", t.lower())


def mapear(encabezados):
    """Qué columna del archivo es cada campo nuestro. Devuelve campo → índice.

    Se trabaja con índices y no con nombres porque estas planillas repiten
    encabezados —LAD tiene dos columnas que se llaman PATENTE— y buscar por
    nombre devuelve cualquiera de las dos.
    """
    columnas = [(simplificar(h), i) for i, h in enumerate(encabezados)]
    mapa, usadas = {}, set()

    for pasada in ("exacta", "empieza", "contiene"):
        for campo, formas in ALIAS.items():
            if campo in mapa:
                continue
            for simple, i in columnas:
                if not simple or i in usadas:
                    continue
                if pasada == "exacta":
                    coincide = simple in formas
                elif pasada == "empieza":
                    coincide = any(simple.startswith(x) for x in formas)
                else:
                    # La pasada suelta solo con alias largos: 'km' adentro de
                    # otra palabra engancharía cualquier cosa.
                    coincide = any(x in simple for x in formas if len(x) >= 5)
                if coincide:
                    mapa[campo] = i
                    usadas.add(i)
                    break
    return mapa


def _es_encabezado(fila):
    """Si esta fila tiene, por lo menos, la patente y el kilometraje."""
    mapa = mapear(fila)
    return all(c in mapa for c in OBLIGATORIAS)


def leer(ruta):
    """Devuelve (encabezados, filas) salteando lo que haya arriba de la tabla.

    Las planillas del taller arrancan con un título, la fecha de la última
    carga y filas en blanco: la tabla empieza más abajo. En vez de pedir que
    las limpien, se busca dónde empieza.
    """
    if ruta.lower().endswith((".xlsx", ".xlsm", ".xls")):
        import openpyxl
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        crudas = [["" if c is None else c for c in fila]
                  for fila in ws.iter_rows(values_only=True)]
        wb.close()
    else:
        with open(ruta, encoding="utf-8-sig", newline="") as f:
            crudas = list(csv.reader(f))

    for n, fila in enumerate(crudas[:25]):
        if _es_encabezado(fila):
            return [str(c).strip() for c in fila], crudas[n + 1:]
    # No se encontró: se devuelve la primera fila igual, para que el mensaje
    # de error diga qué columnas hay en vez de un "no se pudo leer".
    return [str(c).strip() for c in (crudas[0] if crudas else [])], crudas[1:]


def valor(fila, mapa, campo):
    i = mapa.get(campo)
    if i is None or i >= len(fila):
        return None
    v = fila[i]
    return v if not isinstance(v, str) else v.strip()


def numero(v):
    """Los números como los escribe una planilla argentina.

    1.719.118 son un millón setecientos mil, y "281.964,00" son doscientos
    ochenta y un mil. El punto separa los miles y la coma los decimales.
    """
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("$", "").replace(" ", "").replace("km", "")
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def fecha_de(v):
    """20/7/26, 28/8/2026, 2026-08-28. Devuelve '?' si hay algo y no se entiende."""
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    texto = str(v).strip()[:10]
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return "?"


def revisar(ruta, cx, unidades, internos):
    """Lee un archivo y devuelve (listas, problemas, salteadas, repetidas)."""
    encabezados, filas = leer(ruta)
    mapa = mapear(encabezados)

    print(f"\n{os.path.basename(ruta)} — {len(filas)} filas debajo del encabezado")
    for campo in ALIAS:
        i = mapa.get(campo)
        print(f"  {campo:11} → {encabezados[i] if i is not None else '(no está)'}")

    faltan = [c for c in OBLIGATORIAS if c not in mapa]
    if faltan:
        print(f"  ¡Falta la columna «{'» y «'.join(faltan)}»! "
              f"Columnas del archivo: {', '.join(x for x in encabezados if x)}")
        return [], [f"{os.path.basename(ruta)}: falta la columna «{faltan[0]}»"], 0, 0

    listas, problemas, salteadas, repetidas = [], [], 0, 0
    sin_intervalo = 0

    for n, fila in enumerate(filas, start=2):
        crudo = str(valor(fila, mapa, "patente") or "").strip()
        if not crudo:
            continue                      # fila vacía de las que sobran abajo
        plano = "".join(c for c in crudo.upper() if c.isalnum())
        unidad_id = unidades.get(plano) or internos.get(crudo.upper())
        if not unidad_id:
            problemas.append(f"{os.path.basename(ruta)} fila {n}: "
                             f"no existe la unidad «{crudo}»")
            continue

        km = numero(valor(fila, mapa, "km"))
        if km is None or km < 0:
            # Una unidad cargada en la planilla pero todavía sin service no es
            # un error del archivo: es una unidad sin service. Se saltea.
            salteadas += 1
            continue

        f = fecha_de(valor(fila, mapa, "fecha"))
        if f == "?":
            problemas.append(f"{os.path.basename(ruta)} fila {n}: "
                             f"no se entiende la fecha «{valor(fila, mapa, 'fecha')}»")
            continue

        cada = numero(valor(fila, mapa, "cada_km"))
        if not cada or cada <= 0:
            # De la columna del próximo service: próximo menos último. Es de
            # donde sale el intervalo real de cada camión.
            proximo = numero(valor(fila, mapa, "proximo_km"))
            if proximo and proximo > km:
                cada = proximo - km
        if not cada or cada <= 0:
            previo = cx.execute("""select cada_km from services
                                   where unidad_id = %s order by km desc limit 1""",
                                (unidad_id,)).fetchone()
            cada = float(previo["cada_km"]) if previo else CADA_KM_POR_DEFECTO
            sin_intervalo += 1

        texto = lambda campo, n=200: (str(valor(fila, mapa, campo) or "").strip()[:n]
                                      or None)

        ya = cx.execute("""select 1 from services
                           where unidad_id = %s and km = %s
                             and fecha = coalesce(%s::date, fecha)""",
                        (unidad_id, km, f)).fetchone()
        if ya:
            repetidas += 1
            continue

        listas.append((unidad_id, f, km, texto("tipo", 60), cada,
                       texto("taller", 120), texto("nota", 500)))

    print(f"  {len(listas)} para cargar · {repetidas} ya estaban · "
          f"{salteadas} sin service todavía")
    if sin_intervalo:
        print(f"  ojo: {sin_intervalo} sin «cada cuántos km» en la planilla; "
              f"quedan con {CADA_KM_POR_DEFECTO:,.0f}".replace(",", ".") +
              " o con el que ya tenían")
    return listas, problemas, salteadas, repetidas


def main():
    p = argparse.ArgumentParser(
        description="Carga los services desde una o varias planillas.")
    p.add_argument("archivos", nargs="+", help="los CSV o Excel, todos juntos")
    p.add_argument("--simular", action="store_true",
                   help="muestra qué haría y no escribe nada")
    args = p.parse_args()

    for ruta in args.archivos:
        if not os.path.exists(ruta):
            sys.exit(f"No encuentro el archivo: {ruta}")

    with base.conectar() as cx:
        existe = cx.execute("select to_regclass('public.services') as t").fetchone()
        if not existe or not existe["t"]:
            sys.exit("Falta la tabla de services. Corré gomeria/20_alertas.sql "
                     "en el SQL Editor de Supabase.")

        unidades = {u["patente"]: u["id"] for u in cx.execute(
            "select id, patente from unidades").fetchall()}
        internos = {str(u["interno"]).strip().upper(): u["id"] for u in cx.execute(
            "select id, interno from unidades where interno is not null").fetchall()}

        todo, problemas = [], []
        for ruta in args.archivos:
            listas, malas, _, _ = revisar(ruta, cx, unidades, internos)
            todo += listas
            problemas += malas

        print(f"\n{'=' * 52}\nEn total: {len(todo)} services para cargar")

        if problemas:
            print(f"\n{len(problemas)} filas con problemas:")
            for x in problemas[:25]:
                print("  " + x)
            if len(problemas) > 25:
                print(f"  … y {len(problemas) - 25} más")
            sys.exit("\nNo se cargó nada, de ningún archivo. Corregí y volvé a correrlo.")

        if args.simular:
            print("\n(simulación: no se escribió nada)")
            return
        if not todo:
            print("\nNo hay nada nuevo para cargar.")
            return

        for datos in todo:
            cx.execute("""
                insert into services (unidad_id, fecha, km, tipo, cada_km,
                                      taller, observaciones, usuario)
                values (%s, coalesce(%s, current_date), %s, %s, %s, %s, %s, 'importado')
            """, datos)
        cx.commit()
        print(f"\nListo: {len(todo)} services cargados.")

        print("\nCómo quedó cada unidad:")
        for f in cx.execute("""
                select patente, estado, km_restantes, cada_km from v_services_hoy
                where ultimo_km is not null
                order by km_restantes nulls last""").fetchall():
            falta = ("—" if f["km_restantes"] is None
                     else f"{float(f['km_restantes']):,.0f}".replace(",", "."))
            cada = f"{float(f['cada_km']):,.0f}".replace(",", ".")
            print(f"  {f['patente']:10} {f['estado']:13} faltan {falta:>10}  "
                  f"(cada {cada})")


if __name__ == "__main__":
    main()
