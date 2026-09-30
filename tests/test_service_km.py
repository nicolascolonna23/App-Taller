"""Que un service cargado con el kilometraje equivocado no pase en silencio.

Pasó con la AF 470 UT. Se cargó un servicio externo preventivo el 28/09 con
405.265 km, cuando ese mismo día el satelital ya marcaba 585.763. El service
se guardó —la fila está en la base— pero la pantalla de control de servicios
siguió mostrando el de junio, y el que lo cargó no tuvo forma de enterarse.

Eran dos fallas encadenadas:

  1. La vista tomaba como «último service» el de más kilómetros, no el más
     reciente. El de junio tenía 525.962, así que le ganaba al nuevo y el
     nuevo desaparecía de la pantalla.
  2. Nada le avisó a nadie que 405.265 no podía ser: la unidad ya había
     pasado esa marca hacía meses.

Acá se fija la segunda. La primera vive en la vista (20_alertas.sql,
22_planes_mantenimiento.sql y 24_asignacion_services_y_km.sql) y se ve en el
estado 'km_dudoso', que existía desde el principio pero no se alcanzaba
nunca porque el orden por kilometraje lo tapaba.
"""
import datetime
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import alertas


class Resultado:
    def __init__(self, una=None):
        self.una = una

    def fetchone(self):
        return self.una

    def fetchall(self):
        return []


class Base:
    """La unidad, su plan y lo que marcaba el satelital."""

    def __init__(self, lectura=None):
        self.lectura = lectura
        self.consultas = []

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("select id, patente, km_actual from unidades"):
            return Resultado({"id": 9, "patente": "AF470UT", "km_actual": 586511})
        if sql.startswith("select p.cada_km from unidades"):
            return Resultado({"cada_km": 40000})
        if sql.startswith("select fecha, km from odometros"):
            return Resultado(self.lectura)
        if sql.startswith("select id from services where orden_id"):
            return Resultado(None)
        if sql.startswith("insert into services"):
            return Resultado({"id": 53})
        if sql.startswith(("delete", "update")):
            return Resultado()
        raise AssertionError(f"Consulta inesperada: {sql}")

    def guardo(self):
        return any(sql.startswith("insert into services")
                   for sql, _ in self.consultas)


DIA = datetime.date(2026, 9, 28)


class KilometrajeDelService(unittest.TestCase):
    def test_no_entra_con_menos_km_de_los_que_ya_tenia(self):
        """El caso real de la AF 470 UT."""
        cx = Base({"fecha": DIA, "km": 585762.97})
        with self.assertRaises(ValueError) as e:
            alertas.guardar_service(cx, {"unidad_id": 9, "fecha": "2026-09-28",
                                         "km": 405265})
        self.assertIn("405.265", str(e.exception))
        self.assertIn("585.763", str(e.exception))
        self.assertIn("AF470UT", str(e.exception))
        self.assertFalse(cx.guardo())

    def test_el_km_bueno_entra(self):
        cx = Base({"fecha": DIA, "km": 585762.97})
        self.assertEqual(
            alertas.guardar_service(cx, {"unidad_id": 9, "fecha": "2026-09-28",
                                         "km": 585763}), 53)
        self.assertTrue(cx.guardo())

    def test_una_carga_retroactiva_se_mide_contra_ese_dia(self):
        """El service viejo que aparece después sigue entrando.

        Se compara contra lo que el camión marcaba entonces, no contra lo
        que marca hoy: si no, cargar el service de junio con 525.962 sería
        imposible porque hoy tiene 586.511.
        """
        cx = Base({"fecha": datetime.date(2026, 6, 12), "km": 525000})
        self.assertEqual(
            alertas.guardar_service(cx, {"unidad_id": 9, "fecha": "2026-06-12",
                                         "km": 525962}), 53)
        self.assertTrue(cx.guardo())

    def test_sin_lectura_del_satelital_no_se_bloquea_nada(self):
        """La unidad sin equipo, o sin lecturas todavía, se carga a mano."""
        cx = Base(None)
        self.assertEqual(
            alertas.guardar_service(cx, {"unidad_id": 9, "fecha": "2026-09-28",
                                         "km": 405265}), 53)
        self.assertTrue(cx.guardo())

    def test_se_pregunta_por_la_lectura_de_la_fecha_del_service(self):
        """Y no por la última de todas."""
        cx = Base({"fecha": DIA, "km": 585762.97})
        alertas.guardar_service(cx, {"unidad_id": 9, "fecha": "2026-09-28",
                                     "km": 585763})
        sql, valores = next(x for x in cx.consultas
                            if x[0].startswith("select fecha, km from odometros"))
        self.assertIn("fecha <= coalesce(%s::date, current_date)", sql)
        self.assertEqual(valores, (9, "2026-09-28"))


if __name__ == "__main__":
    unittest.main()
