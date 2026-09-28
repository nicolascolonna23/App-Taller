"""Los fluidos del depósito: nadie edita el saldo.

Lo que se prueba acá es lo que hace que el número se pueda creer: que el
signo lo ponga el tipo de movimiento y no quien carga, que una medición
que no da se anote como diferencia con su motivo en vez de pisar el
saldo, y que despachar —el acto de todos los días— no le pida permisos a
nadie, mientras que comprar, medir y tocar el catálogo sí.
"""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import fluidos


class Resultado:
    def __init__(self, una=None, muchas=None):
        self.una, self.muchas = una, muchas or []

    def fetchone(self):
        return self.una

    def fetchall(self):
        return self.muchas


UREA = {"id": 1, "nombre": "Urea", "clave": "urea", "unidad": "litros",
        "envase": "bin", "capacidad": 1000, "minimo": 200, "activo": True,
        "orden": 1, "sucursal_codigo": None, "proveedor_id": None}
ACEITE = dict(UREA, id=2, nombre="Aceite 15W40", clave="aceite15w40",
              envase="tambor", capacidad=205, minimo=41, orden=10)


class BaseFalsa:
    def __init__(self, saldo=600.0, estado="ok", dias=20, fluidos_=None,
                 proveedores=None, movimientos=0, compras=0):
        self.saldo = saldo
        self.estado = estado
        self.dias = dias
        self.fluidos = fluidos_ if fluidos_ is not None else [UREA]
        self.proveedores = proveedores if proveedores is not None else []
        self.movimientos = movimientos
        self.compras = compras
        self.consultas = []
        self.insertados = []

    def rollback(self):
        pass

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("select * from fluidos where activo"):
            return Resultado(muchas=[f for f in self.fluidos if f["activo"]])
        if sql.startswith("select * from fluidos where id"):
            return Resultado(next((f for f in self.fluidos
                                   if f["id"] == int(valores[0])), None))
        if sql.startswith("select * from fluidos where clave"):
            return Resultado(next((f for f in self.fluidos
                                   if f["clave"] == valores[0]), None))
        if sql.startswith("select nombre from fluidos"):
            return Resultado(next((f for f in self.fluidos
                                   if f["id"] == int(valores[0])), None))
        if sql.startswith("select 1 from fluidos where clave"):
            repetida = any(f["clave"] == valores[0] and
                           (len(valores) < 2 or f["id"] != valores[1])
                           for f in self.fluidos)
            return Resultado({"?column?": 1} if repetida else None)
        if sql.startswith("select saldo from v_fluidos_saldo"):
            return Resultado({"saldo": self.saldo})
        if sql.startswith("select * from v_fluidos_saldo"):
            return Resultado(dict(UREA, saldo=self.saldo, estado=self.estado,
                                  dias_restantes=self.dias, fluido_id=1))
        if sql.startswith("select id, patente from unidades where id"):
            return Resultado({"id": 7, "patente": "AD247MQ"})
        if sql.startswith("select id from unidades where patente"):
            return Resultado({"id": 7})
        if sql.startswith("select id, nombre from proveedores where id"):
            return Resultado(next((p for p in self.proveedores
                                   if p["id"] == int(valores[0])), None))
        if sql.startswith("select id, nombre from proveedores where lower(nombre)"):
            return Resultado(next((p for p in self.proveedores
                                   if p["nombre"].lower() == str(valores[0]).lower()), None))
        if sql.startswith("select 1 from proveedores where lower(nombre)"):
            return Resultado({"?column?": 1} if any(
                p["nombre"].lower() == str(valores[0]).lower()
                for p in self.proveedores) else None)
        if sql.startswith("select nombre from proveedores"):
            return Resultado(next((p for p in self.proveedores
                                   if p["id"] == int(valores[0])), None))
        if sql.startswith("select count(*) as n from fluido_movimientos where fluido_id"):
            return Resultado({"n": self.movimientos})
        if sql.startswith("select count(*) as n from fluido_movimientos where proveedor_id"):
            return Resultado({"n": self.compras})
        if sql.startswith("insert into fluido_movimientos"):
            columnas = sql.split("(", 1)[1].split(")", 1)[0].split(", ")
            self.insertados.append(dict(zip(columnas, valores)))
            return Resultado({"id": len(self.insertados)})
        if sql.startswith("delete from fluido_movimientos"):
            return Resultado({"fluido_id": 1})
        if sql.startswith(("update", "insert", "delete")):
            return Resultado({"id": 1})
        raise AssertionError(f"Consulta inesperada: {sql}")

    def sql_con(self, texto):
        return [c for c in self.consultas if texto in c[0]]


