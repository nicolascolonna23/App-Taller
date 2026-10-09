"""Orden del registro de combustible y métricas del taller."""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app  # noqa: F401  (agrega gomeria/ al camino)
import combustible as comb
import ordenes as ots


class OrdenDeTickets(unittest.TestCase):
    def consultas(self, **kw):
        cx = MagicMock()
        cx.execute.return_value.fetchall.return_value = []
        comb.tickets(cx, **kw)
        return [c[0][0] for c in cx.execute.call_args_list]

    def test_ordena_por_la_columna_pedida(self):
        sql = self.consultas(orden="litros", sentido="asc")[-1]
        self.assertIn("order by c.litros asc nulls last", sql)

    def test_columna_o_sentido_desconocidos_no_llegan_al_sql(self):
        sql = self.consultas(orden="1; drop table x", sentido="sideways")[-1]
        self.assertIn("order by c.fecha desc nulls last", sql)
        self.assertNotIn("drop", sql)

    def test_busca_tambien_por_chofer(self):
        sql = self.consultas(texto="garnica")[0]
        self.assertIn("c.chofer", sql)


class Metricas(unittest.TestCase):
    def test_costo_por_km_solo_con_unidades_con_lecturas(self):
        unidades = [
            {"patente": "AA111AA", "ordenes": 2, "preventivo": 100, "correctivo": 300,
             "sin_clasificar": 0, "total": 400, "externo": 400, "km": 1000},
            {"patente": "BB222BB", "ordenes": 1, "preventivo": 0, "correctivo": 500,
             "sin_clasificar": 0, "total": 500, "externo": 500, "km": None},
        ]
        respuestas = iter([unidades, [], []])
        cx = MagicMock()

        def ejecutar(sql, params=None):
            r = MagicMock()
            if "km_flota" in sql or "from (" in sql:
                r.fetchone.return_value = {"km": 1500, "unidades": 3}
            else:
                r.fetchall.return_value = next(respuestas)
            return r
        cx.execute.side_effect = ejecutar
        d = ots.metricas(cx, "2026-09-01", "2026-09-30")
        r = d["resumen"]
        self.assertEqual(r["total"], 900)
        self.assertEqual(r["km"], 1000)
        self.assertEqual(r["por_km"], 0.4)          # 400 / 1000, sin la unidad sin km
        self.assertEqual(r["preventivo_por_km"], 0.1)
        self.assertEqual(r["unidades_con_km"], 1)

    def test_fechas_invertidas_o_vacias(self):
        cx = MagicMock()
        cx.execute.return_value.fetchall.return_value = []
        cx.execute.return_value.fetchone.return_value = {"km": 0, "unidades": 0}
        d = ots.metricas(cx, "2026-09-30", "2026-09-01")
        self.assertEqual((d["desde"], d["hasta"]), ("2026-09-01", "2026-09-30"))
        self.assertIsNone(ots.metricas(cx, "x", None)["resumen"]["por_km"])


if __name__ == "__main__":
    unittest.main()
