"""Los planes de mantenimiento: qué se acepta, qué se rechaza y a quién le toca.

El plan es el criterio del taller escrito una sola vez —M1 cada 45.000, M3
cada 135.000— para que no dependa de lo que escriba el que carga el
service. Por eso lo que se prueba acá es la puerta de entrada: sin base de
datos, lo que decide Python.
"""
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

    def fetchone(self):
        return self.fila

    def fetchall(self):
        return self.filas


class BaseFalsa:
    """Contesta según con qué empieza la consulta. Lo que no está, explota."""

    def __init__(self, planes=(1, 2), unidades=(7,), servicios_del_plan=False,
                 nombre_repetido=False):
        self.consultas = []
        self.planes = list(planes)
        self.unidades = list(unidades)
        self.servicios_del_plan = servicios_del_plan
        self.nombre_repetido = nombre_repetido
        self.deshecho = 0

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("insert into mantenimiento_planes"):
            if self.nombre_repetido:
                raise RuntimeError('duplicate key value violates unique '
                                   'constraint "mantenimiento_planes_nombre_key"')
            return Resultado({"id": 9})
        if sql.startswith("update mantenimiento_planes"):
            return Resultado({"id": valores[-1]})
        if sql.startswith("select 1 from mantenimiento_planes"):
            return Resultado({"?column?": 1} if valores[0] in self.planes else None)
        if sql.startswith("select id from mantenimiento_planes"):
            return Resultado(filas=[{"id": i} for i in valores[0]
                                    if i in self.planes])
        if sql.startswith("delete from mantenimiento_planes"):
            return Resultado({"id": valores[0]})
        if sql.startswith("select 1 from services where plan_id"):
            return Resultado({"?column?": 1} if self.servicios_del_plan else None)
        if sql.startswith("select 1 from unidades where id"):
            return Resultado({"?column?": 1} if valores[0] in self.unidades else None)
        if sql.startswith("select id from unidades where activa and modelo"):
            return Resultado(filas=[{"id": i} for i in self.unidades])
        if sql.startswith("select id,nombre from mantenimiento_planes where activo"):
            return Resultado(filas=[{"id": 3, "nombre": "FURGONES"}])
        if sql.startswith("select id,patente from unidades where activa"):
            return Resultado(filas=[{"id": 7, "patente": "AD247MQ"}])
        if sql.startswith(("delete from unidad_planes", "insert into unidad_planes")):
            return Resultado()
        # Las tres lecturas con las que aplicar() devuelve cómo quedó todo.
        if sql.startswith(("select p.id, p.nombre", "select u.id as unidad_id",
                           "select modelo, count(*)")):
            return Resultado(filas=[])
        raise AssertionError(f"consulta sin respuesta preparada: {sql[:90]}")

    def rollback(self):
        self.deshecho += 1

    def escritas(self, prefijo):
        return [v for q, v in self.consultas if q.startswith(prefijo)]


ADMIN = {"rol": "admin", "nombre": "Nicolás"}


class CrearYCambiar(unittest.TestCase):
    def test_crea_el_plan_con_su_intervalo(self):
        cx = BaseFalsa()
        mantenimiento.aplicar(cx, {"op": "plan_guardar", "nombre": "M1 Hi-Way",
                                   "cada_km": 40000}, ADMIN)
        self.assertEqual(cx.escritas("insert into mantenimiento_planes"),
                         [("M1 Hi-Way", None, 40000.0)])

    def test_sin_nombre_no_hay_plan(self):
        with self.assertRaises(ValueError):
            mantenimiento.aplicar(BaseFalsa(), {"op": "plan_guardar", "nombre": "   ",
                                                "cada_km": 40000}, ADMIN)

    def test_el_intervalo_tiene_que_ser_un_numero_positivo(self):
        for cada in (None, "", "cuarenta mil", 0, -100):
            with self.assertRaises(ValueError):
                mantenimiento.aplicar(BaseFalsa(), {"op": "plan_guardar",
                                                    "nombre": "M1", "cada_km": cada}, ADMIN)

    def test_un_intervalo_absurdo_se_frena(self):
        """Un cero de más en 45.000 no lo ve nadie hasta que la unidad no
        avisa nunca más."""
        with self.assertRaises(ValueError):
            mantenimiento.aplicar(BaseFalsa(), {"op": "plan_guardar", "nombre": "M1",
                                                "cada_km": 4500000}, ADMIN)

    def test_dos_planes_no_se_pueden_llamar_igual(self):
        """El nombre es lo único que ve el que carga el service: si hay dos
        M1 no hay forma de saber cuál eligió."""
        cx = BaseFalsa(nombre_repetido=True)
        with self.assertRaises(ValueError) as e:
            mantenimiento.aplicar(cx, {"op": "plan_guardar", "nombre": "M1 S-Way",
                                       "cada_km": 45000}, ADMIN)
        self.assertIn("M1 S-Way", str(e.exception))
        self.assertEqual(cx.deshecho, 1)

    def test_solo_gestores_parametrizan(self):
        with self.assertRaises(PermissionError):
            mantenimiento.aplicar(BaseFalsa(), {"op": "plan_guardar", "nombre": "M1",
                                                "cada_km": 10000}, {"rol": "operario"})


