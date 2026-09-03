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
import re

GESTORES = {"admin", "encargado"}

# Los campos que la pantalla puede tocar. Todo lo que no esté acá se ignora,
# así un JSON de más no llega nunca a la consulta.
CAMPOS = ("interno", "tipo", "marca", "modelo", "chasis", "chofer", "semi",
          "sucursal", "uso", "nota", "activa")


def _exigir_gestor(usuario):
    if (usuario or {}).get("rol") not in GESTORES:
        raise PermissionError("Solo un encargado o administrador puede tocar el maestro de unidades.")


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
