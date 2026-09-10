"""
Combustible: lo que gasta la flota, y el control de lo que nos facturan.

Dos cosas que salen del mismo archivo:

  El combustible de la flota. Nuestra planilla de cargas es el registro
  de cuánto combustible se puso y cuánto costó. Cruzada con la serie de
  odómetros del satelital sale el consumo real —litros cada 100 km— por
  unidad y por mes, que hasta acá había que ir a buscar a una planilla
  de Google y copiar a mano.

  El cruce de remitos, que es el control de la factura y sigue igual que
  siempre.

Un archivo, dos usos: lo que se sube para pagarle a la estación es lo
mismo que dice cuánto gasta la flota. Cargarlo dos veces sería garantía
de que un día los dos números no den lo mismo.

La estación de servicio manda un listado de remitos y después la factura.
Nosotros tenemos nuestra planilla de cargas. Hoy alguien compara las dos a
ojo antes de pagar. Acá se cruzan por número de remito y queda a la vista
lo que no coincide: lo que nos facturan y no tenemos, lo que cargamos y no
vino, y las diferencias de litros o de importe.

Está en prueba: se usa en paralelo con lo de siempre hasta que los números
den. Todo se carga por lotes, y un lote se borra entero.

Los archivos vienen del navegador en base64 y se leen acá, no allá: así el
mismo código lee el .xlsx de la estación y el .csv de la planilla, y no hay
que mantener dos parseos.
"""
import base64
import csv
import datetime
import io
import re

GESTORES = {"admin", "encargado"}

# Cómo se llama cada dato en los archivos que llegan. Cada estación arma su
# listado a su manera, así que se busca por lo que contiene el título, no
# por igualdad, y se prueban varios nombres.
ALIAS = {
    "remito":  ("REMITO", "COMPROBANTE", "TICKET", "NRO REMITO", "N REMITO", "VALE"),
    "fecha":   ("FECHA", "DIA"),
    "patente": ("PATENTE", "DOMINIO", "MOVIL", "MÓVIL", "UNIDAD", "CHAPA"),
    "litros":  ("LITROS", "LTS", "CANTIDAD", "VOLUMEN"),
    "importe": ("IMPORTE", "TOTAL", "MONTO", "PRECIO"),
    "estacion": ("ESTACION", "ESTACIÓN", "SURTIDOR", "PROVEEDOR", "RAZON SOCIAL"),
    "chofer":  ("CHOFER", "CONDUCTOR"),
}
# Cuando dos títulos entran en el mismo campo gana el primero de la lista,
# porque están ordenados de más específico a más general: "NRO REMITO" antes
# que "REMITO", y "TOTAL" no le puede ganar a "IMPORTE".


def _exigir_gestor(usuario, que="cargar combustible"):
    if (usuario or {}).get("rol") not in GESTORES:
        raise PermissionError(f"Solo un encargado o administrador puede {que}.")


def _remito(valor):
    """El número del remito, comparable venga como venga.

    La estación factura con el punto de venta adelante —0001-00123456— y
    nuestra planilla anota solo el número —123456—. Sacar todos los guiones
    y pegar los dígitos daría 100123456, que no es el mismo número: por eso
    lo que va antes del guión se descarta, que es lo que significa.

    0001-00123456, 00123456, 123456 y R 123.456 quedan todos en 123456.
    """
    texto = str(valor or "")
    if "-" in texto:
        texto = texto.rsplit("-", 1)[1]
    return re.sub(r"[^0-9]", "", texto).lstrip("0") or ""


# Lo que escribe la planilla cuando no se pudo leer la patente del ticket.
# Sin esto entran como si fueran una unidad más y "NOENCONTRADO" termina
# encabezando el ranking de la que más combustible cargó, que es una unidad
# que no existe.
SIN_PATENTE = {"NOENCONTRADO", "SD", "SN", "NA", "NN", "SINPATENTE",
               "NOENCONTRADA", "NOFIGURA", "NOSABE", "NOLEGIBLE"}