GESTOR = {"id": 2, "nombre": "Nicolás", "rol": "admin", "gestiona": True, "administra": True}
CHOFER = {"id": 5, "nombre": "Ramón", "rol": "operario", "gestiona": False,
          "administra": False}


# =====================================================================
class QuienPuedeQue(unittest.TestCase):
    def test_despachar_no_le_pide_permiso_a_nadie(self):
        """Es el acto de todos los días: anotarlo tiene que costar menos
        que no anotarlo."""
        cx = BaseFalsa()
        salida = fluidos.despachar(cx, {"unidad_id": 7, "cantidad": 40}, CHOFER)
        self.assertTrue(salida["ok"])

    def test_cargar_es_del_que_gestiona(self):
        with self.assertRaises(PermissionError):
            fluidos.cargar(BaseFalsa(), {"cantidad": 600}, CHOFER)

    def test_medir_es_del_que_gestiona(self):
        with self.assertRaises(PermissionError):
            fluidos.medir(BaseFalsa(), {"medido": 500, "motivo": "merma"}, CHOFER)

    def test_borrar_un_movimiento_es_del_que_gestiona(self):
        with self.assertRaises(PermissionError):
            fluidos.borrar(BaseFalsa(), {"id": 3}, CHOFER)

    def test_el_catalogo_es_del_que_gestiona(self):
        cx = BaseFalsa()
        for llamada in (
                lambda: fluidos.guardar_fluido(cx, {"nombre": "Grasa", "capacidad": 20}, CHOFER),
                lambda: fluidos.borrar_fluido(cx, {"id": 1}, CHOFER),
                lambda: fluidos.guardar_proveedor(cx, {"nombre": "YPF"}, CHOFER),
                lambda: fluidos.borrar_proveedor(cx, {"id": 1}, CHOFER)):
            with self.assertRaises(PermissionError):
                llamada()
        self.assertEqual(cx.consultas, [], "no tendría que haber tocado la base")


