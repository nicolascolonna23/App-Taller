"""El circuito del vale: pedir, aprobar, reparar, rendir.

Lo que se prueba acá es lo que no se puede aflojar sin que el módulo deje
de servir: que el número salga de la sucursal que pide y no se repita, que
un rechazado sea terminal, que cada cambio de estado deje su renglón en el
historial, y que una factura de taller no entre sin un vale cerrado.
"""
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import ordenes
import vales


class Resultado:
    def __init__(self, una=None, muchas=None):
        self.una = una
        self.muchas = muchas or []

    def fetchone(self):
        return self.una

    def fetchall(self):
        return self.muchas


class BaseFalsa:
    """Lo mínimo de Postgres que necesita el módulo, con el contador adentro."""

    def __init__(self, vale=None, contadores=None, unidad=None):
        self.vale = vale
        self.contadores = dict(contadores or {"CAT": 0, "COR": 0})
        self.unidad = unidad or {"id": 7, "patente": "AD247MQ", "chofer": "Ana",
                                 "km_actual": 120000}
        self.consultas = []
        self.vales_insertados = []
        self.eventos = []

    def rollback(self):
        pass

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))

        if sql.startswith("select codigo, nombre, activa from sucursales"):
            codigo = valores[0]
            return Resultado({"codigo": codigo, "nombre": f"Sucursal {codigo}",
                              "activa": True})
        if sql.startswith("select * from unidades where id"):
            return Resultado(self.unidad)
        if sql.startswith("select * from unidades where patente"):
            return Resultado(self.unidad)
        if sql.startswith("select ultimo from vales_contador"):
            codigo = valores[0]
            if codigo not in self.contadores:
                return Resultado(None)
            return Resultado({"ultimo": self.contadores[codigo]})
        if sql.startswith("update vales_contador set ultimo"):
            self.contadores[valores[1]] = valores[0]
            return Resultado()
        if sql.startswith("insert into vales_contador"):
            self.contadores.setdefault(valores[0], 0)
            return Resultado()
        if sql.startswith("insert into vales"):
            self.vales_insertados.append(valores)
            return Resultado()
        if sql.startswith("insert into vale_eventos"):
            self.eventos.append(valores)
            return Resultado()
        if sql.startswith("select * from vales where id"):
            return Resultado(self.vale)
        if sql.startswith("select id from services where vale_id"):
            return Resultado(None)
        if sql.startswith(("update", "delete")):
            return Resultado()
        raise AssertionError(f"Consulta inesperada: {sql}")


SUCURSAL = {"id": 5, "nombre": "Ramón", "rol": "operario", "sucursal_codigo": "CAT"}
TALLER = {"id": 2, "nombre": "Nicolás", "rol": "admin"}

PEDIDO = {"unidad_id": 7, "km": 123000, "tipo": "CORRECTIVO",
          "origen": "CHECKLIST", "urgencia": "OPERA_CON_RIESGO",
          "detalle": "Pierde aire el sistema de frenos"}


def _vale(**cambios):
    base = {"id": "CAT-00001", "sucursal_codigo": "CAT", "numero": 1,
            "unidad_id": 7, "patente": "AD247MQ", "km": 123000,
            "tipo": "CORRECTIVO", "origen": "CHECKLIST",
            "urgencia": "OPERA_CON_RIESGO", "estado": "SOLICITADO",
            "detalle": "Pierde aire el sistema de frenos",
            "taller_sugerido": "Frenos del Valle", "taller": None,
            "monto_estimado": 80000, "monto_autorizado": None,
            "solicitante": "Ramón", "nota": None, "factura_numero": None,
            "creado_en": datetime.now(timezone.utc)}
    base.update(cambios)
    return base