def _patente(valor):
    limpia = re.sub(r"[^A-Z0-9]", "", str(valor or "").upper())
    if not limpia or limpia in SIN_PATENTE:
        return None
    return limpia


def _separador(valores):
    """Si en esta columna la coma separa decimales o miles.

    Celda por celda no se puede decidir: "52,019" es cincuenta y dos mil
    diecinueve en un archivo y cincuenta y dos litros con diecinueve
    milésimas en otro, y las dos lecturas son igual de válidas mirando
    solo ese número. Adivinar mal no da un error: da un litraje mil veces
    más grande que el real, y eso después es un consumo inventado.

    Lo que sí decide es la columna entera. Alcanza con que UNA celda tenga
    la coma seguida de algo que no sean exactamente tres dígitos —"37,09",
    "66,7"— para saber que en este archivo la coma separa decimales, y
    entonces los separa en todas, "52,019" incluida.

    Devuelve ',' o '.' cuando la columna se delata, y None cuando de verdad
    no hay con qué decidir.
    """
    coma = punto = False
    for v in valores:
        s = re.sub(r"[\s$]", "", str(v or ""))
        if not s or not re.fullmatch(r"[\d.,-]+", s):
            continue
        # Con los dos signos presentes el de más a la derecha es el decimal
        # y no hace falta ninguna estadística.
        if "," in s and "." in s:
            return "," if s.rfind(",") > s.rfind(".") else "."
        if re.search(r",\d{1,2}$|,\d{4,}$", s):
            coma = True
        if re.search(r"\.\d{1,2}$|\.\d{4,}$", s):
            punto = True
    # Si las dos cosas aparecen, el archivo está mezclado y no hay regla
    # que valga: se cae en la lectura de a una celda.
    if coma != punto:
        return "," if coma else "."
    return None


def _numero(valor, dec=None):
    """Números en formato argentino y en el crudo del Excel.

    `dec` es cuál signo separa los decimales en esta columna, si se pudo
    saber mirándola entera. Sin eso se decide por la celda, que es lo que
    se puede hacer cuando no hay más información.
    """
    if isinstance(valor, (int, float)):
        return None if valor != valor else float(valor)
    s = re.sub(r"[\s$]", "", str(valor or ""))
    if not s or not re.fullmatch(r"[\d.,-]+", s):
        return None
    if dec in (",", "."):
        miles = "." if dec == "," else ","
        s = s.replace(miles, "").replace(dec, ".")
    else:
        coma, punto = s.rfind(","), s.rfind(".")
        if coma >= 0 and punto >= 0:
            d = "," if coma > punto else "."
            s = s.replace("." if d == "," else ",", "").replace(d, ".")
        elif coma >= 0:
            s = s.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
        elif punto >= 0 and re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _fecha(valor):
    if isinstance(valor, datetime.datetime):
        return valor.date()
    if isinstance(valor, datetime.date):
        return valor
    texto = str(valor or "").strip()[:10]
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$", texto)
    if m:
        anio = m[3] if len(m[3]) == 4 else "20" + m[3]
        try:
            return datetime.date(int(anio), int(m[2]), int(m[1]))
        except ValueError:
            return None
    try:
        return datetime.date.fromisoformat(texto)
    except ValueError:
        return None


# =====================================================================
# LEER EL ARCHIVO
# =====================================================================
def _filas_de(nombre, crudo):
    """Las filas del archivo, sea .xlsx o .csv, como listas de celdas."""
    if nombre.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        libro = openpyxl.load_workbook(io.BytesIO(crudo), data_only=True, read_only=True)
        hoja = libro[libro.sheetnames[0]]
        return [list(f) for f in hoja.iter_rows(values_only=True)]

    texto = crudo.decode("utf-8-sig", "replace")
    # La coma y el punto y coma se usan las dos; gana la que más aparece en
    # la primera línea, que es donde están los títulos.
    primera = texto.split("\n", 1)[0]
    sep = ";" if primera.count(";") > primera.count(",") else ","
    return [f for f in csv.reader(io.StringIO(texto), delimiter=sep)]


