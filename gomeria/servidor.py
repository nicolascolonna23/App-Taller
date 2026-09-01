#!/usr/bin/env python3
"""
Servidor del módulo de gomería.

Sirve la pantalla que se abre al escanear el QR de una unidad y resuelve la
interpretación del texto libre. Igual que el chat: la clave de la API y la
conexión a la base viven acá, nunca en el celular.

    export SUPABASE_DB_URL=postgresql://...
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 servidor.py --host 0.0.0.0
"""
import argparse, json, os, sys, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import anthropic
import auth, base, interpretar, mapas


def jstr(d):
    return json.dumps(d, ensure_ascii=False, default=str)


# Lo único que se sirve sin haber entrado.
LIBRES = ("/login", "/logo.png")


class Handler(BaseHTTPRequestHandler):
    server_version = "GomeriaDiemar/1.0"
    usuario = None

    def _es_https(self):
        """En la nube el candado lo pone el proxy, y avisa con esta cabecera."""
        return (self.headers.get("X-Forwarded-Proto", "").lower() == "https"
                or os.environ.get("FORZAR_HTTPS") == "1")

    def _origen(self):
        """De dónde viene, para contarle los intentos fallidos."""
        adelantado = self.headers.get("X-Forwarded-For", "")
        return (adelantado.split(",")[0].strip() if adelantado
                else self.client_address[0])

    def _sesion(self):
        """Deja self.usuario cargado. True si hay sesión válida."""
        token = auth.token_de_cookie(self.headers.get("Cookie"))
        if not token:
            return False
        with base.conectar() as cx:
            self.usuario = auth.usuario_de_sesion(cx, token)
            cx.commit()
        return self.usuario is not None

    def _exigir_sesion(self):
        """Corta la petición si no entró. Devuelve True si puede seguir."""
        if self._sesion():
            return True
        ruta = urlparse(self.path).path
        if ruta.startswith("/api/"):
            self._error("Se cerró la sesión. Recargá la página y entrá de nuevo.", 401)
        else:
            destino = self.path if ruta not in ("/login",) else "/"
            self._responder(auth.pagina_login(destino=destino),
                            "text/html; charset=utf-8", codigo=200)
        return False

    def log_message(self, formato, *args):
        sys.stderr.write("  %s\n" % (formato % args))

    def _responder(self, cuerpo, tipo="application/json; charset=utf-8", codigo=200, cookie=None):
        if isinstance(cuerpo, str):
            cuerpo = cuerpo.encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(cuerpo)

    def _error(self, mensaje, codigo=400):
        self._responder(jstr({"error": mensaje}), codigo=codigo)

    # -----------------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        ruta, params = u.path, parse_qs(u.query)

        if ruta == "/logo.png":
            archivo = os.path.join(AQUI, os.pardir, "logo_diemar4.png")
            if not os.path.exists(archivo):
                return self._error("sin logo", 404)
            return self._responder(open(archivo, "rb").read(), "image/png")

        if ruta == "/login":
            if self._sesion():
                return self._redirigir("/")
            return self._responder(auth.pagina_login(), "text/html; charset=utf-8")

        if ruta == "/salir":
            token = auth.token_de_cookie(self.headers.get("Cookie"))
            with base.conectar() as cx:
                auth.cerrar_sesion(cx, token)
                cx.commit()
            return self._redirigir("/login", cookie=auth.cookie_de_sesion(
                None, borrar=True, seguro=self._es_https()))

        if not self._exigir_sesion():
            return

        if ruta == "/api/yo":
            return self._responder(jstr({
                "usuario": self.usuario["usuario"], "nombre": self.usuario["nombre"],
                "rol": self.usuario["rol"]}))

        # El QR apunta acá: /u/AD247MQ
        if ruta.startswith("/u/") or ruta in ("/", "/index.html"):
            archivo = os.path.join(AQUI, "movil.html")
            if not os.path.exists(archivo):
                return self._error("Falta movil.html", 404)
            return self._responder(open(archivo, "rb").read(), "text/html; charset=utf-8")

        if ruta == "/api/mapa":
            patente = (params.get("patente") or [""])[0]
            try:
                with base.conectar() as cx:
                    unidad = base.buscar_unidad(cx, unquote(patente))
                    if not unidad:
                        return self._error(f"No encontré la unidad {patente}.", 404)
                    return self._responder(jstr({
                        "unidad": unidad,
                        "mapa": base.mapa_unidad(cx, unidad["id"]),
                    }))
            except Exception as e:
                traceback.print_exc()
                return self._error(str(e), 500)

        return self._error("No existe", 404)

    # -----------------------------------------------------------------
    def _redirigir(self, a, cookie=None):
        self.send_response(303)
        self.send_header("Location", a)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _login(self):
        largo = int(self.headers.get("Content-Length") or 0)
        from urllib.parse import parse_qs as pq
        campos = pq(self.rfile.read(largo).decode("utf-8", "replace"))
        usuario = (campos.get("usuario") or [""])[0].strip()
        clave = (campos.get("clave") or [""])[0]
        destino = (campos.get("destino") or ["/"])[0] or "/"
        if not destino.startswith("/") or destino.startswith("//"):
            destino = "/"          # que nadie use el login para mandar a otro sitio

        origen = self._origen()
        puede, minutos = auth.puede_intentar(origen)
        if not puede:
            return self._responder(
                auth.pagina_login(f"Demasiados intentos fallidos. Probá de nuevo en "
                                  f"{minutos} minuto{'s' if minutos > 1 else ''}.", destino),
                "text/html; charset=utf-8", codigo=429)

        with base.conectar() as cx:
            quien = auth.autenticar(cx, usuario, clave)
            if not quien:
                cx.commit()
                auth.anotar_fallo(origen)
                # Un solo mensaje para los dos casos: decir cuál falló le
                # confirma a quien prueba que ese usuario existe.
                return self._responder(
                    auth.pagina_login("Usuario o contraseña incorrectos.", destino),
                    "text/html; charset=utf-8", codigo=401)
            auth.limpiar_intentos(origen)
            token = auth.abrir_sesion(cx, quien["id"], self.headers.get("User-Agent"))
            auth.limpiar_vencidas(cx)
            cx.commit()
        return self._redirigir(destino,
                               cookie=auth.cookie_de_sesion(token, seguro=self._es_https()))

    def do_POST(self):
        ruta = urlparse(self.path).path
        if ruta == "/login":
            try:
                return self._login()
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo entrar: {e}", 500)
        if not self._exigir_sesion():
            return
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            datos = json.loads(self.rfile.read(largo) or b"{}")
        except Exception:
            return self._error("Cuerpo inválido")

        try:
            if ruta == "/api/interpretar":
                return self._interpretar(datos)
            if ruta == "/api/confirmar":
                return self._confirmar(datos)
            if ruta == "/api/descartar":
                return self._descartar(datos)
        except anthropic.APIStatusError as e:
            return self._error(f"La API respondió {e.status_code}. Revisá la clave o el saldo.", 502)
        except anthropic.APIConnectionError:
            return self._error("No se pudo conectar con la API de Claude.", 502)
        except ValueError as e:
            return self._error(str(e))
        except Exception as e:
            traceback.print_exc()
            return self._error(f"Error inesperado: {e}", 500)

        return self._error("No existe", 404)

    # -----------------------------------------------------------------
    def _interpretar(self, datos):
        """Guarda lo que escribió el gomero y devuelve la propuesta, sin aplicarla."""
        patente = (datos.get("patente") or "").strip()
        texto = (datos.get("texto") or "").strip()
        autor = self.usuario["nombre"]
        if not texto:
            return self._error("Escribí qué hiciste.")

        with base.conectar() as cx:
            # La unidad puede venir de la URL (un QR por unidad) o salir del
            # mismo texto (un QR solo para toda la gomería).
            if patente:
                unidad = base.buscar_unidad(cx, patente)
                if not unidad:
                    return self._error(f"No encontré la unidad {patente}.", 404)
            else:
                unidad, falta = base.resolver_unidad(cx, texto)
                if not unidad:
                    # El texto se guarda igual: es lo que escribió el gomero.
                    cx.execute("""insert into partes (texto, autor, estado, error)
                                  values (%s,%s,'error',%s)""", (texto, autor, falta))
                    cx.commit()
                    return self._error(falta, 404)

            # El parte se guarda apenas llega: aunque falle la interpretación o
            # el gomero se vaya sin confirmar, lo que escribió no se pierde.
            parte = cx.execute("""
                insert into partes (unidad_id, texto, autor, usuario_id, estado)
                values (%s,%s,%s,%s,'pendiente') returning id""",
                (unidad["id"], texto, autor, self.usuario["id"])).fetchone()
            cx.commit()

            if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
                cx.execute("update partes set estado='error', error=%s where id=%s",
                           ("sin clave de la API", parte["id"]))
                cx.commit()
                return self._error(
                    "Falta la clave de la API. Lo que escribiste quedó guardado; "
                    "poné la clave en chat/clave.txt, reiniciá el servidor y volvé a mandarlo.")

            mapa = base.mapa_unidad(cx, unidad["id"])
            try:
                propuesta = interpretar.interpretar(unidad, mapa, texto)
            except Exception as e:
                cx.execute("update partes set estado='error', error=%s where id=%s",
                           (str(e), parte["id"]))
                cx.commit()
                raise

            cx.execute("update partes set interpretacion = %s where id = %s",
                       (json.dumps(propuesta, ensure_ascii=False), parte["id"]))
            cx.commit()
            return self._responder(jstr({"parte_id": parte["id"], "propuesta": propuesta,
                                         "unidad": unidad, "mapa": mapa}))

    def _confirmar(self, datos):
        parte_id = datos.get("parte_id")
        usuario = self.usuario["nombre"]
        if not parte_id:
            return self._error("Falta el parte.")

        with base.conectar() as cx:
            parte = cx.execute("select * from partes where id = %s", (parte_id,)).fetchone()
            if not parte:
                return self._error("No existe ese parte.", 404)
            if parte["estado"] == "confirmado":
                return self._error("Ese parte ya estaba confirmado.")
            unidad = cx.execute("select * from unidades where id = %s",
                                (parte["unidad_id"],)).fetchone()
            propuesta = parte["interpretacion"]

            try:
                hecho = interpretar.aplicar(cx, unidad, propuesta,
                                            parte_id=parte["id"], usuario=usuario, base=base)
            except Exception as e:
                cx.rollback()
                cx.execute("update partes set estado='error', error=%s where id=%s",
                           (str(e), parte["id"]))
                cx.commit()
                return self._error(str(e))

            if propuesta.get("km_unidad"):
                cx.execute("update unidades set km_actual = %s where id = %s",
                           (propuesta["km_unidad"], unidad["id"]))
            cx.execute("""update partes set estado='confirmado', resuelto=now(), resuelto_por=%s
                          where id = %s""", (usuario, parte["id"]))
            cx.commit()
            return self._responder(jstr({
                "hecho": hecho,
                "mapa": base.mapa_unidad(cx, unidad["id"]),
            }))

    def _descartar(self, datos):
        with base.conectar() as cx:
            cx.execute("""update partes set estado='descartado', resuelto=now()
                          where id = %s and estado = 'pendiente'""", (datos.get("parte_id"),))
            cx.commit()
        return self._responder(jstr({"ok": True}))


