#!/usr/bin/env python3
"""
App Taller — un solo servidor para todas las pantallas.

Es lo que corre en la nube. Sirve, detrás del mismo login:

    /            inicio, con los accesos a cada módulo
    /flota       panel general de flota
    /control     control de flota y mantenimiento
    /repuestos   stock de repuestos
    /gomeria     carga de movimientos de cubiertas (a donde apunta el QR)
    /unidades    maestro de unidades: de acá sale la info de cada vehículo

Configuración, toda por variables de entorno:

    SUPABASE_DB_URL   conexión a la base           (obligatoria)
    ANTHROPIC_API_KEY clave de la API de Claude    (si falta, no se cargan partes)
    USUARIO_INICIAL   "usuario:Nombre:contraseña"  (solo la primera vez)
    PORT              el puerto; en la nube lo pone el servicio

Local: python3 app.py
"""
import datetime, json, os, sys, traceback
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

import psycopg
import anthropic

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "gomeria"))

import auth, base, etiquetas, inicio, repuestos, unidades as uni
import vencimientos as venc
import servidor as gom

# Cada dirección con el archivo que le toca. Todas piden sesión.
PANTALLAS = {
    "/":           ("inicio.html",             "text/html; charset=utf-8"),
    # La foto responde por los dos nombres: el del archivo y el corto. Que
    # una pantalla la pida por el nombre que no era es un 404 silencioso —
    # no rompe nada, simplemente no se ve la imagen y cuesta darse cuenta.
    "/inicio-camion.jpg":      ("inicio-camion-hero.jpg", "image/jpeg"),
    "/inicio-camion-hero.jpg": ("inicio-camion-hero.jpg", "image/jpeg"),
    "/flota":      ("index.html",              "text/html; charset=utf-8"),
    "/control":    ("control_flota.html",      "text/html; charset=utf-8"),
    "/repuestos":  ("stock_repuestos.html",    "text/html; charset=utf-8"),
    "/vencimientos": ("vencimientos.html",     "text/html; charset=utf-8"),
    "/unidades":   ("unidades.html",           "text/html; charset=utf-8"),
    # El logo de la app es blanco; sobre el papel claro de la cédula no se
    # vería. Este es el azul, el mismo que se imprime en las etiquetas.
    "/logo-cedula.png": ("logo-cedula.png",     "image/png"),
    "/favicon.png": ("favicon.png",             "image/png"),
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

        # Los números que la portada muestra en vivo.
        if ruta == "/api/inicio":
            if not self._exigir_sesion():
                return
            try:
                with base.conectar() as cx:
                    return self._responder(gom.jstr(inicio.resumen(cx)))
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo leer el resumen: {e}", 500)

        # La hoja de etiquetas QR para pegar en los estantes.
        if ruta == "/repuestos/etiquetas":
            if not self._exigir_sesion():
                return
            params = parse_qs(urlparse(self.path).query)
            codigos = [c for c in (params.get("codigos") or [""])[0].split(",") if c]
            try:
                with base.conectar() as cx:
                    # La dirección tiene que ser la que ve el celular que
                    # escanea, no la del servidor: sale del pedido.
                    esquema = "https" if self._es_https() else "http"
                    origen = f"{esquema}://{self.headers.get('Host', '')}"
                    pagina = etiquetas.hoja(cx, origen,
                                            rubro=(params.get("rubro") or [""])[0] or None,
                                            codigos=codigos or None)
                return self._responder(pagina.encode(), "text/html; charset=utf-8")
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudieron armar las etiquetas: {e}", 500)

        # Lo que deja un QR escaneado: la pantalla de repuestos parada en
        # ese código. Cuál es lo resuelve la propia página con la dirección.
        if ruta.startswith("/repuestos/"):
            if not self._exigir_sesion():
                return
            entero = os.path.join(AQUI, "stock_repuestos.html")
            return self._responder(open(entero, "rb").read(),
                                   "text/html; charset=utf-8")

        # El km que tenía una unidad en una fecha. Lo usa el formulario de
        # service: la fecha del trabajo es la que manda, no la de hoy.
        if ruta == "/api/odometro":
            if not self._exigir_sesion():
                return
            params = parse_qs(urlparse(self.path).query)
            patente = (params.get("patente") or [""])[0]
            fecha = (params.get("fecha") or [""])[0]
            try:
                datetime.date.fromisoformat(fecha)
            except ValueError:
                return self._error("La fecha tiene que venir como AAAA-MM-DD.")
            try:
                with base.conectar() as cx:
                    fila = base.odometro_en(cx, patente, fecha)
                return self._responder(gom.jstr(dict(fila) if fila else {"km": None}))
            except psycopg.errors.UndefinedTable:
                return self._responder(gom.jstr({"km": None, "sin_tabla": True}))
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo leer el odómetro: {e}", 500)

        # El maestro con la forma que esperan los tableros de flota. Antes lo
        # sacaban de la planilla; ahora la planilla es una copia y el que
        # manda es este.
        if ruta == "/api/flota":
            if not self._exigir_sesion():
                return
            try:
                with base.conectar() as cx:
                    return self._responder(gom.jstr(uni.para_tablero(cx)))
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo leer el maestro: {e}", 500)

        # Three.js y sus complementos viven en el repo, no en un CDN: el
        # taller no siempre tiene buena conexión y una pantalla que depende
        # de que conteste Cloudflare es una pantalla que un día no abre.
        if ruta.startswith("/vendor/") and ruta.endswith(".js"):
            if not self._exigir_sesion():
                return
            camino = os.path.join(AQUI, "vendor", os.path.basename(ruta))
            if not os.path.isfile(camino):
                return self._error("No existe ese archivo.", 404)
            cuerpo = open(camino, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "public, max-age=604800")
            self.end_headers()
            return self.wfile.write(cuerpo)

        # Los modelos 3D. Son archivos estáticos y no cambian nunca, así que
        # se dejan cachear: son 240 KB y no tiene sentido bajarlos en cada
        # unidad que se abre.
        if ruta.startswith("/modelos/") and ruta.endswith(".obj"):
            if not self._exigir_sesion():
                return
            nombre = os.path.basename(ruta)
            camino = os.path.join(AQUI, "modelos", nombre)
            if not os.path.isfile(camino):
                return self._error("No existe ese modelo.", 404)
            cuerpo = open(camino, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "public, max-age=604800")
            self.end_headers()
            return self.wfile.write(cuerpo)

        # Las cubiertas que se pueden poner: lo que hay en stock, con la
        # medida que ya está montada primero.
        if ruta == "/api/gomeria/stock":
            if not self._exigir_sesion():
                return
            medida = (parse_qs(urlparse(self.path).query).get("medida") or [None])[0]
            try:
                with base.conectar() as cx:
                    return self._responder(gom.jstr(uni.stock_para(cx, medida)))
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo leer el stock: {e}", 500)

        # La ficha de una unidad: el maestro más lo que sabe cada módulo.
        if ruta.startswith("/api/unidades/"):
            if not self._exigir_sesion():
                return
            try:
                unidad_id = int(ruta.rsplit("/", 1)[1])
            except ValueError:
                return self._error("Esa unidad no existe.", 404)
            try:
                with base.conectar() as cx:
                    datos = uni.ficha(cx, unidad_id)
                if not datos:
                    return self._error("Esa unidad no existe.", 404)
                return self._responder(gom.jstr(datos))
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo leer la unidad: {e}", 500)

        # El maestro de unidades. De acá sale la información de cada vehículo
        # para el resto del sistema, así que la pantalla lee la vista entera.
        if ruta == "/api/unidades":
            if not self._exigir_sesion():
                return
            try:
                with base.conectar() as cx:
                    return self._responder(gom.jstr(uni.listar(cx)))
            except psycopg.errors.UndefinedColumn:
                return self._error(
                    "Al maestro de unidades le faltan columnas. Corré "
                    "gomeria/07_unidades.sql en el SQL Editor de Supabase.", 503)
            except psycopg.errors.UndefinedTable:
                return self._error(
                    "Falta crear la vista de unidades. Corré "
                    "gomeria/07_unidades.sql en el SQL Editor de Supabase.", 503)
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo leer el maestro de unidades: {e}", 500)

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

        # El cambio de cubierta hecho tocando la rueda en el 3D. Es la misma
        # operación que el parte escrito, pero acá la unidad y la posición ya
        # se saben, así que no hay texto que interpretar.
        if ruta == "/api/gomeria/posicion":
            if not self._exigir_sesion():
                return
            try:
                largo = int(self.headers.get("Content-Length") or 0)
                if largo > 32 * 1024:
                    return self._error("El pedido es demasiado grande.", 413)
                datos = json.loads(self.rfile.read(largo) or b"{}")
                with base.conectar() as cx:
                    salida = uni.mover_cubierta(cx, datos, self.usuario)
                    cx.commit()
                return self._responder(gom.jstr(salida))
            except PermissionError as e:
                return self._error(str(e), 403)
            except ValueError as e:
                return self._error(str(e))
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo hacer el cambio: {e}", 500)

        if ruta == "/api/unidades":
            return self._unidad_escribir()

        if ruta.startswith("/gomeria/api/"):
            self.path = ruta[len("/gomeria"):]
        return super().do_POST()


    def do_DELETE(self):
        ruta = urlparse(self.path).path
        if ruta == "/api/unidades":
            return self._unidad_escribir(borrar=True)
        return self._error("No existe", 404)

    def _unidad_escribir(self, borrar=False):
        """El alta, el cambio y la baja del maestro comparten todo salvo una línea."""
        if not self._exigir_sesion():
            return
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            if largo > 64 * 1024:
                return self._error("El pedido es demasiado grande.", 413)
            datos = json.loads(self.rfile.read(largo) or b"{}")
            with base.conectar() as cx:
                if borrar:
                    salida = uni.eliminar(cx, datos.get("id"), self.usuario)
                else:
                    salida = uni.guardar(cx, datos, self.usuario)
                cx.commit()
            return self._responder(gom.jstr(salida))
        except PermissionError as e:
            return self._error(str(e), 403)
        except ValueError as e:
            return self._error(str(e))
        except psycopg.errors.UndefinedColumn:
            return self._error(
                "Al maestro de unidades le faltan columnas. Corré "
                "gomeria/07_unidades.sql en el SQL Editor de Supabase.", 503)
        except Exception as e:
            traceback.print_exc()
            return self._error(f"No se pudo guardar la unidad: {e}", 500)


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

        # El maestro no es una tabla nueva sino columnas agregadas a una que
        # ya estaba, así que se pregunta por una de ellas.
        tiene_maestro = cx.execute("""
            select count(*) as n from information_schema.columns
            where table_schema = 'public' and table_name = 'unidades'
              and column_name in ('chasis','chofer','semi','tipo')""").fetchone()["n"]
        if tiene_maestro < 4:
            print("  Al maestro de unidades le faltan columnas: corré "
                  "gomeria/07_unidades.sql en Supabase.")

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
