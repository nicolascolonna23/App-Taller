"""Los KPI de costo del taller: gasto por patente y pesos por kilómetro."""
from datetime import date, timedelta
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gomeria"))
import kpi_ordenes as kpi
from inicio import _ordenes_costos

DESDE, HASTA = date(2025, 10, 1), date(2026, 9, 14)


def orden(patente, fecha, total, mantenimiento="correctivo", **extra):
    fila = {"patente": patente, "fecha": fecha, "total": total,
            "mantenimiento": mantenimiento, "estado": "cerrada",
            "tipo": "interna", "interno": None, "marca": None, "modelo": None}
    fila.update(extra)
    return fila


def km(patente, kilometros, desde=DESDE, hasta=HASTA):
    return {"patente": patente, "km": kilometros,
            "desde": desde, "hasta": hasta, "dias": 300}


class Kpi(unittest.TestCase):
    def test_gasto_por_patente_suma_internas_y_externas(self):
        salida = kpi.calcular([
            orden("AD247MQ", date(2026, 2, 3), 150000),
            orden("AD247MQ", date(2026, 5, 9), 50000, "preventivo",
                  tipo="externa"),
            orden("AB123CD", date(2026, 5, 9), 90000),
        ], [], DESDE, HASTA)
        primera = salida["unidades"][0]
        self.assertEqual(primera["patente"], "AD247MQ")
        self.assertEqual(primera["total"], 200000)
        self.assertEqual(primera["correctivo"], 150000)
        self.assertEqual(primera["preventivo"], 50000)
        self.assertEqual(salida["gasto"]["total"], 290000)
        self.assertEqual(salida["gasto"]["unidades"], 2)

    def test_anuladas_no_son_gasto(self):
        salida = kpi.calcular([
            orden("AD247MQ", date(2026, 2, 3), 150000, estado="anulada"),
            orden("AD247MQ", date(2026, 2, 4), 10000),
        ], [], DESDE, HASTA)
        self.assertEqual(salida["gasto"]["total"], 10000)
        self.assertEqual(salida["gasto"]["ordenes"], 1)

    def test_pesos_por_kilometro_separa_preventivo_de_correctivo(self):
        salida = kpi.calcular([
            orden("AD247MQ", date(2026, 2, 3), 200000),
            orden("AD247MQ", date(2026, 3, 3), 100000, "preventivo"),
        ], [km("AD247MQ", 100000)], DESDE, HASTA)
        unidad = salida["unidades"][0]
        self.assertEqual(unidad["pesos_km_correctivo"], 2.0)
        self.assertEqual(unidad["pesos_km_preventivo"], 1.0)
        self.assertEqual(unidad["pesos_km"], 3.0)
        self.assertEqual(salida["flota"]["pesos_km_correctivo"], 2.0)
        self.assertEqual(salida["flota"]["pesos_km_preventivo"], 1.0)
        self.assertEqual(salida["flota"]["km"], 100000)

    def test_la_flota_pondera_por_kilometro_y_no_promedia_unidades(self):
        """Un utilitario que hizo 5.000 km no vale lo mismo que un camión
        que hizo 95.000: el peso por kilómetro de la flota es la plata
        sobre los kilómetros, no el promedio de los dos números."""
        salida = kpi.calcular([
            orden("AD247MQ", date(2026, 2, 3), 950000),
            orden("AB123CD", date(2026, 2, 3), 50000),
        ], [km("AD247MQ", 95000), km("AB123CD", 5000)], DESDE, HASTA)
        self.assertEqual(salida["flota"]["pesos_km_correctivo"], 10.0)

    def test_solo_divide_el_gasto_que_los_kilometros_explican(self):
        """La orden de octubre queda afuera del peso por kilómetro porque
        el satelital recién empezó a leer esa unidad en marzo. Dividir un
        año de gasto por seis meses de kilómetros es inventar un número."""
        salida = kpi.calcular([
            orden("AD247MQ", date(2025, 10, 15), 400000),
            orden("AD247MQ", date(2026, 4, 10), 200000),
        ], [km("AD247MQ", 100000, desde=date(2026, 3, 1))], DESDE, HASTA)
        unidad = salida["unidades"][0]
        self.assertEqual(unidad["total"], 600000)
        self.assertEqual(unidad["pesos_km_correctivo"], 2.0)
        self.assertTrue(unidad["parcial"])

    def test_sin_lecturas_hay_gasto_pero_no_hay_peso_por_kilometro(self):
        salida = kpi.calcular([orden("AD247MQ", date(2026, 2, 3), 150000)],
                              [], DESDE, HASTA)
        unidad = salida["unidades"][0]
        self.assertEqual(unidad["total"], 150000)
        self.assertIsNone(unidad["km"])
        self.assertIsNone(unidad["pesos_km_correctivo"])
        self.assertIsNone(salida["flota"]["pesos_km"])
        self.assertEqual(salida["flota"]["unidades_sin_km"], 1)
        self.assertEqual(salida["flota"]["unidades_con_km"], 0)

    def test_sin_clasificar_no_se_reparte_entre_los_otros_dos(self):
        salida = kpi.calcular([orden("AD247MQ", date(2026, 2, 3), 80000, None)],
                              [km("AD247MQ", 40000)], DESDE, HASTA)
        self.assertEqual(salida["gasto"]["sin_clasificar"], 80000)
        self.assertEqual(salida["gasto"]["correctivo"], 0)
        self.assertEqual(salida["gasto"]["preventivo"], 0)
        # Cero no es "no se sabe": con kilómetros leídos y sin correctivos
        # cargados, el correctivo por kilómetro de esa unidad es cero.
        self.assertEqual(salida["flota"]["pesos_km_correctivo"], 0.0)
        self.assertEqual(salida["flota"]["pesos_km"], 2.0)

    def test_la_serie_tiene_un_renglon_por_mes_y_cierra_con_el_total(self):
        salida = kpi.calcular([
            orden("AD247MQ", date(2026, 2, 3), 150000),
            orden("AB123CD", date(2026, 2, 20), 50000, "preventivo"),
            orden("AB123CD", date(2026, 8, 1), 30000, "preventivo"),
        ], [], DESDE, HASTA)
        self.assertEqual(len(salida["serie"]), 12)
        self.assertEqual(salida["serie"][0]["mes"], "2025-10-01")
        febrero = next(m for m in salida["serie"] if m["mes"] == "2026-02-01")
        self.assertEqual(febrero["correctivo"], 150000)
        self.assertEqual(febrero["preventivo"], 50000)
        self.assertEqual(sum(m["total"] for m in salida["serie"]),
                         salida["gasto"]["total"])

    def test_lo_de_afuera_de_la_ventana_no_entra(self):
        salida = kpi.calcular([
            orden("AD247MQ", date(2025, 6, 1), 999999),
            orden("AD247MQ", date(2026, 2, 3), 1000),
        ], [], DESDE, HASTA)
        self.assertEqual(salida["gasto"]["total"], 1000)

    def test_el_ranking_corta_y_resume_el_resto(self):
        ordenes = [orden(f"AA{i:03d}ZZ", date(2026, 2, 3), 1000 * (30 - i))
                   for i in range(10)]
        salida = kpi.calcular(ordenes, [], DESDE, HASTA, tope=3)
        self.assertEqual(len(salida["unidades"]), 3)
        self.assertEqual([u["patente"] for u in salida["unidades"]],
                         ["AA000ZZ", "AA001ZZ", "AA002ZZ"])
        self.assertEqual(salida["resto"]["unidades"], 7)
        self.assertEqual(salida["resto"]["total"],
                         salida["gasto"]["total"] -
                         sum(u["total"] for u in salida["unidades"]))

    def test_la_ventana_arranca_el_primero_del_mes_de_hace_un_anio(self):
        self.assertEqual(kpi.desde_hasta(date(2026, 9, 14)),
                         (date(2025, 10, 1), date(2026, 9, 14)))
        self.assertEqual(kpi.desde_hasta(date(2026, 1, 5))[0], date(2025, 2, 1))
        self.assertEqual(kpi.desde_hasta(date(2026, 9, 14), meses=3)[0],
                         date(2026, 7, 1))

    def test_la_patente_se_mira_igual_venga_como_venga(self):
        salida = kpi.calcular([orden("ad247mq", date(2026, 2, 3), 100000)],
                              [km("AD247MQ", 50000)], DESDE, HASTA)
        self.assertEqual(salida["unidades"][0]["patente"], "AD247MQ")
        self.assertEqual(salida["unidades"][0]["pesos_km_correctivo"], 2.0)


