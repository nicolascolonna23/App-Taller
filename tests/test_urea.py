"""El tacho de urea: nadie edita el saldo.

Lo que se prueba acá es lo que hace que el número del tacho se pueda
creer: que el signo lo ponga el tipo de movimiento y no quien carga, que
una medición que no da se anote como diferencia con su motivo en vez de
pisar el saldo, y que despachar —el acto de todos los días— no le pida
permisos a nadie, mientras que comprar y ajustar sí.
"""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import urea


class Resultado:
    def __init__(self, una=None, muchas=None):
        self.una, self.muchas = una, muchas or []

    def fetchone(self):
        return self.una

    def fetchall(self):
        return self.muchas


TANQUE = {"id": 1, "nombre": "Tacho de urea", "capacidad_litros": 1000,
          "minimo_litros": 200, "activo": True, "sucursal_codigo": None}


class BaseFalsa:
    def __init__(self, saldo=600.0, estado="ok", dias=20, tanques=None):
        self.saldo = saldo
        self.estado = estado
        self.dias = dias
        self.tanques = tanques if tanques is not None else [TANQUE]
        self.consultas = []
        self.insertados = []

    def rollback(self):
        pass

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("select * from urea_tanques where activo"):
            return Resultado(muchas=self.tanques)
        if sql.startswith("select * from urea_tanques where id"):
            return Resultado(next((t for t in self.tanques if t["id"] == int(valores[0])), None))
        if sql.startswith("select saldo from v_urea_saldo"):
            return Resultado({"saldo": self.saldo})
        if sql.startswith("select * from v_urea_saldo"):
            return Resultado(dict(TANQUE, saldo=self.saldo, estado=self.estado,
                                  dias_restantes=self.dias, tanque_id=1,
                                  porcentaje=self.saldo / 10, capacidad_litros=1000,
                                  minimo_litros=200))
        if sql.startswith("select id, patente from unidades where id"):
            return Resultado({"id": 7, "patente": "AD247MQ"})
        if sql.startswith("select id from unidades where patente"):
            return Resultado({"id": 7})
        if sql.startswith("insert into urea_movimientos"):
            columnas = sql.split("(", 1)[1].split(")", 1)[0].split(", ")
            self.insertados.append(dict(zip(columnas, valores)))
            return Resultado({"id": len(self.insertados)})
        if sql.startswith("delete from urea_movimientos"):
            return Resultado({"tanque_id": 1})
        if sql.startswith(("update", "insert")):
            return Resultado({"id": 1})
        raise AssertionError(f"Consulta inesperada: {sql}")


GESTOR = {"id": 2, "nombre": "Nicolás", "rol": "admin", "gestiona": True, "administra": True}
CHOFER = {"id": 5, "nombre": "Ramón", "rol": "operario", "gestiona": False,
          "administra": False}


# =====================================================================
class QuienPuedeQue(unittest.TestCase):
    def test_despachar_no_le_pide_permiso_a_nadie(self):
        """Es el acto de todos los días: anotarlo tiene que costar menos
        que no anotarlo."""
        cx = BaseFalsa()
        salida = urea.despachar(cx, {"unidad_id": 7, "litros": 40}, CHOFER)
        self.assertTrue(salida["ok"])

    def test_cargar_el_tacho_es_del_que_gestiona(self):
        with self.assertRaises(PermissionError):
            urea.cargar(BaseFalsa(), {"litros": 600}, CHOFER)

    def test_medir_el_tacho_es_del_que_gestiona(self):
        with self.assertRaises(PermissionError):
            urea.medir(BaseFalsa(), {"medido_litros": 500, "motivo": "merma"}, CHOFER)

    def test_borrar_un_movimiento_es_del_que_gestiona(self):
        with self.assertRaises(PermissionError):
            urea.borrar(BaseFalsa(), {"id": 3}, CHOFER)


