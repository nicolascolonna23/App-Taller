"""
Desgaste, costo y rendimiento de las cubiertas.

Tres preguntas, que son la misma mirada desde tres lados:

    ¿a cuál hay que bajar?      → alertas()
    ¿cuánto sale el kilómetro?  → rendimiento(), por vida
    ¿qué marca conviene?        → rendimiento(), por marca y banda

Todo se apoya en las vistas de ``18_desgaste.sql``. Acá no se recalcula
nada: se pide, se ordena y se le pone el nombre que va en pantalla.

La unidad de medida es la VIDA, no la cubierta. Una goma vive varias
vidas —la original y cada recapado— y cada una tiene su banda, su costo y
sus kilómetros. Sumar todo junto no compara nada: mezcla una Michelin
nueva con la banda que le pusieron encima tres años después.
"""

# Los milímetros mínimos que puede tener una goma para que valga la pena
# calcular su ritmo de desgaste. Con menos que esto la cuenta km/mm da
# cualquier cosa: dos mediciones parecidas y un redondeo mandan el número
# a la luna.
MINIMO_PARA_CALCULAR_MM = 1


def _tabla(cx, consulta, valores=()):
    """La consulta, o una lista vacía si la vista todavía no existe.

    Los módulos se prenden de a uno y el SQL se corre a mano: hasta que no
    esté corrido ``18_desgaste.sql``, estas vistas no están. Que falten
    apaga la pantalla de desgaste, no el resto de Gomería.
    """
    try:
        return cx.execute(consulta, valores).fetchall()
    except Exception:
        # Después de un error la conexión queda inservible hasta que se
        # deshaga la transacción.
        cx.rollback()
        return []


def instalado(cx):
    """Si ya se corrió el SQL de desgaste."""
    fila = cx.execute("select to_regclass('public.vidas_cubierta') as t").fetchone()
    return bool(fila and fila["t"])


def _exigir_instalado(cx):
    """Antes de escribir. Es mejor decir qué falta que tirar el error crudo
    de Postgres, que nadie fuera del taller sabe leer."""
    if not instalado(cx):
        raise ValueError("Todavía no está prendido el módulo de desgaste. "
                         "Hay que correr gomeria/18_desgaste.sql en Supabase.")


# =====================================================================
# LO QUE SE CONFIGURA UNA VEZ
# =====================================================================
FUNCIONES = ("direccional", "traccion", "arrastre", "auxilio")


def criterios(cx):
    return _tabla(cx, "select * from criterios_desgaste order by funcion")


def guardar_criterio(cx, funcion, minimo_mm, aviso_mm):
    """Cambia el mínimo de una función de eje.

    El aviso nunca puede quedar por debajo del mínimo: sería un amarillo
    que se prende después del rojo.
    """
    _exigir_instalado(cx)
    if funcion not in FUNCIONES:
        raise ValueError("Esa función de eje no existe.")
    minimo, aviso = float(minimo_mm), float(aviso_mm)
    if minimo <= 0:
        raise ValueError("El mínimo tiene que ser mayor que cero.")
    if aviso < minimo:
        raise ValueError("El aviso tiene que ser igual o mayor que el mínimo: "
                         "es el amarillo antes del rojo.")
    cx.execute("""update criterios_desgaste set minimo_mm = %s, aviso_mm = %s
                  where funcion = %s""", (minimo, aviso, funcion))


def dibujos(cx):
    return _tabla(cx, """select * from dibujos_nuevos
                         order by medida nulls last, marca nulls first,
                                  dibujo nulls first""")


def guardar_dibujo(cx, mm, medida=None, marca=None, dibujo=None, nota=None):
    """Anota con cuántos milímetros sale de fábrica una medida o una banda.

    Lo que se carga a mano vale como medido: pisa al valor típico que vino
    con el SQL. Cargar el dato real de una medida es la diferencia entre
    un costo por milímetro estimado y uno de verdad.
    """
    _exigir_instalado(cx)
    mm = float(mm)
    if mm <= 0:
        raise ValueError("El dibujo tiene que ser mayor que cero.")
    if mm > 40:
        raise ValueError("Ese dibujo no es de una cubierta. Revisá el número.")
    limpio = lambda x: (str(x).strip().upper() or None) if x else None
    cx.execute("""
        insert into dibujos_nuevos (medida, marca, dibujo, mm, origen, nota)
        values (%s,%s,%s,%s,'cargado',%s)
        on conflict (coalesce(medida,''), coalesce(marca,''), coalesce(dibujo,''))
        do update set mm = excluded.mm, origen = 'cargado', nota = excluded.nota
    """, (limpio(medida), limpio(marca), limpio(dibujo), mm,
          (str(nota).strip() or None) if nota else None))