# =====================================================================
class Numeracion(unittest.TestCase):
    def test_el_numero_sale_de_la_sucursal_que_pide(self):
        cx = BaseFalsa()
        salida = vales.crear(cx, dict(PEDIDO), SUCURSAL)
        self.assertEqual(salida["id"], "CAT-00001")
        self.assertEqual(salida["sucursal_codigo"], "CAT")

    def test_el_correlativo_es_por_sucursal_y_no_global(self):
        """Dos sucursales cargando a la vez: cada una sigue su propia serie."""
        cx = BaseFalsa(contadores={"CAT": 12, "COR": 46})
        catamarca = vales.crear(cx, dict(PEDIDO), SUCURSAL)
        cordoba = vales.crear(cx, dict(PEDIDO),
                              dict(SUCURSAL, sucursal_codigo="COR"))
        self.assertEqual(catamarca["id"], "CAT-00013")
        self.assertEqual(cordoba["id"], "COR-00047")
        self.assertEqual(cx.contadores, {"CAT": 13, "COR": 47})

    def test_el_contador_se_toma_bloqueado(self):
        """Sin el bloqueo, dos cargas leen el mismo número y lo repiten."""
        cx = BaseFalsa()
        vales.crear(cx, dict(PEDIDO), SUCURSAL)
        lectura = next(sql for sql, _ in cx.consultas
                       if sql.startswith("select ultimo from vales_contador"))
        self.assertIn("for update", lectura)
        self.assertFalse(any("max(numero)" in sql for sql, _ in cx.consultas),
                         "El número no puede salir de un max() sin bloqueo.")

    def test_la_sucursal_del_usuario_le_gana_a_la_que_manda_la_pantalla(self):
        cx = BaseFalsa()
        salida = vales.crear(cx, dict(PEDIDO, sucursal_codigo="COR"), SUCURSAL)
        self.assertEqual(salida["sucursal_codigo"], "CAT")

    def test_sin_sucursal_no_hay_vale(self):
        with self.assertRaises(ValueError):
            vales.crear(BaseFalsa(), dict(PEDIDO), {"nombre": "Administración"})


class CamposDelPedido(unittest.TestCase):
    def test_tipo_origen_y_detalle_son_obligatorios(self):
        for campo in ("tipo", "origen", "detalle"):
            datos = dict(PEDIDO)
            datos[campo] = ""
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                vales.crear(BaseFalsa(), datos, SUCURSAL)

    def test_el_km_se_completa_con_el_del_maestro(self):
        cx = BaseFalsa()
        vales.crear(cx, dict(PEDIDO, km=""), SUCURSAL)
        self.assertEqual(cx.vales_insertados[0][5], 120000)

    def test_el_vale_nace_solicitado_y_con_su_evento(self):
        cx = BaseFalsa()
        vales.crear(cx, dict(PEDIDO), SUCURSAL)
        self.assertEqual(cx.eventos[0][1], "SOLICITADO")
        self.assertEqual(cx.eventos[0][2], "Ramón")


