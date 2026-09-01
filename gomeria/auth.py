"""
Usuarios, contraseñas y sesiones.

La contraseña nunca se guarda: se guarda el resultado de pasarla por scrypt
con una sal distinta para cada uno. Aunque alguien se lleve la tabla entera,
no puede volver a las contraseñas.

Al entrar se crea una sesión con un token al azar que viaja en una cookie.
El celular no guarda la contraseña, solo ese token, y se puede cortar
borrando la fila.
"""
import hashlib, hmac, os, secrets
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie

DIAS_SESION = 30           # el gomero no debería tener que entrar todos los días
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
def abrir_sesion(cx, usuario_id, agente=None):
    token = secrets.token_urlsafe(32)
    expira = datetime.now(timezone.utc) + timedelta(days=DIAS_SESION)
    cx.execute("""insert into sesiones (token, usuario_id, expira, agente)
                  values (%s,%s,%s,%s)""", (token, usuario_id, expira, (agente or "")[:200]))
    cx.execute("update usuarios set ultimo_ingreso = now() where id = %s", (usuario_id,))
    return token


def usuario_de_sesion(cx, token):
    if not token:
        return None
    fila = cx.execute("""
        select u.* from sesiones s
        join usuarios u on u.id = s.usuario_id
        where s.token = %s and s.expira > now() and u.activo""", (token,)).fetchone()
    if fila:
        cx.execute("update sesiones set ultimo_uso = now() where token = %s", (token,))
    return fila


def cerrar_sesion(cx, token):
    if token:
        cx.execute("delete from sesiones where token = %s", (token,))


def limpiar_vencidas(cx):
    cx.execute("delete from sesiones where expira < now()")


def token_de_cookie(cabecera):
    if not cabecera:
        return None
    try:
        c = SimpleCookie()
        c.load(cabecera)
        return c[COOKIE].value if COOKIE in c else None
    except Exception:
        return None


def cookie_de_sesion(token, borrar=False):
    """Armá la cookie. HttpOnly para que ningún script de la página la lea."""
    if borrar:
        return f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
    return (f"{COOKIE}={token}; Path=/; Max-Age={DIAS_SESION * 86400}; "
            f"HttpOnly; SameSite=Lax")


# =====================================================================
# PANTALLA DE INGRESO
# =====================================================================
LOGIN = """<!DOCTYPE html><html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Ingresar | Diemar</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%2312161a'/%3E%3Crect x='12' y='7' width='8' height='18' fill='%23ff7a1a'/%3E%3C/svg%3E">
<style>
  :root{color-scheme:dark;--plane:#08090b;--surface-1:#12161a;--surface-2:#171c21;
        --hairline:rgba(255,255,255,.07);--hairline-2:rgba(255,255,255,.12);
        --ink:#e9ecef;--ink-2:#a9b0b8;--ink-muted:#7b828b;--brand:#ff7a1a;--mal:#d03b3b}
  *{box-sizing:border-box}
  html,body{height:100%;margin:0}
  body{font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;background:var(--plane);
       color:var(--ink);font-size:16px;display:grid;place-items:center;padding:24px}
  .caja{width:100%;max-width:360px}
  .marca{text-align:center;margin-bottom:26px}
  .marca img{height:34px;margin-bottom:14px}
  .marca .t{font-size:11px;letter-spacing:2.4px;text-transform:uppercase;color:var(--ink-muted);font-weight:600}
  label{display:block;font-size:11.5px;letter-spacing:1.4px;text-transform:uppercase;
        color:var(--ink-muted);font-weight:600;margin:16px 0 7px}
  input{width:100%;font:inherit;font-size:16px;color:var(--ink);background:var(--surface-2);
        border:1px solid var(--hairline-2);border-radius:12px;padding:13px 14px;outline:none}
  input:focus{border-color:rgba(255,122,26,.55)}
  button{width:100%;font:inherit;font-size:16px;font-weight:600;color:#fff;background:var(--brand);
         border:none;border-radius:12px;padding:15px;margin-top:22px;cursor:pointer}
  button:disabled{opacity:.5;cursor:default}
  .error{margin-top:16px;border-left:2px solid var(--mal);padding-left:12px;color:#f0a8a8;font-size:14.5px}
  .pie{margin-top:22px;text-align:center;font-size:12px;color:var(--ink-muted)}
</style></head><body>
<form class="caja" method="POST" action="/login">
  <div class="marca">
    <img src="/logo.png" alt="Diemar" onerror="this.style.display='none'">
    <div class="t">Taller Diemar</div>
  </div>
  <label for="usuario">Usuario</label>
  <input id="usuario" name="usuario" autocapitalize="none" autocorrect="off" autofocus required>
  <label for="clave">Contraseña</label>
  <input id="clave" name="clave" type="password" required>
  <input type="hidden" name="destino" value="__DESTINO__">
  <button type="submit">Entrar</button>
  __ERROR__
  <div class="pie">Si no tenés usuario, pedíselo al encargado.</div>
</form>
</body></html>"""


def pagina_login(error=None, destino="/"):
    from html import escape
    return (LOGIN
            .replace("__ERROR__", f'<div class="error">{escape(error)}</div>' if error else "")
            .replace("__DESTINO__", escape(destino or "/", quote=True)))
