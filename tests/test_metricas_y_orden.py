"""Orden del registro de combustible y métricas del taller."""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app  # noqa: F401  (agrega gomeria/ al camino)
import combustible as comb
import ordenes as ots


class OrdenDeTickets(unittest.TestCase):
    def consultas(self, **kw):
        cx = MagicMock()
        cx.execute.return_value.fetchall.return_value = []
        comb.tickets(cx, **kw)
        return [c[0][0] for c in cx.execute.call_args_list]

    def test_ordena_por_la_columna_pedida(self):
        sql = self.consultas(orden="litros", sentido="asc")[-1]
        self.assertIn("order by c.litros asc nulls last", sql)

    def test_columna_o_sentido_desconocidos_no_llegan_al_sql(self):
        sql = self.consultas(orden="1; drop table x", sentido="sideways")[-1]
        self.assertIn("order by c.fecha desc nulls last", sql)
        self.assertNotIn("drop", sql)

    def test_busca_tambien_por_chofer(self):
        sql = self.consultas(texto="garnica")[0]
        self.assertIn("c.chofer", sql)


class Metricas(unittest.TestCase):
    def test_costo_por_km_solo_con_unidades_con_lecturas(self):
        unidades = [
            {"patente": "AA111AA", "ordenes": 2, "preventivo": 100, "correctivo": 300,
             "sin_clasificar": 0, "total": 400, "externo": 400, "km": 1000},
            {"patente": "BB222BB", "ordenes": 1, "preventivo": 0, "correctivo": 500,
             "sin_clasificar": 0, "total": 500, "externo": 500, "km": None},
        ]
        respuestas = iter([unidades, [], []])
        cx = MagicMock()

        def ejecutar(sql, params=None):
            r = MagicMock()
            if "km_flota" in sql or "from (" in sql:
                r.fetchone.return_value = {"km": 1500, "unidades": 3}
            else:
                r.fetchall.return_value = next(respuestas)
            return r
        cx.execute.side_effect = ejecutar
        d = ots.metricas(cx, "2026-09-01", "2026-09-30")
        r = d["resumen"]
        self.assertEqual(r["total"], 900)
        self.assertEqual(r["km"], 1000)
        self.assertEqual(r["por_km"], 0.4)          # 400 / 1000, sin la unidad sin km
        self.assertEqual(r["preventivo_por_km"], 0.1)
        self.assertEqual(r["unidades_con_km"], 1)

    def test_fechas_invertidas_o_vacias(self):
        cx = MagicMock()
        cx.execute.return_value.fetchall.return_value = []
        cx.execute.return_value.fetchone.return_value = {"km": 0, "unidades": 0}
        d = ots.metricas(cx, "2026-09-30", "2026-09-01")
        self.assertEqual((d["desde"], d["hasta"]), ("2026-09-01", "2026-09-30"))
        self.assertIsNone(ots.metricas(cx, "x", None)["resumen"]["por_km"])


if __name__ == "__main__":
    unittest.main()


class GastoDeRepuestos(unittest.TestCase):
    """La salida directa a una patente va al gasto de la unidad."""

    def base(self, orden_del_dia=None):
        cx = MagicMock()
        self.sqls = []

        def ejecutar(sql, params=()):
            plano = " ".join(sql.split())
            self.sqls.append((plano, params))
            r = MagicMock()
            if "information_schema" in plano:
                r.fetchone.return_value = {"x": 1}
            elif plano.startswith("select id, activo from repuestos_articulos"):
                r.fetchone.return_value = {"id": 4, "activo": True}
            elif plano.startswith("insert into repuestos_movimientos"):
                r.fetchone.return_value = {"id": 88}
            elif plano.startswith("select a.codigo"):
                r.fetchone.return_value = {"codigo": "FIL-1", "descripcion": "Filtro",
                                           "ultimo_costo": 1500}
            elif plano.startswith("select id, km_actual from unidades"):
                r.fetchone.return_value = {"id": 7, "km_actual": 120000}
            elif plano.startswith("select id from ordenes_trabajo"):
                r.fetchone.return_value = orden_del_dia
            elif plano.startswith("insert into ordenes_trabajo"):
                r.fetchone.return_value = {"id": 55}
            return r
        cx.execute.side_effect = ejecutar
        return cx

    def salida(self, cx):
        import repuestos
        repuestos.crear_movimiento(cx, {"codigo": "FIL-1", "tipo": "Salida", "cantidad": 2,
                                        "fecha": "2026-10-09", "patente": "AB 123 CD"},
                                   {"id": 1, "nombre": "N"})

    def test_crea_orden_interna_cerrada_con_el_repuesto_al_ultimo_costo(self):
        cx = self.base()
        self.salida(cx)
        orden = [p for s, p in self.sqls if s.startswith("insert into ordenes_trabajo")]
        self.assertEqual(len(orden), 1)
        renglon = [p for s, p in self.sqls if s.startswith("insert into ordenes_repuestos")][0]
        self.assertEqual(renglon, (55, 4, 88, "FIL-1", "Filtro", 2, 1500))

    def test_la_segunda_salida_del_dia_va_a_la_misma_orden(self):
        cx = self.base(orden_del_dia={"id": 31})
        self.salida(cx)
        self.assertFalse([s for s, _ in self.sqls if s.startswith("insert into ordenes_trabajo")])
        renglon = [p for s, p in self.sqls if s.startswith("insert into ordenes_repuestos")][0]
        self.assertEqual(renglon[0], 31)


