"""El circuito de recapado: lo que sale, lo que vuelve y lo que no volvió.

Todas las semanas el gomero se lleva un lote a recapar y trae el de la
semana anterior. Antes cada mitad se cargaba por separado —estado
'recapado' al salir, desgaste.recapar() al volver— y las dos no se
hablaban. Por eso no se podía contestar la única pregunta que importa:

    si se llevó doce y trajo diez, ¿cuáles son las dos que faltan?

Eso es plata parada en lo de un tercero, y no se notaba.
"""
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import recapado


class Resultado:
    def __init__(self, una=None, muchas=None):
        self.una = una
        self.muchas = muchas or []

    def fetchone(self):
        return self.una

    def fetchall(self):
        return self.muchas


GESTOR = {"id": 1, "nombre": "Nicolás", "rol": "admin"}


class Base:
    """Un depósito con tres gomas y un contador de remitos."""

    def __init__(self, cubiertas=None, tope=3, pendientes=0, movidas=0):
        self.cubiertas = cubiertas or [
            {"id": 1, "codigo": "4521", "estado": "stock", "recapados": 1,
             "remanente_mm": 4},
            {"id": 2, "codigo": "4522", "estado": "stock", "recapados": 0,
             "remanente_mm": 5},
            {"id": 3, "codigo": "STK-R007", "estado": "montada", "recapados": 1,
             "remanente_mm": 6},
            {"id": 4, "codigo": "9999", "estado": "stock", "recapados": 3,
             "remanente_mm": 2},
        ]
        self.tope = tope
        self.pendientes = pendientes
        self.movidas = movidas
        self.consultas = []
        self.renglones = []

    def rollback(self):
        pass

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("select recapados_maximo from parametros"):
            return Resultado({"recapados_maximo": self.tope})
        if sql.startswith("select id, codigo, estado, recapados, remanente_mm"):
            pedidas = valores[0]
            return Resultado(muchas=[c for c in self.cubiertas
                                     if c["id"] in pedidas])
        if sql.startswith("update recapado_contador"):
            return Resultado({"ultimo": 7})
        if sql.startswith("insert into recapado_renglones"):
            self.renglones.append(valores)
            return Resultado()
        if sql.startswith("select * from recapado_envios where id"):
            return Resultado({"id": "REC-00007", "estado": "abierto",
                              "recapador": "BANDAG", "numero": 7})
        if sql.startswith("select * from recapado_renglones where envio_id = %s and estado"):
            return Resultado(muchas=[{"id": 10, "cubierta_id": 1},
                                     {"id": 11, "cubierta_id": 2}])
        if sql.startswith("select * from recapado_renglones where envio_id"):
            return Resultado(muchas=[{"id": 10, "cubierta_id": 1},
                                     {"id": 11, "cubierta_id": 2}])
        if sql.startswith("select count(*) as n from recapado_renglones where envio_id = %s and estado = 'enviada'"):
            return Resultado({"n": self.pendientes})
        if sql.startswith("select count(*) as n from recapado_renglones where envio_id = %s and estado <>"):
            return Resultado({"n": self.movidas})
        if sql.startswith("select * from v_recapado_envios where id"):
            return Resultado({"id": "REC-00007", "numero": 7,
                              "recapador": "BANDAG", "estado": "abierto"})
        if sql.startswith("select r.*, c.codigo"):
            return Resultado(muchas=[])
        if sql.startswith(("insert", "update")):
            return Resultado()
        raise AssertionError(f"Consulta inesperada: {sql}")

    def hizo(self, arranque):
        return [(sql, v) for sql, v in self.consultas if sql.startswith(arranque)]


class Enviar(unittest.TestCase):
    def enviar(self, cx=None, **cambios):
        datos = {"recapador": "BANDAG", "cubiertas": [1, 2]}
        datos.update(cambios)
        cx = cx or Base()
        return cx, recapado.enviar(cx, datos, GESTOR)

    def test_numera_el_remito_con_el_contador(self):
        """Y no con max(numero)+1: dos cargas a la vez leerían el mismo."""
        cx, _ = self.enviar()
        self.assertTrue(cx.hizo("update recapado_contador"))
        inserto = cx.hizo("insert into recapado_envios")[0][1]
        self.assertEqual(inserto[0], "REC-00007")
        self.assertEqual(inserto[1], 7)

    def test_las_gomas_quedan_en_recapado(self):
        cx, _ = self.enviar()
        estados = [v for sql, v in cx.hizo("update cubiertas set estado = 'recapado'")]
        self.assertEqual(sorted(estados), [(1,), (2,)])

    def test_guarda_con_cuanto_dibujo_se_fue(self):
        """Sirve para discutir con el recapador cuando dice que la carcasa
        no servía."""
        cx, _ = self.enviar()
        porid = {r[1]: r for r in cx.renglones}
        self.assertEqual(porid[1][2], 4)      # remanente
        self.assertEqual(porid[1][3], 1)      # recapados al salir

    def test_la_montada_no_se_puede_mandar(self):
        with self.assertRaisesRegex(ValueError, "montada|dep.sito|stock"):
            self.enviar(cubiertas=[1, 3])

    def test_la_que_llego_al_tope_no_se_puede_mandar(self):
        """Tres recapados aguanta una carcasa. El cuarto es tirar plata en
        una goma que se va a abrir."""
        with self.assertRaisesRegex(ValueError, "3 recapados"):
            self.enviar(cubiertas=[1, 4])

    def test_el_tope_sale_de_parametros(self):
        """Con el tope en uno, la que ya lleva un recapado no va más."""
        cx = Base(tope=1)
        with self.assertRaisesRegex(ValueError, "m.ximo es 1"):
            self.enviar(cx, cubiertas=[1])

    def test_con_el_tope_mas_alto_la_misma_goma_sale(self):
        cx, _ = self.enviar(Base(tope=4), cubiertas=[4])
        self.assertTrue(cx.hizo("insert into recapado_envios"))

    def test_sin_recapador_no_sale(self):
        with self.assertRaisesRegex(ValueError, "recapador"):
            self.enviar(recapador="")

    def test_sin_cubiertas_no_sale(self):
        with self.assertRaisesRegex(ValueError, "al menos una"):
            self.enviar(cubiertas=[])

    def test_la_repetida_se_rechaza(self):
        """Cargar dos veces la misma goma en un remito haría que vuelva
        dos veces."""
        with self.assertRaisesRegex(ValueError, "repetida"):
            self.enviar(cubiertas=[1, 1])

    def test_lo_firma_un_gestor(self):
        with self.assertRaises(PermissionError):
            recapado.enviar(Base(), {"recapador": "X", "cubiertas": [1]},
                            {"rol": "consulta"})