def _cabecera(filas, elegidas=None):
    """Dónde están los títulos y qué columna es cada cosa.

    Adivina por el nombre del título, pero adivinar no alcanza: una planilla
    de cargas puede tener a la vez el número de ticket y el de remito, y el
    que sirve para cruzar es el que figura en la factura. Por eso `elegidas`
    manda por encima de todo: es lo que el usuario eligió en la pantalla,
    columna por columna.
    """
    elegidas = elegidas or {}
    for i, fila in enumerate(filas[:15]):
        titulos = [" ".join(str(c or "").upper().split()) for c in fila]
        if not any(titulos):
            continue
        indice = {}
        for campo, nombres in ALIAS.items():
            # Lo elegido a mano gana: se busca por el nombre exacto de la
            # columna, que es lo que la pantalla devuelve.
            if campo in elegidas:
                j = next((k for k, t in enumerate(titulos)
                          if t == elegidas[campo]), None)
                if j is not None:
                    indice[campo] = j
                    continue
            for n in nombres:
                j = next((k for k, t in enumerate(titulos)
                          if n in t and k not in indice.values()), None)
                if j is not None:
                    indice[campo] = j
                    break
        if "remito" in indice:
            return i, indice, titulos
    return None, None, None


def leer(nombre, crudo, elegidas=None):
    """El archivo hecho filas listas para guardar, más lo que se descartó."""
    filas = _filas_de(nombre, crudo)
    if not filas:
        raise ValueError("El archivo está vacío.")

    fila_titulos, indice, titulos = _cabecera(filas, elegidas)
    if indice is None:
        vistos = ", ".join(str(c) for c in filas[0][:8] if c)
        raise ValueError(
            "No encuentro la columna del remito. Tiene que haber una que se "
            f"llame REMITO, COMPROBANTE, TICKET o VALE. En la primera fila vi: {vistos}")

    def celda(fila, campo):
        j = indice.get(campo)
        return fila[j] if j is not None and j < len(fila) else None

    # Cómo escribe los decimales este archivo. Se mira la columna entera
    # una vez, antes de leer ninguna fila: la respuesta es del archivo, no
    # de cada celda.
    datos = filas[fila_titulos + 1:]
    decimal = {c: _separador(celda(f, c) for f in datos)
               for c in ("litros", "importe")}

    salida, descartadas = [], 0
    for fila in datos:
        remito = _remito(celda(fila, "remito"))
        if not remito:
            descartadas += 1          # totales, subtotales, filas en blanco
            continue
        salida.append({
            "remito": remito,
            "remito_bruto": str(celda(fila, "remito") or "").strip()[:40],
            "fecha": _fecha(celda(fila, "fecha")),
            "patente": _patente(celda(fila, "patente")),
            "litros": _numero(celda(fila, "litros"), decimal["litros"]),
            "importe": _numero(celda(fila, "importe"), decimal["importe"]),
            "estacion": (str(celda(fila, "estacion") or "").strip() or None),
            "chofer": (str(celda(fila, "chofer") or "").strip().upper() or None),
        })

    # Un remito repetido adentro del mismo archivo es un error de armado y
    # hay que verlo antes de guardar, no después.
    repetidos = {}
    for f in salida:
        repetidos[f["remito"]] = repetidos.get(f["remito"], 0) + 1
    repetidos = sorted(r for r, n in repetidos.items() if n > 1)

    return {"filas": salida, "descartadas": descartadas, "repetidos": repetidos,
            "columnas": sorted(indice),
            "decimal": decimal,
            # Qué columna terminó siendo cada cosa, y todas las que hay:
            # con eso la pantalla arma los selectores para corregirlo.
            "usadas": {campo: titulos[j] for campo, j in indice.items()},
            "cabeceras": [t for t in titulos if t]}


