"""
El maestro de unidades: alta, cambio y baja.

De acá sale la información de un vehículo para todo el sistema. La patente
se guarda normalizada —sin espacios ni guiones, AD247MQ— porque es la
forma en que la manda el satelital y la que escribe el gomero; para
mostrarla, `base.fmtPat` la vuelve a separar.

Los equipos que no tienen patente (autoelevadores, apiladores) van en la
misma tabla con su código en el lugar de la patente y `tipo = 'equipo'`.
Están en el mismo listado que en la planilla, y así se mantiene.
"""
import os
import re

AQUI = os.path.dirname(os.path.abspath(__file__))

GESTORES = {"admin", "encargado"}

# Los campos que la pantalla puede tocar. Todo lo que no esté acá se ignora,
# así un JSON de más no llega nunca a la consulta.
CAMPOS = ("interno", "tipo", "marca", "modelo", "chasis", "chofer", "semi",
          "sucursal", "uso", "nota", "activa", "modelo_3d")


def _exigir_gestor(usuario, que="tocar el maestro de unidades"):
    if (usuario or {}).get("rol") not in GESTORES:
        raise PermissionError(f"Solo un encargado o administrador puede {que}.")


def normalizar(patente):
    """AD 247 MQ, ad-247-mq y AD247MQ son la misma patente."""
    return "".join(ch for ch in str(patente or "").upper() if ch.isalnum())


def es_patente(texto):
    """AA123BB o ABC123. Lo que no entra acá es un código de equipo."""
    n = normalizar(texto)
    return bool(re.fullmatch(r"[A-Z]{2}\d{3}[A-Z]{2}", n) or re.fullmatch(r"[A-Z]{3}\d{3}", n))


def _texto(valor, limite=120):
    t = " ".join(str(valor or "").split())
    return t[:limite] or None


# =====================================================================
# LECTURA
# =====================================================================
def listar(cx):
    """Todo el maestro, más las listas que la pantalla usa en los selectores."""
    filas = cx.execute("""
        select * from v_unidades
        -- Los equipos al final: son pocos y no se miran todos los días.
        order by tipo, coalesce(nullif(interno,'')::text, 'zzz'), patente
    """).fetchall()

    # Los valores de sucursal y uso salen de lo que ya está cargado, no de
    # una lista fija: si mañana abren una sucursal, aparece sola.
    def distintos(campo):
        return [r[campo] for r in cx.execute(
            f"select distinct {campo} from unidades "
            f"where coalesce({campo},'') <> '' order by {campo}").fetchall()]

    return {
        "unidades": filas,
        "sucursales": distintos("sucursal"),
        "usos": distintos("uso"),
        "configuraciones": cx.execute(
            "select id, nombre from configuraciones order by nombre").fetchall(),
        "revisar": cx.execute("select * from v_unidades_a_revisar").fetchall(),
    }


# Los modelos 3D que hay. Se eligen por la cantidad de ejes, no por la
# marca: un tractor de tres ejes se parece más a otro de tres ejes que a
# uno de dos de la misma marca, y lo que importa acá es dónde están las
# ruedas.
MODELOS_3D = (
    ("6x2", "Tractor 6x2 / 6x4"),
    ("4x2", "Tractor 4x2"),
)
# Los nombres que se usaron antes, por si alguna unidad quedó con uno
# elegido a mano.
ALIAS_3D = {"hiway": "4x2", "sway": "6x2"}

# En el código de Iveco, el número de tres cifras antes de la S es el peso
# bruto combinado en toneladas por diez: 490S44 son 49 toneladas, 600S44
# son 60. Sesenta toneladas no las lleva un chasis de dos ejes.
_TRES_EJES_DESDE = 560


