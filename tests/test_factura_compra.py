"""Las altas por factura: el modelo propone, la persona decide.

El riesgo real no es que el modelo lea mal un número. Es que cree
duplicados: «FILTRO ACEITE», «FILTRO DE ACEITE» y «F. ACEITE» como tres
artículos distintos. Por eso de cada renglón sale lo que puede llegar a
ser —con un puntaje— y el alta la decide una persona.

En las cubiertas no hay catálogo contra qué comparar: cada goma es una
ficha nueva. Lo que falta ahí es el número de fuego, que el gomero graba
cuando la recibe.
"""
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import factura_compra as fc

CATALOGO = [
    {"codigo": "FIL-020", "descripcion": "Filtro de aceite R400",
     "rubro": "Mecánica", "codigo_interno": "W950"},
    {"codigo": "FIL-021", "descripcion": "Filtro de combustible R400",
     "rubro": "Mecánica", "codigo_interno": None},
    {"codigo": "COR-005", "descripcion": "Correa poly V 8PK",
     "rubro": "Mecánica", "codigo_interno": None},
]


class Parecidos(unittest.TestCase):
    def test_encuentra_el_mismo_escrito_distinto(self):
        r = fc.parecidos("FILTRO ACEITE SCANIA R400", CATALOGO)
        self.assertEqual(r[0]["codigo"], "FIL-020")

    def test_no_confunde_aceite_con_combustible(self):
        aceite = fc.parecidos("FILTRO DE ACEITE", CATALOGO)
        self.assertEqual(aceite[0]["codigo"], "FIL-020")
        combustible = fc.parecidos("FILTRO DE COMBUSTIBLE", CATALOGO)
        self.assertEqual(combustible[0]["codigo"], "FIL-021")

    def test_lo_que_no_se_parece_a_nada_no_propone_nada(self):
        """Proponer cualquier cosa es peor que no proponer: el que carga
        termina ignorando todas las propuestas."""
        self.assertEqual(fc.parecidos("CUBIERTA 295/80R22.5", CATALOGO), [])

    def test_ignora_tildes_y_mayusculas(self):
        self.assertTrue(fc.parecidos("filtro de aceite r400", CATALOGO))
        self.assertTrue(fc.parecidos("CORREA POLY V", CATALOGO))

    def test_el_vacio_no_propone(self):
        for valor in ("", None, "   "):
            with self.subTest(valor=valor):
                self.assertEqual(fc.parecidos(valor, CATALOGO), [])


class Emparejar(unittest.TestCase):
    def test_el_codigo_del_proveedor_manda(self):
        """Si coincide, es ese y no hay nada que adivinar."""
        r = fc.emparejar([{"descripcion": "cualquier cosa",
                           "codigo_proveedor": "W950"}], CATALOGO)
        self.assertEqual(r[0]["articulo"]["codigo"], "FIL-020")
        self.assertEqual(r[0]["por"], "codigo")

    def test_sin_codigo_propone_pero_no_decide(self):
        r = fc.emparejar([{"descripcion": "FILTRO ACEITE R400",
                           "codigo_proveedor": None}], CATALOGO)
        self.assertIsNone(r[0]["articulo"])
        self.assertEqual(r[0]["candidatos"][0]["codigo"], "FIL-020")

    def test_el_que_no_existe_queda_sin_candidatos(self):
        r = fc.emparejar([{"descripcion": "BUJE DE BARRA ESTABILIZADORA",
                           "codigo_proveedor": None}], CATALOGO)
        self.assertIsNone(r[0]["articulo"])
        self.assertEqual(r[0]["candidatos"], [])


class Resultado:
    def __init__(self, una=None):
        self.una = una

    def fetchone(self):
        return self.una


GESTOR = {"id": 1, "nombre": "Nicolás", "rol": "admin"}