class ElSignoLoPoneElTipo(unittest.TestCase):
    def test_la_entrada_y_la_salida_se_guardan_en_positivo(self):
        """Quien carga escribe litros, no signos: el signo es del tipo."""
        cx = BaseFalsa()
        fluidos.cargar(cx, {"cantidad": 600}, GESTOR)
        fluidos.despachar(cx, {"unidad_id": 7, "cantidad": 40}, CHOFER)
        self.assertEqual(cx.insertados[0]["tipo"], "entrada")
        self.assertEqual(cx.insertados[0]["cantidad"], 600)
        self.assertEqual(cx.insertados[1]["tipo"], "salida")
        self.assertEqual(cx.insertados[1]["cantidad"], 40)

    def test_el_ajuste_lleva_signo_porque_es_una_diferencia(self):
        cx = BaseFalsa(saldo=552)
        salida = fluidos.medir(cx, {"medido": 540, "motivo": "Merma del mes"}, GESTOR)
        self.assertEqual(salida["diferencia"], -12)
        self.assertEqual(cx.insertados[0]["tipo"], "ajuste")
        self.assertEqual(cx.insertados[0]["cantidad"], -12)
        self.assertEqual(cx.insertados[0]["medido"], 540)

    def test_cero_y_negativos_no_son_una_cantidad(self):
        for cantidad in (0, -5, "", "mucha"):
            with self.subTest(cantidad=cantidad), self.assertRaises(ValueError):
                fluidos.despachar(BaseFalsa(), {"unidad_id": 7, "cantidad": cantidad}, CHOFER)

    def test_la_fecha_de_manana_no_existe(self):
        manana = (date.today() + timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            fluidos.despachar(BaseFalsa(), {"unidad_id": 7, "cantidad": 10,
                                            "fecha": manana}, CHOFER)


class ElDespacho(unittest.TestCase):
    def test_sin_unidad_ni_motivo_no_se_anota(self):
        """Si salió del depósito, salió para algo: eso se dice."""
        with self.assertRaises(ValueError) as e:
            fluidos.despachar(BaseFalsa(), {"cantidad": 10}, CHOFER)
        self.assertIn("motivo", str(e.exception))

    def test_un_derrame_tambien_sale_del_deposito(self):
        cx = BaseFalsa()
        fluidos.despachar(cx, {"cantidad": 8, "motivo": "Derrame al cargar"}, CHOFER)
        self.assertEqual(cx.insertados[0]["motivo"], "Derrame al cargar")
        self.assertIsNone(cx.insertados[0]["patente"])

    def test_el_km_del_despacho_pone_al_dia_el_maestro(self):
        cx = BaseFalsa()
        fluidos.despachar(cx, {"unidad_id": 7, "cantidad": 40, "km": 124000}, CHOFER)
        puesta = next(v for sql, v in cx.consultas if sql.startswith("update unidades"))
        self.assertEqual(puesta[0], 124000)

    def test_avisa_cuando_queda_poco(self):
        cx = BaseFalsa(saldo=140, estado="aviso", dias=9)
        salida = fluidos.despachar(cx, {"unidad_id": 7, "cantidad": 40}, CHOFER)
        self.assertIn("140", salida["aviso"])
        self.assertIn("9 días", salida["aviso"])
        self.assertIn("Urea", salida["aviso"])

    def test_un_saldo_negativo_no_se_bloquea_pero_se_dice(self):
        """El que despacha tiene la manguera en la mano: lo que pasó, pasó.
        Lo que hace falta es decir que el número dejó de ser creíble."""
        cx = BaseFalsa(saldo=-60, estado="vacio", dias=0)
        salida = fluidos.despachar(cx, {"unidad_id": 7, "cantidad": 200}, CHOFER)
        self.assertTrue(salida["ok"])
        self.assertIn("medí", salida["aviso"].lower())


class LaMedicion(unittest.TestCase):
    def test_sin_motivo_no_se_ajusta(self):
        """Un ajuste sin motivo tapa el problema en vez de explicarlo."""
        with self.assertRaises(ValueError):
            fluidos.medir(BaseFalsa(saldo=552), {"medido": 540}, GESTOR)

    def test_si_da_exacto_no_escribe_nada(self):
        cx = BaseFalsa(saldo=540)
        salida = fluidos.medir(cx, {"medido": 540}, GESTOR)
        self.assertEqual(salida["diferencia"], 0)
        self.assertEqual(cx.insertados, [])

    def test_el_saldo_queda_en_lo_que_se_midio(self):
        cx = BaseFalsa(saldo=500)
        salida = fluidos.medir(cx, {"medido": 530, "motivo": "Carga sin anotar"}, GESTOR)
        self.assertEqual(salida["saldo"], 530)
        self.assertEqual(salida["diferencia"], 30)


class DeQueFluido(unittest.TestCase):
    def test_con_uno_solo_no_se_pregunta_cual(self):
        cx = BaseFalsa()
        fluidos.despachar(cx, {"unidad_id": 7, "cantidad": 10}, CHOFER)
        self.assertEqual(cx.insertados[0]["fluido_id"], 1)

    def test_con_varios_hay_que_decir_cual(self):
        cx = BaseFalsa(fluidos_=[UREA, ACEITE])
        with self.assertRaises(ValueError):
            fluidos.despachar(cx, {"unidad_id": 7, "cantidad": 10}, CHOFER)

    def test_se_puede_pedir_por_clave(self):
        cx = BaseFalsa(fluidos_=[UREA, ACEITE])
        fluidos.despachar(cx, {"clave": "Aceite 15W40", "unidad_id": 7,
                               "cantidad": 38}, CHOFER)
        self.assertEqual(cx.insertados[0]["fluido_id"], 2)

    def test_sin_fluidos_cargados_dice_que_script_falta(self):
        cx = BaseFalsa(fluidos_=[])
        with self.assertRaises(ValueError) as e:
            fluidos.despachar(cx, {"unidad_id": 7, "cantidad": 10}, CHOFER)
        self.assertIn("32_fluidos.sql", str(e.exception))


class ElCatalogo(unittest.TestCase):
    def test_el_envase_y_la_unidad_son_de_los_que_hay(self):
        cx = BaseFalsa()
        with self.assertRaises(ValueError):
            fluidos.guardar_fluido(cx, {"nombre": "Nafta", "capacidad": 200,
                                        "envase": "bidoncito"}, GESTOR)
        with self.assertRaises(ValueError):
            fluidos.guardar_fluido(cx, {"nombre": "Nafta", "capacidad": 200,
                                        "unidad": "galones"}, GESTOR)

    def test_sin_capacidad_no_hay_envase_que_dibujar(self):
        with self.assertRaises(ValueError):
            fluidos.guardar_fluido(BaseFalsa(), {"nombre": "Nafta"}, GESTOR)

    def test_no_entra_dos_veces_el_mismo_fluido(self):
        cx = BaseFalsa()
        with self.assertRaises(ValueError) as e:
            fluidos.guardar_fluido(cx, {"nombre": "UREA", "capacidad": 1000}, GESTOR)
        self.assertIn("ya está cargado", str(e.exception))

    def test_el_fluido_con_movimientos_se_da_de_baja_no_se_borra(self):
        cx = BaseFalsa(movimientos=37)
        with self.assertRaises(ValueError) as e:
            fluidos.borrar_fluido(cx, {"id": 1}, GESTOR)
        self.assertIn("dar de baja", str(e.exception))
        self.assertEqual(cx.sql_con("delete from fluidos"), [])

    def test_el_que_no_se_usó_se_borra(self):
        cx = BaseFalsa(movimientos=0)
        self.assertEqual(fluidos.borrar_fluido(cx, {"id": 1}, GESTOR), {"ok": True})
        self.assertEqual(len(cx.sql_con("delete from fluidos")), 1)

    def test_la_grasa_se_mide_en_kilos(self):
        cx = BaseFalsa(fluidos_=[])
        fluidos.guardar_fluido(cx, {"nombre": "Grasa", "unidad": "kilos",
                                    "envase": "balde", "capacidad": 20}, GESTOR)
        valores = cx.sql_con("insert into fluidos")[0][1]
        self.assertEqual(valores[2], "kilos")
        self.assertEqual(valores[3], "balde")


class LosProveedores(unittest.TestCase):
    def test_el_rubro_tiene_que_ser_uno_de_los_que_hay(self):
        with self.assertRaises(ValueError):
            fluidos.guardar_proveedor(BaseFalsa(), {"nombre": "YPF",
                                                    "rubros": ["pizzas"]}, GESTOR)

    def test_no_entra_dos_veces_el_mismo(self):
        cx = BaseFalsa(proveedores=[{"id": 1, "nombre": "YPF"}])
        with self.assertRaises(ValueError):
            fluidos.guardar_proveedor(cx, {"nombre": "ypf"}, GESTOR)

    def test_al_que_se_le_compro_se_da_de_baja_no_se_borra(self):
        cx = BaseFalsa(proveedores=[{"id": 1, "nombre": "YPF"}], compras=12)
        with self.assertRaises(ValueError) as e:
            fluidos.borrar_proveedor(cx, {"id": 1}, GESTOR)
        self.assertIn("dar de baja", str(e.exception))

    def test_el_escrito_a_mano_se_engancha_con_el_cargado(self):
        """«YPF» y «ypf» tienen que sumar para el mismo proveedor."""
        cx = BaseFalsa(proveedores=[{"id": 3, "nombre": "YPF"}])
        fluidos.cargar(cx, {"cantidad": 600, "proveedor": "ypf"}, GESTOR)
        self.assertEqual(cx.insertados[0]["proveedor_id"], 3)
        self.assertEqual(cx.insertados[0]["proveedor"], "YPF")

    def test_uno_que_no_existe_no_se_guarda_en_la_compra(self):
        cx = BaseFalsa(proveedores=[])
        with self.assertRaises(ValueError):
            fluidos.cargar(cx, {"cantidad": 600, "proveedor_id": 9}, GESTOR)


class LaApi(unittest.TestCase):
    def test_una_operacion_que_no_existe_se_rechaza(self):
        with self.assertRaises(ValueError):
            fluidos.aplicar(BaseFalsa(), {"op": "vaciar_todo"}, GESTOR)


if __name__ == "__main__":
    unittest.main()
