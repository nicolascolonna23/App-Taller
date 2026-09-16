"""El circuito de la solicitud: pedir, aprobar, reparar, rendir.

Lo que se prueba acá es lo que no se puede aflojar sin que el módulo deje
de servir: que el número salga de la sucursal que pide y no se repita, que
un rechazado sea terminal, que cada cambio de estado deje su renglón en el
historial, y que una factura de taller no entre sin una solicitud cerrada.
"""
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import ordenes
import solicitudes


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

    def __init__(self, solicitud=None, contadores=None, unidad=None):
        self.solicitud = solicitud
        self.contadores = dict(contadores or {"CAT": 0, "COR": 0})
        self.unidad = unidad or {"id": 7, "patente": "AD247MQ", "chofer": "Ana",
                                 "km_actual": 120000}
        self.consultas = []
        self.solicitudes_insertados = []
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
        if sql.startswith("select ultimo from solicitudes_contador"):
            codigo = valores[0]
            if codigo not in self.contadores:
                return Resultado(None)
            return Resultado({"ultimo": self.contadores[codigo]})
        if sql.startswith("update solicitudes_contador set ultimo"):
            self.contadores[valores[1]] = valores[0]
            return Resultado()
        if sql.startswith("insert into solicitudes_contador"):
            self.contadores.setdefault(valores[0], 0)
            return Resultado()
        if sql.startswith("insert into solicitudes_compra"):
            self.solicitudes_insertados.append(valores)
            return Resultado()
        if sql.startswith("insert into solicitud_eventos"):
            self.eventos.append(valores)
            return Resultado()
        if sql.startswith("select * from solicitudes_compra where id"):
            return Resultado(self.solicitud)
        if sql.startswith("select id from services where solicitud_id"):
            return Resultado(None)
        if sql.startswith(("update", "delete")):
            return Resultado()
        raise AssertionError(f"Consulta inesperada: {sql}")


SUCURSAL = {"id": 5, "nombre": "Ramón", "rol": "operario", "sucursal_codigo": "CAT"}
TALLER = {"id": 2, "nombre": "Nicolás", "rol": "admin"}

PEDIDO = {"unidad_id": 7, "km": 123000, "tipo": "CORRECTIVO",
          "origen": "CHECKLIST", "urgencia": "OPERA_CON_RIESGO",
          "detalle": "Pierde aire el sistema de frenos"}


def _solicitud(**cambios):
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
        salida = solicitudes.crear(cx, dict(PEDIDO), SUCURSAL)
        self.assertEqual(salida["id"], "CAT-00001")
        self.assertEqual(salida["sucursal_codigo"], "CAT")

    def test_el_correlativo_es_por_sucursal_y_no_global(self):
        """Dos sucursales cargando a la vez: cada una sigue su propia serie."""
        cx = BaseFalsa(contadores={"CAT": 12, "COR": 46})
        catamarca = solicitudes.crear(cx, dict(PEDIDO), SUCURSAL)
        cordoba = solicitudes.crear(cx, dict(PEDIDO),
                              dict(SUCURSAL, sucursal_codigo="COR"))
        self.assertEqual(catamarca["id"], "CAT-00013")
        self.assertEqual(cordoba["id"], "COR-00047")
        self.assertEqual(cx.contadores, {"CAT": 13, "COR": 47})

    def test_el_contador_se_toma_bloqueado(self):
        """Sin el bloqueo, dos cargas leen el mismo número y lo repiten."""
        cx = BaseFalsa()
        solicitudes.crear(cx, dict(PEDIDO), SUCURSAL)
        lectura = next(sql for sql, _ in cx.consultas
                       if sql.startswith("select ultimo from solicitudes_contador"))
        self.assertIn("for update", lectura)
        self.assertFalse(any("max(numero)" in sql for sql, _ in cx.consultas),
                         "El número no puede salir de un max() sin bloqueo.")

    def test_la_sucursal_del_usuario_le_gana_a_la_que_manda_la_pantalla(self):
        cx = BaseFalsa()
        salida = solicitudes.crear(cx, dict(PEDIDO, sucursal_codigo="COR"), SUCURSAL)
        self.assertEqual(salida["sucursal_codigo"], "CAT")

    def test_sin_sucursal_no_hay_solicitud(self):
        with self.assertRaises(ValueError):
            solicitudes.crear(BaseFalsa(), dict(PEDIDO), {"nombre": "Administración"})


