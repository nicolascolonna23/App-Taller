"""El plan de prefiltro se asigna desde la ficha de la unidad en Flota."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gomeria"))
import unidades


class R:
    def __init__(self, una=None):
        self.una = una

    def fetchone(self):
        return self.una


class Base:
    def __init__(self, instalado=True, clase="prefiltro"):
        self.instalado, self.clase = instalado, clase

    def rollback(self):
        pass

    def execute(self, sql, valores=()):
        if "information_schema.columns" in sql:
            return R({"x": 1} if self.instalado else None)
        if "select clase from mantenimiento_planes" in sql:
            return R({"clase": self.clase} if valores[0] == 5 else None)
        raise AssertionError(sql)


class PlanDePrefiltro(unittest.TestCase):
    def test_vacio_es_sacarselo(self):
        self.assertIsNone(unidades._plan_prefiltro(Base(), ""))

    def test_un_plan_de_prefiltro_entra(self):
        self.assertEqual(unidades._plan_prefiltro(Base(), "5"), 5)

    def test_un_plan_de_service_no_va_como_prefiltro(self):
        with self.assertRaisesRegex(ValueError, "plan de prefiltro"):
            unidades._plan_prefiltro(Base(clase="preventivo"), "5")

    def test_un_plan_que_no_existe(self):
        with self.assertRaises(ValueError):
            unidades._plan_prefiltro(Base(), "9")

    def test_sin_el_sql_lo_dice(self):
        with self.assertRaisesRegex(ValueError, "44_prefiltros.sql"):
            unidades._plan_prefiltro(Base(instalado=False), "5")


if __name__ == "__main__":
    unittest.main()