class ElSignoLoPoneElTipo(unittest.TestCase):
    def test_la_entrada_y_la_salida_se_guardan_en_positivo(self):
        """Quien carga escribe litros, no signos: el signo es del tipo."""
        cx = BaseFalsa()
        urea.cargar(cx, {"litros": 600}, GESTOR)
        urea.despachar(cx, {"unidad_id": 7, "litros": 40}, CHOFER)
        self.assertEqual(cx.insertados[0]["tipo"], "entrada")
        self.assertEqual(cx.insertados[0]["litros"], 600)
        self.assertEqual(cx.insertados[1]["tipo"], "salida")
        self.assertEqual(cx.insertados[1]["litros"], 40)

    def test_el_ajuste_lleva_signo_porque_es_una_diferencia(self):
        cx = BaseFalsa(saldo=552)
        salida = urea.medir(cx, {"medido_litros": 540, "motivo": "Merma del mes"}, GESTOR)
        self.assertEqual(salida["diferencia"], -12)
        self.assertEqual(cx.insertados[0]["tipo"], "ajuste")
        self.assertEqual(cx.insertados[0]["litros"], -12)
        self.assertEqual(cx.insertados[0]["medido_litros"], 540)

    def test_cero_y_negativos_no_son_litros(self):
        for litros in (0, -5, "", "mucha"):
            with self.subTest(litros=litros), self.assertRaises(ValueError):
                urea.despachar(BaseFalsa(), {"unidad_id": 7, "litros": litros}, CHOFER)

    def test_la_fecha_de_manana_no_existe(self):
        manana = (date.today() + timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            urea.despachar(BaseFalsa(), {"unidad_id": 7, "litros": 10,
                                         "fecha": manana}, CHOFER)


class ElDespacho(unittest.TestCase):
    def test_sin_unidad_ni_motivo_no_se_anota(self):
        """Si salió del tacho, salió para algo: eso se dice."""
        with self.assertRaises(ValueError) as e:
            urea.despachar(BaseFalsa(), {"litros": 10}, CHOFER)
        self.assertIn("motivo", str(e.exception))

    def test_un_derrame_tambien_sale_del_tacho(self):
        cx = BaseFalsa()
        urea.despachar(cx, {"litros": 8, "motivo": "Derrame al cargar"}, CHOFER)
        self.assertEqual(cx.insertados[0]["motivo"], "Derrame al cargar")
        self.assertIsNone(cx.insertados[0]["patente"])

    def test_el_km_del_despacho_pone_al_dia_el_maestro(self):
        cx = BaseFalsa()
        urea.despachar(cx, {"unidad_id": 7, "litros": 40, "km": 124000}, CHOFER)
        puesta = next(v for sql, v in cx.consultas if sql.startswith("update unidades"))
        self.assertEqual(puesta[0], 124000)

    def test_avisa_cuando_el_tacho_esta_bajo(self):
        cx = BaseFalsa(saldo=140, estado="aviso", dias=9)
        salida = urea.despachar(cx, {"unidad_id": 7, "litros": 40}, CHOFER)
        self.assertIn("140", salida["aviso"])
        self.assertIn("9 días", salida["aviso"])

    def test_un_saldo_negativo_no_se_bloquea_pero_se_dice(self):
        """El que despacha tiene la manguera en la mano: lo que pasó, pasó.
        Lo que hace falta es decir que el número dejó de ser creíble."""
        cx = BaseFalsa(saldo=-60, estado="vacio", dias=0)
        salida = urea.despachar(cx, {"unidad_id": 7, "litros": 200}, CHOFER)
        self.assertTrue(salida["ok"])
        self.assertIn("medí el tacho", salida["aviso"].lower())


class LaMedicion(unittest.TestCase):
    def test_sin_motivo_no_se_ajusta(self):
        """Un ajuste sin motivo tapa el problema en vez de explicarlo."""
        with self.assertRaises(ValueError):
            urea.medir(BaseFalsa(saldo=552), {"medido_litros": 540}, GESTOR)

    def test_si_da_exacto_no_escribe_nada(self):
        cx = BaseFalsa(saldo=540)
        salida = urea.medir(cx, {"medido_litros": 540}, GESTOR)
        self.assertEqual(salida["diferencia"], 0)
        self.assertEqual(cx.insertados, [])

    def test_el_saldo_queda_en_lo_que_se_midio(self):
        cx = BaseFalsa(saldo=500)
        salida = urea.medir(cx, {"medido_litros": 530, "motivo": "Carga sin anotar"}, GESTOR)
        self.assertEqual(salida["saldo"], 530)
        self.assertEqual(salida["diferencia"], 30)


class ElTacho(unittest.TestCase):
    def test_con_un_solo_tacho_no_se_pregunta_cual(self):
        cx = BaseFalsa()
        urea.despachar(cx, {"unidad_id": 7, "litros": 10}, CHOFER)
        self.assertEqual(cx.insertados[0]["tanque_id"], 1)

    def test_con_dos_tachos_hay_que_decir_cual(self):
        cx = BaseFalsa(tanques=[TANQUE, dict(TANQUE, id=2, nombre="Tacho Tucumán")])
        with self.assertRaises(ValueError):
            urea.despachar(cx, {"unidad_id": 7, "litros": 10}, CHOFER)

    def test_sin_tacho_cargado_lo_dice(self):
        cx = BaseFalsa(tanques=[])
        with self.assertRaises(ValueError) as e:
            urea.despachar(cx, {"unidad_id": 7, "litros": 10}, CHOFER)
        self.assertIn("28_urea.sql", str(e.exception))

    def test_el_minimo_no_puede_ser_mayor_que_la_capacidad(self):
        with self.assertRaises(ValueError):
            urea.guardar_tanque(BaseFalsa(), {"id": 1, "nombre": "Tacho",
                                              "capacidad_litros": 1000,
                                              "minimo_litros": 1500}, GESTOR)

    def test_llenarlo_de_mas_avisa_pero_no_bloquea(self):
        cx = BaseFalsa(saldo=1300)
        salida = urea.cargar(cx, {"litros": 800}, GESTOR)
        self.assertTrue(salida["ok"])
        self.assertIn("capacidad", salida["aviso"])


if __name__ == "__main__":
    unittest.main()
