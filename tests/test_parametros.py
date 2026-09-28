"""Los parámetros: lo que antes decidía el código.

Dos cosas se prueban acá. Que el kilometraje en manual apague de verdad
al satelital —si no, el job le pisa el número al que lo cargó a mano— y
que un plan sepa qué clase es: el preventivo sin intervalo no puede
avisar, y el correctivo con intervalo es una agenda que nadie va a
cumplir, porque las roturas no se agendan.
"""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import parametros


class Resultado:
    def __init__(self, una=None, muchas=None):
        self.una, self.muchas = una, muchas or []

    def fetchone(self):
        return self.una

    def fetchall(self):
        return self.muchas


class BaseFalsa:
    def __init__(self, km_origen="automatico", sin_tablas=False, plan=None,
                 combustible_origen="manual", combustible_fuente=None):
        self.km_origen = km_origen
        self.combustible_origen = combustible_origen
        self.combustible_fuente = combustible_fuente
        self.sin_tablas = sin_tablas
        self.plan = plan
        self.consultas = []

    def rollback(self):
        pass

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if self.sin_tablas:
            raise RuntimeError('relation "parametros" does not exist')
        if sql.startswith("select * from parametros"):
            return Resultado({"unica": True, "km_origen": self.km_origen,
                              "km_hora": "05:00",
                              "combustible_origen": self.combustible_origen,
                              "combustible_fuente": self.combustible_fuente,
                              "combustible_hora": "06:00"})
        if sql.startswith("select clase from mantenimiento_planes"):
            return Resultado(self.plan)
        if sql.startswith("insert into mantenimiento_planes"):
            return Resultado({"id": 11})
        if sql.startswith(("update", "insert", "delete")):
            return Resultado({"id": 1})
        raise AssertionError(f"Consulta inesperada: {sql}")


ADMIN = {"id": 1, "nombre": "Nicolás", "rol": "admin", "administra": True, "gestiona": True}
TALLER = {"id": 3, "nombre": "Juan", "rol": "taller", "administra": False, "gestiona": True}
CHOFER = {"id": 5, "nombre": "Ramón", "rol": "chofer", "administra": False, "gestiona": False}


class Kilometraje(unittest.TestCase):
    def test_solo_un_administrador_cambia_de_dónde_salen_los_km(self):
        for quien in (TALLER, CHOFER):
            with self.subTest(rol=quien["rol"]), self.assertRaises(PermissionError):
                parametros.guardar(BaseFalsa(), {"km_origen": "manual"}, quien)

    def test_en_manual_el_satelital_no_escribe(self):
        """Si escribiera, le pisaría el número al que lo cargó a mano."""
        self.assertFalse(parametros.km_automatico(BaseFalsa(km_origen="manual")))
        self.assertTrue(parametros.km_automatico(BaseFalsa(km_origen="automatico")))

    def test_sin_el_sql_corrido_sigue_siendo_automatico(self):
        """Como fue siempre: una migración que no se corrió no apaga nada."""
        self.assertTrue(parametros.km_automatico(BaseFalsa(sin_tablas=True)))

    def test_un_origen_inventado_no_entra(self):
        with self.assertRaises(ValueError):
            parametros.guardar(BaseFalsa(), {"km_origen": "satelital"}, ADMIN)

    def test_la_hora_va_en_formato_de_reloj(self):
        with self.assertRaises(ValueError):
            parametros.guardar(BaseFalsa(), {"km_origen": "automatico",
                                             "km_hora": "a la mañana"}, ADMIN)

    def test_guardar_deja_el_origen_elegido(self):
        cx = BaseFalsa()
        salida = parametros.guardar(cx, {"km_origen": "manual", "km_hora": "06:30"}, ADMIN)
        self.assertEqual(salida["km_origen"], "manual")
        puesta = next(v for sql, v in cx.consultas if sql.startswith("update parametros"))
        self.assertEqual(puesta[:2], ("manual", "06:30"))


