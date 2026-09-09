"""Lo que la pantalla de alertas promete, sin base de datos de por medio.

Las consultas se prueban contra Postgres a mano; lo que se prueba acá es
lo que decide Python: en qué orden se muestran, qué se rechaza al cargar y
qué pasa cuando falta una fuente. Son las tres cosas que se rompen sin que
nadie se entere.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gomeria"))
import alertas


class Cursor:
    def __init__(self, filas):
        self._filas = filas

    def fetchall(self):
        return self._filas

    def fetchone(self):
        return self._filas[0] if self._filas else None


class BaseFalsa:
    """Contesta según lo que diga la consulta. Lo que no está, explota."""

    def __init__(self, respuestas, rotas=()):
        self.respuestas = respuestas
        self.rotas = tuple(rotas)
        self.escrituras = []
        self.deshecho = 0

    def execute(self, consulta, valores=()):
        texto = " ".join(consulta.split())
        for rota in self.rotas:
            if rota in texto:
                raise RuntimeError(f'relation "{rota}" does not exist')
        for clave, filas in self.respuestas.items():
            if clave in texto:
                if texto.lower().startswith(("insert", "update", "delete")):
                    self.escrituras.append((clave, valores))
                return Cursor(filas)
        if texto.lower().startswith(("insert", "update", "delete")):
            self.escrituras.append((texto[:40], valores))
            return Cursor([])
        raise AssertionError(f"consulta sin respuesta preparada: {texto[:90]}")

    def rollback(self):
        self.deshecho += 1


REGLAS = [{"id": 1, "litros_maximos": 450, "service_urgente_km": 5000,
           "service_aviso_km": 15000, "combustible_dias": 90}]


def base_con(**cambios):
    """Una base con una alerta de cada fuente, todas de la misma gravedad."""
    respuestas = {
        "to_regclass": [{"t": "alertas_reglas"}],
        "from alertas_reglas": REGLAS,
        "from alertas_silenciadas": [],
        "from v_vencimientos_hoy": [{
            "id": 7, "tipo": "VTV", "ambito": "unidad", "patente": "AD247MQ",
            "interno": "2", "persona": None, "identificador": "OB-1",
            "detalle": None, "vence": None, "dias": 5, "estado": "por_vencer",
            "sucursal": "LAD"}],
        "from v_services_hoy": [{
            "unidad_id": 3, "patente": "AF533SB", "interno": "12",
            "sucursal": "LAD", "tipo": "M6", "estado": "urgente",
            "km_restantes": 2700, "dias_restantes": 7, "ultimo_fecha": None,
            "ultimo_km": 395000, "cada_km": 20000, "km_actual": 412300}],
        "from v_cargas_grandes": [{
            "carga_id": 11, "remito": "9001", "remito_bruto": "9001",
            "fecha": None, "patente": "AD247MQ", "unidad_id": 1, "interno": "2",
            "litros": 482, "importe": 1, "estacion": "YPF", "chofer": "Ramón",
            "litros_maximos": 450, "litros_de_mas": 32}],
        "from v_alertas_cubiertas": [{
            "cubierta_id": 5, "codigo": "4523", "patente": "AD247MQ",
            "interno": "2", "posicion": "2IE", "funcion": "traccion",
            "remanente_mm": 4.5, "minimo_mm": 3, "alerta": "cerca",
            "km_restantes": 10436, "dias_restantes": 26}],
    }
    respuestas.update(cambios)
    return BaseFalsa(respuestas)


class Orden(unittest.TestCase):
    def test_a_igual_gravedad_manda_la_consecuencia(self):
        """Días, kilómetros, litros y milímetros no se pueden comparar entre
        sí. Dentro de un mismo nivel ordena qué deja antes al camión parado."""
        cx = base_con()
        fuentes = [a["fuente"] for a in alertas.listar(cx)["alertas"]]
        self.assertEqual(fuentes, ["vencimiento", "cubierta", "service", "combustible"])

    def test_lo_grave_va_antes_que_lo_leve(self):
        cx = base_con()
        cx.respuestas["from v_vencimientos_hoy"] = [dict(
            cx.respuestas["from v_vencimientos_hoy"][0], dias=-3, estado="vencido")]
        salida = alertas.listar(cx)
        self.assertEqual(salida["alertas"][0]["severidad"], "grave")
        self.assertEqual(salida["alertas"][0]["detalle"], "venció hace 3 días")
        self.assertEqual(salida["resumen"]["grave"], 1)


class OdometroQueNoCierra(unittest.TestCase):
    """El satelital marca menos kilómetros que el último service.

    Pasó de verdad en nueve unidades de la flota: les cambiaron el equipo de
    GPS y el contador arrancó de nuevo, o dejaron de reportar. La cuenta
    «próximo menos hoy» deja de tener sentido, y la primera versión las
    mostraba en verde: una unidad que puede estar pasada de service pintada
    de «al día» es peor que no tener la pantalla.
    """

    def _base(self):
        cx = base_con()
        cx.respuestas["from v_services_hoy"] = [{
            "unidad_id": 9, "patente": "AF577BD", "interno": "7",
            "sucursal": "LAD", "tipo": None, "estado": "km_dudoso",
            "km_restantes": 885034, "dias_restantes": None, "ultimo_fecha": None,
            "ultimo_km": 845034, "cada_km": 40000, "km_actual": 0}]
        return cx

    def test_avisa_en_vez_de_desaparecer(self):
        alerta = next(a for a in alertas.listar(self._base())["alertas"]
                      if a["fuente"] == "service")
        self.assertEqual(alerta["severidad"], "leve")
        self.assertIn("No se sabe", alerta["titulo"])

    def test_no_muestra_los_kilometros_que_faltan(self):
        """885.034 km para un service que se hace cada 40.000 es un número
        que no significa nada. Se dice qué pasó, no el resultado de la resta."""
        alerta = next(a for a in alertas.listar(self._base())["alertas"]
                      if a["fuente"] == "service")
        self.assertNotIn("885.034", alerta["detalle"])
        self.assertIn("0 km", alerta["detalle"])
        self.assertIn("845.034", alerta["detalle"])

    def test_se_puede_silenciar_como_cualquier_otra(self):
        cx = self._base()
        alertas.silenciar(cx, "service", "9", "le cambiamos el GPS, se arregla el lunes")
        self.assertTrue(cx.escrituras)


class Silencio(unittest.TestCase):
    def test_lo_silenciado_no_cuenta_pero_no_se_pierde(self):
        cx = base_con()
        cx.respuestas["from alertas_silenciadas"] = [{
            "fuente": "combustible", "clave": "11", "motivo": "tanque de 600 L",
            "hasta": None, "usuario": "nico"}]
        salida = alertas.listar(cx, incluir_silenciadas=True)
        self.assertEqual(salida["resumen"]["total"], 3)
        self.assertEqual(salida["resumen"]["silenciadas"], 1)
        self.assertEqual(salida["silenciadas"][0]["silenciada"]["motivo"], "tanque de 600 L")
        self.assertNotIn("combustible", [a["fuente"] for a in salida["alertas"]])

    def test_el_motivo_es_obligatorio(self):
        """Dentro de seis meses «alguien la ocultó» no le sirve a nadie."""
        cx = base_con()
        for malo in ("", "  ", "ok"):
            with self.assertRaises(ValueError):
                alertas.silenciar(cx, "combustible", "11", malo)
        alertas.silenciar(cx, "combustible", "11", "el tanque es de 600 litros", usuario="n")
        self.assertTrue(cx.escrituras)

    def test_no_se_silencia_una_fuente_inventada(self):
        with self.assertRaises(ValueError):
            alertas.silenciar(base_con(), "loquesea", "1", "un motivo largo")


class Reglas(unittest.TestCase):
    def test_el_aviso_no_puede_ir_despues_del_rojo(self):
        cx = base_con()
        with self.assertRaises(ValueError):
            alertas.guardar_reglas(cx, {"service_urgente_km": 20000,
                                        "service_aviso_km": 5000})
        self.assertEqual(cx.escrituras, [])

    def test_no_acepta_texto_ni_negativos(self):
        cx = base_con()
        for datos in ({"litros_maximos": "mucho"}, {"litros_maximos": -1}):
            with self.assertRaises(ValueError):
                alertas.guardar_reglas(cx, datos)


class FuenteCaida(unittest.TestCase):
    def test_una_tabla_que_falta_se_dice_y_no_apaga_el_resto(self):
        """Los módulos se prenden de a uno. Que falte el SQL de combustible
        no puede hacer que la pantalla diga que no hay nada que mirar."""
        cx = base_con()
        cx.rotas = ("v_cargas_grandes",)
        salida = alertas.listar(cx)
        self.assertEqual(salida["fuentes_apagadas"], ["Combustible"])
        self.assertEqual(len(salida["alertas"]), 3)
        self.assertGreaterEqual(cx.deshecho, 1)

    def test_sin_el_sql_corrido_lo_dice_en_vez_de_romper(self):
        cx = BaseFalsa({"to_regclass": [{"t": None}]})
        salida = alertas.listar(cx)
        self.assertFalse(salida["instalado"])
        self.assertIn("20_alertas.sql", salida["aviso"])


class Numeros(unittest.TestCase):
    def test_los_miles_van_con_punto(self):
        self.assertEqual(alertas._miles(2700), "2.700")
        self.assertEqual(alertas._miles(197000.4), "197.000")
        self.assertEqual(alertas._miles(0), "0")

    def test_el_texto_de_cada_fuente_se_entiende_solo(self):
        cx = base_con()
        por = {a["fuente"]: a for a in alertas.listar(cx)["alertas"]}
        self.assertEqual(por["vencimiento"]["detalle"], "vence en 5 días")
        self.assertEqual(por["service"]["detalle"], "faltan 2.700 km · unos 7 días")
        self.assertEqual(por["combustible"]["titulo"], "Carga de 482 litros")
        self.assertEqual(por["combustible"]["detalle"], "32 litros por encima del máximo")
        self.assertIn("el mínimo es 3,0", por["cubierta"]["detalle"])


if __name__ == "__main__":
    unittest.main()