# =====================================================================
# GUARDAR
# =====================================================================
def subir(cx, datos, usuario=None):
    """Lee el archivo y, si `confirmar` viene, lo guarda. Devuelve el resumen."""
    _exigir_gestor(usuario)

    origen = (datos.get("origen") or "").strip()
    if origen not in ("estacion", "planilla"):
        raise ValueError("Decí si el archivo es el listado de la estación o nuestra planilla.")
    nombre = (datos.get("nombre") or "archivo").strip()[:120]
    try:
        crudo = base64.b64decode(datos.get("contenido") or "", validate=False)
    except Exception:
        raise ValueError("El archivo no se pudo leer.")
    if not crudo:
        raise ValueError("El archivo llegó vacío.")

    leido = leer(nombre, crudo, datos.get("columnas"))
    filas = leido["filas"]
    if not filas:
        raise ValueError("No encontré ninguna fila con número de remito.")

    # Sin confirmar solo se muestra qué entraría. La primera vez conviene
    # mirarlo: si la estación cambió el formato, se ve acá y no después de
    # haber ensuciado la tabla.
    if not datos.get("confirmar"):
        return {"previo": True, "leidas": len(filas),
                "descartadas": leido["descartadas"],
                "repetidos": leido["repetidos"],
                "columnas": leido["columnas"],
                "decimal": leido["decimal"],
                "usadas": leido["usadas"],
                "cabeceras": leido["cabeceras"],
                "muestra": filas[:8]}

    lote = cx.execute("""
        insert into combustible_lotes (origen, archivo, estacion, periodo, filas, usuario)
        values (%s,%s,%s,%s,%s,%s) returning id""",
        (origen, nombre,
         (datos.get("estacion") or "").strip()[:120] or None,
         (datos.get("periodo") or "").strip()[:20] or None,
         len(filas), (usuario or {}).get("nombre"))).fetchone()["id"]

    # El remito que ya estaba se pisa: subir de nuevo el listado corregido
    # tiene que dejar la última versión, no dos.
    antes = cx.execute("select count(*) as n from combustible_cargas where origen = %s",
                       (origen,)).fetchone()["n"]

    # Los repetidos se resuelven acá y no en la base. Postgres no deja que
    # un mismo INSERT toque dos veces la misma fila —"ON CONFLICT DO UPDATE
    # command cannot affect row a second time"— y una planilla de un año
    # trae el mismo remito repetido de a decenas. Queda el último, que es
    # lo que hace falta y lo que ya decía la documentación.
    unicas = {}
    for f in filas:
        unicas[(f["remito"], f["patente"] or "")] = f

    # De a montones y no de a uno. Una fila por vez son mil idas y vueltas
    # contra Supabase para un archivo de mil remitos: con la base del otro
    # lado de internet eso es un minuto largo de pantalla colgada, y el
    # que sube la planilla del año se cansa antes de que termine.
    porrada = 500
    valores = list(unicas.values())
    for desde in range(0, len(valores), porrada):
        tanda = valores[desde:desde + porrada]
        cx.execute("""
            insert into combustible_cargas
              (lote_id, origen, remito, remito_bruto, fecha, patente,
               litros, importe, estacion, chofer)
            select %s, %s, f.remito, f.bruto, f.fecha, f.patente,
                   f.litros, f.importe, f.estacion, f.chofer
            from unnest(%s::text[], %s::text[], %s::date[], %s::text[],
                        %s::numeric[], %s::numeric[], %s::text[], %s::text[])
                 as f(remito, bruto, fecha, patente, litros, importe, estacion, chofer)
            on conflict (origen, remito, coalesce(patente, '')) do update set
              lote_id = excluded.lote_id, fecha = excluded.fecha,
              patente = excluded.patente, litros = excluded.litros,
              importe = excluded.importe, estacion = excluded.estacion,
              chofer = excluded.chofer, remito_bruto = excluded.remito_bruto""",
            (lote, origen,
             [f["remito"] for f in tanda],
             [f["remito_bruto"] for f in tanda],
             [f["fecha"] for f in tanda],
             [f["patente"] for f in tanda],
             [f["litros"] for f in tanda],
             [f["importe"] for f in tanda],
             [f["estacion"] or (datos.get("estacion") or None) for f in tanda],
             [f["chofer"] for f in tanda]))

    despues = cx.execute("select count(*) as n from combustible_cargas where origen = %s",
                         (origen,)).fetchone()["n"]

    return {"previo": False, "lote": lote, "leidas": len(filas),
            "guardadas": len(unicas),
            "repetidos": leido["repetidos"],
            "nuevas": despues - antes,
            "actualizadas": len(unicas) - (despues - antes),
            "descartadas": leido["descartadas"]}


