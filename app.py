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
    /combustible cruce de remitos contra el listado de la estación (en prueba)
    /ordenes     órdenes de trabajo del taller y servicios externos
    /alertas     todo lo que hay que mirar hoy, de las cuatro fuentes

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

import alertas as alr
import auth, base, combustible as comb, etiquetas, facturas, inicio, repuestos
import asistente
import ordenes as ots
import mantenimiento as mant
import preferencias as prefs
import unidades as uni
import vencimientos as venc
import servidor as gom

# Cada dirección con el archivo que le toca. Todas piden sesión.
PANTALLAS = {
    "/sistema.css": ("sistema.css", "text/css; charset=utf-8"),
    "/pengui.js": ("pengui.js", "text/javascript; charset=utf-8"),
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
    "/alertas":     ("alertas.html",           "text/html; charset=utf-8"),
    "/unidades":   ("unidades.html",           "text/html; charset=utf-8"),
    "/asistente": ("asistente.html", "text/html; charset=utf-8"),
    "/asistente/guia": ("docs/ASISTENTE.md", "text/plain; charset=utf-8"),
    "/combustible": ("combustible.html",       "text/html; charset=utf-8"),
    "/ordenes":    ("ordenes.html",            "text/html; charset=utf-8"),
    "/configuracion": ("configuracion.html",   "text/html; charset=utf-8"),
    # El logo de la app es blanco; sobre el papel claro de la cédula no se
    # vería. Este es el azul, el mismo que se imprime en las etiquetas.
    "/logo-cedula.png": ("logo-cedula.png",     "image/png"),
    "/favicon.png": ("favicon.png",             "image/png"),
    # El visor 3D del camión. Está afuera de las pantallas porque lo usan
    # dos: la ficha de la unidad en Flota y el mapa de cubiertas en
    # Gomería.
    "/camion3d.js": ("camion3d.js",             "text/javascript; charset=utf-8"),
    # Cómo ve cada uno la aplicación. Lo cargan todas las pantallas.
    "/tema.js":     ("tema.js",                 "text/javascript; charset=utf-8"),
}


