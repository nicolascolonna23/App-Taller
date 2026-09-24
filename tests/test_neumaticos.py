"""El aviso de cambios de neumáticos.

Dos partes:

- Las validaciones de lo que se escribe, sin base.
- Las vistas de 28_cambios_neumaticos.sql contra un PostgreSQL de prueba,
  en un esquema propio que se borra al final. Solo corren con
  MT_TEST_DATABASE_URL, nunca contra la base de verdad.

Lo que importa probar de las vistas es lo que no se ve a simple vista: que
el semi herede los km del tractor que lo llevaba, que una rotación dentro
del mismo eje no reinicie la cuenta, y que un cambio cargado a mano no se
cuente dos veces en las métricas.
"""
import datetime
import os
import sys
import unittest
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))

import mapas  # noqa: E402
import neumaticos as neu  # noqa: E402

HOY = datetime.date.today()
ENCARGADO = {"id": 1, "usuario": "enc", "nombre": "Encargado", "rol": "encargado"}
OPERARIO = {"id": 2, "usuario": "op", "nombre": "Operario", "rol": "operario"}


class Validaciones(unittest.TestCase):
    def test_numeros_con_puntos(self):
        self.assertEqual(neu._entero("150.000", "x"), 150000)
        self.assertIsNone(neu._entero("", "x"))
        with self.assertRaises(ValueError):
            neu._entero("abc", "x")
        with self.assertRaises(ValueError):
            neu._entero("", "x", obligatorio=True)

    def test_fecha_futura_no(self):
        with self.assertRaises(ValueError):
            neu._fecha((HOY + datetime.timedelta(days=2)).isoformat())
        self.assertEqual(neu._fecha(HOY.isoformat()), HOY)


@unittest.skipUnless(os.environ.get("MT_TEST_DATABASE_URL"),
                     "Requiere PostgreSQL de prueba explícito")