class Borrar(unittest.TestCase):
    def test_un_plan_sin_usar_se_borra(self):
        cx = BaseFalsa()
        mantenimiento.aplicar(cx, {"op": "plan_borrar", "id": 1}, ADMIN)
        self.assertTrue(cx.escritas("delete from mantenimiento_planes"))

    def test_un_plan_con_historia_se_apaga_pero_no_se_borra(self):
        """Los services que se hicieron bajo ese plan dicen de qué fueron.
        Borrar el plan sería perder eso."""
        cx = BaseFalsa(servicios_del_plan=True)
        mantenimiento.aplicar(cx, {"op": "plan_borrar", "id": 1}, ADMIN)
        self.assertFalse(cx.escritas("delete from mantenimiento_planes"))
        self.assertTrue(cx.escritas("update mantenimiento_planes set activo = false"))

    def test_un_plan_que_no_existe_lo_dice(self):
        with self.assertRaises(ValueError):
            mantenimiento.aplicar(BaseFalsa(), {"op": "plan_borrar", "id": 99}, ADMIN)


class Asignar(unittest.TestCase):
    def test_la_unidad_queda_con_los_planes_que_se_le_pasan(self):
        """Un camión lleva M1, M2 y M3 a la vez: cada uno cuenta y avisa
        por su cuenta."""
        cx = BaseFalsa()
        mantenimiento.aplicar(cx, {"op": "asignar", "unidad_id": 7,
                                   "planes": [1, 2]}, ADMIN)
        self.assertEqual(cx.escritas("delete from unidad_planes where unidad_id"),
                         [(7,)])
        self.assertEqual(cx.escritas("insert into unidad_planes"),
                         [(7, 1, "Nicolás"), (7, 2, "Nicolás")])

    def test_sacarle_todos_los_planes_es_mandar_la_lista_vacia(self):
        cx = BaseFalsa()
        mantenimiento.aplicar(cx, {"op": "asignar", "unidad_id": 7, "planes": []}, ADMIN)
        self.assertTrue(cx.escritas("delete from unidad_planes where unidad_id"))
        self.assertFalse(cx.escritas("insert into unidad_planes"))

    def test_un_plan_que_ya_no_existe_no_se_asigna(self):
        with self.assertRaises(ValueError):
            mantenimiento.aplicar(BaseFalsa(), {"op": "asignar", "unidad_id": 7,
                                                "planes": [1, 99]}, ADMIN)

    def test_una_unidad_que_no_existe_lo_dice(self):
        with self.assertRaises(ValueError):
            mantenimiento.aplicar(BaseFalsa(), {"op": "asignar", "unidad_id": 404,
                                                "planes": [1]}, ADMIN)

    def test_por_modelo_alcanza_a_todas_las_unidades_del_modelo(self):
        """El plan lo fija la fábrica por modelo: asignarlo de a una
        patente en una flota de cien es media tarde de trabajo."""
        cx = BaseFalsa(unidades=(7, 8, 9))
        mantenimiento.aplicar(cx, {"op": "asignar_modelo", "modelo": "S-WAY 480",
                                   "planes": [1, 2]}, ADMIN)
        self.assertEqual(len(cx.escritas("insert into unidad_planes")), 6)

    def test_un_modelo_sin_unidades_lo_dice(self):
        cx = BaseFalsa(unidades=())
        with self.assertRaises(ValueError):
            mantenimiento.aplicar(cx, {"op": "asignar_modelo", "modelo": "HI-WAY 999",
                                       "planes": [1]}, ADMIN)

    def test_sin_modelo_no_se_asigna_nada(self):
        with self.assertRaises(ValueError):
            mantenimiento.aplicar(BaseFalsa(), {"op": "asignar_modelo", "modelo": " ",
                                                "planes": [1]}, ADMIN)

    def test_importa_excel_y_agrega_el_plan_a_la_patente(self):
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
        self.assertIn((7, 3), cx.escritas("insert into unidad_planes"))


if __name__ == "__main__":
    unittest.main()