def borrar_lote(cx, lote_id, usuario=None):
    _exigir_gestor(usuario, "borrar una carga")
    fila = cx.execute("delete from combustible_lotes where id = %s returning archivo",
                      (lote_id,)).fetchone()
    if not fila:
        raise ValueError("Ese lote no existe.")
    return {"borrado": fila["archivo"]}


# =====================================================================
# LEER
# =====================================================================
def _uno(cx, consulta, valores=()):
    try:
        return cx.execute(consulta, valores).fetchall()
    except Exception:
        cx.rollback()
        return []


def flota(cx, mes=None, limite=400):
    """El combustible de la flota: el total del mes y unidad por unidad.

    Sale de lo mismo que se sube como "nuestra planilla". El archivo es
    uno solo y sirve para las dos cosas: acá dice cuánto gastó la flota,
    y en el cruce sirve para validar la factura de la estación.

    Sin `mes` se toma el último que tenga cargas, que es el que se está
    mirando el 99% de las veces.
    """
    # Sin _uno a propósito: si la vista todavía no existe tiene que
    # reventar para que la pantalla diga que falta correr el SQL. Tragarse
    # el error acá deja una pantalla vacía que parece "no hay cargas".
    meses = cx.execute(
        "select * from v_combustible_mes order by mes desc limit 36").fetchall()
    if not meses:
        return {"meses": [], "mes": None, "total": None, "unidades": []}

    # El mes que se pidió, si existe.
    elegido = next((dict(m) for m in meses if str(m["mes"])[:7] == str(mes or "")[:7]), None)

    # Si no se pidió ninguno, el último que ya pasó. No el último de la
    # lista: una fecha tipeada mal —2027 en vez de 2026— es del futuro, y
    # abrir ahí muestra una pantalla con dos cargas y el resto vacío, que
    # parece que no se cargó nada. El mes de un dedazo existe igual y se
    # puede elegir a mano; lo que no puede es ser lo primero que se ve.
    if elegido is None:
        este_mes = datetime.date.today().replace(day=1)
        elegido = next((dict(m) for m in meses if m["mes"] <= este_mes),
                       dict(meses[0]))

    return {
        "meses": [dict(m) for m in meses],
        "mes": str(elegido["mes"]),
        "total": elegido,
        "unidades": _uno(cx, """
            select * from v_combustible_flota
            where mes = %s
            -- Primero el que más gastó: es por donde se empieza a mirar.
            order by importe desc nulls last, litros desc nulls last
            limit %s""", (elegido["mes"], limite)),
    }


