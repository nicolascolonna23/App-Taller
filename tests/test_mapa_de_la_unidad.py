"""El mapa de cubiertas se asigna en Flota, y en ningún otro lado.

Estaban separados el modelo 3D —el dibujo— y el mapa de cubiertas —dónde
entra cada goma—, pero el modelo se elegía en Flota y el mapa solo en
Gomería. El que le ponía el modelo 3D a una unidad creía que le estaba
poniendo el mapa, y después Gomería se la mostraba «sin mapa» con el
camión dibujado y todas las gomas grises.

Ahora el mapa es un campo más de la ficha. Lo que se prueba acá es que
pase por la regla que ya existía —no se cambia el mapa con cubiertas
montadas— y, sobre todo, que guardar la ficha sin nombrarlo no se lo
lleve puesto.
"""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import unidades


class Resultado:
    def __init__(self, una=None):
        self.una = una

    def fetchone(self):
        return self.una

    def fetchall(self):
        return []


class Base:
    """La unidad 7, con el mapa y los montajes que diga cada prueba."""

    def __init__(self, mapa_actual=None, montadas=0, existe_mapa=True):
        self.mapa_actual = mapa_actual
        self.montadas = montadas
        self.existe_mapa = existe_mapa
        self.consultas = []

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("select configuracion_id from unidades"):
            return Resultado({"configuracion_id": self.mapa_actual})
        if sql.startswith("select id from configuraciones"):
            return Resultado({"id": valores[0]} if self.existe_mapa else None)
        if sql.startswith("select count(*) as n from montajes"):
            return Resultado({"n": self.montadas})
        if sql.startswith("update unidades"):
            return Resultado({"patente": "AG055TX"})
        raise AssertionError(f"Consulta inesperada: {sql}")

    def escribio_mapa(self):
        return [v for sql, v in self.consultas
                if sql.startswith("update unidades set configuracion_id")]


class AsignarElMapa(unittest.TestCase):
    def test_se_le_pone_a_la_que_no_tenia(self):
        cx = Base(mapa_actual=None)
        unidades._mapa(cx, 7, 3)
        self.assertEqual(cx.escribio_mapa(), [(3, 7)])

    def test_no_se_cambia_con_cubiertas_montadas(self):
        cx = Base(mapa_actual=2, montadas=4)
        with self.assertRaisesRegex(ValueError, "montadas"):
            unidades._mapa(cx, 7, 3)
        self.assertEqual(cx.escribio_mapa(), [])

    def test_tampoco_se_saca_con_cubiertas_montadas(self):
        """Una unidad con gomas puestas no puede quedarse sin los lugares
        donde están puestas."""
        cx = Base(mapa_actual=2, montadas=4)
        with self.assertRaisesRegex(ValueError, "montadas"):
            unidades._mapa(cx, 7, None)
        self.assertEqual(cx.escribio_mapa(), [])

    def test_se_saca_si_no_hay_nada_montado(self):
        cx = Base(mapa_actual=2, montadas=0)
        unidades._mapa(cx, 7, None)
        self.assertEqual(cx.escribio_mapa(), [(7,)])

    def test_el_mapa_que_no_existe_se_rechaza(self):
        cx = Base(mapa_actual=None, existe_mapa=False)
        with self.assertRaisesRegex(ValueError, "no existe"):
            unidades._mapa(cx, 7, 99)

    def test_el_mismo_mapa_no_valida_ni_escribe_nada(self):
        """Guardar la ficha sin tocar el mapa no puede fallar por las
        cubiertas montadas: no se está cambiando nada."""
        cx = Base(mapa_actual=3, montadas=6)
        unidades._mapa(cx, 7, 3)
        self.assertEqual(cx.escribio_mapa(), [])


class BaseFicha(Base):
    """Lo mínimo para que guardar() llegue hasta el final."""

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        if sql.startswith("select id from unidades where patente"):
            self.consultas.append((sql, valores))
            return Resultado(None)
        if sql.startswith("select * from v_unidades"):
            self.consultas.append((sql, valores))
            return Resultado({"id": 7, "patente": "AG055TX"})
        if sql.startswith("update unidades set") and "configuracion_id = %s where" not in sql:
            self.consultas.append((sql, valores))
            return Resultado()
        return super().execute(consulta, valores)


GESTOR = {"id": 1, "nombre": "Nicolás", "rol": "admin"}


class GuardarLaFicha(unittest.TestCase):
    """El mapa solo se toca cuando la ficha lo nombra. Se llama a guardar()
    de verdad: es el camino por el que puede perderse el mapa sin que
    nadie lo haya pedido."""

    def guardar(self, datos, **kw):
        cx = BaseFicha(**kw)
        unidades.guardar(cx, datos, usuario=GESTOR)
        return cx

    def test_sin_el_campo_no_se_toca_el_mapa(self):
        """Guardar la marca de una unidad no puede dejarla sin mapa."""
        cx = self.guardar({"id": 7, "marca": "HERMANN"}, mapa_actual=3, montadas=6)
        self.assertEqual(cx.escribio_mapa(), [])

    def test_con_el_campo_vacio_se_le_saca(self):
        """El desplegable manda '' cuando se eligió «Sin mapa asignado»."""
        cx = self.guardar({"id": 7, "configuracion_id": ""}, mapa_actual=3)
        self.assertEqual(cx.escribio_mapa(), [(7,)])

    def test_con_el_campo_lleno_se_le_pone(self):
        cx = self.guardar({"id": 7, "configuracion_id": "3"}, mapa_actual=None)
        self.assertEqual(cx.escribio_mapa(), [(3, 7)])

    def test_guardar_otra_cosa_con_el_mismo_mapa_no_falla(self):
        """Aunque tenga cubiertas montadas: no se está cambiando el mapa."""
        cx = self.guardar({"id": 7, "marca": "X", "configuracion_id": "3"},
                          mapa_actual=3, montadas=6)
        self.assertEqual(cx.escribio_mapa(), [])

    def test_no_se_puede_sacar_el_mapa_con_cubiertas_montadas(self):
        with self.assertRaisesRegex(ValueError, "montadas"):
            self.guardar({"id": 7, "configuracion_id": ""},
                         mapa_actual=3, montadas=6)


if __name__ == "__main__":
    unittest.main()