def borrar_dibujo(cx, dibujo_id):
    _exigir_instalado(cx)
    cx.execute("delete from dibujos_nuevos where id = %s", (int(dibujo_id),))


# =====================================================================
# LA ALERTA
# =====================================================================
def alertas(cx):
    """Las gomas puestas ordenadas por urgencia, y lo que sobra en el depósito.

    El orden no es por milímetros sino por lo que falta para llegar al
    mínimo: 5 mm en un direccional aprietan más que 5 mm en un eje de
    arrastre, porque el direccional se baja a los 4.
    """
    montadas = _tabla(cx, """
        select * from v_alertas_cubiertas
        order by case alerta when 'al_limite' then 0 when 'cerca' then 1
                             when 'sin_medir' then 2 else 3 end,
                 (remanente_mm - minimo_mm) nulls last,
                 km_restantes nulls last
    """)
    depos = _tabla(cx, "select * from v_stock_gastado order by remanente_mm, codigo")

    resumen = {"al_limite": 0, "cerca": 0, "sin_medir": 0, "ok": 0,
               "stock_gastado": len(depos)}
    for fila in montadas:
        resumen[fila["alerta"]] = resumen.get(fila["alerta"], 0) + 1
    return {"montadas": montadas, "stock_gastado": depos, "resumen": resumen}


def resumen(cx):
    """Los dos números que van a la portada."""
    if not instalado(cx):
        return None
    fila = cx.execute("""
        select count(*) filter (where alerta = 'al_limite')::int as al_limite,
               count(*) filter (where alerta = 'cerca')::int     as cerca,
               count(*) filter (where alerta = 'sin_medir')::int as sin_medir,
               min(km_restantes) filter (where alerta = 'cerca') as km_del_mas_urgente
        from v_alertas_cubiertas
    """).fetchone()
    return dict(fila) if fila else None


# =====================================================================
# EL RENDIMIENTO
# =====================================================================
def rendimiento(cx):
    """Lo que hay que mirar para decidir a quién comprarle.

    Las filas de marca salen ordenadas por kilómetros por milímetro, que
    es lo que compara gomas sin que el precio ensucie la comparación: una
    goma barata que rinde la mitad no es barata.

    Aparte va el detalle vida por vida y, sobre todo, qué falta para que
    la cuenta cierre. Un tablero que muestra doce cubiertas de ciento diez
    sin decir por qué es un tablero que engaña.
    """
    marcas = _tabla(cx, """
        select * from v_rendimiento_marcas
        order by km_por_mm desc nulls last, km desc nulls last
    """)
    vidas = _tabla(cx, """
        select * from v_rendimiento_cubiertas
        order by confiable desc, km_por_mm desc nulls last, codigo
    """)

    # Por qué una vida no entra en la comparación. Es lo primero que hay
    # que poder contestar cuando el ranking tiene tres filas.
    faltantes = {"sin_dibujo_inicial": 0, "sin_medicion": 0,
                 "sin_kilometros": 0, "poco_uso": 0, "listas": 0}
    estimadas = 0
    for v in vidas:
        if v["confiable"]:
            faltantes["listas"] += 1
        elif v["inicial_mm"] is None:
            faltantes["sin_dibujo_inicial"] += 1
        elif v["remanente_mm"] is None:
            faltantes["sin_medicion"] += 1
        elif v["km"] is None:
            faltantes["sin_kilometros"] += 1
        else:
            faltantes["poco_uso"] += 1
        if v["inicial_origen"] == "tipico":
            estimadas += 1

    return {"marcas": marcas, "vidas": vidas, "faltantes": faltantes,
            # Cuántas de las que se muestran se apoyan en un dibujo
            # inicial estimado y no medido. El número se muestra: la
            # cuenta se hace igual, pero se sabe sobre qué se apoya.
            "vidas_con_dibujo_estimado": estimadas,
            "criterios": criterios(cx)}


def vidas_de(cx, cubierta_id):
    """Las vidas de una cubierta, de la más nueva a la más vieja."""
    return _tabla(cx, """
        select * from v_rendimiento_cubiertas
        where cubierta_id = %s order by numero desc
    """, (int(cubierta_id),))


# =====================================================================
# ABRIR Y CERRAR VIDAS
# =====================================================================
def vida_abierta(cx, cubierta_id):
    return cx.execute("""select * from vidas_cubierta
                         where cubierta_id = %s and hasta is null""",
                      (cubierta_id,)).fetchone()


