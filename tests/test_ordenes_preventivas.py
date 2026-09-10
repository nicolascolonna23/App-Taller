"""El contrato entre órdenes, reparaciones externas y el último service."""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import ordenes


class Resultado:
    def __init__(self, una=None, muchas=None):
        self.una = una
        self.muchas = muchas or []

    def fetchone(self):
        return self.una

    def fetchall(self):
        return self.muchas


class BaseFalsa:
    def __init__(self, orden=None):
        self.orden = orden
        self.consultas = []

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("select * from ordenes_trabajo where id"):
            return Resultado(self.orden)
        if "select 1 from ordenes_tareas" in sql:
            return Resultado({"hay": 1})
        if sql.startswith("select * from unidades where id"):
            return Resultado({"id": 7, "patente": "AD247MQ", "chofer": "Ana",
                              "km_actual": 120000})
        if sql.startswith("select numero from ordenes_trabajo"):
            return Resultado(None)
        if sql.startswith("insert into ordenes_trabajo"):
            return Resultado({"id": 41, "numero": 82})
        if sql.startswith(("update", "delete")):
            return Resultado()
        raise AssertionError(f"Consulta inesperada: {sql}")


class BaseService:
    def __init__(self, con_plan=True):
        self.consultas = []
        self.con_plan = con_plan

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("select id, patente, km_actual from unidades"):
            return Resultado({"id": 7, "patente": "AD247MQ", "km_actual": 123000})
        if sql.startswith("select p.cada_km from unidades"):
            return Resultado({"cada_km": 20000} if self.con_plan else None)
        if sql.startswith("select id from services where orden_id"):
            return Resultado(None)
        if sql.startswith("insert into services"):
            return Resultado({"id": 19})
        if sql.startswith("delete from alertas_silenciadas"):
            return Resultado()
        raise AssertionError(f"Consulta inesperada: {sql}")


GESTOR = {"id": 2, "nombre": "Nicolás", "rol": "admin"}


class CamposObligatorios(unittest.TestCase):
    def test_clase_fecha_y_km_son_obligatorios(self):
        validos = {"unidad_id": 7, "mantenimiento": "preventivo",
                   "fecha": "2026-09-09", "km": 123000}
        for campo in ("mantenimiento", "fecha", "km"):
            datos = dict(validos)
            datos[campo] = ""
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                ordenes.abrir(BaseFalsa(), datos, GESTOR)


class OrdenInterna(unittest.TestCase):
    def test_al_abrir_guarda_la_clasificacion_pero_aun_no_el_service(self):
        cx = BaseFalsa()
        with patch.object(ordenes, "_registrar_preventivo") as registrar:
            salida = ordenes.abrir(cx, {
                "unidad_id": 7, "mantenimiento": "preventivo",
                "fecha": "2026-09-09", "km": 123000,
                "solicitado": "Cambio de aceite y filtros",
            }, GESTOR)
        self.assertEqual(salida["id"], 41)
        registrar.assert_not_called()
        insercion = next(x for x in cx.consultas if x[0].startswith("insert into"))
        self.assertEqual(insercion[1][0], "preventivo")

    def test_al_cerrar_un_preventivo_registra_el_service(self):
        orden = {"id": 41, "numero": 82, "tipo": "interna", "estado": "abierta",
                 "mantenimiento": "preventivo", "unidad_id": 7,
                 "patente": "AD247MQ", "fecha": date(2026, 9, 9), "km": 123000,
                 "solicitado": "Cambio de aceite", "diagnostico": None, "taller": None}
        cx = BaseFalsa(orden)
        with patch.object(ordenes, "_registrar_preventivo", return_value=19) as registrar:
            salida = ordenes.cerrar(cx, {"id": 41}, GESTOR)
        registrar.assert_called_once_with(cx, orden, GESTOR)
        self.assertEqual(salida["service_id"], 19)

    def test_el_service_queda_vinculado_a_la_orden(self):
        cx = BaseService()
        service_id = ordenes._registrar_preventivo(cx, {
            "id": 41, "numero": 82, "mantenimiento": "preventivo",
            "unidad_id": 7, "fecha": date(2026, 9, 9), "km": 123000,
            "solicitado": "Cambio de aceite", "diagnostico": None, "taller": None,
        }, GESTOR)
        self.assertEqual(service_id, 19)
        insercion = next(x for x in cx.consultas if x[0].startswith("insert into services"))
        self.assertEqual(insercion[1][-1], 41)
        self.assertEqual(insercion[1][1], "2026-09-09")
        self.assertEqual(insercion[1][2], 123000)

    def test_sin_plan_no_permite_registrar_el_service(self):
        cx = BaseService(con_plan=False)
        with self.assertRaisesRegex(ValueError, "no tiene un plan"):
            ordenes._registrar_preventivo(cx, {
                "id": 41, "numero": 82, "mantenimiento": "preventivo",
                "unidad_id": 7, "fecha": date(2026, 9, 9), "km": 123000,
                "solicitado": "Cambio de aceite", "diagnostico": None, "taller": None,
            }, GESTOR)
        self.assertFalse(any(sql.startswith("insert into services") for sql, _ in cx.consultas))


class ServicioExterno(unittest.TestCase):
    def test_un_preventivo_nace_cerrado_y_registra_el_service(self):
        cx = BaseFalsa()
        with patch.object(ordenes, "_registrar_preventivo", return_value=20) as registrar:
            salida = ordenes.externa(cx, {
                "unidad_id": 7, "mantenimiento": "preventivo",
                "fecha": "2026-09-08", "km": 122500,
                "factura": "A-123", "monto": 250000,
                "taller": "Iveco", "solicitado": "Service M6",
            }, GESTOR)
        self.assertEqual(salida["service_id"], 20)
        orden = registrar.call_args.args[1]
        self.assertEqual(orden["mantenimiento"], "preventivo")
        self.assertEqual(orden["fecha"], date(2026, 9, 8))
        self.assertEqual(orden["km"], 122500)

    def test_un_correctivo_no_se_convierte_en_ultimo_service(self):
        with patch.object(ordenes.alertas, "guardar_service") as guardar:
            salida = ordenes._registrar_preventivo(BaseFalsa(), {
                "mantenimiento": "correctivo"
            }, GESTOR)
        self.assertIsNone(salida)
        guardar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
