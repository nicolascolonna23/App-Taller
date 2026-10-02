"""La factura del recapador se cruza contra lo que el sistema sabe que mandó.

El recapador factura por goma, con el número de fuego en cada renglón. Eso
es lo que hace que esto se pueda verificar: no hay que creerle al modelo,
porque lo que leyó se compara contra los envíos abiertos.

    fuego en la factura y en un envío abierto → volvió
    fuego en la factura que no salió nunca    → algo está mal
    fuego que salió y no está en la factura   → ésa no volvió

El último es el que importa y el que no existía. Si se mandaron doce y la
factura trae diez, las dos que faltan quedan señaladas.
"""
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import recapado
import factura_recapado


AFUERA = [
    {"codigo": "4521", "cubierta_id": 1, "envio_id": "REC-00007", "dias_afuera": 8},
    {"codigo": "4522", "cubierta_id": 2, "envio_id": "REC-00007", "dias_afuera": 8},
    {"codigo": "4523", "cubierta_id": 3, "envio_id": "REC-00007", "dias_afuera": 8},
]
GESTOR = {"id": 1, "nombre": "Nicolás", "rol": "admin"}


class Filas:
    def __init__(self, filas):
        self.filas = filas

    def fetchall(self):
        return self.filas


class Base:
    def __init__(self, afuera=None):
        self.afuera = AFUERA if afuera is None else afuera

    def execute(self, consulta, valores=()):
        if "v_recapado_afuera" in consulta:
            return Filas(self.afuera)
        raise AssertionError(f"Consulta inesperada: {consulta}")


def cotejar(renglones, afuera=None, **extra):
    leido = {"factura": "0001-00001234", "fecha": "2026-10-01",
             "renglones": renglones, "dudas": []}
    leido.update(extra)
    with patch.object(factura_recapado, "leer", return_value=leido):
        return recapado.cotejar(Base(afuera), {"archivos": [{}]}, GESTOR)


def r(codigo, costo=38000, banda="BDR-HT"):
    return {"codigo_fuego": codigo, "costo": costo, "banda": banda}


class ElCruce(unittest.TestCase):
    def test_lo_que_coincide_vuelve(self):
        salida = cotejar([r("4521"), r("4522"), r("4523")])
        self.assertEqual([x["codigo"] for x in salida["vuelven"]],
                         ["4521", "4522", "4523"])
        self.assertEqual(salida["faltan"], [])
        self.assertEqual(salida["desconocidas"], [])

    def test_la_que_no_esta_en_la_factura_queda_senalada(self):
        """Se mandaron tres y la factura trae dos: la tercera no volvió."""
        salida = cotejar([r("4521"), r("4522")])
        self.assertEqual([x["codigo"] for x in salida["faltan"]], ["4523"])

    def test_la_que_no_salio_de_aca_se_avisa(self):
        """Puede ser una goma que entró por otro lado, o un fuego mal leído."""
        salida = cotejar([r("4521"), r("9999")])
        self.assertEqual(len(salida["desconocidas"]), 1)
        self.assertEqual(salida["desconocidas"][0]["codigo_fuego"], "9999")
        # Y las otras dos siguen contando como que no volvieron.
        self.assertEqual([x["codigo"] for x in salida["faltan"]],
                         ["4522", "4523"])

    def test_la_misma_goma_dos_veces_se_cobra_una(self):
        """Dos renglones con el mismo fuego es un error de carga, no dos
        recapados."""
        salida = cotejar([r("4521"), r("4521")])
        self.assertEqual(len(salida["vuelven"]), 1)
        self.assertTrue(salida["desconocidas"][0].get("repetida"))

    def test_el_costo_y_la_banda_viajan(self):
        salida = cotejar([r("4521", costo=41500, banda="R250")])
        self.assertEqual(salida["vuelven"][0]["costo"], 41500)
        self.assertEqual(salida["vuelven"][0]["banda"], "R250")
        # Y con el renglón viene de qué envío era.
        self.assertEqual(salida["vuelven"][0]["envio_id"], "REC-00007")

    def test_las_dudas_del_modelo_llegan(self):
        salida = cotejar([r("4521")], dudas=["El tercer renglón está borroso."])
        self.assertEqual(len(salida["dudas"]), 1)

    def test_sin_nada_afuera_no_hay_contra_que_cotejar(self):
        with self.assertRaisesRegex(ValueError, "no hay contra qué cotejar"):
            cotejar([r("4521")], afuera=[])

    def test_lo_firma_un_gestor(self):
        with self.assertRaises(PermissionError):
            recapado.cotejar(Base(), {"archivos": [{}]}, {"rol": "consulta"})

    def test_no_guarda_nada(self):
        """Arma el cuadro para que una persona lo mire. Guardar es otro
        paso, el de recibir()."""
        leido = {"factura": "X", "fecha": None, "renglones": [r("4521")],
                 "dudas": []}

        class Espia(Base):
            def __init__(self):
                super().__init__()
                self.escribio = []

            def execute(self, consulta, valores=()):
                if consulta.strip().lower().startswith(("insert", "update", "delete")):
                    self.escribio.append(consulta)
                return super().execute(consulta, valores)

        cx = Espia()
        with patch.object(factura_recapado, "leer", return_value=leido):
            recapado.cotejar(cx, {"archivos": [{}]}, GESTOR)
        self.assertEqual(cx.escribio, [])


class LoQueLee(unittest.TestCase):
    """El prompt le pasa los fuegos que están afuera, para que elija entre
    los que existen en vez de adivinar el OCR."""

    def test_los_codigos_van_en_las_instrucciones(self):
        texto = factura_recapado._instrucciones(["4521", "4522"])
        self.assertIn("4521", texto)
        self.assertIn("4522", texto)

    def test_sin_codigos_lo_dice(self):
        self.assertIn("no hay ninguna afuera",
                      factura_recapado._instrucciones([]))

    def test_normaliza_lo_que_vuelve_del_modelo(self):
        leido = {"renglones": [
            {"codigo_fuego": " 4521 ", "costo": "38000,50", "banda": " bdr-ht "},
            {"codigo_fuego": "", "costo": None, "banda": None},
        ], "dudas": [None, "una duda"]}
        with patch.object(factura_recapado.lector, "preparar", return_value=[]), \
             patch.object(factura_recapado.lector, "preguntar", return_value=leido):
            salida = factura_recapado.leer([{}], ["4521"])
        self.assertEqual(salida["renglones"][0]["codigo_fuego"], "4521")
        self.assertEqual(salida["renglones"][0]["costo"], 38000.50)
        self.assertEqual(salida["renglones"][0]["banda"], "BDR-HT")
        self.assertIsNone(salida["renglones"][1]["codigo_fuego"])
        self.assertEqual(salida["dudas"], ["una duda"])


if __name__ == "__main__":
    unittest.main()
