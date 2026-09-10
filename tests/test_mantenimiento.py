import os
import sys
import unittest
import io
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gomeria"))
import mantenimiento


class Resultado:
    def __init__(self, fila=None, filas=None):
        self.fila, self.filas = fila, filas or []
    def fetchone(self): return self.fila
    def fetchall(self): return self.filas


class BaseFalsa:
    def __init__(self): self.consultas = []
    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("insert into mantenimiento_planes"): return Resultado()
        if sql.startswith("update mantenimiento_planes"): return Resultado({"id": valores[-1]})
        if sql.startswith("update unidades set mantenimiento_plan_id"):
            return Resultado({"id": valores[-1]})
        if sql.startswith("delete from mantenimiento_planes"): return Resultado({"id": valores[0]})
        if sql.startswith("select id,nombre from mantenimiento_planes where activo"):
            return Resultado(filas=[{"id": 3, "nombre": "FURGONES"}])
        if sql.startswith("select id,patente from unidades where activa"):
            return Resultado(filas=[{"id": 7, "patente": "AD247MQ"}])
        if sql.startswith("select p.id, p.nombre"): return Resultado(filas=[])
        if sql.startswith("select u.id as unidad_id"): return Resultado(filas=[])
        raise AssertionError(sql)


ADMIN = {"rol": "admin"}


class Planes(unittest.TestCase):
    def test_crea_plan_con_intervalo(self):
        cx = BaseFalsa()
        mantenimiento.aplicar(cx, {"op": "plan_guardar", "nombre": "M1 Hi-Way",
                                  "cada_km": 40000}, ADMIN)
        self.assertTrue(any(q.startswith("insert into mantenimiento_planes") and v[2] == 40000
                            for q, v in cx.consultas))

    def test_asigna_plan_a_unidad(self):
        cx = BaseFalsa()
        mantenimiento.aplicar(cx, {"op": "asignar", "unidad_id": 7, "plan_id": 3}, ADMIN)
        self.assertIn((3, 7), [v for q, v in cx.consultas
                              if q.startswith("update unidades set mantenimiento_plan_id")])

    def test_solo_gestores_parametrizan(self):
        with self.assertRaises(PermissionError):
            mantenimiento.aplicar(BaseFalsa(), {"op": "plan_guardar", "nombre": "M1",
                                                 "cada_km": 10000}, {"rol": "consulta"})

    def test_intervalo_debe_ser_positivo(self):
        with self.assertRaises(ValueError):
            mantenimiento.aplicar(BaseFalsa(), {"op": "plan_guardar", "nombre": "M1",
                                                 "cada_km": 0}, ADMIN)

    def test_importa_excel_y_normaliza_patente(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
        <row r="1"><c r="A1" t="inlineStr"><is><t>PATENTE</t></is></c><c r="B1" t="inlineStr"><is><t>TIPO DE SERVICE</t></is></c></row>
        <row r="2"><c r="A2" t="inlineStr"><is><t>AD 247 MQ</t></is></c><c r="B2" t="inlineStr"><is><t>FURGONES</t></is></c></row>
        </sheetData></worksheet>'''
        archivo = io.BytesIO()
        with zipfile.ZipFile(archivo, "w") as z:
            z.writestr("xl/worksheets/sheet1.xml", xml)
        cx = BaseFalsa()
        salida = mantenimiento.importar(cx, archivo.getvalue())
        self.assertEqual(salida["asignadas"], 1)
        self.assertTrue(any(q.startswith("update unidades set mantenimiento_plan_id")
                            and v == (3, 7) for q, v in cx.consultas))


if __name__ == "__main__":
    unittest.main()