def ejes_de(unidad):
    """Cuántos ejes tiene, y de dónde salió el dato.

    Devuelve (ejes, por_qué). El `por_qué` importa: un dato deducido del
    nombre del modelo no vale lo mismo que el mapa de cubiertas ya cargado,
    y la pantalla tiene que poder decirlo.
    """
    import re

    # 1. El mapa de cubiertas, si está asignado. Es el dato duro: S-D-D son
    #    tres ejes porque alguien los contó.
    mapa = (unidad.get("configuracion") or "").upper()
    if mapa and re.fullmatch(r"[SD](-[SD])*", mapa):
        return mapa.count("-") + 1, "mapa"

    texto = f"{unidad.get('marca') or ''} {unidad.get('modelo') or ''}".upper()

    # 2. Lo que diga el modelo, cuando lo dice.
    if re.search(r"6\s*X\s*[24]", texto):
        return 3, "modelo"
    if re.search(r"4\s*X\s*2", texto):
        return 2, "modelo"

    # 3. La nomenclatura de Iveco.
    m = re.search(r"(\d{3})\s*S\d", texto)
    if m:
        return (3 if int(m[1]) >= _TRES_EJES_DESDE else 2), "codigo"

    return 0, "no se sabe"


def modelo_3d(unidad):
    """Qué camión se dibuja. Lo elegido a mano gana; si no, se deduce.

    Deducir es lo que hace que ande sin cargar nada: son 68 unidades y
    nadie va a elegir el 3D de una por una. Cuando la deducción no acierta,
    se fuerza desde la pantalla y esto no se mete.
    """
    elegido = (unidad.get("modelo_3d") or "").strip().lower()
    elegido = ALIAS_3D.get(elegido, elegido)
    if elegido:
        return elegido if elegido in {m[0] for m in MODELOS_3D} else None
    if unidad.get("tipo") != "vehiculo":
        return None

    ejes, _ = ejes_de(unidad)
    if ejes >= 3:
        return "6x2"
    if ejes == 2:
        return "4x2"
    # Sin ningún dato: se dibuja el de dos ejes, que es el más común en la
    # flota, y desde la ficha se corrige si no era.
    return "4x2" if (unidad.get("uso") or "").upper() == "LARGA DISTANCIA" else None


def _archivo_3d(clave):
    """El archivo del modelo, sea .obj o .fbx. None si no está ninguno.

    Se aceptan los dos porque los modelos se consiguen casi siempre en FBX
    y convertirlos es un paso más que se puede saltear.
    """
    if not clave:
        return None
    for ext in (".obj", ".fbx"):
        nombre = f"iveco-{clave}{ext}"
        if os.path.isfile(os.path.join(AQUI, os.pardir, "modelos", nombre)):
            return nombre
    return None


def _bloque(cx, consulta, valores=()):
    """Un pedazo de la ficha. Si su módulo todavía no está, viene vacío.

    Los módulos se prenden de a uno: hasta que no esté corrido todo el SQL
    va a haber tablas que no existen. Que falte una apaga su bloque, no la
    ficha entera.
    """
    try:
        return cx.execute(consulta, valores).fetchall()
    except Exception:
        cx.rollback()
        return []


