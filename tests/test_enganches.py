"""Tractor y semi: los kilómetros del que no reporta.

Un semi no tiene satelital, pero sus gomas se gastan igual. Lo que se
prueba acá es que sus kilómetros sean los del tractor que lo llevó,
mientras lo llevó: ni un día de más —el del enganche no cuenta— ni un
kilómetro contado dos veces cuando un tractor cambia de semi.
"""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import enganches


class Resultado:
    def __init__(self, una=None, muchas=None):
        self.una, self.muchas = una, muchas or []

    def fetchone(self):
        return self.una

    def fetchall(self):
        return self.muchas


HOY = date.today()
TRACTOR = {"id": 1, "patente": "AA823XJ", "es_semi": False, "km_actual": 102000}
SEMI = {"id": 2, "patente": "AE456MJ", "es_semi": True, "km_actual": None}


class BaseFalsa:
    def __init__(self, abiertos=None, dias=None, enganche=None):
        self.unidades = {1: TRACTOR, 2: SEMI, 3: dict(SEMI, id=3, patente="AE456MK")}
        self.abiertos = abiertos or []
        self.dias = dias or []
        self.enganche = enganche
        self.consultas = []
        self.odometros = []
        self.borrados = 0

    def rollback(self):
        pass

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("select * from unidades where id"):
            return Resultado(self.unidades.get(int(valores[0])))
        if sql.startswith("select id, patente, km_actual from unidades"):
            u = self.unidades.get(int(valores[0]))
            return Resultado(u and {"id": u["id"], "patente": u["patente"],
                                    "km_actual": u["km_actual"]})
        if sql.startswith("select e.id, e.semi_id, e.tractor_id"):
            return Resultado(muchas=self.abiertos)
        if sql.startswith("select * from enganches where id"):
            return Resultado(self.enganche)
        if sql.startswith("select id from enganches"):
            return Resultado({"id": 9} if self.abiertos else None)
        if sql.startswith("insert into enganches"):
            return Resultado({"id": 5})
        if sql.startswith("select fecha, sum(recorrido)"):
            return Resultado(muchas=self.dias)
        if sql.startswith("select max(km) as km from odometros"):
            return Resultado({"km": None})
        if sql.startswith("delete from odometros"):
            self.borrados += 1
            return Resultado()
        if sql.startswith("insert into odometros"):
            self.odometros.append(valores)
            return Resultado()
        if sql.startswith("delete from enganches"):
            return Resultado({"semi_id": 2})
        if sql.startswith(("update", "insert", "delete")):
            return Resultado()
        raise AssertionError(f"Consulta inesperada: {sql}")


GESTOR = {"id": 2, "nombre": "Nicolás", "rol": "admin", "gestiona": True, "administra": True}
CHOFER = {"id": 5, "nombre": "Ramón", "rol": "chofer", "gestiona": False, "administra": False}


