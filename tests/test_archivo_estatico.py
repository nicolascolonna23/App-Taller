"""Que un archivo estático se mande de a pedazos y no entero a memoria.

Los modelos 3D pesan hasta 3,5 MB. Leídos enteros, cada pedido reservaba
todo eso de una sola vez, y con varias pantallas abiertas al mismo tiempo
el servidor se quedaba sin memoria y lo mataban: eso es el 503 que veía el
usuario. Mandándolo de a 64 KB, lo que ocupa un pedido ya no depende de lo
que pese el archivo.

Estas pruebas fijan las tres cosas que tienen que valer: llega el archivo
completo, llega en varios pedazos, y que el navegador corte la bajada a la
mitad no es un error del servidor.
"""
import http.client
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "gomeria"))
import app


class Contador:
    """Se pone en lugar del wfile para saber de a cuánto se escribió."""

    def __init__(self, real):
        self.real = real
        self.pedazos = []

    def write(self, datos):
        self.pedazos.append(len(datos))
        return self.real.write(datos)

    def __getattr__(self, nombre):
        return getattr(self.real, nombre)


class Manejador(BaseHTTPRequestHandler):
    """Lo mínimo para contestar, con el envío de verdad de la aplicación."""

    timeout = 5
    archivo = None
    BLOQUE = app.App.BLOQUE
    _enviar_archivo = app.App._enviar_archivo

    def setup(self):
        super().setup()
        self.wfile = Contador(self.wfile)

    def do_GET(self):
        self._enviar_archivo(Manejador.archivo, "application/octet-stream",
                             "public, max-age=604800")
        # El encabezado sale de un write suelto; los del cuerpo son los que
        # pesan lo que pesa un bloque.
        Manejador.escrituras = [n for n in self.wfile.pedazos
                                if n and n <= self.BLOQUE]

    def log_message(self, *a):
        pass


class ArchivoEstatico(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.carpeta = tempfile.TemporaryDirectory()
        cls.camino = os.path.join(cls.carpeta.name, "modelo.glb")
        # Tres bloques y pico: tiene que viajar en más de un pedazo.
        cls.datos = os.urandom(app.App.BLOQUE * 3 + 1234)
        with open(cls.camino, "wb") as f:
            f.write(cls.datos)
        Manejador.archivo = cls.camino

        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        cls.hilo = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        cls.hilo.start()
        cls.puerto = cls.servidor.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.carpeta.cleanup()

    def pedir(self):
        cx = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=5)
        cx.request("GET", "/modelo.glb")
        return cx, cx.getresponse()

    def test_llega_entero(self):
        cx, r = self.pedir()
        cuerpo = r.read()
        cx.close()
        self.assertEqual(r.status, 200)
        self.assertEqual(cuerpo, self.datos)
        self.assertEqual(r.getheader("Content-Length"), str(len(self.datos)))
        self.assertEqual(r.getheader("Content-Type"), "application/octet-stream")
        self.assertEqual(r.getheader("Cache-Control"), "public, max-age=604800")

    def test_va_de_a_pedazos(self):
        cx, r = self.pedir()
        r.read()
        cx.close()
        # Cuatro bloques para un archivo de tres y pico. Lo que importa es
        # que ninguno pese el archivo entero.
        self.assertGreater(len(Manejador.escrituras), 1)
        self.assertLessEqual(max(Manejador.escrituras), app.App.BLOQUE)

    def test_el_navegador_que_corta_no_es_un_error(self):
        """La pestaña que se cierra a mitad de la bajada no ensucia el log."""

        class Cortado:
            close_connection = False
            BLOQUE = app.App.BLOQUE

            def send_response(self, *a): pass
            def send_header(self, *a): pass
            def end_headers(self): pass

            class wfile:
                @staticmethod
                def write(datos):
                    raise BrokenPipeError("el navegador cerró")

        falso = Cortado()
        app.App._enviar_archivo(falso, self.camino, "application/octet-stream")
        self.assertTrue(falso.close_connection)


if __name__ == "__main__":
    unittest.main()
