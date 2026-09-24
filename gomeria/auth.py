"""
Usuarios, contraseñas y sesiones.

La contraseña nunca se guarda: se guarda el resultado de pasarla por scrypt
con una sal distinta para cada uno. Aunque alguien se lleve la tabla entera,
no puede volver a las contraseñas.

Al entrar se crea una sesión con un token al azar que viaja en una cookie.
El celular no guarda la contraseña, solo ese token, y se puede cortar
borrando la fila.
"""
import base64, hashlib, hmac, os, re, secrets, struct, threading, time
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie

import permisos

DIAS_SESION = 30           # el gomero no debería tener que entrar todos los días
# Quien administra entra de nuevo cada jornada. Se cambia con la variable
# de entorno HORAS_SESION_ADMIN.
HORAS_SESION_ADMIN = int(os.environ.get("HORAS_SESION_ADMIN") or 12)
COOKIE = "sesion"

# Parámetros de scrypt. n más alto = más lento de calcular = más caro de
# atacar. 2**14 tarda milésimas en un servidor y años en una fuerza bruta.
_N, _R, _P = 2 ** 14, 8, 1


# =====================================================================
# CONTRASEÑAS
# =====================================================================
def hashear(clave):
    sal = os.urandom(16)
    dk = hashlib.scrypt(clave.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${dk.hex()}"


def verificar(clave, guardado):
    try:
        etiqueta, n, r, p, sal, esperado = guardado.split("$")
        if etiqueta != "scrypt":
            return False
        dk = hashlib.scrypt(clave.encode(), salt=bytes.fromhex(sal),
                            n=int(n), r=int(r), p=int(p), dklen=len(esperado) // 2)
        # compare_digest y no ==: comparar de a un byte filtra información
        # sobre cuánto acertó quien lo intenta.
        return hmac.compare_digest(dk.hex(), esperado)
    except (ValueError, AttributeError):
        return False


def revisar_clave(clave):
    """Devuelve el problema de la contraseña, o None si está bien."""
    if len(clave) < 8:
        return "La contraseña tiene que tener al menos 8 caracteres."
    if clave.isdigit():
        return "No uses solo números."
    if clave.lower() in ("12345678", "contraseña", "password", "diemar123"):
        return "Esa contraseña es muy fácil de adivinar."
    return None


# =====================================================================
# USUARIOS
# =====================================================================
def crear_usuario(cx, usuario, nombre, clave, rol="operario"):
    problema = revisar_clave(clave)
    if problema:
        raise ValueError(problema)
    return cx.execute("""
        insert into usuarios (usuario, nombre, hash, rol)
        values (%s,%s,%s,%s) returning id""",
        (usuario.strip().lower(), nombre.strip(), hashear(clave), rol)).fetchone()["id"]


def cambiar_clave(cx, usuario_id, clave):
    problema = revisar_clave(clave)
    if problema:
        raise ValueError(problema)
    cx.execute("update usuarios set hash = %s where id = %s", (hashear(clave), usuario_id))
    # Cambiar la contraseña corta las sesiones abiertas: es lo que se espera
    # cuando alguien la cambia porque se la vieron.
    cx.execute("delete from sesiones where usuario_id = %s", (usuario_id,))


def autenticar(cx, usuario, clave):
    """Devuelve el usuario si coincide, None si no. No dice cuál de las dos falló."""
    fila = cx.execute("select * from usuarios where usuario = %s and activo",
                      (str(usuario).strip().lower(),)).fetchone()
    if not fila or not verificar(clave, fila["hash"]):
        return None
    return fila


# =====================================================================
# SESIONES
# =====================================================================
def _h(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _hash_viejo(token):
    """True si el token parece de antes de guardar hashes.

    Los tokens miden 43 caracteres; sus hashes, 64 hexadecimales. Una
    cookie que trae 64 hexadecimales nunca se busca tal cual: si no, quien
    se llevara la tabla podría presentar el hash como si fuera el token.
    """
    return not re.fullmatch(r"[0-9a-f]{64}", token)


def duracion_sesion(cx, usuario):
    """Segundos que dura la sesión de ese usuario.

    La del gomero dura un mes: entra desde el celular del taller y no
    administra nada. La de quien administra dura una jornada: una sesión
    abierta de administrador en una máquina ajena es la llave de todo.
    """
    if permisos.administra(permisos.con_permisos(cx, usuario)):
        return HORAS_SESION_ADMIN * 3600
    return DIAS_SESION * 86400


def abrir_sesion(cx, usuario_id, agente=None, con_2fa=False, segundos=None):
    """Abre la sesión y devuelve el token para la cookie.

    En la base queda el hash del token, no el token: quien lea la tabla
    (un backup que se filtra, un acceso de más) no puede usar las
    sesiones abiertas.
    """
    token = secrets.token_urlsafe(32)
    expira = datetime.now(timezone.utc) + timedelta(seconds=segundos or DIAS_SESION * 86400)
    if hay_seguridad(cx):
        cx.execute("""insert into sesiones (token, usuario_id, expira, agente, con_2fa)
                      values (%s,%s,%s,%s,%s)""",
                   (_h(token), usuario_id, expira, (agente or "")[:200], bool(con_2fa)))
    else:
        cx.execute("""insert into sesiones (token, usuario_id, expira, agente)
                      values (%s,%s,%s,%s)""", (_h(token), usuario_id, expira, (agente or "")[:200]))
    cx.execute("update usuarios set ultimo_ingreso = now() where id = %s", (usuario_id,))
    return token


# Lo que viaja en la fila del usuario y no tiene que salir de este módulo.
_SECRETOS = ("hash", "totp_secreto", "totp_respaldo", "totp_ultimo", "sesion_con_2fa",
             "sesion_creada", "sesion_token")


def usuario_de_sesion(cx, token):
    """Quién está de este lado, con lo que su rol le permite.

    Los permisos se cuelgan acá y no en cada pantalla: es el único lugar
    por el que pasan todos los pedidos, así que es donde no se puede
    olvidar. Ver permisos.py.

    La sesión de alguien que administra no vale si no pasó por el segundo
    factor (es la de antes de correr 35_seguridad.sql, o la de alguien que
    ascendieron a administrador después de entrar), ni si tiene más de
    HORAS_SESION_ADMIN horas.
    """
    if not token:
        return None
    seguridad = hay_seguridad(cx)
    fila = cx.execute(f"""
        select u.*, s.creado as sesion_creada, s.token as sesion_token
               {", s.con_2fa as sesion_con_2fa" if seguridad else ""}
        from sesiones s
        join usuarios u on u.id = s.usuario_id
        where (s.token = %s or (s.token = %s and %s))
          and s.expira > now() and u.activo""",
        (_h(token), token, _hash_viejo(token))).fetchone()
    if not fila:
        return None
    usuario = permisos.con_permisos(cx, fila)
    if permisos.administra(usuario):
        if seguridad and not usuario.get("sesion_con_2fa"):
            return None
        creada = usuario["sesion_creada"]
        if creada.tzinfo is None:
            creada = creada.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - creada > timedelta(hours=HORAS_SESION_ADMIN):
            cx.execute("delete from sesiones where token = %s", (usuario["sesion_token"],))
            return None
    if usuario["sesion_token"] == token:
        # Una sesión de antes de guardar hashes: se pasa a hash la primera
        # vez que se usa, y el que la tiene no se entera.
        cx.execute("update sesiones set token = %s, ultimo_uso = now() where token = %s",
                   (_h(token), token))
    else:
        cx.execute("update sesiones set ultimo_uso = now() where token = %s", (_h(token),))
    for k in _SECRETOS:
        usuario.pop(k, None)
    return usuario


def cerrar_sesion(cx, token):
    if token:
        cx.execute("delete from sesiones where token = %s or (token = %s and %s)",
                   (_h(token), token, _hash_viejo(token)))


def limpiar_vencidas(cx):
    cx.execute("delete from sesiones where expira < now()")
    if hay_seguridad(cx):
        cx.execute("delete from desafios_2fa where expira < now()")
        cx.execute("delete from intentos_login where creado < now() - interval '1 day'")


def token_de_cookie(cabecera, nombre=COOKIE):
    if not cabecera:
        return None
    try:
        c = SimpleCookie()
        c.load(cabecera)
        return c[nombre].value if nombre in c else None
    except Exception:
        return None


def cookie_de_sesion(token, borrar=False, seguro=False, segundos=None):
    """Armá la cookie.

    HttpOnly para que ningún script de la página la lea. Secure cuando la
    conexión es https: sin eso, la cookie viajaría también por http y
    cualquiera en la misma red podría copiarla.
    """
    extra = "; Secure" if seguro else ""
    if borrar:
        return f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax{extra}"
    return (f"{COOKIE}={token}; Path=/; Max-Age={segundos or DIAS_SESION * 86400}; "
            f"HttpOnly; SameSite=Lax{extra}")


# =====================================================================
# ¿ESTÁ CORRIDO 35_seguridad.sql?
# =====================================================================
_SEGURIDAD = False


def hay_seguridad(cx):
    """True si la base ya tiene las tablas del freno y del segundo factor.

    Sin ellas la app anda como antes: los intentos se cuentan en memoria y
    nadie pide segundo factor. Una migración sin correr no puede dejar a
    todos afuera. Una vez que aparecen no se vuelven a buscar.
    """
    global _SEGURIDAD
    if _SEGURIDAD:
        return True
    fila = cx.execute("""
        select to_regclass('public.intentos_login') is not null
           and to_regclass('public.desafios_2fa') is not null
           and exists (select 1 from information_schema.columns
                       where table_schema = 'public' and table_name = 'sesiones'
                         and column_name = 'con_2fa')
           and exists (select 1 from information_schema.columns
                       where table_schema = 'public' and table_name = 'usuarios'
                         and column_name = 'totp_respaldo') as ok""").fetchone()
    _SEGURIDAD = bool(fila and fila["ok"])
    return _SEGURIDAD


# =====================================================================
# FRENO A LA FUERZA BRUTA
# =====================================================================
# Se cuenta por tres lados, cada uno con su tope en la misma ventana:
#   ip:…       quien prueba muchas cuentas desde un mismo lugar;
#   usuario:…  quien prueba una cuenta desde muchos lugares;
#   2fa:…      quien ya tiene la contraseña y prueba códigos.
# Con uno solo alcanza para esquivarlo: el de la IP se burla cambiando de
# IP, y el del usuario, probando una contraseña contra cada cuenta.
VENTANA_MIN = 15
LIMITES = {"ip": 20, "usuario": 8, "2fa": 5}

# Si falta la tabla, en memoria. Se pierde al reiniciar, pero es mejor
# que nada mientras no se corre el script.
_INTENTOS = {}
_CANDADO = threading.Lock()


def clave_ip(ip):
    return "ip:" + str(ip or "?")[:64]


def clave_usuario(usuario):
    return "usuario:" + str(usuario or "").strip().lower()[:100]


def clave_2fa(usuario_id):
    return f"2fa:{usuario_id}"


def bloqueado(cx, *claves):
    """Minutos que faltan para poder intentar de nuevo; 0 si puede ya."""
    peor = 0
    ahora = time.time()
    for clave in claves:
        limite = LIMITES[clave.split(":", 1)[0]]
        if hay_seguridad(cx):
            fila = cx.execute("""
                select count(*) as n, extract(epoch from min(creado)) as desde
                from intentos_login
                where clave = %s and creado > now() - make_interval(mins => %s)""",
                (clave, VENTANA_MIN)).fetchone()
            n, desde = fila["n"], float(fila["desde"] or 0)
        else:
            with _CANDADO:
                vivos = [t for t in _INTENTOS.get(clave, ()) if t > ahora - VENTANA_MIN * 60]
            n, desde = len(vivos), min(vivos, default=0)
        if n >= limite:
            # La ventana corre: cuando el fallo más viejo sale de los
            # quince minutos, vuelve a haber lugar.
            faltan = desde + VENTANA_MIN * 60 - ahora
            peor = max(peor, int(max(faltan, 1) // 60) + 1)
    return peor


def anotar_fallo(cx, *claves):
    if hay_seguridad(cx):
        for clave in claves:
            cx.execute("insert into intentos_login (clave) values (%s)", (clave,))
        return
    ahora = time.time()
    with _CANDADO:
        if len(_INTENTOS) > 5000:
            # Que no crezca sin límite, sin vaciarlo entero: vaciarlo le
            # daría intentos nuevos a quien lo llenó a propósito.
            for k in [k for k, v in _INTENTOS.items() if max(v) < ahora - VENTANA_MIN * 60]:
                del _INTENTOS[k]
        for clave in claves:
            _INTENTOS.setdefault(clave, []).append(ahora)


def limpiar_intentos(cx, *claves):
    if hay_seguridad(cx):
        for clave in claves:
            cx.execute("delete from intentos_login where clave = %s", (clave,))
        return
    with _CANDADO:
        for clave in claves:
            _INTENTOS.pop(clave, None)


# =====================================================================
# SEGUNDO FACTOR (TOTP, RFC 6238)
# =====================================================================
# El código de seis dígitos que muestra Google Authenticator, Authy o
# 1Password. Sale de un secreto compartido y de la hora: no viaja por
# SMS ni por mail, así que no hay servicio externo que contratar ni
# mensaje que interceptar. Lo piden los roles que administran.
EMISOR = "Pengui"
PASO = 30                  # segundos que dura cada código
MARGEN = 1                 # se acepta el código anterior y el siguiente
CUANTOS_RESPALDO = 10
MIN_DESAFIO = 10
COOKIE_DESAFIO = "desafio"
_LETRAS_RESPALDO = "abcdefghjkmnpqrstuvwxyz23456789"   # sin 0/o ni 1/l/i


def pide_2fa(cx, usuario):
    """True si ese usuario tiene que pasar por el segundo factor."""
    return bool(usuario) and hay_seguridad(cx) and \
        permisos.administra(permisos.con_permisos(cx, usuario))


def totp_secreto_nuevo():
    return base64.b32encode(os.urandom(20)).decode()


def _hotp(secreto, paso):
    clave = base64.b32decode(secreto.upper() + "=" * (-len(secreto) % 8))
    h = hmac.new(clave, struct.pack(">Q", paso), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def totp_codigo(secreto, instante=None):
    return _hotp(secreto, int((time.time() if instante is None else instante) // PASO))


def totp_paso(secreto, codigo, ultimo=None, instante=None):
    """El paso al que corresponde el código, o None si no es válido.

    Un paso ya usado (o anterior al último usado) no vale: el código que
    alguien vio por encima del hombro no sirve una segunda vez.
    """
    if not secreto or not re.fullmatch(r"\d{6}", codigo or ""):
        return None
    actual = int((time.time() if instante is None else instante) // PASO)
    for paso in range(actual - MARGEN, actual + MARGEN + 1):
        if ultimo is not None and paso <= ultimo:
            continue
        if hmac.compare_digest(_hotp(secreto, paso), codigo):
            return paso
    return None


def totp_uri(secreto, usuario):
    from urllib.parse import quote
    cuenta = quote(f"{EMISOR}:{usuario}")
    return (f"otpauth://totp/{cuenta}?secret={secreto}&issuer={quote(EMISOR)}"
            f"&algorithm=SHA1&digits=6&period={PASO}")


def _hash_respaldo(codigo):
    limpio = re.sub(r"[^a-z0-9]", "", str(codigo).lower())
    return hashlib.sha256(limpio.encode()).hexdigest()


def preparar_totp(cx, fila):
    """El secreto para dar de alta el autenticador.

    Si ya había uno a medio dar de alta se reusa: recargar la página no
    tiene que dejar inservible el QR que ya se escaneó.
    """
    if fila.get("totp_secreto") and not fila.get("totp_activo"):
        return fila["totp_secreto"]
    secreto = totp_secreto_nuevo()
    cx.execute("update usuarios set totp_secreto = %s, totp_activo = false where id = %s",
               (secreto, fila["id"]))
    return secreto


def verificar_segundo_factor(cx, fila, codigo):
    """True si el código es bueno. Lo gasta: no sirve dos veces.

    Acepta el de la app o, si el autenticador ya está dado de alta, uno de
    los códigos de respaldo.
    """
    codigo = re.sub(r"\s", "", str(codigo or ""))
    paso = totp_paso(fila.get("totp_secreto"), codigo, fila.get("totp_ultimo"))
    if paso is not None:
        # El where hace de candado: dos pedidos con el mismo código al
        # mismo tiempo, solo uno actualiza la fila.
        return cx.execute("""
            update usuarios set totp_ultimo = %s
            where id = %s and (totp_ultimo is null or totp_ultimo < %s)
            returning id""", (paso, fila["id"], paso)).fetchone() is not None
    if fila.get("totp_activo") and len(re.sub(r"[^a-z0-9]", "", codigo.lower())) == 8:
        h = _hash_respaldo(codigo)
        return cx.execute("""
            update usuarios set totp_respaldo = array_remove(totp_respaldo, %s)
            where id = %s and %s = any(totp_respaldo)
            returning id""", (h, fila["id"], h)).fetchone() is not None
    return False


def activar_totp(cx, usuario_id):
    """Da por terminada el alta. Devuelve los códigos de respaldo en claro:
    es la única vez que se ven."""
    codigos = ["".join(secrets.choice(_LETRAS_RESPALDO) for _ in range(8))
               for _ in range(CUANTOS_RESPALDO)]
    codigos = [f"{c[:4]}-{c[4:]}" for c in codigos]
    cx.execute("""update usuarios set totp_activo = true, totp_respaldo = %s
                  where id = %s""", ([_hash_respaldo(c) for c in codigos], usuario_id))
    return codigos


def resetear_totp(cx, usuario_id):
    """Para el que perdió el celular: en el próximo ingreso lo da de alta de nuevo."""
    cx.execute("""update usuarios set totp_secreto = null, totp_activo = false,
                  totp_ultimo = null, totp_respaldo = '{}' where id = %s""", (usuario_id,))
    cx.execute("delete from sesiones where usuario_id = %s", (usuario_id,))
    cx.execute("delete from desafios_2fa where usuario_id = %s", (usuario_id,))


# ---------------------------------------------------------------------
# El paso intermedio: la contraseña ya está, falta el código. Se guarda el
# hash del token: quien lea la tabla no puede usarlo.
# ---------------------------------------------------------------------
def abrir_desafio(cx, usuario_id, destino="/"):
    token = secrets.token_urlsafe(32)
    cx.execute("delete from desafios_2fa where usuario_id = %s or expira < now()",
               (usuario_id,))
    cx.execute("""insert into desafios_2fa (token, usuario_id, destino, expira)
                  values (%s, %s, %s, now() + make_interval(mins => %s))""",
               (_h(token), usuario_id, destino or "/", MIN_DESAFIO))
    return token


def leer_desafio(cx, token):
    """El usuario que está a mitad de entrar, con el destino. None si venció."""
    if not token:
        return None
    return cx.execute("""
        select u.*, d.destino from desafios_2fa d
        join usuarios u on u.id = d.usuario_id
        where d.token = %s and d.expira > now() and u.activo""", (_h(token),)).fetchone()


def cerrar_desafio(cx, token):
    if token:
        cx.execute("delete from desafios_2fa where token = %s", (_h(token),))


def cookie_desafio(token, borrar=False, seguro=False):
    extra = "; Secure" if seguro else ""
    if borrar:
        return f"{COOKIE_DESAFIO}=; Path=/login; Max-Age=0; HttpOnly; SameSite=Strict{extra}"
    return (f"{COOKIE_DESAFIO}={token}; Path=/login; Max-Age={MIN_DESAFIO * 60}; "
            f"HttpOnly; SameSite=Strict{extra}")


# =====================================================================
# PRIMER USUARIO
# =====================================================================
def crear_admin_inicial(cx, spec):
    """Crea el primer admin desde una variable de entorno.

    En la nube no hay terminal para correr usuarios.py, así que el primer
    acceso entra por USUARIO_INICIAL="usuario:Nombre Completo:contraseña".
    Solo actúa si todavía no hay ningún usuario.
    """
    if cx.execute("select count(*) as n from usuarios").fetchone()["n"]:
        return None
    partes = str(spec).split(":", 2)
    if len(partes) != 3 or not all(x.strip() for x in partes):
        raise ValueError('USUARIO_INICIAL tiene que ser "usuario:Nombre Completo:contraseña"')
    usuario, nombre, clave = (x.strip() for x in partes)
    crear_usuario(cx, usuario, nombre, clave, rol="admin")
    return usuario


# =====================================================================
# PANTALLA DE INGRESO
# =====================================================================
_PAGINA = """<!DOCTYPE html><html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__TITULO__ | Pengui</title>
<link rel="icon" href="/favicon.png">
<style>
  :root{color-scheme:light;--plane:#f5f5f2;--surface-1:#fff;--surface-2:#faf9f4;
        --hairline:rgba(0,0,0,.10);--hairline-2:rgba(0,0,0,.20);
        --ink:#121212;--ink-2:#343434;--ink-muted:#666;--brand:#ffd400;--mal:#bd3038}
  *{box-sizing:border-box}
  html,body{height:100%;margin:0}
  body{font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;background:var(--plane);
       color:var(--ink);font-size:16px;display:grid;place-items:center;padding:24px}
  .caja{width:100%;max-width:380px;background:var(--surface-1);border:1px solid var(--hairline);border-radius:16px;padding:32px;box-shadow:0 18px 48px #0002}
  .marca{text-align:center;margin-bottom:26px}
  .marca img{height:104px;max-width:150px;object-fit:contain;margin-bottom:14px}
  .marca .t{font-size:11px;letter-spacing:2.4px;text-transform:uppercase;color:var(--ink-muted);font-weight:600}
  label{display:block;font-size:11.5px;letter-spacing:1.4px;text-transform:uppercase;
        color:var(--ink-muted);font-weight:600;margin:16px 0 7px}
  input{width:100%;font:inherit;font-size:16px;color:var(--ink);background:var(--surface-2);
        border:1px solid var(--hairline-2);border-radius:8px;padding:13px 14px;outline:none}
  input:focus{border-color:#d1ae00;box-shadow:0 0 0 3px #fff3a3}
  button{width:100%;font:inherit;font-size:16px;font-weight:700;color:#111;background:var(--brand);
         border:none;border-radius:12px;padding:15px;margin-top:22px;cursor:pointer}
  button:disabled{opacity:.5;cursor:default}
  .error{margin-top:16px;border-left:2px solid var(--mal);padding-left:12px;color:#f0a8a8;font-size:14.5px}
  .pie{margin-top:22px;text-align:center;font-size:12px;color:var(--ink-muted)}
  .pie a{color:var(--ink-2)}
  p{font-size:14.5px;line-height:1.55;color:var(--ink-2);margin:0 0 12px}
  .qr{display:grid;place-items:center;margin:8px 0 14px}
  .qr svg{width:200px;height:200px}
  .secreto{font-family:ui-monospace,Menlo,monospace;font-size:14px;letter-spacing:1px;text-align:center;
           background:var(--surface-2);border:1px solid var(--hairline);border-radius:8px;padding:10px;
           word-break:break-all;user-select:all}
  .codigos{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:14px 0;padding:0;list-style:none;
           font-family:ui-monospace,Menlo,monospace;font-size:16px;text-align:center}
  .codigos li{background:var(--surface-2);border:1px solid var(--hairline);border-radius:8px;padding:8px}
  a.boton{display:block;text-align:center;text-decoration:none;font-weight:700;color:#111;background:var(--brand);
          border-radius:12px;padding:15px;margin-top:22px}
</style></head><body>
__CUERPO__
</body></html>"""


_MARCA = """  <div class="marca">
    <img src="/logo.png" alt="Gestión de flota" onerror="this.style.display='none'">
    <div class="t">Pengui · Gestión de flota</div>
  </div>
"""

LOGIN = _PAGINA.replace("__TITULO__", "Ingresar").replace("__CUERPO__", """<form class="caja" method="POST" action="/login">
  <div class="marca">
    <img src="/logo.png" alt="Gestión de flota" onerror="this.style.display='none'">
    <div class="t">Pengui · Gestión de flota</div>
  </div>
  <label for="usuario">Usuario</label>
  <input id="usuario" name="usuario" autocapitalize="none" autocorrect="off" autofocus required>
  <label for="clave">Contraseña</label>
  <input id="clave" name="clave" type="password" required>
  <input type="hidden" name="destino" value="__DESTINO__">
  <button type="submit">Entrar</button>
  __ERROR__
  <div class="pie">Si no cuenta con usuario, debe solicitarlo al encargado.</div>
</form>""")


def _pagina(titulo, cuerpo):
    return _PAGINA.replace("__TITULO__", titulo).replace("__CUERPO__", cuerpo)


def _error_html(error):
    from html import escape
    return f'<div class="error">{escape(error)}</div>' if error else ""


_CAMPO_CODIGO = """
  <label for="codigo">Código</label>
  <input id="codigo" name="codigo" inputmode="numeric" autocomplete="one-time-code"
         autocapitalize="none" autocorrect="off" autofocus required maxlength="12">"""


def pagina_codigo(error=None):
    """El segundo paso de todos los días: el código de la app."""
    return _pagina("Código de verificación", f"""<form class="caja" method="POST" action="/login/2fa">
{_MARCA}  <p>Abrí la app autenticadora y escribí el código de 6 dígitos de <b>{EMISOR}</b>.</p>
  {_CAMPO_CODIGO}
  <button type="submit">Verificar</button>
  {_error_html(error)}
  <div class="pie">¿Sin el celular? Escribí uno de los códigos de respaldo.<br>
    <a href="/login">Volver a ingresar</a></div>
</form>""")


def pagina_alta_2fa(usuario, secreto, error=None):
    """La primera vez: escanear el QR y confirmar con un código."""
    from html import escape
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
        import io
        buf = io.BytesIO()
        qrcode.make(totp_uri(secreto, usuario), image_factory=SvgPathImage,
                    box_size=10, border=2).save(buf)
        svg = buf.getvalue().decode()
        qr = f'<div class="qr">{svg[svg.index("<svg"):]}</div>'
    except Exception:
        qr = ""
    agrupado = " ".join(secreto[i:i + 4] for i in range(0, len(secreto), 4))
    return _pagina("Activar verificación en dos pasos", f"""<form class="caja" method="POST" action="/login/2fa">
{_MARCA}  <p>Tu usuario administra el sistema, así que además de la contraseña
    vas a usar un código del celular.</p>
  <p>1. Instalá <b>Google Authenticator</b>, <b>Authy</b> o <b>1Password</b>.<br>
     2. Agregá una cuenta escaneando este código:</p>
  {qr}
  <p>Si no podés escanearlo, cargá esta clave a mano:</p>
  <div class="secreto">{escape(agrupado)}</div>
  <p style="margin-top:14px">3. Escribí el código de 6 dígitos que muestra la app.</p>
  {_CAMPO_CODIGO}
  <button type="submit">Activar</button>
  {_error_html(error)}
  <div class="pie"><a href="/login">Volver a ingresar</a></div>
</form>""")


def pagina_respaldo(codigos, destino="/"):
    """Los códigos de respaldo, una sola vez."""
    from html import escape
    lista = "".join(f"<li>{escape(c)}</li>" for c in codigos)
    return _pagina("Códigos de respaldo", f"""<div class="caja">
{_MARCA}  <p><b>Listo, la verificación en dos pasos quedó activada.</b></p>
  <p>Estos son tus códigos de respaldo. Sirven para entrar si perdés el
    celular: cada uno se usa una sola vez. <b>Guardalos ahora</b> (anotados o en un
    gestor de contraseñas); no se vuelven a mostrar.</p>
  <ul class="codigos">{lista}</ul>
  <a class="boton" href="{escape(destino or "/", quote=True)}">Ya los guardé, continuar</a>
</div>""")


def pagina_login(error=None, destino="/"):
    from html import escape
    return (LOGIN
            .replace("__ERROR__", f'<div class="error">{escape(error)}</div>' if error else "")
            .replace("__DESTINO__", escape(destino or "/", quote=True)))
