"""Estanterías del depósito y la ubicación de cada repuesto.

Armar el depósito es del que gestiona; ubicar un repuesto lo hace
cualquiera que entre al módulo. Un repuesto tiene una sola ubicación:
moverlo la cambia, no suma otra. Y una estantería no se puede achicar
dejando repuestos en casilleros que dejan de existir.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import estanterias


class Resultado:
    def __init__(self, una=None):
        self.una = una

    def fetchone(self):
        return self.una

    def fetchall(self):
        return []


class Base:
    def __init__(self, fuera=0, pisos=4, modulos=3, activo=True):
        self.fuera, self.pisos, self.modulos, self.activo = fuera, pisos, modulos, activo
        self.consultas = []
        self.sig = 10

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("insert into repuestos_estanterias"):
            self.sig += 1
            return Resultado({"id": self.sig})
        if sql.startswith("select count(*) as n from repuestos_ubicaciones"):
            return Resultado({"n": self.fuera})
        if sql.startswith("update repuestos_estanterias"):
            return Resultado({"id": valores[-1]})
        if sql.startswith("select id, activo from repuestos_articulos"):
            return Resultado({"id": 4, "activo": self.activo})
        if sql.startswith("select pisos, modulos from repuestos_estanterias"):
            return Resultado({"pisos": self.pisos, "modulos": self.modulos})
        if sql.startswith("insert into repuestos_ubicaciones"):
            return Resultado()
        raise AssertionError(f"Consulta inesperada: {sql}")

    def hechas(self, inicio):
        return [v for s, v in self.consultas if s.startswith(inicio)]


GESTOR = {"id": 1, "rol": "admin"}
OPERARIO = {"id": 2, "rol": "operario"}
UNA = {"nombre": "A1", "pasillo": "A", "pisos": 4, "modulos": 3,
       "largo_cm": 200, "profundidad_cm": 50, "alto_cm": 200, "frente": "sur"}


def con_permiso(valor):
    return mock.patch.object(estanterias.repuestos, "puede_gestionar", return_value=valor)


class Armar(unittest.TestCase):
    def test_crea_una_estanteria(self):
        cx = Base()
        with con_permiso(True):
            r = estanterias.aplicar(cx, {"op": "estanteria_guardar", "estanteria": UNA}, GESTOR)
        self.assertEqual(r, {"id": 11})
        self.assertEqual(cx.hechas("insert into repuestos_estanterias")[0][:2], ("A1", "A"))

    def test_sin_permiso_no_arma(self):
        with con_permiso(False), self.assertRaises(PermissionError):
            estanterias.aplicar(Base(), {"op": "estanteria_guardar", "estanteria": UNA}, OPERARIO)

    def test_un_pasillo_entero(self):
        lote = [dict(UNA, nombre=f"A{i}") for i in range(1, 9)]
        cx = Base()
        with con_permiso(True):
            r = estanterias.aplicar(cx, {"op": "estanterias_crear", "estanterias": lote}, GESTOR)
        self.assertEqual(len(r["ids"]), 8)

    def test_el_pasillo_no_repite_nombres(self):
        lote = [dict(UNA), dict(UNA, nombre="a1")]
        cx = Base()
        with con_permiso(True), self.assertRaises(ValueError):
            estanterias.crear_lote(cx, lote, GESTOR)
        self.assertEqual(cx.hechas("insert"), [], "no se crea ninguna si una falla")

    def test_limites(self):
        for campo, valor in (("pisos", 0), ("pisos", 16), ("modulos", 21),
                             ("largo_cm", 10), ("frente", "arriba"), ("nombre", " ")):
            with self.subTest(campo=campo, valor=valor), self.assertRaises(ValueError):
                estanterias.limpiar(dict(UNA, **{campo: valor}))

    def test_no_se_achica_con_repuestos_afuera(self):
        cx = Base(fuera=2)
        with con_permiso(True), self.assertRaises(ValueError) as e:
            estanterias.guardar(cx, dict(UNA, id=5, pisos=2), GESTOR)
        self.assertIn("2 repuesto", str(e.exception))
        self.assertEqual(cx.hechas("update"), [])

    def test_mover_guarda_posicion_y_frente(self):
        cx = Base()
        with con_permiso(True):
            estanterias.aplicar(cx, {"op": "estanteria_mover", "id": 5, "x_cm": 300,
                                     "y_cm": 125, "frente": "norte"}, GESTOR)
        self.assertEqual(cx.hechas("update repuestos_estanterias")[0], (300, 125, "norte", 5))


class Ubicar(unittest.TestCase):
    def test_cualquiera_ubica(self):
        cx = Base()
        with con_permiso(False):
            estanterias.aplicar(cx, {"op": "ubicar", "codigo": "FIL-020",
                                     "estanteria_id": 5, "piso": 2, "modulo": 3}, OPERARIO)
        sql = [s for s, _ in cx.consultas if s.startswith("insert into repuestos_ubicaciones")][0]
        self.assertIn("on conflict (articulo_id) do update", sql,
                      "ubicar de nuevo tiene que mover, no duplicar")
        self.assertEqual(cx.hechas("insert into repuestos_ubicaciones")[0], (4, 5, 2, 3, 2))

    def test_casillero_inexistente(self):
        for piso, modulo in ((5, 1), (1, 4), (0, 1)):
            with self.subTest(piso=piso, modulo=modulo), self.assertRaises(ValueError):
                estanterias.ubicar(Base(), {"codigo": "X", "estanteria_id": 5,
                                            "piso": piso, "modulo": modulo}, OPERARIO)

    def test_dado_de_baja_no_se_ubica(self):
        with self.assertRaises(ValueError):
            estanterias.ubicar(Base(activo=False), {"codigo": "X", "estanteria_id": 5,
                                                    "piso": 1, "modulo": 1}, OPERARIO)


if __name__ == "__main__":
    unittest.main()
