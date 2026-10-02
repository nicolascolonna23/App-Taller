"""El número de fuego: cambiarlo sin que la cubierta deje de ser la misma.

El código de una cubierta es su número de fuego. Hay dos momentos en que
entra al sistema sin él: el alta de stock del 07/09 —que se contó por
montón y entró como STK-R001, STK-R002…— y el alta por factura, donde la
factura trae medida, marca y costo pero el fuego todavía no está grabado.

Hasta ahora eso se arreglaba con un update a mano. El problema no era
cambiar el código: era saber a cuáles les faltaba, porque una cubierta con
código provisorio se ve igual que cualquier otra en el listado.
"""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import base


class Resultado:
    def __init__(self, una=None):
        self.una = una

    def fetchone(self):
        return self.una

    def fetchall(self):
        return []


class Base:
    def __init__(self, codigo="STK-R035", provisorio=True, ocupado=False,
                 existe=True):
        self.codigo = codigo
        self.provisorio = provisorio
        self.ocupado = ocupado
        self.existe = existe
        self.consultas = []

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("select codigo, codigo_provisorio from cubiertas"):
            return Resultado({"codigo": self.codigo,
                              "codigo_provisorio": self.provisorio}
                             if self.existe else None)
        if sql.startswith("select id from cubiertas where codigo"):
            return Resultado({"id": 99} if self.ocupado else None)
        if sql.startswith("update cubiertas") or sql.startswith("insert into movimientos"):
            return Resultado()
        raise AssertionError(f"Consulta inesperada: {sql}")

    def escrituras(self):
        return [(sql, v) for sql, v in self.consultas
                if sql.startswith("update cubiertas")]

    def nota(self):
        for sql, v in self.consultas:
            if sql.startswith("insert into movimientos"):
                return v.get("nota") if isinstance(v, dict) else v
        return None


class GrabarElFuego(unittest.TestCase):
    def test_reemplaza_el_provisorio(self):
        cx = Base(codigo="STK-R035")
        self.assertEqual(base.cambiar_codigo(cx, 7, "4521", usuario="Nico"), "4521")
        self.assertEqual(cx.escrituras()[0][1], ("4521", 7))

    def test_lo_deja_de_marcar_como_provisorio(self):
        cx = Base()
        base.cambiar_codigo(cx, 7, "4521")
        self.assertIn("codigo_provisorio = false", cx.escrituras()[0][0])

    def test_queda_en_el_historial_de_donde_salio(self):
        cx = Base(codigo="STK-R035")
        base.cambiar_codigo(cx, 7, "4521", usuario="Nico")
        self.assertIn("STK-R035", cx.nota())
        self.assertIn("4521", cx.nota())

    def test_se_normaliza(self):
        for entra, sale in ((" 4521 ", "4521"), ("ab12", "AB12"),
                            ("45  21", "45 21")):
            with self.subTest(entra=entra):
                cx = Base()
                self.assertEqual(base.cambiar_codigo(cx, 7, entra), sale)

    def test_el_vacio_se_rechaza(self):
        for valor in ("", "   ", None):
            with self.subTest(valor=valor), \
                 self.assertRaisesRegex(ValueError, "Ingresar"):
                base.cambiar_codigo(Base(), 7, valor)

    def test_no_se_pisa_el_codigo_de_otra(self):
        """Dos gomas con el mismo fuego es peor que una sin fuego."""
        cx = Base(ocupado=True)
        with self.assertRaisesRegex(ValueError, "Ya hay otra"):
            base.cambiar_codigo(cx, 7, "4521")
        self.assertEqual(cx.escrituras(), [])

    def test_la_cubierta_que_no_existe(self):
        with self.assertRaisesRegex(ValueError, "no existe"):
            base.cambiar_codigo(Base(existe=False), 7, "4521")

    def test_el_mismo_codigo_no_escribe_nada(self):
        """Guardar sin cambiar nada no tiene que dejar rastro ni chocar
        contra la unicidad de su propio código."""
        cx = Base(codigo="4521", provisorio=False)
        self.assertEqual(base.cambiar_codigo(cx, 7, "4521"), "4521")
        self.assertEqual(cx.escrituras(), [])
        self.assertIsNone(cx.nota())

    def test_tambien_se_le_cambia_a_una_que_ya_tenia_fuego(self):
        """Se cargan mal seguido. Cambiarlo es corregir, no inventar."""
        cx = Base(codigo="4520", provisorio=False)
        base.cambiar_codigo(cx, 7, "4521")
        self.assertEqual(cx.escrituras()[0][1], ("4521", 7))


class LasQueEsperan(unittest.TestCase):
    def test_sin_el_sql_corrido_la_pantalla_sigue_andando(self):
        class Vieja:
            def execute(self, *a):
                raise RuntimeError('relation "v_cubiertas_sin_fuego" does not exist')

            def rollback(self):
                self.volvio = True

        cx = Vieja()
        self.assertEqual(base.sin_fuego(cx), [])
        self.assertTrue(getattr(cx, "volvio", False))


if __name__ == "__main__":
    unittest.main()
