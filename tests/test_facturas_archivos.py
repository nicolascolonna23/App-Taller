"""Que la factura llegue al modelo sin pasar tres veces por la memoria.

El servidor se quedaba sin memoria y Render lo reiniciaba: eso es el 503 y
el «Respuesta ilegible del servidor» que devolvían las pantallas mientras
tanto. Medido, una factura de cuatro hojas de 12 MB costaba 184 MB de un
saque, porque el archivo se abría (b64decode) y se volvía a cerrar
(b64encode) para mandar exactamente el mismo base64 que había llegado: tres
copias del mismo archivo vivas al mismo tiempo.

Ahora se manda tal como vino. Estas pruebas fijan que eso siga valiendo y
que la validación que reemplazó al decode no deje pasar ni rechace de más.
"""
import base64
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import facturas

FOTO = base64.b64encode(b"\xff\xd8\xff" + b"x" * 997).decode()   # 1000 bytes


class Corta(RuntimeError):
    """Llegamos al modelo. De acá para adelante no es lo que se prueba."""


def leer(*archivos, **kw):
    """facturas.leer() hasta el modelo, sin llamarlo."""
    return facturas.leer(list(archivos), **kw)


def hasta_el_modelo(*archivos):
    """Lo que se le termina mandando al modelo, o el ValueError de la validación.

    Se pasa siempre un cliente falso: sin él, la falta de la clave de la
    API tira su propio ValueError y taparía el que se está probando.
    """
    visto = {}

    class Falso:
        class messages:
            @staticmethod
            def create(**kw):
                visto.update(kw)
                raise Corta()

    try:
        leer(*archivos, cliente=Falso())
    except Corta:
        return visto["messages"][0]["content"]
    raise AssertionError("no llegó al modelo y tampoco falló")


class Archivos(unittest.TestCase):
    def armar(self, contenido, tipo="image/jpeg"):
        return {"tipo": tipo, "contenido": contenido, "nombre": "f.jpg"}

    def test_el_contenido_viaja_sin_tocar(self):
        """El mismo texto que llegó, y el mismo objeto: no se copió nada."""
        partes = hasta_el_modelo(self.armar(FOTO))
        self.assertEqual(partes[0]["source"]["data"], FOTO)
        self.assertIs(partes[0]["source"]["data"], FOTO)

    def test_el_pdf_viaja_como_documento(self):
        partes = hasta_el_modelo(self.armar(FOTO, tipo="application/pdf"))
        self.assertEqual(partes[0]["type"], "document")
        self.assertIs(partes[0]["source"]["data"], FOTO)

    def test_lo_que_pesa_de_mas_se_rechaza(self):
        grande = "A" * ((facturas.MAXIMO + 3 * 1024 * 1024) // 3 * 4)
        with self.assertRaisesRegex(ValueError, "máximo"):
            leer(self.armar(grande))

    def test_lo_que_entra_justo_no_se_rechaza(self):
        justo = "A" * (facturas.MAXIMO // 3 * 4)
        self.assertIs(hasta_el_modelo(self.armar(justo))[0]["source"]["data"], justo)

    def test_el_vacio_dice_que_esta_vacio(self):
        for valor in ("", None):
            with self.subTest(valor=valor), \
                 self.assertRaisesRegex(ValueError, "vac"):
                leer(self.armar(valor))

    def test_el_cortado_dice_que_esta_cortado(self):
        for roto in ("no es base64!!", FOTO[:-1], "AAA"):
            with self.subTest(roto=roto), \
                 self.assertRaisesRegex(ValueError, "cortado"):
                leer(self.armar(roto))

    def test_acepta_el_base64_partido_en_lineas(self):
        porpartes = "\n".join(FOTO[i:i+76] for i in range(0, len(FOTO), 76))
        partes = hasta_el_modelo(self.armar(porpartes))
        self.assertEqual(partes[0]["source"]["data"], FOTO)

    def test_acepta_el_data_uri_entero(self):
        partes = hasta_el_modelo(self.armar("data:image/jpeg;base64," + FOTO))
        self.assertEqual(partes[0]["source"]["data"], FOTO)

    def test_el_tipo_que_no_va_se_rechaza(self):
        with self.assertRaisesRegex(ValueError, "foto"):
            leer(self.armar(FOTO, tipo="application/zip"))

    def test_sin_archivos_no_se_llama_al_modelo(self):
        with self.assertRaisesRegex(ValueError, "ninguna imagen"):
            leer()

    def test_mas_de_cuatro_hojas_se_rechaza(self):
        with self.assertRaisesRegex(ValueError, "cuatro"):
            leer(*[self.armar(FOTO)] * 5)


class CuentaDelTamano(unittest.TestCase):
    """La cuenta que reemplazó al decode tiene que dar lo mismo que el decode."""

    def test_da_el_tamano_real(self):
        for largo in range(1, 200):
            crudo = b"x" * largo
            b64 = base64.b64encode(crudo).decode()
            pesa = len(b64) // 4 * 3 - b64[-2:].count("=")
            with self.subTest(largo=largo):
                self.assertEqual(pesa, len(crudo))


if __name__ == "__main__":
    unittest.main()
