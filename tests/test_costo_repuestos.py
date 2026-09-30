"""El costo de un repuesto va en el movimiento, no en la ficha del artículo.

El inventario llevaba cantidades y nada más: cuántos filtros entraron,
cuántos salieron y a qué unidad. Con eso se sabe si falta algo, pero no
cuánto vale lo que hay en el estante ni cuánto costó lo que se le puso a un
camión.

El costo es del movimiento y no del artículo porque el mismo filtro no
cuesta lo mismo en marzo que en septiembre. Guardarlo en la ficha sería
pisar el precio viejo en cada compra; guardándolo en el movimiento queda la
serie entera.
"""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import repuestos


class Resultado:
    def __init__(self, una=None):
        self.una = una

    def fetchone(self):
        return self.una

    def fetchall(self):
        return []


class Base:
    def __init__(self, activo=True):
        self.activo = activo
        self.consultas = []

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("select id, activo from repuestos_articulos"):
            return Resultado({"id": 4, "activo": self.activo})
        if sql.startswith("insert into repuestos_movimientos"):
            return Resultado({"id": 88})
        raise AssertionError(f"Consulta inesperada: {sql}")

    def guardado(self):
        for sql, v in self.consultas:
            if sql.startswith("insert into repuestos_movimientos"):
                return v
        return None


USUARIO = {"id": 2, "nombre": "Nicolás", "rol": "admin"}


def mover(**cambios):
    datos = {"codigo": "FIL-020", "tipo": "Entrada", "cantidad": 10,
             "fecha": "2026-09-30"}
    datos.update(cambios)
    cx = Base()
    repuestos.crear_movimiento(cx, datos, USUARIO)
    return cx


class ElCosto(unittest.TestCase):
    def test_se_guarda_con_la_entrada(self):
        cx = mover(costo_unitario=1250.50)
        self.assertIn(1250.50, cx.guardado())

    def test_se_redondea_a_centavos(self):
        cx = mover(costo_unitario=1250.567)
        self.assertIn(1250.57, cx.guardado())

    def test_acepta_la_coma_decimal(self):
        """Se escribe como se escribe acá."""
        cx = mover(costo_unitario="1250,50")
        self.assertIn(1250.50, cx.guardado())

    def test_vacio_no_es_cero(self):
        """La mayoría de los movimientos viejos no tienen costo. Contarlos
        como gratis ensuciaría todo lo que se calcule encima."""
        for valor in (None, ""):
            with self.subTest(valor=valor):
                self.assertIsNone(repuestos._costo(valor))
                cx = mover(costo_unitario=valor)
                self.assertIn(None, cx.guardado())

    def test_sin_el_campo_entra_igual(self):
        """Los movimientos que ya se cargaban siguen andando."""
        cx = mover()
        self.assertIn(None, cx.guardado())

    def test_el_negativo_se_rechaza(self):
        with self.assertRaisesRegex(ValueError, "negativo"):
            mover(costo_unitario=-5)

    def test_lo_que_no_es_numero_se_rechaza(self):
        with self.assertRaisesRegex(ValueError, "número"):
            mover(costo_unitario="mil doscientos")


class SoloLoQueEntra(unittest.TestCase):
    """Una salida es el repuesto que ya se compró saliendo del estante: su
    costo es el que tenía cuando entró, no uno nuevo."""

    def test_la_salida_no_lleva_costo(self):
        with self.assertRaisesRegex(ValueError, "cuando el repuesto entra"):
            mover(tipo="Salida", patente="AD247MQ", costo_unitario=1000)

    def test_el_ajuste_que_resta_tampoco(self):
        with self.assertRaisesRegex(ValueError, "cuando el repuesto entra"):
            mover(tipo="Ajuste", cantidad=-3, costo_unitario=1000)

    def test_el_ajuste_que_suma_si(self):
        """Aparecieron tres filtros que no estaban contados: valen algo."""
        cx = mover(tipo="Ajuste", cantidad=3, costo_unitario=1000)
        self.assertIn(1000.0, cx.guardado())

    def test_la_salida_sin_costo_sigue_andando(self):
        cx = mover(tipo="Salida", patente="AD247MQ")
        self.assertIn(None, cx.guardado())


class BaseListado:
    """Lo que devuelve la base cuando la pantalla pide todo."""

    def __init__(self, costo):
        self.costo = costo

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        if sql.startswith("select codigo, descripcion, rubro"):
            return Filas([{"codigo": "FIL-020", "descripcion": "Filtro",
                           "rubro": "Mecánica", "codigo_interno": None,
                           "stock_minimo": 2, "activo": True}])
        if sql.startswith("select m.id, m.fecha, m.tipo"):
            return Filas([{"id": 88, "fecha": "2026-09-30", "tipo": "Entrada",
                           "cantidad": 10, "patente": None,
                           "observaciones": None, "costo_unitario": self.costo,
                           "ts": 0, "codigo": "FIL-020",
                           "descripcion": "Filtro"}])
        raise AssertionError(f"Consulta inesperada: {sql}")


class Filas:
    def __init__(self, filas):
        self.filas = filas

    def fetchall(self):
        return self.filas


class Leerlo(unittest.TestCase):
    """El costo tiene que llegar hasta la pantalla: es la que valoriza."""

    def test_el_costo_viaja_al_listado(self):
        salida = repuestos.listar(BaseListado(1250.50), USUARIO)
        self.assertEqual(salida["movs"][0]["costo"], 1250.50)

    def test_el_movimiento_sin_costo_viaja_en_nada(self):
        """Y no en cero, que se leería como gratis."""
        salida = repuestos.listar(BaseListado(None), USUARIO)
        self.assertIsNone(salida["movs"][0]["costo"])


if __name__ == "__main__":
    unittest.main()
