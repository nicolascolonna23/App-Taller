"""Que lo que llega del satelital se entienda antes de guardarlo.

La lectura en sí necesita un navegador y la sesión de Hawk, así que no se
prueba acá. Lo que sí se prueba es todo lo que se hace con la respuesta, que
es donde estuvieron los errores: una fecha en el formato raro de .NET, una
patente escrita de tres maneras distintas y las filas de los equipos que no
contestaron, que no son lecturas de cero kilómetros.
"""
import sys
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "gomeria"))
import hawk
import subir_odometros as subir


class Hawk(unittest.TestCase):
    def test_fecha_dotnet_en_hora_argentina(self):
        # 1789128000000 son las 12:00 UTC del 11/09/2026: acá, las 09:00.
        self.assertEqual(hawk._reporte("/Date(1789128000000)/"), "2026-09-11 09:00:00")
        self.assertIsNone(hawk._reporte(""))
        self.assertIsNone(hawk._reporte("11/09/2026"))

    def test_patente_normalizada_y_erratas_corregidas(self):
        self.assertEqual(hawk._patente("AE 527 FA"), "AE527FA")
        self.assertEqual(hawk._patente("vxo389_(*)"), "VXO389")
        self.assertEqual(hawk._patente("AF527AE"), "AE527FA")
        self.assertEqual(hawk._patente(None), "")


class Carga(unittest.TestCase):
    def lectura(self, **cambios):
        fila = {"Patente": "AE527FA", "Kilometraje": 120000.5,
                "Ultimo_reporte": "2026-09-14 08:15:00", "idGPS": 29627,
                "Fecha_lectura": "2026-09-14 08:31:02"}
        fila.update(cambios)
        return fila

    def test_la_lista_del_scraper_se_carga_como_el_csv(self):
        (patente, fecha, km, reporte, gps), = subir.filas_de([self.lectura()])
        self.assertEqual((patente, fecha, km), ("AE527FA", date(2026, 9, 14), 120000.5))
        self.assertEqual(reporte.hour, 8)
        self.assertEqual(gps, "29627")

    def test_el_equipo_que_no_contesto_no_es_una_lectura(self):
        self.assertEqual(subir.filas_de([self.lectura(Kilometraje=None),
                                         self.lectura(Kilometraje=0)]), [])

    def test_dos_lecturas_del_mismo_dia_dejan_una_sola(self):
        filas = subir.filas_de([self.lectura(Kilometraje=100),
                                self.lectura(Kilometraje=140)])
        self.assertEqual([f[2] for f in filas], [140])

    def test_el_portatil_que_no_es_una_unidad_se_guarda_igual(self):
        (fila,) = subir.filas_de([self.lectura(Patente="PORTATIL0134")])
        self.assertEqual(fila[0], "PORTATIL0134")


if __name__ == "__main__":
    unittest.main()