def serie_consumo(cx, limite=36):
    """El consumo mes a mes, para los tableros de flota.

    Devuelve dos series: la de toda la flota, que es la que se grafica, y
    la de cada unidad, que es la del ranking de quién consume más.

    Litros cada 100 km de toda la flota y, aparte, de larga distancia.
    Sale de lo mismo que el resto del módulo: los litros que se cargan en
    nuestra planilla contra los kilómetros que cuenta el satelital.

    Este número lo traía una planilla de Google con la telemetría de la
    marca. Se calcula acá porque los dos ingredientes ya estaban en la
    base y la planilla era una tercera versión de la verdad, que además
    dejaba de andar cada vez que alguien tocaba los permisos del archivo.

    El consumo se calcula sobre los totales del mes y no promediando el
    de cada unidad, por lo mismo que ya hace `v_combustible_mes`: un
    utilitario que hizo 200 km no puede pesar igual que un tractor que
    hizo 12.000. Y entran solo los litros de las unidades a las que se
    les conocen los kilómetros; los otros darían un consumo inventado.
    """
    filas = _uno(cx, """
        select mes,
               sum(km)                                     as km,
               round(sum(litros) filter (where km > 0), 2)  as litros,
               count(*) filter (where km > 0)::int          as unidades,
               case when sum(km) > 0 and sum(litros) filter (where km > 0) > 0
                    then round(sum(litros) filter (where km > 0) * 100
                               / sum(km), 2)
               end as litros_100km,
               -- Larga distancia va aparte: es la operación que se mira
               -- con lupa y mezclarla con reparto tapa cualquier
               -- desvío. Se reconoce por la sucursal, que es como la
               -- distingue el resto del sistema.
               case when sum(km) filter (where upper(btrim(sucursal)) = 'LAD') > 0
                     and sum(litros) filter (where km > 0
                                               and upper(btrim(sucursal)) = 'LAD') > 0
                    then round(sum(litros) filter (where km > 0
                                                     and upper(btrim(sucursal)) = 'LAD') * 100
                               / sum(km) filter (where upper(btrim(sucursal)) = 'LAD'), 2)
               end as litros_100km_lad
        from v_combustible_flota
        group by mes
        order by mes desc
        limit %s""", (limite,))
    # De vuelta en orden cronológico: los gráficos leen de izquierda a
    # derecha y el límite tiene que quedarse con los meses más nuevos.
    flota = list(reversed(filas or []))

    # Y la misma cuenta unidad por unidad, para los rankings. Se acota a
    # los meses que ya salieron arriba: traer toda la historia por unidad
    # es un archivo grande para dibujar doce barras.
    desde = flota[0]["mes"] if flota else None
    unidades = _uno(cx, """
        select mes, patente, sucursal, interno, marca, modelo, chofer,
               km, litros, litros_100km
        from v_combustible_flota
        where patente is not null and (%s::date is null or mes >= %s::date)
        order by mes, patente""", (desde, desde)) or []

    return {"flota": flota, "unidades": unidades}


def panel(cx, estado=None, limite=400):
    """El cruce, el resumen y los lotes cargados."""
    filtro, valores = "", []
    if estado:
        filtro = "where estado = %s"
        valores.append(estado)
    valores.append(limite)
    return {
        "tickets": _uno(cx, """
            select c.*, u.interno from combustible_cargas c
            left join unidades u on u.id = c.unidad_id
            where c.origen = 'planilla'
            order by c.fecha desc nulls last, c.id desc"""),
        "resumen": _uno(cx, "select * from v_combustible_resumen order by estado"),
        "cruce": _uno(cx, f"""
            select c.*, u.interno, u.chofer as chofer_unidad
            from v_combustible_cruce c
            left join unidades u on u.id = c.unidad_id
            {filtro}
            -- Primero lo que hay que mirar y después lo que está bien.
            order by (c.estado = 'ok'), c.fecha desc nulls last, c.remito
            limit %s""", valores),
        "lotes": _uno(cx, """
            select l.*, count(c.id)::int as vigentes
            from combustible_lotes l
            left join combustible_cargas c on c.lote_id = l.id
            group by l.id order by l.subido desc limit 30"""),
    }
