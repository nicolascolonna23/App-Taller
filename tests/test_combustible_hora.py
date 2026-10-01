"""La hora de la carga, como viene en la planilla de tickets.

"no encontrado" es lo que escribe la planilla cuando el ticket no tenía
hora: tiene que quedar vacía, no como medianoche.
"""
import datetime
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import combustible as comb


class Hora(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(comb._hora("12:14"), datetime.time(12, 14))
        self.assertEqual(comb._hora("8:28"), datetime.time(8, 28))
        self.assertEqual(comb._hora(datetime.time(21, 5, 33)), datetime.time(21, 5))
        self.assertEqual(comb._hora(0.5), datetime.time(12, 0))

    def test_sin_hora(self):
        self.assertIsNone(comb._hora("no encontrado"))
        self.assertIsNone(comb._hora("", "22/04/2026"))
        self.assertIsNone(comb._hora(None, datetime.datetime(2026, 4, 22)))

    def test_pegada_a_la_fecha(self):
        self.assertEqual(comb._hora(None, "05/05/2026 08:28"), datetime.time(8, 28))
        self.assertEqual(comb._hora(None, datetime.datetime(2026, 5, 5, 8, 28)),
                         datetime.time(8, 28))

    def test_la_planilla_de_tickets(self):
        csv = ("Fecha,Hora,Nro Remito,Litros,Chofer,Patente,Odometro,Producto,Proveedor\n"
               "04/05/2026,12:14,152659,\"37,09\",Escobar,AE527FA,168910,INFINIA DIESEL,YPF\n"
               "22/04/2026,no encontrado,142575,630,Martinez,AE527FA,1,GNC,YPF\n").encode()
        filas = comb.leer("tickets.csv", csv)["filas"]
        self.assertEqual(filas[0]["hora"], datetime.time(12, 14))
        self.assertEqual(filas[0]["fecha"], datetime.date(2026, 5, 4))
        self.assertIsNone(filas[1]["hora"])


if __name__ == "__main__":
    unittest.main()
