"""El mismo cambio sobre varias unidades.

El maestro entra con lo que trae la planilla: sin residencia y sin decir
cuál es un semi. Completarlo de a una son cuarenta fichas abiertas y
cerradas, así que la pantalla lo hace sobre las que se tildaron. Lo que
se prueba acá es que toque solo lo que se pidió, y que marcar un semi lo
deje marcado en los dos lugares que el resto del sistema mira.
"""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import unidades as uni


class Resultado:
    def __init__(self, muchas):
        self.muchas = muchas

    def fetchall(self):
        return self.muchas

    def fetchone(self):
        return self.muchas[0] if self.muchas else None


class BaseFalsa:
    def __init__(self):
        self.consultas = []

    def execute(self, consulta, valores=()):
        self.consultas.append((" ".join(consulta.split()), valores))
        return Resultado([{"patente": "AA114ZX"}, {"patente": "AA472IP"}])


ADMIN = {"rol": "admin", "gestiona": True, "nombre": "Nicolás"}
OPERARIO = {"rol": "operario", "nombre": "Ramón"}


class CambioEnLote(unittest.TestCase):
    def test_la_residencia_va_en_mayusculas_y_solo_a_las_tildadas(self):
        cx = BaseFalsa()
        salida = uni.en_lote(cx, {"ids": [1, 2], "sucursal": " lad "}, ADMIN)
        sql, valores = cx.consultas[-1]
        self.assertIn("update unidades set sucursal = %s", sql)
        self.assertEqual(valores[0], "LAD")
        self.assertEqual(valores[-1], [1, 2])
        self.assertEqual(salida["cambiadas"], 2)

    def test_marcar_semi_escribe_tambien_el_uso(self):
        # `es_semi` lo hace aparecer en Asociación de equipos; `uso` es lo
        # que mira el resto del sistema para saber qué dibuja.
        cx = BaseFalsa()
        uni.en_lote(cx, {"ids": [3], "es_semi": True}, ADMIN)
        sql, valores = cx.consultas[-1]
        self.assertIn("es_semi = %s", sql)
        self.assertIn("uso = %s", sql)
        self.assertEqual(valores[:2], [True, "SEMIRREMOLQUE"])

    def test_desmarcar_no_borra_un_uso_que_no_es_de_semi(self):
        cx = BaseFalsa()
        uni.en_lote(cx, {"ids": [3], "es_semi": False}, ADMIN)
        sql, valores = cx.consultas[-1]
        self.assertIn("case when", sql)
        self.assertIn("like 'SEMI%%'", sql)   # el %% lo deshace psycopg
        self.assertEqual(valores[0], False)

    def test_las_dos_cosas_juntas(self):
        cx = BaseFalsa()
        uni.en_lote(cx, {"ids": [1], "sucursal": "LAD", "es_semi": True}, ADMIN)
        sql, _ = cx.consultas[-1]
        self.assertIn("sucursal = %s", sql)
        self.assertIn("es_semi = %s", sql)

    def test_los_ids_repetidos_o_ilegibles_no_cuentan(self):
        cx = BaseFalsa()
        uni.en_lote(cx, {"ids": [2, "2", None, "x", 1], "sucursal": "LAD"}, ADMIN)
        self.assertEqual(cx.consultas[-1][1][-1], [1, 2])

    def test_sin_unidades_no_se_toca_nada(self):
        cx = BaseFalsa()
        with self.assertRaises(ValueError):
            uni.en_lote(cx, {"ids": [], "sucursal": "LAD"}, ADMIN)
        self.assertEqual(cx.consultas, [])

    def test_sin_decir_que_cambiar_no_se_toca_nada(self):
        cx = BaseFalsa()
        with self.assertRaises(ValueError):
            uni.en_lote(cx, {"ids": [1, 2], "sucursal": "  "}, ADMIN)
        self.assertEqual(cx.consultas, [])

    def test_un_operario_no_cambia_el_maestro(self):
        cx = BaseFalsa()
        with self.assertRaises(PermissionError):
            uni.en_lote(cx, {"ids": [1], "sucursal": "LAD"}, OPERARIO)
        self.assertEqual(cx.consultas, [])

    def test_de_a_quinientas_como_mucho(self):
        cx = BaseFalsa()
        with self.assertRaises(ValueError):
            uni.en_lote(cx, {"ids": list(range(1, 700)), "sucursal": "LAD"}, ADMIN)


if __name__ == "__main__":
    unittest.main()
