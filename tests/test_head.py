"""Que un HEAD conteste lo mismo que el GET, sin el cuerpo.

En el log de Render se veía esto en cada arranque:

    code 501, message Unsupported method ('HEAD')
    "HEAD / HTTP/1.1" 501 -

El 501 es «este servidor no sabe hacer eso». Lo mandan el probe de
arranque de Render, los monitores de disponibilidad y cualquier `curl -I`,
y para todos ellos un 501 en la puerta de entrada es un servicio caído.

Un HEAD tiene que contestar el mismo código y los mismos encabezados que
el GET —el Content-Length incluido, que es para lo que se usa— y no
mandar el cuerpo.
"""
import http.client
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "gomeria"))
import app

CUERPO = b"<html>la portada</html>"


class Manejador(BaseHTTPRequestHandler):
    """Un GET cualquiera, con el HEAD de verdad de la aplicación."""

    timeout = 5
    do_HEAD = app.App.do_HEAD

    def do_GET(self):
        if self.path == "/no-existe":
            return self.send_error(404, "No hay nada acá")
        if self.path == "/de-a-pedazos":
            # Como los modelos 3D: varias escrituras después de los
            # encabezados. Ninguna tiene que salir.
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(CUERPO)))
            self.end_headers()
            for i in range(0, len(CUERPO), 5):
                self.wfile.write(CUERPO[i:i + 5])
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(CUERPO)))
        self.end_headers()
        self.wfile.write(CUERPO)

    def log_message(self, *a):
        pass


class Head(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.puerto = cls.servidor.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def pedir(self, metodo, ruta="/"):
        cx = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=5)
        cx.request(metodo, ruta)
        r = cx.getresponse()
        cuerpo = r.read()
        cx.close()
        return r, cuerpo

    def test_no_contesta_501(self):
        r, _ = self.pedir("HEAD")
        self.assertEqual(r.status, 200)

    def test_los_mismos_encabezados_que_el_get(self):
        cabeza, vacio = self.pedir("HEAD")
        entero, cuerpo = self.pedir("GET")
        self.assertEqual(cabeza.status, entero.status)
        self.assertEqual(cabeza.getheader("Content-Type"),
                         entero.getheader("Content-Type"))
        # El Content-Length es el del cuerpo que tendría, no cero: es el
        # dato por el que se pide un HEAD.
        self.assertEqual(cabeza.getheader("Content-Length"), str(len(CUERPO)))
        self.assertEqual(cuerpo, CUERPO)
        self.assertEqual(vacio, b"")

    def test_el_cuerpo_no_sale_ni_de_a_pedazos(self):
        r, cuerpo = self.pedir("HEAD", "/de-a-pedazos")
        self.assertEqual(r.status, 200)
        self.assertEqual(cuerpo, b"")
        self.assertEqual(r.getheader("Content-Length"), str(len(CUERPO)))

    def test_lo_que_no_esta_sigue_siendo_404(self):
        """El HEAD no inventa un 200: dice lo mismo que diría el GET."""
        r, cuerpo = self.pedir("HEAD", "/no-existe")
        self.assertEqual(r.status, 404)
        self.assertEqual(cuerpo, b"")

    def test_el_get_de_despues_sale_entero(self):
        """El tapón del cuerpo es de ese pedido y no queda puesto."""
        self.pedir("HEAD")
        r, cuerpo = self.pedir("GET")
        self.assertEqual(cuerpo, CUERPO)


if __name__ == "__main__":
    unittest.main()
