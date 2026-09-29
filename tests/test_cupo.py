"""Que el tope de pedidos cuente pedidos y no conexiones.

El tope nació para que un pico de visitas no volteara el servicio por
memoria. Puesto sobre la conexión hizo lo contrario: como cada archivo de
una pantalla viaja en su propia conexión, abrir la portada agotaba el cupo
entero y el resto esperaba hasta que el proxy cortaba con un 502. Peor: una
conexión que el navegador abre por las dudas y no usa retenía su lugar sin
hacer nada.

Estas pruebas fijan las tres cosas que tienen que valer: el turno se toma
recién cuando hay un pedido, se devuelve siempre, y una conexión ociosa no
le saca el lugar a nadie.
"""
import http.client
import socket
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "gomeria"))
import app


class Manejador(app.CupoPorPedido, BaseHTTPRequestHandler):
    """Lo mínimo para contestar, con el turno de verdad de la aplicación."""
    timeout = 5
    cupo = None
    dentro = None          # cuántos pedidos hay adentro ahora mismo
    tope_visto = 0         # el máximo que llegó a haber a la vez

    def do_GET(self):
        with Manejador.candado:
            Manejador.dentro += 1
            Manejador.tope_visto = max(Manejador.tope_visto, Manejador.dentro)
        Manejador.adentro.wait(.4) if self.path == "/lento" else None
        with Manejador.candado:
            Manejador.dentro -= 1
        if self.path == "/romper":
            raise RuntimeError("revienta a propósito")
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass

    def handle_error(self, *a):
        pass          # la prueba de "revienta" lo hace a propósito


class Cupo(unittest.TestCase):
    def setUp(self):
        Manejador.candado = threading.Lock()
        Manejador.adentro = threading.Event()
        Manejador.dentro = 0
        Manejador.tope_visto = 0
        self.semaforo = threading.BoundedSemaphore(2)
        Manejador.cupo = self.semaforo
        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self.servidor.daemon_threads = True
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.puerto = self.servidor.server_address[1]

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()

    def pedir(self, ruta="/"):
        c = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=5)
        c.request("GET", ruta)
        r = c.getresponse()
        r.read()
        c.close()
        return r.status

    def libres(self):
        """Cuántos turnos quedan sin usar."""
        n = 0
        while self.semaforo.acquire(blocking=False):
            n += 1
        for _ in range(n):
            self.semaforo.release()
        return n

    def test_el_turno_se_devuelve_despues_de_responder(self):
        for _ in range(6):                      # el triple del cupo
            self.assertEqual(self.pedir(), 200)
        self.assertEqual(self.libres(), 2, "el cupo tiene que quedar entero")

    def test_el_turno_se_devuelve_aunque_el_pedido_reviente(self):
        for _ in range(4):
            try:
                self.pedir("/romper")
            except Exception:
                pass                            # la conexión se corta: da igual
        self.assertEqual(self.libres(), 2,
                         "un pedido que falla no puede quedarse con el turno")

    def test_una_conexion_ociosa_no_ocupa_turno(self):
        """Lo que rompía: el navegador abre conexiones y no las usa."""
        ociosas = []
        for _ in range(4):                      # el doble del cupo
            s = socket.create_connection(("127.0.0.1", self.puerto))
            ociosas.append(s)                   # abiertas y calladas
        self.assertEqual(self.libres(), 2, "abrir no es pedir")
        self.assertEqual(self.pedir(), 200, "el pedido real tiene que pasar")
        for s in ociosas:
            s.close()

    def test_no_se_atienden_mas_pedidos_que_el_tope(self):
        hilos = [threading.Thread(target=self.pedir, args=("/lento",))
                 for _ in range(6)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=10)
        self.assertLessEqual(Manejador.tope_visto, 2,
                             "nunca puede haber más pedidos adentro que el tope")


if __name__ == "__main__":
    unittest.main()