def ip_en_la_red():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser(description="Módulo de gomería")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--puerto", type=int, default=8100)
    a = ap.parse_args()

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        archivo = os.path.join(AQUI, os.pardir, "chat", "clave.txt")
        if os.path.exists(archivo):
            os.environ["ANTHROPIC_API_KEY"] = open(archivo, encoding="utf-8").read().strip()
    # Sin clave el modulo arranca igual: ver los mapas no necesita a Claude.
    # Recien al interpretar un parte hace falta, y ahi avisa.
    hay_clave = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

    with base.conectar() as cx:
        n = cx.execute("select count(*) c from unidades").fetchone()["c"]
        c = cx.execute("select count(*) c from cubiertas").fetchone()["c"]
    print(f"Gomería · {n} unidades · {c} cubiertas")
    if not hay_clave:
        print("  Sin clave de la API: se ven los mapas, pero todavía no se pueden")
        print("  cargar partes. Poné la clave en chat/clave.txt cuando la tengas.")

    ip = ip_en_la_red() if a.host == "0.0.0.0" else a.host
    print(f"  Pantalla:  http://{ip}:{a.puerto}/u/PATENTE")
    print("  Para cortarlo: Ctrl+C")
    try:
        ThreadingHTTPServer((a.host, a.puerto), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nGomería cerrada.")


if __name__ == "__main__":
    main()
