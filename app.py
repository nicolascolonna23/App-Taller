#!/usr/bin/env python3
"""
App Taller — un solo servidor para todas las pantallas.

Es lo que corre en la nube. Sirve, detrás del mismo login:

    /            inicio, con los accesos a cada módulo
    /flota       panel general de flota
    /control     control de flota y mantenimiento
    /repuestos   stock de repuestos
    /gomeria     carga de movimientos de cubiertas (a donde apunta el QR)

Configuración, toda por variables de entorno:

    SUPABASE_DB_URL   conexión a la base           (obligatoria)
    ANTHROPIC_API_KEY clave de la API de Claude    (si falta, no se cargan partes)
    USUARIO_INICIAL   "usuario:Nombre:contraseña"  (solo la primera vez)
    PORT              el puerto; en la nube lo pone el servicio

Local: python3 app.py
"""
import json, os, sys, traceback
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

import psycopg
import anthropic

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "gomeria"))

import auth, base, repuestos, vencimientos as venc
import servidor as gom

# Cada dirección con el archivo que le toca. Todas piden sesión.
PANTALLAS = {
    "/":           ("inicio.html",             "text/html; charset=utf-8"),
    "/inicio-camion.jpg": ("inicio-camion-hero.jpg", "image/jpeg"),
    "/flota":      ("index.html",              "text/html; charset=utf-8"),
    "/control":    ("control_flota.html",      "text/html; charset=utf-8"),
    "/repuestos":  ("stock_repuestos.html",    "text/html; charset=utf-8"),
    "/vencimientos": ("vencimientos.html",     "text/html; charset=utf-8"),
}


class App(gom.Handler):
    """El manejador de gomería, más las pantallas de flota y repuestos."""

    def do_GET(self):
        ruta = urlparse(self.path).path

        if ruta == "/api/repuestos":
            if not self._exigir_sesion():
                return
            try:
                with base.conectar() as cx:
                    datos = repuestos.listar(cx, self.usuario)
                    cx.commit()
                return self._responder(gom.jstr(datos))
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudieron leer los repuestos: {e}", 500)

        if ruta == "/api/vencimientos":
            if not self._exigir_sesion():
                return
            try:
                with base.conectar() as cx:
                    return self._responder(gom.jstr(venc.listar(cx)))
            except psycopg.errors.UndefinedTable:
                return self._error(
                    "Falta crear las tablas de vencimientos. Corré "
                    "gomeria/06_vencimientos.sql en el SQL Editor de Supabase.", 503)
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudieron leer los vencimientos: {e}", 500)

        # El módulo de gomería vive bajo /gomeria; adentro sigue siendo el de siempre.
        if ruta == "/gomeria" or ruta.startswith("/gomeria/"):
            resto = ruta[len("/gomeria"):] or "/"
            self.path = resto if resto.startswith("/u/") else "/"
            return super().do_GET()

        if ruta in PANTALLAS:
            if not self._exigir_sesion():
                return
            archivo, tipo = PANTALLAS[ruta]
            entero = os.path.join(AQUI, archivo)
            if not os.path.exists(entero):
                return self._error(f"Falta {archivo} en el servidor.", 404)
            return self._responder(open(entero, "rb").read(), tipo)

        return super().do_GET()

    def do_POST(self):
        ruta = urlparse(self.path).path
        if ruta == "/api/repuestos":
            if not self._exigir_sesion():
                return
            try:
                largo = int(self.headers.get("Content-Length") or 0)
                if largo > 15 * 1024 * 1024:
                    return self._error("El archivo es demasiado grande.", 413)
                datos = json.loads(self.rfile.read(largo) or b"{}")
                if datos.get("op") == "vision":
                    cuerpo = datos.get("body") or {}
                    respuesta = anthropic.Anthropic().messages.create(**cuerpo)
                    texto = "\n".join(x.text for x in respuesta.content
                                      if getattr(x, "type", None) == "text")
                    return self._responder(gom.jstr({"texto": texto}))
                with base.conectar() as cx:
                    resultado = repuestos.aplicar(cx, datos, self.usuario)
                    cx.commit()
                return self._responder(gom.jstr(resultado))
            except PermissionError as e:
                return self._error(str(e), 403)
            except (ValueError, psycopg.errors.UniqueViolation) as e:
                mensaje = ("Ya existe un repuesto con ese código."
                           if isinstance(e, psycopg.errors.UniqueViolation) else str(e))
                return self._error(mensaje)
            except anthropic.APIStatusError as e:
                return self._error(f"La API respondió {e.status_code}. Revisá la clave o el saldo.", 502)
            except anthropic.APIConnectionError:
                return self._error("No se pudo conectar con la API de Claude.", 502)
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo guardar el cambio: {e}", 500)
        if ruta == "/api/vencimientos":
            if not self._exigir_sesion():
                return
            try:
                largo = int(self.headers.get("Content-Length") or 0)
                if largo > 256 * 1024:
                    return self._error("El pedido es demasiado grande.", 413)
                datos = json.loads(self.rfile.read(largo) or b"{}")
                with base.conectar() as cx:
                    resultado = venc.aplicar(cx, datos, self.usuario)
                    cx.commit()
                return self._responder(gom.jstr(resultado))
            except PermissionError as e:
                return self._error(str(e), 403)
            except psycopg.errors.RaiseException as e:
                # Los avisos del disparador ya vienen escritos para leer.
                return self._error(str(e).split("\n")[0].replace("ERROR:  ", ""))
            except ValueError as e:
                return self._error(str(e))
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo guardar el vencimiento: {e}", 500)

        if ruta.startswith("/gomeria/api/"):
            self.path = ruta[len("/gomeria"):]
        return super().do_POST()