def abrir_vida(cx, cubierta_id, numero=0, tipo="original", **datos):
    """Le abre la vida a una cubierta recién dada de alta."""
    return cx.execute("""
        insert into vidas_cubierta (cubierta_id, numero, tipo, marca, banda,
                                    proveedor, inicial_mm, costo, desde, nota)
        values (%s,%s,%s,%s,%s,%s,%s,%s, coalesce(%s, current_date), %s)
        on conflict do nothing
        returning id
    """, (cubierta_id, numero, tipo, datos.get("marca"), datos.get("banda"),
          datos.get("proveedor"), datos.get("inicial_mm"), datos.get("costo"),
          datos.get("desde"), datos.get("nota"))).fetchone()


def cerrar_vida(cx, cubierta_id, motivo):
    """Cierra la vida que corre. Devuelve el número que tenía, o None."""
    fila = cx.execute("""
        update vidas_cubierta v
           set hasta = current_date, motivo_fin = %s,
               -- Con cuánto dibujo terminó, tomado ahora: en un rato la
               -- goma va a tener el de la banda nueva.
               remanente_fin_mm = c.remanente_mm
          from cubiertas c
         where c.id = v.cubierta_id and v.cubierta_id = %s and v.hasta is null
        returning v.numero""", (motivo, cubierta_id)).fetchone()
    return fila["numero"] if fila else None


def recapar(cx, cubierta_id, marca=None, banda=None, proveedor=None,
            costo=None, inicial_mm=None, usuario=None, nota=None):
    """Registra que una cubierta volvió del recapador con banda nueva.

    Es el momento en que empieza una vida: se cierra la anterior con todo
    lo que acumuló y se abre la siguiente, con la banda que le pusieron y
    lo que salió. De acá sale la comparación entre bandas.

    Si se sabe con cuántos milímetros vino, se anota como medición: es el
    punto de partida contra el que se va a medir el desgaste.
    """
    _exigir_instalado(cx)
    cubierta = cx.execute("select * from cubiertas where id = %s",
                          (cubierta_id,)).fetchone()
    if not cubierta:
        raise ValueError("La cubierta no existe.")
    montada = cx.execute("""select 1 from montajes
                            where cubierta_id = %s and hasta is null""",
                         (cubierta_id,)).fetchone()
    if montada:
        raise ValueError("La cubierta está montada. Registrá primero el desmontaje.")

    if costo not in (None, ""):
        costo = float(costo)
        if costo < 0:
            raise ValueError("El costo no puede ser negativo.")
    else:
        costo = None
    if inicial_mm not in (None, ""):
        inicial_mm = float(inicial_mm)
        if not 0 < inicial_mm <= 40:
            raise ValueError("Ese dibujo no es de una cubierta. Revisá el número.")
    else:
        inicial_mm = None

    limpio = lambda x: (str(x).strip().upper() or None) if x else None
    marca, banda, proveedor = limpio(marca), limpio(banda), limpio(proveedor)

    anterior = cerrar_vida(cx, cubierta_id, "recapado")
    numero = (anterior if anterior is not None else cubierta["recapados"] or 0) + 1

    abrir_vida(cx, cubierta_id, numero=numero, tipo="recapado",
               marca=marca, banda=banda, proveedor=proveedor,
               inicial_mm=inicial_mm, costo=costo, nota=nota)

    # La goma vuelve al depósito con dibujo nuevo. El contador de
    # recapados queda igual al número de vida: son la misma cuenta.
    cx.execute("""
        update cubiertas set estado = 'stock', recapados = %s,
               remanente_mm = coalesce(%s, remanente_mm),
               fecha_baja = null, motivo_baja = null
        where id = %s""", (numero, inicial_mm, cubierta_id))

    if inicial_mm is not None:
        cx.execute("""insert into mediciones (cubierta_id, remanente_mm, usuario)
                      values (%s,%s,%s)""", (cubierta_id, inicial_mm, usuario))

    detalle = " · ".join(x for x in (
        f"recapado {numero}",
        f"banda {marca or ''} {banda or ''}".strip() if (marca or banda) else "",
        f"en {proveedor}" if proveedor else "",
        nota or "") if x)
    cx.execute("""
        insert into movimientos (tipo, cubierta_id, remanente_mm, usuario, nota)
        values ('recapado', %s, %s, %s, %s)""",
        (cubierta_id, inicial_mm, usuario, detalle))
    return numero