def ficha(cx, unidad_id):
    """Todo lo que el sistema sabe de una unidad, junto.

    Es lo que se ve al abrir una unidad en Flota: los datos del maestro más
    las cubiertas que tiene puestas, sus documentos, lo que viene rodando y
    el semi que arrastra. Cada cosa vive en su módulo; acá se juntan.
    """
    unidad = una(cx, unidad_id)
    if not unidad:
        return None

    # El modelo que le tocaría, y si el archivo está o falta. Del S-Way
    # todavía no llegó el .obj: la unidad se deduce igual y la pantalla
    # avisa qué falta, en vez de tirar un 404 sin explicación.
    quiere = modelo_3d(unidad)
    archivo = _archivo_3d(quiere)
    ejes, por = ejes_de(unidad)
    salida = {"unidad": unidad,
              "modelo_3d": quiere if archivo else None,
              "modelo_3d_archivo": archivo,
              "modelo_3d_falta": None if archivo else quiere,
              "modelo_3d_ejes": ejes,
              # De dónde salió: 'mano' si alguien lo eligió, y si no de qué
              # se dedujo. Un dato deducido del nombre del modelo no vale lo
              # mismo que el mapa de cubiertas ya cargado.
              "modelo_3d_por": "mano" if (unidad.get("modelo_3d") or "").strip() else por}

    # El mapa entero, con posiciones vacías incluidas: el 3D las necesita
    # para saber qué se puede montar dónde.
    salida["mapa"] = posiciones(cx, unidad_id)

    # Las cubiertas puestas, en el orden en que se dibuja el mapa.
    salida["cubiertas"] = _bloque(cx, """
        select posicion, eje, lado, es_auxilio, cubierta, marca, medida,
               remanente_mm, recapados, montada_desde
        from v_mapa_unidad
        where unidad_id = %s and cubierta_id is not null
        order by orden""", (unidad_id,))

    # Los documentos de la unidad y los del chofer que la maneja: al que
    # sale a la ruta lo paran por los dos.
    salida["documentos"] = _bloque(cx, """
        select tipo, ambito, identificador, vence, dias, estado, donde, persona
        from v_vencimientos_hoy
        where unidad_id = %s
        order by vence""", (unidad_id,))

    # Lo que rodó en los últimos 30 días, con la misma cuenta que la
    # portada: última lectura menos primera, que aguanta que falte un día.
    recorrido = _bloque(cx, """
        select max(km) - min(km) as km,
               count(distinct fecha)::int as dias,
               min(fecha) as desde, max(fecha) as hasta
        from odometros
        where unidad_id = %s and fecha >= current_date - 31""", (unidad_id,))
    salida["recorrido"] = recorrido[0] if recorrido else None

    salida["lecturas"] = _bloque(cx, """
        select fecha, km from odometros
        where unidad_id = %s order by fecha desc limit 10""", (unidad_id,))

    # El semi es texto: puede o no estar cargado como unidad. Si está, se
    # devuelve su id para poder saltar; si no, queda la patente sola.
    salida["semi_unidad"] = None
    if unidad.get("semi"):
        fila = _bloque(cx, """
            select id, patente, marca, modelo, configuracion_id
            from unidades where patente = %s""", (unidad["semi"],))
        salida["semi_unidad"] = fila[0] if fila else None

    return salida


def una(cx, unidad_id):
    return cx.execute("select * from v_unidades where id = %s", (unidad_id,)).fetchone()


# =====================================================================
# ESCRITURA
# =====================================================================
def _limpiar(datos):
    """Deja los campos como van a la base, sin decidir todavía qué se hace."""
    limpio = {}
    for campo in CAMPOS:
        if campo not in datos:
            continue
        valor = datos[campo]
        if campo == "activa":
            limpio[campo] = bool(valor)
        elif campo == "tipo":
            limpio[campo] = "equipo" if str(valor).strip().lower() == "equipo" else "vehiculo"
        elif campo == "semi":
            # El semi se guarda normalizado como cualquier patente, para que
            # cruzarlo con la tabla no dependa de cómo lo escribieron.
            limpio[campo] = normalizar(valor) or None
        elif campo in ("sucursal", "uso"):
            limpio[campo] = (_texto(valor, 40) or "").upper() or None
        elif campo in ("marca", "chofer"):
            limpio[campo] = (_texto(valor) or "").upper() or None
        else:
            limpio[campo] = _texto(valor, 200)
    return limpio


def guardar(cx, datos, usuario=None):
    """Da de alta una unidad o cambia la que ya está. Devuelve la unidad."""
    _exigir_gestor(usuario)

    patente = normalizar(datos.get("patente"))
    unidad_id = datos.get("id")

    if not unidad_id and not patente:
        raise ValueError("Falta la patente, o el código si es un equipo.")

    campos = _limpiar(datos)

    # El tipo no se pide: se deduce de la patente, salvo que lo manden.
    if "tipo" not in campos and patente:
        campos["tipo"] = "vehiculo" if es_patente(patente) else "equipo"

    if unidad_id:
        # Cambiar la patente está permitido —se cargan mal seguido— pero no
        # puede chocar con otra unidad.
        if patente:
            ya = cx.execute("select id from unidades where patente = %s and id <> %s",
                            (patente, unidad_id)).fetchone()
            if ya:
                raise ValueError(f"{base_fmt(patente)} ya está cargada en otra unidad.")
            campos["patente"] = patente
        if not campos:
            return una(cx, unidad_id)
        sets = ", ".join(f"{c} = %s" for c in campos)
        cx.execute(f"update unidades set {sets} where id = %s",
                   list(campos.values()) + [unidad_id])
        return una(cx, unidad_id)

    ya = cx.execute("select id from unidades where patente = %s", (patente,)).fetchone()
    if ya:
        raise ValueError(f"{base_fmt(patente)} ya está cargada.")

    campos["patente"] = patente
    columnas = ", ".join(campos)
    huecos = ", ".join(["%s"] * len(campos))
    fila = cx.execute(f"insert into unidades ({columnas}) values ({huecos}) returning id",
                      list(campos.values())).fetchone()
    return una(cx, fila["id"])