class Planes(unittest.TestCase):
    def test_un_preventivo_sin_intervalo_no_puede_avisar(self):
        with self.assertRaises(ValueError) as e:
            parametros.guardar_plan(BaseFalsa(), {"clase": "preventivo",
                                                  "nombre": "Service"}, ADMIN)
        self.assertIn("kilómetros", str(e.exception))

    def test_un_preventivo_por_dias_alcanza(self):
        """El aceite se vence aunque el camión no ruede."""
        cx = BaseFalsa()
        parametros.guardar_plan(cx, {"clase": "preventivo", "nombre": "Aceite",
                                     "cada_dias": 180}, ADMIN)
        valores = next(v for sql, v in cx.consultas
                       if sql.startswith("insert into mantenimiento_planes"))
        self.assertEqual(valores[3], None)    # sin km
        self.assertEqual(valores[4], 180)     # con días

    def test_un_correctivo_no_guarda_intervalo(self):
        """Una rotura no se agenda: si trae intervalo, se eligió mal la clase."""
        cx = BaseFalsa()
        parametros.guardar_plan(cx, {"clase": "correctivo", "nombre": "Embrague",
                                     "cada_km": 5000, "horas_estimadas": 8,
                                     "costo_estimado": 900000}, ADMIN)
        valores = next(v for sql, v in cx.consultas
                       if sql.startswith("insert into mantenimiento_planes"))
        self.assertEqual(valores[3], None)
        self.assertEqual(valores[4], None)
        self.assertEqual(valores[6], 8)       # las horas sí
        self.assertEqual(valores[7], 900000)  # y el costo

    def test_el_responsable_de_taller_toca_los_planes(self):
        """Parametrizar el mantenimiento es su trabajo, no el del dueño."""
        cx = BaseFalsa()
        salida = parametros.guardar_plan(cx, {"clase": "preventivo", "nombre": "M6",
                                              "cada_km": 20000}, TALLER)
        self.assertTrue(salida["ok"])

    def test_el_chofer_no_toca_los_planes(self):
        with self.assertRaises(PermissionError):
            parametros.guardar_plan(BaseFalsa(), {"clase": "preventivo", "nombre": "M6",
                                                  "cada_km": 20000}, CHOFER)

    def test_a_una_unidad_no_se_le_asigna_un_correctivo(self):
        cx = BaseFalsa(plan={"clase": "correctivo"})
        with self.assertRaises(ValueError) as e:
            parametros.asignar(cx, {"unidad_id": 7, "plan_id": 2}, ADMIN)
        self.assertIn("preventivo", str(e.exception))

    def test_sacarle_el_plan_a_una_unidad_es_valido(self):
        cx = BaseFalsa()
        self.assertTrue(parametros.asignar(cx, {"unidad_id": 7, "plan_id": None},
                                           ADMIN)["ok"])


if __name__ == "__main__":
    unittest.main()


# =====================================================================
class CombustibleDeUnLink(unittest.TestCase):
    """De dónde salen las cargas: de la mano de alguien o de un link.

    Lo que se prueba es lo que hace que se pueda confiar en el automático:
    que el link de la barra de direcciones de una hoja de Google se
    convierta solo al CSV —es donde más se traba esto—, que no se pueda
    apuntar el servidor a su propia red, y que ponerlo en automático sin
    link no se pueda guardar: no traería nada y nadie se enteraría.
    """

    def test_el_link_de_la_hoja_se_convierte_a_csv(self):
        import combustible
        casos = {
            "https://docs.google.com/spreadsheets/d/1AbC-d/edit#gid=77":
                "https://docs.google.com/spreadsheets/d/1AbC-d/export?format=csv&gid=77",
            "https://docs.google.com/spreadsheets/d/1AbC-d/edit":
                "https://docs.google.com/spreadsheets/d/1AbC-d/export?format=csv",
        }
        for pegado, esperado in casos.items():
            self.assertEqual(combustible.link_csv(pegado), esperado)

    def test_la_hoja_ya_publicada_y_cualquier_otro_link_quedan_como_estan(self):
        import combustible
        for link in ("https://docs.google.com/spreadsheets/d/e/2PACX-1v/pub?output=csv",
                     "https://ejemplo.com/planilla.csv"):
            self.assertEqual(combustible.link_csv(link), link)

    def test_el_servidor_no_se_apunta_a_su_propia_red(self):
        """El que sale a buscar es el servidor: un link interno lo
        convertiría en la puerta de entrada a lo que él ve y nadie más."""
        import combustible
        for link in ("http://ejemplo.com/x.csv", "https://127.0.0.1/x.csv",
                     "https://localhost/x.csv"):
            with self.subTest(link=link), self.assertRaises(ValueError):
                combustible._revisar_link(link)

    def test_automatico_sin_link_no_se_guarda(self):
        cx = BaseFalsa()
        with self.assertRaises(ValueError) as e:
            parametros.guardar(cx, {"combustible_origen": "automatico"}, ADMIN)
        self.assertIn("link", str(e.exception))

    def test_restablecer_vuelve_a_lo_de_fabrica(self):
        cx = BaseFalsa()
        parametros.restablecer(cx, {"campo": "km_hora"}, ADMIN)
        guardado = next(v for sql, v in cx.consultas if sql.startswith("update parametros"))
        self.assertIn(parametros.DE_FABRICA["km_hora"], guardado)

    def test_un_parametro_que_no_existe_no_se_restablece(self):
        with self.assertRaises(ValueError):
            parametros.restablecer(BaseFalsa(), {"campo": "lo_que_sea"}, ADMIN)