class CostoDeCubiertas(unittest.TestCase):
    def test_la_primera_vez_que_se_monta_crea_el_servicio_externo(self):
        import base
        base._COLUMNAS.add(("cubiertas", "costo_pendiente"))
        sqls = []

        def ejecutar(sql, params=()):
            plano = " ".join(sql.split())
            sqls.append((plano, params))
            r = MagicMock()
            if plano.startswith("select id, codigo, marca"):
                r.fetchone.return_value = {"id": 9, "codigo": "FC-1-01", "marca": "FATE",
                                           "modelo": None, "medida": "295/80R22.5",
                                           "costo_compra": 450000, "proveedor_id": 3,
                                           "proveedor": "Gomería Morandi", "factura": "0001-1"}
            elif plano.startswith("select patente, km_actual"):
                r.fetchone.return_value = {"patente": "AB123CD", "km_actual": 98000}
            elif plano.startswith("select codigo from configuracion_posiciones"):
                r.fetchone.return_value = {"codigo": "2IE"}
            elif plano.startswith("insert into ordenes_trabajo"):
                r.fetchone.return_value = {"id": 70}
            return r
        cx = MagicMock()
        cx.execute.side_effect = ejecutar
        self.assertEqual(base._cargar_costo_cubierta(cx, 9, 7, 3), 70)
        orden = [p for s, p in sqls if s.startswith("insert into ordenes_trabajo")][0]
        self.assertEqual(orden[:6], (7, "AB123CD", 98000, "Gomería Morandi", "0001-1", 450000))
        self.assertIn("2IE", orden[6])
        self.assertTrue(any(s.startswith("update cubiertas set costo_pendiente = false")
                            for s, _ in sqls))

    def test_sin_costo_pendiente_no_hace_nada(self):
        import base
        base._COLUMNAS.add(("cubiertas", "costo_pendiente"))
        cx = MagicMock()
        cx.execute.return_value.fetchone.return_value = None
        self.assertIsNone(base._cargar_costo_cubierta(cx, 9, 7))


class Proveedores(unittest.TestCase):
    CATALOGO = [{"id": 1, "nombre": "Frenos Catamarca", "cuit": "30-71234567-8"},
                {"id": 2, "nombre": "Gomería Morandi", "cuit": None},
                {"id": 3, "nombre": "VIENOR S.A.", "cuit": ""},
                {"id": 4, "nombre": "Frenos del Valle", "cuit": ""}]

    def nombre(self, *args):
        import proveedores
        p, como = proveedores.emparejar(*args)
        return (p and p["nombre"], como)

    def test_por_cuit_aunque_el_nombre_no_se_parezca(self):
        self.assertEqual(self.nombre("Cualquiera", "30712345678", self.CATALOGO),
                         ("Frenos Catamarca", "cuit"))

    def test_mal_escrito_o_con_forma_societaria(self):
        self.assertEqual(self.nombre("FRENOS CATAMRCA S.R.L.", None, self.CATALOGO)[0],
                         "Frenos Catamarca")
        self.assertEqual(self.nombre("Vienor SA", None, self.CATALOGO)[0], "VIENOR S.A.")

    def test_razon_social_en_vez_del_nombre_de_fantasia(self):
        self.assertEqual(self.nombre("Morandi Carlos Ezequiel", None, self.CATALOGO)[0],
                         "Gomería Morandi")

    def test_lo_que_no_se_parece_queda_sin_elegir(self):
        self.assertEqual(self.nombre("Frenos Sur", None, self.CATALOGO), (None, None))
        self.assertEqual(self.nombre("Taller Nuevo", None, self.CATALOGO), (None, None))

    def test_el_elegido_por_el_modelo_tiene_que_estar_en_la_lista(self):
        self.assertEqual(self.nombre("x", None, self.CATALOGO, "Gomería Morandi"),
                         ("Gomería Morandi", "nombre"))
        self.assertEqual(self.nombre("x", None, self.CATALOGO, "Inventado SRL"), (None, None))