def eliminar(cx, unidad_id, usuario=None):
    """Borra la unidad, si no tiene historia colgando.

    Una unidad con cubiertas montadas, lecturas del satelital o documentos
    no se borra: borrarla dejaría huérfano todo eso. En ese caso se la da
    de baja, que es lo que en la práctica se quiere decir con "sacarla".
    """
    _exigir_gestor(usuario)

    unidad = una(cx, unidad_id)
    if not unidad:
        raise ValueError("Esa unidad no existe.")

    ligada = []
    for tabla, nombre in (("montajes", "movimientos de cubiertas"),
                          ("odometros", "lecturas del satelital"),
                          ("vencimientos", "documentos")):
        try:
            n = cx.execute(f"select count(*) as n from {tabla} where unidad_id = %s",
                           (unidad_id,)).fetchone()["n"]
        except Exception:
            # La tabla puede no existir todavía: ese módulo no ata nada.
            cx.rollback()
            continue
        if n:
            ligada.append(f"{n} {nombre}")

    if ligada:
        cx.execute("update unidades set activa = false where id = %s", (unidad_id,))
        return {"baja": True, "unidad": una(cx, unidad_id),
                "aviso": ("No se puede borrar porque tiene " + " y ".join(ligada) +
                          ". Se la dio de baja: deja de contar en los tableros "
                          "pero la historia queda.")}

    cx.execute("delete from unidades where id = %s", (unidad_id,))
    return {"baja": False, "borrada": unidad["patente"]}


def base_fmt(patente):
    """AD247MQ -> AD 247 MQ. Repetido acá para no arrastrar base.py entero."""
    m = re.fullmatch(r"([A-Z]{2})(\d{3})([A-Z]{2})", patente or "")
    if m:
        return f"{m[1]} {m[2]} {m[3]}"
    o = re.fullmatch(r"([A-Z]{3})(\d{3})", patente or "")
    return f"{o[1]} {o[2]}" if o else (patente or "")


def para_tablero(cx):
    """El maestro con la forma en que lo leían los tableros de flota.

    Los paneles venían sacando el maestro de la planilla de Google. Ahora lo
    piden acá, pero se les devuelve exactamente la misma forma —incluida la
    patente separada, AD 247 MQ— para que no cambie nada de cómo la
    interpretan. Solo vehículos activos: los equipos no tienen service ni
    telemetría y entraban al tablero como unidades sin datos.
    """
    filas = cx.execute("""
        select patente, interno, marca, modelo, chofer, semi, sucursal, uso
        from unidades
        where activa and tipo = 'vehiculo'
        order by patente""").fetchall()
    for f in filas:
        f["patente"] = base_fmt(f["patente"])
        f["semi"] = base_fmt(f["semi"]) if f["semi"] else ""
        for campo in list(f):
            f[campo] = f[campo] or ""
    return filas


# =====================================================================
# LAS CUBIERTAS, DESDE EL 3D
# ---------------------------------------------------------------------
# El gomero toca una rueda en el modelo y cambia la cubierta ahí mismo.
# Es la misma operación que hace el parte escrito, pero sin texto: acá ya
# se sabe la unidad y la posición, así que no hay nada que interpretar.
# =====================================================================
def posiciones(cx, unidad_id):
    """El mapa de la unidad: cada lugar donde entra una cubierta y qué tiene."""
    return _bloque(cx, """
        select posicion_id, posicion, eje, lado, montaje, es_auxilio, orden,
               cubierta_id, cubierta, marca, medida, remanente_mm, recapados,
               montada_desde
        from v_mapa_unidad where unidad_id = %s order by orden""", (unidad_id,))


