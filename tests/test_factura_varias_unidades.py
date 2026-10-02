"""Una factura de servicio que es de más de una unidad.

La de San Justo Neumáticos: dos cubiertas para PIQ468 y una para KSP007,
con la patente anotada a mano y a medias al lado de cada renglón.
"""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "gomeria"))
import facturas
import ordenes

FLOTA = ["PIQ468", "KSP007", "AD247MQ", "AH861UB"]


class PatenteAMedias(unittest.TestCase):
    def test_la_exacta_pasa(self):
        self.assertEqual(facturas._buscar_patente("ad 247 mq", FLOTA), "AD247MQ")

    def test_el_comienzo_que_encaja_con_una_sola(self):
        self.assertEqual(facturas._buscar_patente("PIQ", FLOTA), "PIQ468")

    def test_con_una_letra_de_mas(self):
        self.assertEqual(facturas._buscar_patente("AKSP007", FLOTA), "KSP007")

    def test_si_encaja_con_dos_no_se_adivina(self):
        self.assertIsNone(facturas._buscar_patente("A", FLOTA))
        self.assertIsNone(facturas._buscar_patente("AH8", FLOTA + ["AH842GQ"]))


class Reparto(unittest.TestCase):
    def test_el_total_se_reparte_como_el_subtotal(self):
        u = facturas._repartir([
            {"patente": "PIQ", "detalle": "2 cubiertas 205/75 R16", "importe": 391812},
            {"patente": "AKSP007", "detalle": "1 cubierta 205/70 R15", "importe": 166531},
        ], 686761.89, FLOTA)
        self.assertEqual([x["patente"] for x in u], ["PIQ468", "KSP007"])
        self.assertAlmostEqual(sum(x["monto"] for x in u), 686761.89, places=2)
        self.assertAlmostEqual(u[0]["monto"], 481928.76, places=2)

    def test_la_misma_unidad_dos_veces_se_junta(self):
        u = facturas._repartir([
            {"patente": "PIQ468", "detalle": "a", "importe": 100},
            {"patente": "PIQ468", "detalle": "b", "importe": 50},
        ], 181.5, FLOTA)
        self.assertEqual(len(u), 1)
        self.assertEqual(u[0]["monto"], 181.5)
        self.assertEqual(u[0]["detalle"], "a; b")

    def test_sin_importe_no_se_inventa_el_reparto(self):
        u = facturas._repartir([
            {"patente": "PIQ468", "detalle": None, "importe": None},
            {"patente": "KSP007", "detalle": None, "importe": 10},
        ], 100, FLOTA)
        self.assertTrue(all(x["monto"] is None for x in u))

    def test_la_patente_ajena_se_descarta(self):
        u = facturas._repartir([{"patente": "ZZZ999", "detalle": None, "importe": 1}], 1, FLOTA)
        self.assertEqual(u, [])


class VariasOrdenes(unittest.TestCase):
    def setUp(self):
        self.llamadas = []
        self.original = ordenes.externa

        def falsa(cx, datos, usuario):
            self.llamadas.append(datos)
            if datos.get("unidad_id") == 99:
                raise ValueError("Falta el monto de la factura.")
            return {"ok": True, "id": len(self.llamadas), "numero": 100 + len(self.llamadas)}
        ordenes.externa = falsa

    def tearDown(self):
        ordenes.externa = self.original

    def test_una_orden_por_unidad_con_lo_comun(self):
        r = ordenes.externas(None, {
            "op": "externas", "factura": "0006-00028979", "taller": "San Justo",
            "fecha": "2026-09-28", "mantenimiento": "correctivo",
            "unidades": [{"unidad_id": 1, "monto": 10, "km": 5},
                         {"unidad_id": 2, "monto": 20, "km": 6}]}, {})
        self.assertEqual(len(r["ordenes"]), 2)
        self.assertEqual([c["factura"] for c in self.llamadas], ["0006-00028979"] * 2)
        self.assertEqual([c["mantenimiento"] for c in self.llamadas], ["correctivo"] * 2)
        self.assertEqual([c["monto"] for c in self.llamadas], [10, 20])
        self.assertNotIn("unidades", self.llamadas[0])

    def test_lo_de_cada_unidad_no_pisa_lo_comun(self):
        ordenes.externas(None, {"factura": "1", "unidades": [
            {"unidad_id": 1, "factura": "otra"}, {"unidad_id": 2}]}, {})
        self.assertEqual(self.llamadas[0]["factura"], "1")

    def test_la_misma_unidad_dos_veces_no(self):
        with self.assertRaises(ValueError):
            ordenes.externas(None, {"unidades": [{"unidad_id": 1}, {"unidad_id": 1}]}, {})

    def test_el_error_dice_de_que_unidad_es(self):
        with self.assertRaisesRegex(ValueError, "Unidad 2"):
            ordenes.externas(None, {"unidades": [{"unidad_id": 1}, {"unidad_id": 99}]}, {})

    def test_sin_unidades_no(self):
        with self.assertRaises(ValueError):
            ordenes.externas(None, {"unidades": []}, {})


if __name__ == "__main__":
    unittest.main()