class Vistas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.rows import dict_row
        cls.pg, cls.row = psycopg, dict_row
        cls.esquema = "test_neu_" + uuid.uuid4().hex
        with psycopg.connect(os.environ["MT_TEST_DATABASE_URL"], autocommit=True) as cx:
            cx.execute("create schema " + cls.esquema)
        cls.addClassCleanup(cls.limpiar)
        with cls.conectar() as cx:
            for f in ("01_esquema.sql", "05_odometros.sql", "07_unidades.sql"):
                cx.execute((RAIZ / "gomeria" / f).read_text())
            cls.cargar_datos(cx)
            cx.execute((RAIZ / "gomeria" / "28_cambios_neumaticos.sql").read_text())
            cls.despues_del_sql(cx)
            cx.commit()

    @classmethod
    def conectar(cls):
        return cls.pg.connect(os.environ["MT_TEST_DATABASE_URL"], row_factory=cls.row,
                              options="-c search_path=" + cls.esquema + ",public")

    @classmethod
    def limpiar(cls):
        with cls.pg.connect(os.environ["MT_TEST_DATABASE_URL"], autocommit=True) as cx:
            cx.execute("drop schema " + cls.esquema + " cascade")

    @staticmethod
    def dia(n):
        return HOY - datetime.timedelta(days=n)

    @classmethod
    def cargar_datos(cls, cx):
        ids = {}
        for nombre in ("S-D-D", "D-D-D"):
            cfg = cx.execute("insert into configuraciones(nombre) values (%s) returning id",
                             (nombre,)).fetchone()["id"]
            ids[nombre] = cfg
            for p in mapas.expandir(nombre):
                cx.execute("""insert into configuracion_posiciones
                    (configuracion_id,codigo,eje,lado,montaje,es_auxilio,orden)
                    values (%s,%s,%s,%s,%s,%s,%s)""",
                    (cfg, p["codigo"], p["eje"], p["lado"], p["montaje"],
                     p["es_auxilio"], p["orden"]))
        cls.semi = cx.execute("""insert into unidades(patente,uso,configuracion_id)
            values ('AB123CD','SEMIRREMOLQUE',%s) returning id""",
            (ids["D-D-D"],)).fetchone()["id"]
        cls.tractor = cx.execute("""insert into unidades(patente,uso,configuracion_id,semi)
            values ('AA111AA','LARGA DISTANCIA',%s,'AB 123 CD') returning id""",
            (ids["S-D-D"],)).fetchone()["id"]
        cls.otro = cx.execute("""insert into unidades(patente,uso,configuracion_id)
            values ('AC222BB','LARGA DISTANCIA',%s) returning id""",
            (ids["S-D-D"],)).fetchone()["id"]
        cls.cfg = ids
        # El tractor hace 500 km por día desde hace 200 días. El semi no
        # tiene satelital.
        for n in range(199, -1, -1):
            cx.execute("insert into odometros(unidad_id,patente,fecha,km) values (%s,'AA111AA',%s,%s)",
                       (cls.tractor, cls.dia(n), 100000 + (199 - n) * 500))

        def pos(unidad, codigo):
            return cx.execute("""select p.id from configuracion_posiciones p
                join unidades u on u.configuracion_id = p.configuracion_id
                where u.id=%s and p.codigo=%s""", (unidad, codigo)).fetchone()["id"]

        def cubierta(codigo, marca, modelo):
            return cx.execute("""insert into cubiertas(codigo,marca,modelo,estado)
                values (%s,%s,%s,'montada') returning id""", (codigo, marca, modelo)).fetchone()["id"]

        c1 = cubierta("C1", "MICHELIN", "X MULTI Z")
        c2 = cubierta("C2", "FATE", "SR200")
        c3 = cubierta("C3", "FATE", "SR200")
        # C1 en el direccional desde hace 100 días.
        cx.execute("insert into montajes(unidad_id,posicion_id,cubierta_id,desde) values (%s,%s,%s,%s)",
                   (cls.tractor, pos(cls.tractor, "1I"), c1, cls.dia(100)))
        # C2: 2IE hace 150 días, rotada a 2II hace 50. Mismo eje: la cuenta
        # sigue desde hace 150.
        cx.execute("insert into montajes(unidad_id,posicion_id,cubierta_id,desde,hasta) values (%s,%s,%s,%s,%s)",
                   (cls.tractor, pos(cls.tractor, "2IE"), c2, cls.dia(150), cls.dia(50)))
        cx.execute("insert into montajes(unidad_id,posicion_id,cubierta_id,desde) values (%s,%s,%s,%s)",
                   (cls.tractor, pos(cls.tractor, "2II"), c2, cls.dia(50)))
        # C3 estuvo 30 días en el eje 2 y salió: es una duración cerrada.
        cx.execute("insert into montajes(unidad_id,posicion_id,cubierta_id,desde,hasta) values (%s,%s,%s,%s,%s)",
                   (cls.tractor, pos(cls.tractor, "2DE"), c3, cls.dia(190), cls.dia(160)))
        cx.execute("update cubiertas set estado='stock' where id=%s", (c3,))

    @classmethod
    def despues_del_sql(cls, cx):
        cx.execute("""insert into neumaticos_reglas(configuracion_id,eje,cada_km,aviso_km)
                      values (%s,1,50000,15000)""", (cls.cfg["D-D-D"],))
        cx.execute("insert into neumaticos_cambios(unidad_id,eje,fecha) values (%s,1,%s)",
                   (cls.semi, cls.dia(100)))
        cx.execute("""insert into neumaticos_cambios(unidad_id,eje,fecha,marca,modelo)
                      values (%s,2,%s,'BRIDGESTONE','R168'), (%s,2,%s,'BRIDGESTONE','R168')""",
                   (cls.semi, cls.dia(180), cls.semi, cls.dia(60)))

    def eje(self, cx, unidad, eje):
        return cx.execute("select * from v_neumaticos_ejes where unidad_id=%s and eje=%s",
                          (unidad, eje)).fetchone()

    def test_reglas_iniciales_del_tractor(self):
        with self.conectar() as cx:
            r = {f["eje"]: f for f in cx.execute(
                "select * from v_neumaticos_mapa_ejes where mapa='S-D-D'").fetchall()}
        self.assertEqual(r[1]["cada_km"], 150000)
        self.assertEqual(r[1]["tipo_eje"], "direccion")
        self.assertEqual(r[2]["cada_km"], 220000)
        self.assertEqual(r[3]["cada_km"], 220000)

    def test_enganche_inicial_desde_la_primera_lectura(self):
        with self.conectar() as cx:
            e = cx.execute("select * from enganches where semi_id=%s", (self.semi,)).fetchall()
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["tractor_id"], self.tractor)
        self.assertEqual(e[0]["desde"], self.dia(199))
        self.assertEqual(e[0]["origen"], "inicial")

    def test_semi_hereda_los_km_del_tractor(self):
        with self.conectar() as cx:
            f = self.eje(cx, self.semi, 1)
        # 100 días de 500 km desde el cambio.
        self.assertEqual(f["km"], 50000)
        self.assertEqual(f["tractor"], "AA111AA")
        self.assertEqual(f["estado"], "vencido")

    def test_rotacion_en_el_mismo_eje_no_reinicia(self):
        with self.conectar() as cx:
            p = cx.execute("""select * from v_neumaticos_posiciones
                              where unidad_id=%s and posicion='2II'""", (self.tractor,)).fetchone()
        self.assertEqual(p["base_fecha"], self.dia(150))
        self.assertEqual(p["km"], 150 * 500)
        self.assertEqual(p["km_restantes"], 220000 - 150 * 500)

    def test_eje_sin_regla_y_sin_dato(self):
        with self.conectar() as cx:
            self.assertEqual(self.eje(cx, self.semi, 3)["estado"], "sin_regla")
            self.assertEqual(self.eje(cx, self.otro, 1)["estado"], "sin_dato")

    def test_cambio_manual_mas_nuevo_que_el_montaje_manda(self):
        with self.conectar() as cx:
            cx.execute("insert into neumaticos_cambios(unidad_id,eje,fecha) values (%s,1,%s)",
                       (self.tractor, self.dia(10)))
            p = cx.execute("""select * from v_neumaticos_posiciones
                              where unidad_id=%s and posicion='1I'""", (self.tractor,)).fetchone()
            cx.rollback()
        self.assertEqual(p["origen"], "cambio")
        self.assertEqual(p["km"], 10 * 500)

    def test_duraciones(self):
        with self.conectar() as cx:
            d = cx.execute("select * from v_neumaticos_duraciones order by fuente").fetchall()
        self.assertEqual(len(d), 2)
        cambio, montaje = d
        self.assertEqual((cambio["patente"], cambio["eje"], cambio["dias"], cambio["km"]),
                         ("AB123CD", 2, 120, 120 * 500))
        self.assertEqual(cambio["tipo_eje"], "arrastre")
        self.assertEqual((montaje["cubierta"], montaje["dias"], montaje["km"]),
                         ("C3", 30, 30 * 500))
        self.assertEqual(montaje["tipo_eje"], "traccion")

    def test_cambiar_el_semi_en_la_ficha_cierra_el_enganche(self):
        with self.conectar() as cx:
            cx.execute("update unidades set semi=null where id=%s", (self.tractor,))
            cx.execute("update unidades set semi='AB123CD' where id=%s", (self.otro,))
            e = cx.execute("select * from enganches where semi_id=%s order by desde",
                           (self.semi,)).fetchall()
            cx.rollback()
        self.assertEqual(len(e), 2)
        self.assertEqual(e[0]["hasta"], HOY)
        self.assertEqual((e[1]["tractor_id"], e[1]["desde"], e[1]["hasta"]),
                         (self.otro, HOY, None))

    def test_panel_y_permisos(self):
        with self.conectar() as cx:
            p = neu.panel(cx)
            self.assertTrue(p["instalado"])
            self.assertEqual(p["resumen"]["vencido"], 1)
            with self.assertRaises(PermissionError):
                neu.aplicar(cx, {"op": "regla_guardar", "configuracion_id": self.cfg["D-D-D"],
                                 "eje": 2, "cada_km": "90.000"}, OPERARIO)
            neu.aplicar(cx, {"op": "regla_guardar", "configuracion_id": self.cfg["D-D-D"],
                             "eje": 2, "cada_km": "90.000", "tipo_eje": "arrastre"}, ENCARGADO)
            with self.assertRaises(ValueError):
                neu.aplicar(cx, {"op": "regla_guardar", "configuracion_id": self.cfg["D-D-D"],
                                 "eje": 9, "cada_km": 1000}, ENCARGADO)
            # El gomero registra; dos ejes en la misma parada.
            neu.aplicar(cx, {"op": "cambio_registrar", "unidad_id": self.tractor,
                             "ejes": [2, 3], "fecha": HOY.isoformat()}, OPERARIO)
            with self.assertRaises(ValueError):
                neu.aplicar(cx, {"op": "cambio_registrar", "unidad_id": self.tractor,
                                 "ejes": [4], "fecha": HOY.isoformat()}, OPERARIO)
            # Enganche viejo que se superpone con el inicial.
            with self.assertRaises(ValueError):
                neu.aplicar(cx, {"op": "enganche_cargar", "semi_id": self.semi,
                                 "tractor_id": self.otro, "desde": self.dia(250).isoformat(),
                                 "hasta": self.dia(100).isoformat()}, ENCARGADO)
            neu.aplicar(cx, {"op": "enganche_cargar", "semi_id": self.semi,
                             "tractor_id": self.otro, "desde": self.dia(300).isoformat(),
                             "hasta": self.dia(199).isoformat()}, ENCARGADO)
            r = cx.execute("""select cada_km from neumaticos_reglas
                              where configuracion_id=%s and eje=2""",
                           (self.cfg["D-D-D"],)).fetchone()
            self.assertEqual(r["cada_km"], 90000)
            self.assertEqual(self.eje(cx, self.tractor, 3)["km"], 0)
            cx.rollback()


if __name__ == "__main__":
    unittest.main()