def mover_cubierta(cx, datos, usuario=None):
    """Monta o desmonta en una posición. Devuelve el mapa ya actualizado."""
    import base as _base

    _exigir_gestor(usuario, "cambiar cubiertas")

    unidad_id = datos.get("unidad_id")
    posicion_id = datos.get("posicion_id")
    accion = (datos.get("accion") or "").strip().lower()
    if not unidad_id or not posicion_id:
        raise ValueError("Falta la unidad o la posición.")

    unidad = cx.execute("select * from unidades where id = %s", (unidad_id,)).fetchone()
    if not unidad:
        raise ValueError("Esa unidad no existe.")

    # La posición tiene que ser del mapa de esta unidad. Sin esto, un id
    # suelto podría montar una cubierta en el mapa de otro camión.
    de_esta = cx.execute("""
        select 1 from configuracion_posiciones
        where id = %s and configuracion_id = %s""",
        (posicion_id, unidad["configuracion_id"])).fetchone()
    if not de_esta:
        raise ValueError("Esa posición no es de esta unidad.")

    quien = (usuario or {}).get("nombre")

    if accion == "desmontar":
        # A dónde va la que sale lo decide el gomero: al stock si sirve, a
        # recapar si está gastada, a baja si no da para más.
        destino = (datos.get("destino") or "stock").strip().lower()
        if destino not in ("stock", "recapado", "reparacion", "baja"):
            raise ValueError("La cubierta que sale tiene que ir a stock, recapado, reparación o baja.")
        puesta = _base.montaje_abierto(cx, unidad_id, posicion_id)
        if not puesta:
            raise ValueError("Esa posición ya estaba vacía.")
        _base.sacar_de_servicio(cx, puesta["cubierta_id"], destino=destino,
                                unidad_id=unidad_id, posicion_id=posicion_id,
                                usuario=quien, nota=_texto(datos.get("nota"), 300))
        cx.execute("""update montajes set hasta = now()
                      where unidad_id = %s and posicion_id = %s and hasta is null""",
                   (unidad_id, posicion_id))

    elif accion == "montar":
        cubierta_id = datos.get("cubierta_id")
        if not cubierta_id:
            raise ValueError("Elegí qué cubierta va.")
        cubierta = cx.execute("select * from cubiertas where id = %s",
                              (cubierta_id,)).fetchone()
        if not cubierta:
            raise ValueError("Esa cubierta no existe.")
        # Una cubierta puesta en otra unidad no se puede poner acá sin
        # sacarla antes: quedaría en dos lugares a la vez.
        otra = cx.execute("""
            select u.patente, p.codigo from montajes m
            join unidades u on u.id = m.unidad_id
            join configuracion_posiciones p on p.id = m.posicion_id
            where m.cubierta_id = %s and m.hasta is null""", (cubierta_id,)).fetchone()
        if otra:
            raise ValueError(f"La {cubierta['codigo']} está puesta en "
                             f"{base_fmt(otra['patente'])}, posición {otra['codigo']}. "
                             f"Sacala de ahí primero.")
        _base.montar(cx, unidad_id, posicion_id, cubierta_id,
                     usuario=quien, nota=_texto(datos.get("nota"), 300))
    else:
        raise ValueError("La acción tiene que ser montar o desmontar.")

    return {"mapa": posiciones(cx, unidad_id)}


def stock_para(cx, medida=None, limite=200):
    """Las cubiertas que se pueden poner: en stock o recapadas, y libres.

    El estado no alcanza para saber si está libre. Los mapas se cargaron a
    mano y hay cubiertas marcadas 'stock' que en realidad están puestas: lo
    que manda es si tienen un montaje abierto.
    """
    # El filtro por medida se arma o no se arma. Mandarlo como "%s is null"
    # no anda: psycopg no puede deducir el tipo de un parámetro que solo
    # aparece en una comparación con null.
    filtro, valores = "", []
    if medida:
        filtro = "and c.medida = %s"
        valores.append(medida)
    valores.append(limite)
    return _bloque(cx, f"""
        select c.id, c.codigo, c.marca, c.modelo, c.medida, c.remanente_mm,
               c.recapados, c.estado
        from cubiertas c
        where c.estado in ('stock','recapado')
          and not exists (select 1 from montajes m
                           where m.cubierta_id = c.id and m.hasta is null)
          {filtro}
        order by c.medida, c.codigo limit %s""", valores)