class App(gom.Handler):
    """El manejador de gomería, más las pantallas de flota y repuestos."""

    def _ruta_pedida(self):
        """La dirección que escribió el navegador, antes de reescribirla.

        /gomeria le cambia self.path a "/" para que el manejador de Gomería
        sirva su pantalla. Cualquier decisión que dependa de en qué pantalla
        estamos tiene que mirar esto y no self.path, que para entonces ya
        dice otra cosa.
        """
        return getattr(self, "ruta_original", None) or urlparse(self.path).path

    def _responder(self, cuerpo, tipo="application/json; charset=utf-8", codigo=200, cookie=None):
        # Incluye las pantallas servidas por el manejador de Gomería.
        if tipo.startswith("text/html") and getattr(self, "usuario", None):
            html = cuerpo.decode("utf-8") if isinstance(cuerpo, bytes) else cuerpo
            tema = '' if 'src="/tema.js"' in html else '<script src="/tema.js"></script>'
            estilos = tema + '<link rel="stylesheet" href="/sistema.css">'
            # El logo de la empresa en la solapa del navegador. Va acá y no
            # en cada archivo porque cada pantalla que se agregue se lo iba
            # a olvidar: Gomería y Configuración no lo tenían, y en la
            # solapa se veía el globo gris del navegador.
            if 'rel="icon"' not in html:
                estilos += '<link rel="icon" href="/favicon.png" type="image/png">'
            html = html.replace('</head>', estilos + '</head>', 1) if '</head>' in html else html + estilos
            # Pengui vive en la portada. Inyectarlo en todas las pantallas
            # lo dejaba encima de formularios, tablas y botones de trabajo.
            script = ('<script src="/pengui.js"></script>'
                      if self._ruta_pedida() == "/" else "")
            if '</body>' in html:
                antes, despues = html.rsplit('</body>', 1)
                cuerpo = antes + script + '</body>' + despues
            else:
                cuerpo = html + script
        return super()._responder(cuerpo, tipo, codigo, cookie)

    def do_GET(self):
        ruta = urlparse(self.path).path
        self.ruta_original = ruta

        if ruta == "/api/asistente":
            if not self._exigir_sesion():
                return
            return self._responder(gom.jstr({"habilitado": asistente.habilitado()}))

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

        # Cómo ve la aplicación este usuario: tema, paleta y portada.
        if ruta == "/api/preferencias":
            if not self._exigir_sesion():
                return
            try:
                with base.conectar() as cx:
                    return self._responder(gom.jstr(prefs.leer(cx, self.usuario["id"])))
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudieron leer las preferencias: {e}", 500)

        # La portada que subió. Es de cada uno: sale de la sesión y no de
        # la dirección, así nadie puede mirar la del otro.
        if ruta == "/api/fondo":
            if not self._exigir_sesion():
                return
            try:
                with base.conectar() as cx:
                    cuerpo, tipo = prefs.fondo(cx, self.usuario["id"])
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo leer la portada: {e}", 500)
            if not cuerpo:
                return self._error("Este usuario no tiene portada propia.", 404)
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            # Privada: es de este usuario y no la puede guardar un
            # intermediario para servírsela a otro.
            self.send_header("Cache-Control", "private, max-age=86400")
            self.end_headers()
            return self.wfile.write(cuerpo)

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

        # La fuente de verdad del tablero de mantenimiento. La planilla de
        # Google queda como respaldo del navegador, pero una orden preventiva
        # tiene que verse apenas se guarda en Supabase.
        if ruta == "/api/services":
            if not self._exigir_sesion():
                return
            try:
                with base.conectar() as cx:
                    return self._responder(gom.jstr(alr.services(cx)))
            except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
                return self._error(
                    "Falta actualizar los services. Corré gomeria/20_alertas.sql y "
                    "gomeria/21_ordenes_preventivas.sql y gomeria/22_planes_mantenimiento.sql "
                    "en Supabase.", 503)
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudieron leer los services: {e}", 500)

        if ruta == "/api/mantenimiento":
            if not self._exigir_sesion():
                return
            try:
                with base.conectar() as cx:
                    return self._responder(gom.jstr(mant.listar(cx)))
            except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
                return self._error("Falta crear los planes. Corré gomeria/22_planes_mantenimiento.sql en Supabase.", 503)
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo leer la parametrización: {e}", 500)

        # Los logos de las marcas de cubierta. Que falte uno no es un
        # error: la pantalla muestra el nombre en texto y sigue.
        if ruta.startswith("/marcas/") and ruta.endswith(".png"):
            if not self._exigir_sesion():
                return
            camino = os.path.join(AQUI, "marcas", os.path.basename(ruta))
            if not os.path.isfile(camino):
                return self._error("No hay logo de esa marca.", 404)
            cuerpo = open(camino, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "public, max-age=604800")
            self.end_headers()
            return self.wfile.write(cuerpo)

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
        if ruta.startswith("/modelos/") and ruta.endswith((".obj", ".fbx", ".glb", ".gltf")):
            if not self._exigir_sesion():
                return
            nombre = os.path.basename(ruta)
            camino = os.path.join(AQUI, "modelos", nombre)
            if not os.path.isfile(camino):
                return self._error("No existe ese modelo.", 404)
            cuerpo = open(camino, "rb").read()
            self.send_response(200)
            # El FBX es binario; el OBJ es texto. Mandar el binario como
            # texto lo rompe en el camino.
            self.send_header("Content-Type", "application/octet-stream"
                             if nombre.endswith((".fbx", ".glb"))
                             else "text/plain; charset=utf-8")
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

        # El cruce de remitos de combustible. Módulo en prueba: si su SQL
        # todavía no se corrió, lo dice en vez de romper.
        if ruta == "/api/combustible":
            if not self._exigir_sesion():
                return
            params = parse_qs(urlparse(self.path).query)
            estado = (params.get("estado") or [None])[0]
            # La misma dirección sirve las dos vistas del módulo: lo que
            # gastó la flota y el control de la factura. Salen de la misma
            # tabla, así que separarlas en dos direcciones sería fingir que
            # son dos módulos.
            vista = (params.get("vista") or [""])[0]
            try:
                with base.conectar() as cx:
                    if vista == "flota":
                        mes = (params.get("mes") or [None])[0]
                        return self._responder(gom.jstr(comb.flota(cx, mes)))
                    return self._responder(gom.jstr(comb.panel(cx, estado)))
            except psycopg.errors.UndefinedTable:
                # Cuál de los dos SQL falta depende de qué se estaba
                # mirando: las vistas de la flota son de un archivo
                # posterior, y mandar a correr el que ya se corrió deja a
                # cualquiera dando vueltas.
                falta = ("gomeria/17_combustible_flota.sql" if vista == "flota"
                         else "gomeria/10_combustible.sql")
                return self._error(
                    f"Falta correr {falta} en el SQL Editor de Supabase.", 503)
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo leer el combustible: {e}", 500)

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

        # Las órdenes de trabajo del taller, con los totales ya sumados.
        if ruta == "/api/ordenes":
            if not self._exigir_sesion():
                return
            try:
                with base.conectar() as cx:
                    return self._responder(gom.jstr(ots.listar(cx, self.usuario)))
            except psycopg.errors.UndefinedTable:
                return self._error(
                    "Falta crear las tablas de órdenes de trabajo. Corré "
                    "gomeria/15_ordenes.sql en el SQL Editor de Supabase.", 503)
            except psycopg.errors.UndefinedColumn:
                return self._error(
                    "Falta actualizar las órdenes preventivas. Corré "
                    "gomeria/21_ordenes_preventivas.sql en el SQL Editor de Supabase.", 503)
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudieron leer las órdenes: {e}", 500)

        if ruta == "/api/alertas":
            if not self._exigir_sesion():
                return
            try:
                ver = (parse_qs(urlparse(self.path).query).get("silenciadas")
                       or ["0"])[0] in ("1", "true", "si")
                with base.conectar() as cx:
                    salida = alr.listar(cx, incluir_silenciadas=ver)
                    if salida.get("instalado"):
                        salida["services"] = alr.services(cx)
                        salida["unidades"] = cx.execute("""
                            select id, patente, interno, marca, modelo, km_actual
                            from unidades where activa order by patente""").fetchall()
                    return self._responder(gom.jstr(salida))
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudieron leer las alertas: {e}", 500)

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

    def do_DELETE(self):
        """Volver a la portada de la empresa."""
        if urlparse(self.path).path != "/api/fondo":
            return self._error("No existe", 404)
        if not self._exigir_sesion():
            return
        try:
            with base.conectar() as cx:
                salida = prefs.borrar_fondo(cx, self.usuario["id"])
                cx.commit()
            return self._responder(gom.jstr(salida))
        except Exception as e:
            traceback.print_exc()
            return self._error(f"No se pudo sacar la portada: {e}", 500)

    def do_POST(self):
        ruta = urlparse(self.path).path
        self.ruta_original = ruta
        if ruta == "/api/asistente":
            if not self._exigir_sesion():
                return
            # El navegador sólo puede iniciar consultas desde el mismo origen.
            origen = self.headers.get("Origin")
            if origen and urlparse(origen).netloc != self.headers.get("Host"):
                return self._error("Origen de consulta no permitido.", 403)
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._error("Se requiere JSON.", 415)
            try:
                largo = int(self.headers.get("Content-Length") or 0)
                if not 0 < largo <= 100000:
                    return self._error("La consulta es demasiado grande o está vacía.", 413)
                datos = json.loads(self.rfile.read(largo))
                return self._responder(gom.jstr(asistente.responder(datos, self.usuario)))
            except PermissionError as e:
                return self._error(str(e), 403)
            except asistente.Ocupado as e:
                return self._error(str(e), 429)
            except asistente.NoDisponible as e:
                return self._error(str(e), 503)
            except (ValueError, UnicodeError) as e:
                return self._error("Consulta inválida. Revisá el texto y su longitud.", 400)
            except Exception:
                return self._error("No se pudo completar la consulta. Intentá nuevamente.", 500)


        # Cómo quiere ver la aplicación este usuario.
        if ruta == "/api/preferencias":
            if not self._exigir_sesion():
                return
            try:
                largo = int(self.headers.get("Content-Length") or 0)
                datos = json.loads(self.rfile.read(largo) or b"{}")
                with base.conectar() as cx:
                    salida = prefs.guardar(cx, self.usuario["id"], datos)
                    cx.commit()
                return self._responder(gom.jstr(salida))
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudieron guardar las preferencias: {e}", 500)

        # La portada propia. Llega el archivo crudo, con su tipo en la
        # cabecera: no hace falta un formulario para una sola imagen.
        if ruta == "/api/fondo":
            if not self._exigir_sesion():
                return
            try:
                largo = int(self.headers.get("Content-Length") or 0)
                if largo > prefs.FONDO_MAXIMO + 1024:
                    # Se corta antes de leerla: no tiene sentido subir seis
                    # megas para después decir que no entra.
                    return self._error(
                        f"La imagen no puede pasar de "
                        f"{prefs.FONDO_MAXIMO // (1024 * 1024)} MB.", 413)
                cuerpo = self.rfile.read(largo)
                with base.conectar() as cx:
                    salida = prefs.guardar_fondo(
                        cx, self.usuario["id"], cuerpo,
                        self.headers.get("Content-Type"))
                    cx.commit()
                return self._responder(gom.jstr(salida))
            except ValueError as e:
                return self._error(str(e), 400)
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo guardar la portada: {e}", 500)

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
        # Las órdenes de trabajo. Una orden mueve stock, así que todo lo que
        # toca —el renglón y la salida del depósito— se guarda en la misma
        # transacción: o quedan las dos cosas o no queda ninguna.
        if ruta == "/api/ordenes":
            if not self._exigir_sesion():
                return
            try:
                largo = int(self.headers.get("Content-Length") or 0)
                if largo > 256 * 1024:
                    return self._error("El pedido es demasiado grande.", 413)
                datos = json.loads(self.rfile.read(largo) or b"{}")
                with base.conectar() as cx:
                    resultado = ots.aplicar(cx, datos, self.usuario)
                    cx.commit()
                return self._responder(gom.jstr(resultado))
            except PermissionError as e:
                return self._error(str(e), 403)
            except ValueError as e:
                return self._error(str(e))
            except psycopg.errors.UndefinedTable:
                return self._error(
                    "Falta crear las tablas de órdenes de trabajo. Corré "
                    "gomeria/15_ordenes.sql en el SQL Editor de Supabase.", 503)
            except psycopg.errors.UndefinedColumn:
                return self._error(
                    "Falta actualizar las órdenes preventivas. Corré "
                    "gomeria/21_ordenes_preventivas.sql en el SQL Editor de Supabase.", 503)
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo guardar la orden: {e}", 500)

        # La foto de la factura de un servicio externo. Va por su propia
        # dirección y no por /api/ordenes porque una foto de celular no
        # entra en los 256 KB que alcanzan para el resto.
        if ruta == "/api/factura":
            return self._leer_factura()

        if ruta == "/api/alertas":
            return self._alertas()

        if ruta == "/api/mantenimiento":
            if not self._exigir_sesion():
                return
            try:
                largo = int(self.headers.get("Content-Length") or 0)
                datos = json.loads(self.rfile.read(largo) or b"{}")
                with base.conectar() as cx:
                    salida = mant.aplicar(cx, datos, self.usuario)
                    cx.commit()
                return self._responder(gom.jstr(salida))
            except PermissionError as e:
                return self._error(str(e), 403)
            except ValueError as e:
                return self._error(str(e))
            except psycopg.errors.UniqueViolation:
                return self._error("Ya existe un plan con ese nombre.")
            except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
                return self._error("Falta crear los planes. Corré gomeria/22_planes_mantenimiento.sql en Supabase.", 503)
            except Exception as e:
                traceback.print_exc()
                return self._error(f"No se pudo guardar la parametrización: {e}", 500)

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

        # Los archivos llegan en base64 adentro del JSON. Es un archivo por
        # vez y de pocos cientos de filas: armar multipart para eso sería
        # cargar el servidor con un parseo que no hace falta.
        if ruta == "/api/combustible":
            return self._combustible()

        if ruta == "/api/unidades":
            return self._unidad_escribir()

        if ruta.startswith("/gomeria/api/"):
            self.path = ruta[len("/gomeria"):]
        return super().do_POST()


    def do_DELETE(self):
        ruta = urlparse(self.path).path
        self.ruta_original = ruta
        if ruta == "/api/unidades":
            return self._unidad_escribir(borrar=True)
        if ruta == "/api/combustible":
            return self._combustible(borrar=True)
        return self._error("No existe", 404)

    def _alertas(self):
        """Silenciar una alerta, cambiar un umbral o anotar un service.

        Las tres cambian lo que ve todo el mundo —una alerta silenciada
        deja de verse para todos—, así que las firma un encargado.
        """
        if not self._exigir_sesion():
            return
        if self.usuario["rol"] not in ("encargado", "admin"):
            return self._error("Solo un encargado o administrador puede tocar "
                               "las alertas.", 403)
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            if largo > 256 * 1024:
                return self._error("El pedido es demasiado grande.", 413)
            datos = json.loads(self.rfile.read(largo) or b"{}")
            op = (datos.get("op") or "").strip()
            with base.conectar() as cx:
                if op == "silenciar":
                    alr.silenciar(cx, datos.get("fuente"), datos.get("clave"),
                                  datos.get("motivo"), usuario=self.usuario["nombre"],
                                  hasta=datos.get("hasta") or None)
                elif op == "reactivar":
                    alr.reactivar(cx, datos.get("fuente"), datos.get("clave"))
                elif op == "reglas":
                    alr.guardar_reglas(cx, datos)
                elif op == "service_guardar":
                    alr.guardar_service(cx, datos, usuario=self.usuario["nombre"])
                elif op == "service_borrar":
                    alr.borrar_service(cx, datos.get("id"))
                else:
                    return self._error("No entiendo qué hay que hacer con la alerta.")
                cx.commit()
                salida = alr.listar(cx, incluir_silenciadas=bool(datos.get("ver_silenciadas")))
                salida["services"] = alr.services(cx)
                return self._responder(gom.jstr(salida))
        except PermissionError as e:
            return self._error(str(e), 403)
        except ValueError as e:
            return self._error(str(e))
        except psycopg.errors.UndefinedTable:
            return self._error("Falta crear las tablas de alertas. Corré "
                               "gomeria/20_alertas.sql en el SQL Editor de Supabase.", 503)
        except Exception as e:
            traceback.print_exc()
            return self._error(f"No se pudo guardar: {e}", 500)

    def _leer_factura(self):
        """Lee la factura de un servicio externo y propone los campos.

        No guarda nada: devuelve lo que entendió para que el encargado lo
        revise en el mismo formulario de siempre. Una factura mal leída que
        entra sola al historial de una unidad es peor que no tener la foto.
        """
        if not self._exigir_sesion():
            return
        if self.usuario["rol"] not in ("encargado", "admin"):
            return self._error("Solo un encargado o administrador puede cargar "
                               "un servicio externo.", 403)
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            # Cuatro hojas del tamaño máximo, más lo que agrega el base64.
            if largo > 68 * 1024 * 1024:
                return self._error("Las fotos pesan demasiado. Sacalas de nuevo "
                                   "con menos calidad.", 413)
            datos = json.loads(self.rfile.read(largo) or b"{}")
        except Exception:
            return self._error("El pedido llegó cortado. Probá de nuevo.")

        try:
            with base.conectar() as cx:
                # El listado de patentes de la flota viaja con la foto: es lo
                # que evita que una patente escrita a mano se lea al revés.
                patentes = [f["patente"] for f in cx.execute(
                    "select patente from unidades where activa").fetchall()]
            leido = facturas.leer(datos.get("archivos") or [], patentes=patentes)
            return self._responder(gom.jstr({"ok": True, "factura": leido}))
        except ValueError as e:
            return self._error(str(e))
        except anthropic.APIStatusError as e:
            return self._error(f"La API respondió {e.status_code}. Revisá la clave "
                               f"o el saldo.", 502)
        except anthropic.APIConnectionError:
            return self._error("No se pudo conectar con la API de Claude.", 502)
        except Exception as e:
            traceback.print_exc()
            return self._error(f"No se pudo leer la factura: {e}", 500)

    def _combustible(self, borrar=False):
        if not self._exigir_sesion():
            return
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            # Un listado de estación de 5.000 renglones no llega a 1 MB en
            # xlsx; 12 deja lugar de sobra sin dejar entrar cualquier cosa.
            if largo > 12 * 1024 * 1024:
                return self._error("El archivo es demasiado grande.", 413)
            datos = json.loads(self.rfile.read(largo) or b"{}")
            with base.conectar() as cx:
                if borrar:
                    salida = comb.borrar_lote(cx, datos.get("lote_id"), self.usuario)
                else:
                    salida = comb.subir(cx, datos, self.usuario)
                cx.commit()
            return self._responder(gom.jstr(salida))
        except PermissionError as e:
            return self._error(str(e), 403)
        except ValueError as e:
            return self._error(str(e))
        except psycopg.errors.UndefinedTable:
            return self._error(
                "Falta crear las tablas de combustible. Corré "
                "gomeria/10_combustible.sql en el SQL Editor de Supabase.", 503)
        except Exception as e:
            traceback.print_exc()
            return self._error(f"No se pudo procesar el archivo: {e}", 500)

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
            "órdenes de trabajo": ("ordenes_trabajo", "ordenes_tareas",
                                   "ordenes_repuestos"),
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
