"""El freno a la fuerza bruta y el segundo factor.

Lo que se prueba: que el código de la app sea el del estándar (si no, el
celular y el servidor no se entienden), que un código no sirva dos veces,
que cambiar la IP en una cabecera no esquive el freno, y que sin la
migración la app siga dejando entrar.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import auth
import servidor


class SinTablas:
    """Una base que todavía no corrió 35_seguridad.sql."""

    def execute(self, consulta, valores=()):
        class R:
            def fetchone(self):
                return {"ok": False}
        return R()


class Totp(unittest.TestCase):
    # El secreto de los vectores de prueba del RFC 6238, en base32.
    SECRETO = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    def test_vectores_del_rfc(self):
        # El RFC da 8 dígitos; la app muestra los últimos 6.
        for instante, esperado in ((59, "94287082"), (1111111109, "07081804"),
                                   (1234567890, "89005924"), (2000000000, "69279037")):
            self.assertEqual(auth.totp_codigo(self.SECRETO, instante), esperado[-6:])

    def test_acepta_el_paso_de_al_lado(self):
        codigo = auth.totp_codigo(self.SECRETO, 1000 * 30)
        self.assertEqual(auth.totp_paso(self.SECRETO, codigo, instante=1001 * 30), 1000)
        self.assertIsNone(auth.totp_paso(self.SECRETO, codigo, instante=1003 * 30))

    def test_un_codigo_no_sirve_dos_veces(self):
        codigo = auth.totp_codigo(self.SECRETO, 1000 * 30)
        self.assertIsNone(auth.totp_paso(self.SECRETO, codigo, ultimo=1000, instante=1000 * 30))

    def test_rechaza_lo_que_no_es_un_codigo(self):
        for malo in ("", "12345", "1234567", "abcdef", None):
            self.assertIsNone(auth.totp_paso(self.SECRETO, malo))

    def test_uri_para_el_qr(self):
        uri = auth.totp_uri(self.SECRETO, "nico")
        self.assertTrue(uri.startswith("otpauth://totp/Pengui%3Anico?secret=" + self.SECRETO))

    def test_respaldo_no_depende_del_guion_ni_mayusculas(self):
        self.assertEqual(auth._hash_respaldo("abcd-efgh"), auth._hash_respaldo("ABCDEFGH"))


class Freno(unittest.TestCase):
    def setUp(self):
        auth._INTENTOS.clear()
        auth._SEGURIDAD = False

    def test_sin_migracion_cuenta_en_memoria(self):
        cx = SinTablas()
        cuenta = auth.clave_usuario("Nico")
        for _ in range(auth.LIMITES["usuario"] - 1):
            auth.anotar_fallo(cx, cuenta)
        self.assertEqual(auth.bloqueado(cx, cuenta), 0)
        auth.anotar_fallo(cx, cuenta)
        self.assertGreater(auth.bloqueado(cx, cuenta), 0)
        auth.limpiar_intentos(cx, cuenta)
        self.assertEqual(auth.bloqueado(cx, cuenta), 0)

    def test_la_cuenta_se_frena_aunque_cambie_la_ip(self):
        cx = SinTablas()
        cuenta = auth.clave_usuario("nico")
        for i in range(auth.LIMITES["usuario"]):
            auth.anotar_fallo(cx, auth.clave_ip(f"10.0.0.{i}"), cuenta)
        self.assertGreater(auth.bloqueado(cx, auth.clave_ip("10.0.0.99"), cuenta), 0)

    def test_sin_migracion_no_pide_segundo_factor(self):
        self.assertFalse(auth.pide_2fa(SinTablas(), {"id": 1, "rol": "admin"}))


class Origen(unittest.TestCase):
    def origen(self, cabeceras, entorno):
        h = servidor.Handler.__new__(servidor.Handler)
        h.headers = cabeceras
        h.client_address = ("192.0.2.1", 5000)
        with mock.patch.dict(os.environ, entorno, clear=True):
            return h._origen()

    def test_ignora_x_forwarded_for(self):
        self.assertEqual(self.origen({"X-Forwarded-For": "1.2.3.4"}, {}), "192.0.2.1")

    def test_en_render_usa_la_de_cloudflare(self):
        cab = {"X-Forwarded-For": "1.2.3.4", "True-Client-IP": "203.0.113.7"}
        self.assertEqual(self.origen(cab, {"RENDER": "true"}), "203.0.113.7")

    def test_cabecera_configurada(self):
        self.assertEqual(self.origen({"X-Real-IP": "203.0.113.8"},
                                     {"IP_CABECERA": "X-Real-IP"}), "203.0.113.8")


if __name__ == "__main__":
    unittest.main()