class Portada(unittest.TestCase):
    """El panel de la portada: lo que falta apaga el panel, no la página."""

    class Cx:
        """Una base que contesta lo que se le diga, o se rompe."""

        def __init__(self, filas=(), romper=()):
            self.filas, self.romper, self.deshizo, self.ultima = filas, romper, 0, []

        def execute(self, consulta, valores=()):
            if any(p in consulta for p in self.romper):
                raise RuntimeError("relation does not exist")
            self.ultima = list(self.filas)
            return self

        def fetchall(self):
            return self.ultima

        def rollback(self):
            self.deshizo += 1

    def test_sin_las_tablas_de_ordenes_el_panel_se_apaga(self):
        cx = self.Cx(romper=("v_ordenes",))
        self.assertIsNone(_ordenes_costos(cx))
        self.assertTrue(cx.deshizo)

    def test_sin_satelital_el_gasto_se_muestra_igual(self):
        """Los kilómetros son opcionales: sin ellos queda el gasto por
        patente y el peso por kilómetro en blanco."""
        # La fecha se calcula desde hoy: la ventana es móvil y una fecha
        # escrita a mano deja de entrar el año que viene.
        cx = self.Cx(filas=[orden("AD247MQ", date.today() - timedelta(days=5), 100000)],
                     romper=("v_km_diarios",))
        salida = _ordenes_costos(cx)
        self.assertEqual(salida["gasto"]["total"], 100000)
        self.assertIsNone(salida["flota"]["pesos_km"])
        self.assertEqual(cx.deshizo, 1)


if __name__ == "__main__":
    unittest.main()