class GuardarCubiertas(unittest.TestCase):
    class Base:
        def __init__(self, ya=0):
            self.ya = ya

        def execute(self, consulta, valores=()):
            if "count(*) as n from cubiertas" in consulta:
                return Resultado({"n": self.ya})
            raise AssertionError(f"Consulta inesperada: {consulta}")

    def guardar(self, renglones, ya=0, factura="0001-00001234"):
        altas = []

        def falsa(cx, codigo, **datos):
            altas.append((codigo, datos))
            return len(altas)

        with patch.object(fc, "permisos_gestiona", return_value=True), \
             patch("base.alta_cubierta", falsa):
            salida = fc.guardar_cubiertas(
                self.Base(ya), {"factura": factura, "renglones": renglones},
                GESTOR)
        return salida, altas

    def test_una_ficha_por_cubierta_no_una_por_renglon(self):
        """Cada goma tiene su vida propia: cuatro cubiertas son cuatro
        fichas, aunque la factura las traiga en un solo renglón."""
        salida, altas = self.guardar([
            {"marca": "MICHELIN", "medida": "295/80R22.5", "cantidad": 4,
             "costo_unitario": 520000}])
        self.assertEqual(salida["cargadas"], 4)
        self.assertEqual(len(altas), 4)

    def test_entran_sin_numero_de_fuego_y_lo_dice(self):
        salida, altas = self.guardar([
            {"marca": "FATE", "medida": "1000x20", "cantidad": 1}])
        self.assertTrue(altas[0][1]["codigo_provisorio"])
        self.assertIn("sin número de fuego", salida["aviso"])

    def test_el_codigo_sale_de_la_factura(self):
        _, altas = self.guardar([{"marca": "FATE", "medida": "1000x20",
                                  "cantidad": 2}])
        self.assertEqual([c for c, _ in altas],
                         ["FC-000100001234-01", "FC-000100001234-02"])

    def test_la_segunda_hoja_no_pisa_la_primera(self):
        """Se sigue numerando desde lo que ya entró de esa misma factura."""
        _, altas = self.guardar([{"marca": "FATE", "medida": "1000x20",
                                  "cantidad": 2}], ya=4)
        self.assertEqual([c for c, _ in altas],
                         ["FC-000100001234-05", "FC-000100001234-06"])

    def test_sin_factura_no_hay_codigo(self):
        with self.assertRaisesRegex(ValueError, "número de factura"):
            self.guardar([{"marca": "FATE"}], factura="")

    def test_el_renglon_omitido_no_entra(self):
        salida, altas = self.guardar([
            {"marca": "FATE", "medida": "1000x20", "cantidad": 1},
            {"marca": "X", "medida": "Y", "cantidad": 9, "omitir": True}])
        self.assertEqual(salida["cargadas"], 1)

    def test_el_costo_queda_en_la_ficha(self):
        _, altas = self.guardar([{"marca": "FATE", "medida": "1000x20",
                                  "cantidad": 1, "costo_unitario": 480000}])
        self.assertEqual(altas[0][1]["costo_compra"], 480000)


class LoQueLee(unittest.TestCase):
    def test_descarta_el_renglon_sin_descripcion(self):
        """El IVA y el total vienen como renglones y no son artículos."""
        leido = {"renglones": [
            {"descripcion": "Filtro de aceite", "cantidad": 2,
             "costo_unitario": 12500, "codigo_proveedor": "W950"},
            {"descripcion": "   ", "cantidad": None, "costo_unitario": None,
             "codigo_proveedor": None},
        ], "dudas": []}
        with patch.object(fc.lector, "preparar", return_value=[]), \
             patch.object(fc.lector, "preguntar", return_value=leido):
            salida = fc.leer_repuestos([{}])
        self.assertEqual(len(salida["renglones"]), 1)

    def test_la_cubierta_sin_marca_ni_medida_se_descarta(self):
        leido = {"renglones": [
            {"marca": "fate", "medida": "1000x20", "cantidad": 2,
             "costo_unitario": "480000,50", "modelo": None},
            {"marca": None, "medida": None, "cantidad": 1,
             "costo_unitario": None, "modelo": None},
        ], "dudas": []}
        with patch.object(fc.lector, "preparar", return_value=[]), \
             patch.object(fc.lector, "preguntar", return_value=leido):
            salida = fc.leer_cubiertas([{}])
        self.assertEqual(len(salida["renglones"]), 1)
        self.assertEqual(salida["renglones"][0]["marca"], "FATE")
        self.assertEqual(salida["renglones"][0]["costo_unitario"], 480000.50)

    def test_la_cubierta_sin_cantidad_es_una(self):
        leido = {"renglones": [{"marca": "FATE", "medida": "1000x20",
                                "cantidad": None, "costo_unitario": None,
                                "modelo": None}], "dudas": []}
        with patch.object(fc.lector, "preparar", return_value=[]), \
             patch.object(fc.lector, "preguntar", return_value=leido):
            salida = fc.leer_cubiertas([{}])
        self.assertEqual(salida["renglones"][0]["cantidad"], 1)


if __name__ == "__main__":
    unittest.main()