class CamposDelPedido(unittest.TestCase):
    def test_tipo_origen_y_detalle_son_obligatorios(self):
        for campo in ("tipo", "origen", "detalle"):
            datos = dict(PEDIDO)
            datos[campo] = ""
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                solicitudes.crear(BaseFalsa(), datos, SUCURSAL)

    def test_el_km_se_completa_con_el_del_maestro(self):
        cx = BaseFalsa()
        solicitudes.crear(cx, dict(PEDIDO, km=""), SUCURSAL)
        self.assertEqual(cx.solicitudes_insertados[0][5], 120000)

    def test_la_solicitud_nace_solicitada_y_con_su_evento(self):
        cx = BaseFalsa()
        solicitudes.crear(cx, dict(PEDIDO), SUCURSAL)
        self.assertEqual(cx.eventos[0][1], "SOLICITADO")
        self.assertEqual(cx.eventos[0][2], "Ramón")


class RegularizacionDeRuta(unittest.TestCase):
    def test_una_fecha_anterior_necesita_estar_marcada_como_regularizacion(self):
        ayer = (date.today() - timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            solicitudes.crear(BaseFalsa(), dict(PEDIDO, fecha_hecho=ayer), SUCURSAL)

    def test_marcada_entra_con_la_fecha_del_hecho(self):
        ayer = date.today() - timedelta(days=1)
        cx = BaseFalsa()
        solicitudes.crear(cx, dict(PEDIDO, fecha_hecho=ayer.isoformat(),
                             regularizacion_ruta=True), SUCURSAL)
        insercion = cx.solicitudes_insertados[0]
        self.assertEqual(insercion[-3], ayer)
        self.assertTrue(insercion[-2])

    def test_la_fecha_de_manana_no_existe(self):
        manana = (date.today() + timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            solicitudes.crear(BaseFalsa(), dict(PEDIDO, fecha_hecho=manana,
                                          regularizacion_ruta=True), SUCURSAL)


# =====================================================================
class MaquinaDeEstados(unittest.TestCase):
    def test_solo_el_taller_aprueba(self):
        cx = BaseFalsa(solicitud=_solicitud())
        with self.assertRaises(PermissionError):
            solicitudes.aprobar(cx, {"id": "CAT-00001"}, SUCURSAL)

    def test_aprobar_guarda_quien_y_deja_evento(self):
        cx = BaseFalsa(solicitud=_solicitud())
        salida = solicitudes.aprobar(cx, {"id": "CAT-00001", "monto_autorizado": 90000,
                                    "taller": "Frenos del Valle"}, TALLER)
        self.assertEqual(salida["estado"], "APROBADO")
        self.assertEqual(cx.eventos[0][1], "APROBADO")
        self.assertEqual(cx.eventos[0][2], "Nicolás")

    def test_un_rechazo_sin_motivo_no_va(self):
        cx = BaseFalsa(solicitud=_solicitud())
        with self.assertRaises(ValueError):
            solicitudes.rechazar(cx, {"id": "CAT-00001"}, TALLER)

    def test_un_rechazado_no_llega_a_ejecucion_por_ningun_camino(self):
        """Es terminal: si la sucursal insiste, carga una nueva citándola."""
        cx = BaseFalsa(solicitud=_solicitud(estado="RECHAZADO", nota="Lo hace el taller propio"))
        for paso, quien in ((solicitudes.iniciar, SUCURSAL), (solicitudes.aprobar, TALLER),
                            (solicitudes.cerrar, SUCURSAL)):
            with self.subTest(paso=paso.__name__), self.assertRaises(ValueError):
                paso(cx, {"id": "CAT-00001", "factura_numero": "A-1"}, quien)

    def test_no_se_repara_con_la_solicitud_recien_pedida(self):
        cx = BaseFalsa(solicitud=_solicitud(estado="SOLICITADO"))
        with self.assertRaises(ValueError):
            solicitudes.iniciar(cx, {"id": "CAT-00001"}, SUCURSAL)

    def test_un_cerrado_no_se_vuelve_a_cerrar(self):
        cx = BaseFalsa(solicitud=_solicitud(estado="CERRADO", factura_numero="A-1"))
        with self.assertRaises(ValueError):
            solicitudes.cerrar(cx, {"id": "CAT-00001", "factura_numero": "A-2"}, SUCURSAL)

    def test_sin_factura_la_solicitud_no_cierra(self):
        cx = BaseFalsa(solicitud=_solicitud(estado="EN_EJECUCION"))
        with self.assertRaises(ValueError):
            solicitudes.cerrar(cx, {"id": "CAT-00001"}, SUCURSAL)

    def test_el_historial_reconstruye_el_circuito_entero(self):
        cx = BaseFalsa(solicitud=_solicitud())
        solicitudes.aprobar(cx, {"id": "CAT-00001"}, TALLER)
        cx.solicitud = _solicitud(estado="APROBADO")
        solicitudes.iniciar(cx, {"id": "CAT-00001"}, SUCURSAL)
        cx.solicitud = _solicitud(estado="EN_EJECUCION", tipo="CORRECTIVO")
        solicitudes.cerrar(cx, {"id": "CAT-00001", "factura_numero": "0001-0009"}, SUCURSAL)
        self.assertEqual([e[1] for e in cx.eventos],
                         ["APROBADO", "EN_EJECUCION", "CERRADO"])


class CierrePreventivo(unittest.TestCase):
    def test_cerrar_un_preventivo_registra_el_service(self):
        cx = BaseFalsa(solicitud=_solicitud(estado="APROBADO", tipo="PREVENTIVO",
                                  detalle="Service de 40.000"))
        with patch.object(solicitudes.alertas, "guardar_service", return_value=31) as guardar:
            salida = solicitudes.cerrar(cx, {"id": "CAT-00001",
                                       "factura_numero": "0001-0009"}, SUCURSAL)
        guardar.assert_called_once()
        self.assertEqual(salida["service_id"], 31)
        self.assertIsNone(salida["aviso"])

    def test_un_correctivo_no_toca_el_proximo_service(self):
        cx = BaseFalsa(solicitud=_solicitud(estado="APROBADO", tipo="CORRECTIVO"))
        with patch.object(solicitudes.alertas, "guardar_service") as guardar:
            solicitudes.cerrar(cx, {"id": "CAT-00001", "factura_numero": "A-1"}, SUCURSAL)
        guardar.assert_not_called()

    def test_sin_plan_de_mantenimiento_la_solicitud_cierra_igual_y_avisa(self):
        """La sucursal tiene la factura en la mano: no puede quedar trabada."""
        cx = BaseFalsa(solicitud=_solicitud(estado="APROBADO", tipo="PREVENTIVO"))
        with patch.object(solicitudes.alertas, "guardar_service",
                          side_effect=ValueError("La unidad no tiene un plan")):
            salida = solicitudes.cerrar(cx, {"id": "CAT-00001",
                                       "factura_numero": "A-1"}, SUCURSAL)
        self.assertEqual(salida["estado"], "CERRADO")
        self.assertIn("plan", salida["aviso"])


# =====================================================================
class Demoras(unittest.TestCase):
    def test_los_dias_habiles_no_cuentan_el_fin_de_semana(self):
        viernes, lunes = date(2026, 9, 11), date(2026, 9, 14)
        self.assertEqual(solicitudes.dias_habiles(viernes, lunes), 1)

    def test_un_pedido_de_hoy_no_esta_demorado(self):
        self.assertFalse(solicitudes.demorado(_solicitud()))

    def test_con_la_unidad_parada_la_respuesta_es_inmediata(self):
        hace_tres_horas = datetime.now(timezone.utc) - timedelta(hours=3)
        self.assertTrue(solicitudes.demorado(_solicitud(urgencia="UNIDAD_PARADA",
                                             creado_en=hace_tres_horas)))
        self.assertFalse(solicitudes.demorado(_solicitud(urgencia="PUEDE_ESPERAR",
                                              creado_en=hace_tres_horas)))

    def test_una_solicitud_resuelta_nunca_esta_demorada(self):
        viejo = datetime.now(timezone.utc) - timedelta(days=30)
        self.assertFalse(solicitudes.demorado(_solicitud(estado="APROBADO", creado_en=viejo)))


# =====================================================================
class RendirLaFactura(unittest.TestCase):
    """Quién mandó a hacer el trabajo es lo que decide si va con solicitud.

    Mantenimiento se carga como siempre: el área que decide el gasto es la
    misma que lo controla. Lo que mandó a hacer una sucursal va con su
    solicitud cerrada, que es el gasto que antes se rendía sin constancia.
    """

    class BaseGasto(BaseFalsa):
        def __init__(self, solicitud=None, exigir=True, usado=None):
            super().__init__(solicitud=solicitud)
            self.exigir = exigir
            self.usado = usado

        def execute(self, consulta, valores=()):
            sql = " ".join(consulta.split())
            if sql.startswith("select exigir_solicitud from solicitudes_ajustes"):
                self.consultas.append((sql, valores))
                return Resultado({"exigir_solicitud": self.exigir})
            if sql.startswith("select numero from ordenes_trabajo where solicitud_id"):
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

    def _insercion(self, cx):
        return next(v for sql, v in cx.consultas
                    if sql.startswith("insert into ordenes_trabajo"))

    def test_lo_que_manda_mantenimiento_se_carga_sin_solicitud(self):
        """Es el caso de siempre: el taller no se pide permiso a sí mismo."""
        cx = self.BaseGasto(exigir=True)
        with patch.object(ordenes, "_registrar_preventivo", return_value=None):
            salida = ordenes.externa(cx, dict(self.FACTURA, gestion="mantenimiento"), TALLER)
        self.assertEqual(salida["numero"], 82)
        insercion = self._insercion(cx)
        self.assertIsNone(insercion[-2])                  # sin solicitud
        self.assertEqual(insercion[-1], "mantenimiento")  # y queda dicho quién fue

    def test_lo_que_manda_una_sucursal_sin_solicitud_no_entra(self):
        cx = self.BaseGasto(exigir=True)
        with self.assertRaises(ValueError) as e:
            ordenes.externa(cx, dict(self.FACTURA, gestion="sucursal"), TALLER)
        self.assertIn("solicitud", str(e.exception).lower())

    def test_sin_decir_quien_lo_mando_a_hacer_no_se_carga(self):
        """La pregunta no se adivina: de ella depende toda la regla."""
        cx = self.BaseGasto(exigir=True)
        with self.assertRaises(ValueError) as e:
            ordenes.externa(cx, dict(self.FACTURA), TALLER)
        self.assertIn("mantenimiento", str(e.exception).lower())

    def test_con_una_solicitud_cerrada_entra_y_queda_atada(self):
        cx = self.BaseGasto(solicitud=_solicitud(estado="CERRADO", factura_numero="0001-0009"))
        with patch.object(ordenes, "_registrar_preventivo", return_value=None):
            salida = ordenes.externa(cx, dict(self.FACTURA, gestion="sucursal",
                                              solicitud_id="CAT-00001"), TALLER)
        self.assertEqual(salida["numero"], 82)
        insercion = self._insercion(cx)
        self.assertEqual(insercion[-2], "CAT-00001")
        self.assertEqual(insercion[-1], "sucursal")

    def test_traer_una_solicitud_ya_dice_que_fue_una_sucursal(self):
        cx = self.BaseGasto(solicitud=_solicitud(estado="CERRADO", factura_numero="A-1"))
        with patch.object(ordenes, "_registrar_preventivo", return_value=None):
            ordenes.externa(cx, dict(self.FACTURA, solicitud_id="CAT-00001"), TALLER)
        self.assertEqual(self._insercion(cx)[-1], "sucursal")

    def test_con_la_solicitud_todavia_abierta_no_se_rinde(self):
        cx = self.BaseGasto(solicitud=_solicitud(estado="EN_EJECUCION"))
        with self.assertRaises(ValueError) as e:
            ordenes.externa(cx, dict(self.FACTURA, gestion="sucursal",
                                     solicitud_id="CAT-00001"), TALLER)
        self.assertIn("cerrada", str(e.exception))

    def test_la_solicitud_de_otra_unidad_no_sirve(self):
        cx = self.BaseGasto(solicitud=_solicitud(estado="CERRADO", patente="AA823XJ",
                                                 factura_numero="A-1"))
        with self.assertRaises(ValueError):
            ordenes.externa(cx, dict(self.FACTURA, gestion="sucursal",
                                     solicitud_id="CAT-00001"), TALLER)

    def test_una_solicitud_no_se_rinde_dos_veces(self):
        cx = self.BaseGasto(solicitud=_solicitud(estado="CERRADO", factura_numero="A-1"),
                            usado={"numero": 80})
        with self.assertRaises(ValueError) as e:
            ordenes.externa(cx, dict(self.FACTURA, gestion="sucursal",
                                     solicitud_id="CAT-00001"), TALLER)
        self.assertIn("80", str(e.exception))

    def test_sin_el_modulo_instalado_nadie_queda_trabado(self):
        cx = self.BaseGasto(exigir=False)
        with patch.object(ordenes, "_registrar_preventivo", return_value=None):
            salida = ordenes.externa(cx, dict(self.FACTURA, gestion="sucursal"), TALLER)
        self.assertEqual(salida["numero"], 82)


if __name__ == "__main__":
    unittest.main()