def preparar():
    """Revisa la configuración y crea el primer usuario si hace falta."""
    if not (os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")):
        raise SystemExit("Falta SUPABASE_DB_URL. Es la conexión a la base.")

    with base.conectar() as cx:
        # base.conectar() devuelve diccionarios, así que la columna se nombra.
        def existe(tabla):
            return cx.execute("select to_regclass(%s) as existe",
                              (f"public.{tabla}",)).fetchone()["existe"]

        # Sin estas la app no puede ni levantar.
        faltan = [t for t in ("unidades", "usuarios", "sesiones",
                              "repuestos_articulos", "repuestos_movimientos")
                  if not existe(t)]
        if faltan:
            raise SystemExit(
                "A la base le faltan tablas: " + ", ".join(faltan) +
                "\nCorré los scripts 01 a 04 de gomeria en Supabase.")

        # Las de un módulo agregado después solo apagan ese módulo. Que
        # falte el SQL de vencimientos no puede dejar sin gomería al taller.
        opcionales = {
            "vencimientos": ("vencimientos", "tipos_vencimiento", "personas"),
            "odómetros":    ("odometros",),
        }
        for modulo, tablas in opcionales.items():
            if any(not existe(t) for t in tablas):
                print(f"  Sin las tablas de {modulo}: ese módulo va a avisar "
                      f"que falta correr su script en Supabase.")

        inicial = os.environ.get("USUARIO_INICIAL", "").strip()
        if inicial:
            try:
                creado = auth.crear_admin_inicial(cx, inicial)
                cx.commit()
                if creado:
                    print(f"  Primer usuario creado: '{creado}' (admin).")
                    print("  Sacá USUARIO_INICIAL de las variables de entorno.")
            except ValueError as e:
                print(f"  USUARIO_INICIAL: {e}")

        cuantos = cx.execute("select count(*) as n from usuarios").fetchone()["n"]
        unidades = cx.execute("select count(*) as n from unidades").fetchone()["n"]
        cx.commit()

    if not cuantos:
        print("  Todavía no hay usuarios: nadie va a poder entrar.")
        print('  Poné USUARIO_INICIAL="usuario:Nombre Completo:contraseña" y reiniciá.')
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  Sin ANTHROPIC_API_KEY: se ven los mapas, no se cargan partes.")
    return cuantos, unidades


def main():
    puerto = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")

    print("App Taller")
    usuarios, unidades = preparar()
    print(f"  {unidades} unidades · {usuarios} usuarios")
    print(f"  Escuchando en http://{host}:{puerto}")

    try:
        ThreadingHTTPServer((host, puerto), App).serve_forever()
    except KeyboardInterrupt:
        print("\nCerrado.")


if __name__ == "__main__":
    main()