class Recibir(unittest.TestCase):
    def recibir(self, cx=None, **cambios):
        datos = {"envio_id": "REC-00007",
                 "vueltas": [{"cubierta_id": 1, "costo": 38000}]}
        datos.update(cambios)
        cx = cx or Base(pendientes=1)
        with patch.object(recapado.desgaste, "recapar", return_value=2) as rec:
            salida = recapado.recibir(cx, datos, GESTOR)
        return cx, salida, rec

    def test_la_vuelta_la_registra_desgaste_recapar(self):
        """Es quien cierra la vida anterior y abre la nueva. Acá no se
        duplica nada de eso."""
        _, _, rec = self.recibir()
        rec.assert_called_once()
        self.assertEqual(rec.call_args.kwargs["costo"], 38000)
        self.assertEqual(rec.call_args.kwargs["proveedor"], "BANDAG")

    def test_el_envio_sigue_abierto_si_falta_una(self):
        """Mientras falte una goma aparece en «qué hay afuera»: es lo que
        hace que lo que no volvió no se pierda de vista."""
        cx = Base(pendientes=1)
        _, salida, _ = self.recibir(cx)
        self.assertEqual(salida["pendientes"], 1)
        self.assertFalse(cx.hizo("update recapado_envios set estado = 'cerrado'"))

    def test_se_cierra_cuando_no_queda_nada(self):
        cx = Base(pendientes=0)
        self.recibir(cx)
        self.assertTrue(cx.hizo("update recapado_envios set estado = 'cerrado'"))

    def test_la_rechazada_se_da_de_baja(self):
        """El recapador dice que la carcasa no va: no vuelve al stock."""
        cx = Base(pendientes=1)
        with patch.object(recapado.desgaste, "recapar") as rec, \
             patch.object(recapado.base, "cambiar_estado_cubierta") as baja:
            recapado.recibir(cx, {"envio_id": "REC-00007", "vueltas": [
                {"cubierta_id": 1, "rechazada": True, "motivo": "Carcasa abierta"}
            ]}, GESTOR)
        rec.assert_not_called()
        self.assertEqual(baja.call_args.args[2], "baja")
        self.assertIn("Carcasa abierta", baja.call_args.kwargs["nota"])

    def test_la_factura_va_en_el_envio(self):
        """Es una sola factura para todo el lote, no una por goma."""
        cx, _, _ = self.recibir(factura="0001-00001234")
        puesta = cx.hizo("update recapado_envios set factura")
        self.assertEqual(puesta[0][1][0], "0001-00001234")

    def test_una_cubierta_ajena_al_envio_se_rechaza(self):
        with self.assertRaisesRegex(ValueError, "no está pendiente"):
            self.recibir(vueltas=[{"cubierta_id": 99}])


class Anular(unittest.TestCase):
    def test_devuelve_las_gomas_al_deposito(self):
        cx = Base(movidas=0)
        recapado.anular(cx, {"envio_id": "REC-00007"}, GESTOR)
        vueltas = cx.hizo("update cubiertas set estado = 'stock'")
        self.assertEqual(len(vueltas), 2)

    def test_no_se_anula_si_ya_volvio_alguna(self):
        """Su vida nueva ya está abierta: deshacer el envío no la
        desharía."""
        cx = Base(movidas=2)
        with self.assertRaisesRegex(ValueError, "ya volvieron 2"):
            recapado.anular(cx, {"envio_id": "REC-00007"}, GESTOR)

    def test_el_numero_no_se_reutiliza(self):
        """El correlativo es inmutable: el papel con ese número puede
        estar dando vueltas."""
        cx = Base(movidas=0)
        recapado.anular(cx, {"envio_id": "REC-00007"}, GESTOR)
        self.assertFalse(cx.hizo("update recapado_contador"))


if __name__ == "__main__":
    unittest.main()