class Enganchar(unittest.TestCase):
    def test_solo_el_que_gestiona_engancha(self):
        with self.assertRaises(PermissionError):
            enganches.enganchar(BaseFalsa(), {"tractor_id": 1, "semi_id": 2}, CHOFER)

    def test_una_unidad_no_se_engancha_a_si_misma(self):
        with self.assertRaises(ValueError):
            enganches.enganchar(BaseFalsa(), {"tractor_id": 1, "semi_id": 1}, GESTOR)

    def test_el_mismo_par_dos_veces_no_va(self):
        cx = BaseFalsa(abiertos=[{"id": 7, "semi_id": 2, "tractor_id": 1,
                                  "desde": HOY - timedelta(days=5)}])
        with self.assertRaises(ValueError) as e:
            enganches.enganchar(cx, {"tractor_id": 1, "semi_id": 2}, GESTOR)
        self.assertIn("ya está enganchado", str(e.exception))

    def test_cambiar_de_semi_cierra_el_anterior(self):
        """Los kilómetros de esos días tienen que ir a uno solo."""
        cx = BaseFalsa(abiertos=[{"id": 7, "semi_id": 2, "tractor_id": 1,
                                  "desde": HOY - timedelta(days=5)}],
                       enganche={"id": 7, "semi_id": 2, "tractor_id": 1,
                                 "desde": HOY - timedelta(days=5), "hasta": None})
        enganches.enganchar(cx, {"tractor_id": 1, "semi_id": 3}, GESTOR)
        cierre = next(v for sql, v in cx.consultas if sql.startswith("update enganches set hasta"))
        self.assertEqual(cierre[0], HOY)

    def test_no_se_engancha_antes_de_que_empezara_el_anterior(self):
        cx = BaseFalsa(abiertos=[{"id": 7, "semi_id": 2, "tractor_id": 1,
                                  "desde": HOY - timedelta(days=2)}])
        with self.assertRaises(ValueError):
            enganches.enganchar(cx, {"tractor_id": 1, "semi_id": 3,
                                     "desde": (HOY - timedelta(days=10)).isoformat()}, GESTOR)

    def test_la_fecha_de_manana_no_existe(self):
        with self.assertRaises(ValueError):
            enganches.enganchar(BaseFalsa(), {"tractor_id": 1, "semi_id": 2,
                                              "desde": (HOY + timedelta(days=1)).isoformat()},
                                GESTOR)

    def test_el_maestro_queda_diciendo_que_semi_lleva(self):
        """Las pantallas que todavía no saben de enganches leen esa columna."""
        cx = BaseFalsa()
        enganches.enganchar(cx, {"tractor_id": 1, "semi_id": 2}, GESTOR)
        puesta = next(v for sql, v in cx.consultas if sql.startswith("update unidades set semi"))
        self.assertEqual(puesta, ("AE456MJ", 1))


class LosKilometrosDelSemi(unittest.TestCase):
    def test_se_escriben_acumulados_en_odometros(self):
        """Así el semi entra en services y cubiertas como cualquier unidad."""
        cx = BaseFalsa(dias=[{"fecha": HOY - timedelta(days=2), "km": 500},
                             {"fecha": HOY - timedelta(days=1), "km": 600},
                             {"fecha": HOY, "km": 500}])
        total = enganches.recalcular(cx, 2)
        self.assertEqual(total, 1600)
        self.assertEqual([float(v[3]) for v in cx.odometros], [500, 1100, 1600])
        # La fuente va escrita en la consulta: es lo que después distingue
        # la serie del semi de una lectura del satelital.
        inserciones = [sql for sql, _ in cx.consultas if sql.startswith("insert into odometros")]
        self.assertTrue(all("'enganche'" in sql for sql in inserciones))

    def test_se_rehace_entera_y_no_se_va_sumando(self):
        """Un enganche que se corrige cambia el pasado."""
        cx = BaseFalsa(dias=[{"fecha": HOY, "km": 100}])
        enganches.recalcular(cx, 2)
        self.assertEqual(cx.borrados, 1)

    def test_sin_dias_enganchado_no_inventa_kilometros(self):
        cx = BaseFalsa(dias=[])
        self.assertEqual(enganches.recalcular(cx, 2), 0)
        self.assertEqual(cx.odometros, [])


class Desenganchar(unittest.TestCase):
    def test_un_semi_suelto_no_se_desengancha(self):
        cx = BaseFalsa(abiertos=[])
        with self.assertRaises(ValueError) as e:
            enganches.desenganchar(cx, {"semi_id": 2}, GESTOR)
        self.assertIn("no está enganchado", str(e.exception))

    def test_no_se_cierra_antes_de_que_empezara(self):
        cx = BaseFalsa(abiertos=[{"id": 9, "semi_id": 2, "tractor_id": 1, "desde": HOY}],
                       enganche={"id": 9, "semi_id": 2, "tractor_id": 1,
                                 "desde": HOY, "hasta": None})
        with self.assertRaises(ValueError):
            enganches.desenganchar(cx, {"semi_id": 2,
                                        "hasta": (HOY - timedelta(days=3)).isoformat()}, GESTOR)

    def test_uno_ya_cerrado_no_se_cierra_dos_veces(self):
        cx = BaseFalsa(abiertos=[{"id": 9, "semi_id": 2, "tractor_id": 1, "desde": HOY}],
                       enganche={"id": 9, "semi_id": 2, "tractor_id": 1,
                                 "desde": HOY, "hasta": HOY})
        with self.assertRaises(ValueError):
            enganches.desenganchar(cx, {"id": 9}, GESTOR)


if __name__ == "__main__":
    unittest.main()