class RegularizacionDeRuta(unittest.TestCase):
    def test_una_fecha_anterior_necesita_estar_marcada_como_regularizacion(self):
        ayer = (date.today() - timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            vales.crear(BaseFalsa(), dict(PEDIDO, fecha_hecho=ayer), SUCURSAL)

    def test_marcada_entra_con_la_fecha_del_hecho(self):
        ayer = date.today() - timedelta(days=1)
        cx = BaseFalsa()
        vales.crear(cx, dict(PEDIDO, fecha_hecho=ayer.isoformat(),
                             regularizacion_ruta=True), SUCURSAL)
        insercion = cx.vales_insertados[0]
        self.assertEqual(insercion[-3], ayer)
        self.assertTrue(insercion[-2])

    def test_la_fecha_de_manana_no_existe(self):
        manana = (date.today() + timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            vales.crear(BaseFalsa(), dict(PEDIDO, fecha_hecho=manana,
                                          regularizacion_ruta=True), SUCURSAL)


# =====================================================================
class MaquinaDeEstados(unittest.TestCase):
    def test_solo_el_taller_aprueba(self):
        cx = BaseFalsa(vale=_vale())
        with self.assertRaises(PermissionError):
            vales.aprobar(cx, {"id": "CAT-00001"}, SUCURSAL)

    def test_aprobar_guarda_quien_y_deja_evento(self):
        cx = BaseFalsa(vale=_vale())
        salida = vales.aprobar(cx, {"id": "CAT-00001", "monto_autorizado": 90000,
                                    "taller": "Frenos del Valle"}, TALLER)
        self.assertEqual(salida["estado"], "APROBADO")
        self.assertEqual(cx.eventos[0][1], "APROBADO")
        self.assertEqual(cx.eventos[0][2], "Nicolás")

    def test_un_rechazo_sin_motivo_no_va(self):
        cx = BaseFalsa(vale=_vale())
        with self.assertRaises(ValueError):
            vales.rechazar(cx, {"id": "CAT-00001"}, TALLER)

    def test_un_rechazado_no_llega_a_ejecucion_por_ningun_camino(self):
        """Es terminal: si la sucursal insiste, carga uno nuevo citándolo."""
        cx = BaseFalsa(vale=_vale(estado="RECHAZADO", nota="Lo hace el taller propio"))
        for paso, quien in ((vales.iniciar, SUCURSAL), (vales.aprobar, TALLER),
                            (vales.cerrar, SUCURSAL)):
            with self.subTest(paso=paso.__name__), self.assertRaises(ValueError):
                paso(cx, {"id": "CAT-00001", "factura_numero": "A-1"}, quien)

    def test_no_se_repara_con_el_vale_solicitado(self):
        cx = BaseFalsa(vale=_vale(estado="SOLICITADO"))
        with self.assertRaises(ValueError):
            vales.iniciar(cx, {"id": "CAT-00001"}, SUCURSAL)

    def test_un_cerrado_no_se_vuelve_a_cerrar(self):
        cx = BaseFalsa(vale=_vale(estado="CERRADO", factura_numero="A-1"))
        with self.assertRaises(ValueError):
            vales.cerrar(cx, {"id": "CAT-00001", "factura_numero": "A-2"}, SUCURSAL)

    def test_sin_factura_el_vale_no_cierra(self):
        cx = BaseFalsa(vale=_vale(estado="EN_EJECUCION"))
        with self.assertRaises(ValueError):
            vales.cerrar(cx, {"id": "CAT-00001"}, SUCURSAL)

    def test_el_historial_reconstruye_el_circuito_entero(self):
        cx = BaseFalsa(vale=_vale())
        vales.aprobar(cx, {"id": "CAT-00001"}, TALLER)
        cx.vale = _vale(estado="APROBADO")
        vales.iniciar(cx, {"id": "CAT-00001"}, SUCURSAL)
        cx.vale = _vale(estado="EN_EJECUCION", tipo="CORRECTIVO")
        vales.cerrar(cx, {"id": "CAT-00001", "factura_numero": "0001-0009"}, SUCURSAL)
        self.assertEqual([e[1] for e in cx.eventos],
                         ["APROBADO", "EN_EJECUCION", "CERRADO"])


class CierrePreventivo(unittest.TestCase):
    def test_cerrar_un_preventivo_registra_el_service(self):
        cx = BaseFalsa(vale=_vale(estado="APROBADO", tipo="PREVENTIVO",
                                  detalle="Service de 40.000"))
        with patch.object(vales.alertas, "guardar_service", return_value=31) as guardar:
            salida = vales.cerrar(cx, {"id": "CAT-00001",
                                       "factura_numero": "0001-0009"}, SUCURSAL)
        guardar.assert_called_once()
        self.assertEqual(salida["service_id"], 31)
        self.assertIsNone(salida["aviso"])

    def test_un_correctivo_no_toca_el_proximo_service(self):
        cx = BaseFalsa(vale=_vale(estado="APROBADO", tipo="CORRECTIVO"))
        with patch.object(vales.alertas, "guardar_service") as guardar:
            vales.cerrar(cx, {"id": "CAT-00001", "factura_numero": "A-1"}, SUCURSAL)
        guardar.assert_not_called()

    def test_sin_plan_de_mantenimiento_el_vale_cierra_igual_y_avisa(self):
        """La sucursal tiene la factura en la mano: no puede quedar trabada."""
        cx = BaseFalsa(vale=_vale(estado="APROBADO", tipo="PREVENTIVO"))
        with patch.object(vales.alertas, "guardar_service",
                          side_effect=ValueError("La unidad no tiene un plan")):
            salida = vales.cerrar(cx, {"id": "CAT-00001",
                                       "factura_numero": "A-1"}, SUCURSAL)
        self.assertEqual(salida["estado"], "CERRADO")
        self.assertIn("plan", salida["aviso"])


# =====================================================================
class Demoras(unittest.TestCase):
    def test_los_dias_habiles_no_cuentan_el_fin_de_semana(self):
        viernes, lunes = date(2026, 9, 11), date(2026, 9, 14)
        self.assertEqual(vales.dias_habiles(viernes, lunes), 1)

    def test_un_pedido_de_hoy_no_esta_demorado(self):
        self.assertFalse(vales.demorado(_vale()))

    def test_con_la_unidad_parada_la_respuesta_es_inmediata(self):
        hace_tres_horas = datetime.now(timezone.utc) - timedelta(hours=3)
        self.assertTrue(vales.demorado(_vale(urgencia="UNIDAD_PARADA",
                                             creado_en=hace_tres_horas)))
        self.assertFalse(vales.demorado(_vale(urgencia="PUEDE_ESPERAR",
                                              creado_en=hace_tres_horas)))

    def test_un_vale_resuelto_nunca_esta_demorado(self):
        viejo = datetime.now(timezone.utc) - timedelta(days=30)
        self.assertFalse(vales.demorado(_vale(estado="APROBADO", creado_en=viejo)))


# =====================================================================
class RendirLaFactura(unittest.TestCase):
    """La regla que mira el módulo de gastos: sin vale cerrado no se rinde."""

    class BaseGasto(BaseFalsa):
        def __init__(self, vale=None, exigir=True, usado=None):
            super().__init__(vale=vale)
            self.exigir = exigir
            self.usado = usado

        def execute(self, consulta, valores=()):
            sql = " ".join(consulta.split())
            if sql.startswith("select exigir_vale from vales_ajustes"):
                self.consultas.append((sql, valores))
                return Resultado({"exigir_vale": self.exigir})
            if sql.startswith("select numero from ordenes_trabajo where vale_id"):
                self.consultas.append((sql, valores))
                return Resultado(self.usado)
            if sql.startswith("select numero from ordenes_trabajo"):
                self.consultas.append((sql, valores))
                return Resultado(None)
            if sql.startswith("insert into ordenes_trabajo"):
                self.consultas.append((sql, valores))
                return Resultado({"id": 41, "numero": 82})
            return super().execute(consulta, valores)

    FACTURA = {"unidad_id": 7, "mantenimiento": "correctivo", "fecha": "2026-09-09",
               "km": 123000, "factura": "0001-0009", "monto": 90000,
               "taller": "Frenos del Valle"}

    def test_una_factura_de_taller_sin_vale_no_entra(self):
        cx = self.BaseGasto(exigir=True)
        with self.assertRaises(ValueError) as e:
            ordenes.externa(cx, dict(self.FACTURA), TALLER)
        self.assertIn("vale", str(e.exception).lower())

    def test_con_un_vale_cerrado_entra_y_queda_atada(self):
        cx = self.BaseGasto(vale=_vale(estado="CERRADO", factura_numero="0001-0009"))
        with patch.object(ordenes, "_registrar_preventivo", return_value=None):
            salida = ordenes.externa(cx, dict(self.FACTURA, vale_id="CAT-00001"), TALLER)
        self.assertEqual(salida["numero"], 82)
        insercion = next(v for sql, v in cx.consultas
                         if sql.startswith("insert into ordenes_trabajo"))
        self.assertEqual(insercion[-1], "CAT-00001")

    def test_con_el_vale_todavia_abierto_no_se_rinde(self):
        cx = self.BaseGasto(vale=_vale(estado="EN_EJECUCION"))
        with self.assertRaises(ValueError) as e:
            ordenes.externa(cx, dict(self.FACTURA, vale_id="CAT-00001"), TALLER)
        self.assertIn("cerrado", str(e.exception))

    def test_el_vale_de_otra_unidad_no_sirve(self):
        cx = self.BaseGasto(vale=_vale(estado="CERRADO", patente="AA823XJ",
                                       factura_numero="A-1"))
        with self.assertRaises(ValueError):
            ordenes.externa(cx, dict(self.FACTURA, vale_id="CAT-00001"), TALLER)

    def test_un_vale_no_se_rinde_dos_veces(self):
        cx = self.BaseGasto(vale=_vale(estado="CERRADO", factura_numero="A-1"),
                            usado={"numero": 80})
        with self.assertRaises(ValueError) as e:
            ordenes.externa(cx, dict(self.FACTURA, vale_id="CAT-00001"), TALLER)
        self.assertIn("80", str(e.exception))

    def test_sin_el_modulo_instalado_nadie_queda_trabado(self):
        cx = self.BaseGasto(exigir=False)
        with patch.object(ordenes, "_registrar_preventivo", return_value=None):
            salida = ordenes.externa(cx, dict(self.FACTURA), TALLER)
        self.assertEqual(salida["numero"], 82)


if __name__ == "__main__":
    unittest.main()
