"""El viento de cada viaje, sin red y sin base.

La planilla del BI no se vio al escribir el módulo, así que lo que más se
prueba es que la lea con nombres de columna distintos, con el encabezado
más abajo y con fechas en los formatos de siempre. Y la cuenta del viento
de frente, que es fácil de dar vuelta.
"""
import sys
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import viento as v


def planilla(*filas, encabezado=("Nro Hoja", "Fecha Salida", "Hora Salida",
                                 "Fecha Llegada", "Hora Llegada", "Origen",
                                 "Destino", "Dominio", "Chofer")):
    return [list(encabezado)] + [list(f) for f in filas]


class Columnas(unittest.TestCase):
    def test_nombres_habituales(self):
        m = v.detectar(["Nro Hoja", "Fecha Salida", "Hora Salida", "Fecha Llegada",
                        "Origen", "Destino", "Dominio", "Chofer"])
        self.assertEqual(m["salida"], 1)
        self.assertEqual(m["hora_salida"], 2)
        self.assertEqual(m["llegada"], 3)
        self.assertEqual(m["patente"], 6)
        self.assertEqual(m["hoja"], 0)

    def test_fecha_sola_no_le_gana_a_fecha_salida(self):
        m = v.detectar(["Fecha", "Fecha de Salida", "Origen", "Destino"])
        self.assertEqual(m["salida"], 1)

    def test_tildes_y_mayusculas(self):
        m = v.detectar(["FECHA SALIDA", "Localidad Origen", "LOCALIDAD DESTINO",
                        "Patente Tractor", "Conductor"])
        self.assertEqual((m["salida"], m["origen"], m["destino"], m["patente"],
                          m["chofer"]), (0, 1, 2, 3, 4))

    def test_sin_fecha_avisa_con_las_columnas(self):
        with self.assertRaises(ValueError) as e:
            v.leer_filas([["Cliente", "Importe"], ["X", 1]])
        self.assertIn("Cliente", str(e.exception))


class Planilla(unittest.TestCase):
    def test_ida_vuelta_y_otros(self):
        d = v.leer_filas(planilla(
            (1, "05/08/2026", "21:30", "06/08/2026", "16:00", "BUENOS AIRES",
             "CATAMARCA", "ae 123 cd", "Pérez"),
            (2, datetime(2026, 8, 8), time(6, 0), None, None, "Catamarca",
             "Bs As", "AB123CD", "Gómez"),
            (3, "05/08/2026", "10:00", None, None, "BUENOS AIRES", "ROSARIO", "X", ""),
            (None, None, None, None, None, None, None, None, None),
        ))
        self.assertEqual([x["sentido"] for x in d["viajes"]], ["ida", "vuelta"])
        self.assertEqual(d["otros"], 1)
        ida = d["viajes"][0]
        self.assertEqual(ida["salida"], datetime(2026, 8, 5, 21, 30))
        self.assertEqual(ida["llegada"], datetime(2026, 8, 6, 16, 0))
        self.assertEqual(ida["patente"], "AE123CD")
        self.assertIsNone(d["viajes"][1]["llegada"])

    def test_encabezado_debajo_de_un_titulo(self):
        filas = [["Reporte de hojas de ruta", None], [None, None]] + planilla(
            (7, "2026-08-05 21:30:00", None, None, None, "CABA", "S.F.V. Catamarca",
             "AA000AA", ""))
        d = v.leer_filas(filas)
        self.assertEqual(len(d["viajes"]), 1)
        self.assertTrue(d["viajes"][0]["salida_real"])

    def test_recorrido_en_una_sola_columna(self):
        d = v.leer_filas([["Fecha", "Recorrido"],
                          ["05/08/2026", "CATAMARCA - BUENOS AIRES"],
                          ["06/08/2026", "Bs.As / Catamarca"]])
        self.assertEqual([x["sentido"] for x in d["viajes"]], ["vuelta", "ida"])
        # Sin hora: la supuesta, y marcada como supuesta.
        self.assertEqual(d["viajes"][0]["salida"].hour, v.HORA_SUPUESTA)
        self.assertFalse(d["viajes"][0]["salida_real"])

    def test_fecha_serial_de_excel(self):
        self.assertEqual(v._fecha(46239.5), datetime(2026, 8, 5, 12, 0))


class Patentes(unittest.TestCase):
    def test_varias_en_una_celda(self):
        self.assertEqual(v.patentes_de("AE 123 CD, AB456EF / ABC123"),
                         ["AE123CD", "AB456EF", "ABC123"])
        self.assertEqual(v.patentes_de("ae123cd-ab456ef"), ["AE123CD", "AB456EF"])
        self.assertEqual(v.patentes_de("AE123CD y AB456EF"), ["AE123CD", "AB456EF"])
        self.assertEqual(v.patentes_de(""), [])

    def test_se_queda_con_el_tractor_de_larga_distancia(self):
        lad = {"AB456EF": False, "SEM111": True}
        viajes = [{"patentes": ["SEM111", "ZZ999ZZ", "AB456EF"]},
                  {"patentes": ["SEM111"]},
                  {"patentes": ["XX111XX"]}]
        ajenas = v.elegir_patentes(viajes, lad)
        self.assertEqual([x["patente"] for x in viajes], ["AB456EF", "", ""])
        self.assertEqual(ajenas, {"SEM111", "XX111XX"})

    def test_sin_flota_queda_la_primera(self):
        viajes = [{"patentes": ["AA111AA", "BB222BB"], "patente": "AA111AA"}]
        v.elegir_patentes(viajes, None)
        self.assertEqual(viajes[0]["patente"], "AA111AA")

    def test_la_planilla_trae_todas(self):
        d = v.leer_filas([["Fecha Salida", "Origen", "Destino", "Patentes"],
                          ["05/08/2026", "BUENOS AIRES", "CATAMARCA", "AE123CD, AB456EF"]])
        self.assertEqual(d["viajes"][0]["patentes"], ["AE123CD", "AB456EF"])

    def test_sin_columna_las_busca_en_la_fila(self):
        d = v.leer_filas([["Fecha Salida", "Origen", "Destino", "Observaciones"],
                          ["05/08/2026", "BUENOS AIRES", "CATAMARCA", "Tractor AE123CD"]])
        self.assertEqual(d["viajes"][0]["patentes"], ["AE123CD"])

    def test_informe_avisa_las_que_no_son_de_larga_distancia(self):
        hojas = {"viajes": [
            {"hoja": "1", "sentido": "ida", "salida": datetime(2026, 3, 5, 21),
             "salida_real": True, "llegada": None, "llegada_real": False,
             "patentes": ["QQ111QQ"], "patente": "QQ111QQ"}],
            "descartados": 0, "otros": 0, "columnas": {}, "encabezados": []}
        r = v.informe(None, "2026-03-01", "2026-03-31", leer_hojas=lambda: hojas,
                      pedir=lambda a, b: [], lad={"AB456EF": False})
        self.assertEqual(r["viajes"][0]["patente"], "")
        self.assertTrue(any("QQ111QQ" in a for a in r["avisos"]))
        # La planilla en memoria no se toca.
        self.assertEqual(hojas["viajes"][0]["patente"], "QQ111QQ")


class Recorrido(unittest.TestCase):
    def test_empieza_en_buenos_aires_y_termina_en_catamarca(self):
        ida = v.recorrido_por_hora(datetime(2026, 8, 5, 0), datetime(2026, 8, 5, 20))
        self.assertEqual(v.PUNTOS[ida[0]["punto"]]["lugar"], "Buenos Aires")
        self.assertEqual(v.PUNTOS[ida[-1]["punto"]]["lugar"], "Catamarca")
        self.assertEqual(len(ida), 21)
        vuelta = v.recorrido_por_hora(datetime(2026, 8, 5, 0), datetime(2026, 8, 5, 20), True)
        self.assertEqual(v.PUNTOS[vuelta[0]["punto"]]["lugar"], "Catamarca")
        self.assertEqual(v.PUNTOS[vuelta[-1]["punto"]]["lugar"], "Buenos Aires")
        # De ida, saliendo de Buenos Aires se va al noroeste; de vuelta, al sureste.
        self.assertTrue(270 < ida[0]["rumbo"] < 360)
        self.assertTrue(90 < vuelta[-1]["rumbo"] < 180)

    def test_pasa_por_cordoba(self):
        self.assertIn("Córdoba", [p["lugar"] for p in v.PUNTOS])

    def test_llegada_imposible_se_estima(self):
        s = datetime(2026, 8, 5, 8)
        viaje = {"salida": s, "llegada": s + timedelta(hours=3), "llegada_real": True}
        llegada, real = v.llegada_estimada(viaje)
        self.assertFalse(real)
        self.assertAlmostEqual((llegada - s).total_seconds() / 3600,
                               v.KM_TOTAL / v.VELOCIDAD_MEDIA, places=3)


class DeFrente(unittest.TestCase):
    def test_viento_del_norte_yendo_al_norte_es_de_frente(self):
        self.assertEqual(v.de_frente(20, 0, 0), (20.0, "frente"))

    def test_viento_del_sur_yendo_al_norte_es_de_cola(self):
        self.assertEqual(v.de_frente(20, 180, 0), (-20.0, "cola"))

    def test_cruzado(self):
        contra, tipo = v.de_frente(20, 90, 0)
        self.assertEqual(tipo, "costado")
        self.assertAlmostEqual(contra, 0, places=5)

    def test_da_la_vuelta_por_el_norte(self):
        self.assertEqual(v.de_frente(10, 350, 10)[1], "frente")


class Resumen(unittest.TestCase):
    def test_viaje_con_viento_del_noroeste(self):
        viaje = {"salida": datetime(2026, 8, 5, 20), "llegada": datetime(2026, 8, 6, 14),
                 "llegada_real": True, "salida_real": True, "sentido": "ida",
                 "patente": "AE123CD"}
        def del_noroeste(lat, lon, hora):
            return {"velocidad": 30, "rafaga": 50 if hora.hour == 3 else 40, "direccion": 315}
        r = v.resumir(viaje, del_noroeste)
        self.assertEqual(r["estado"], "ok")
        self.assertEqual(r["calificacion"], "en contra fuerte")
        self.assertGreater(r["pct_frente"], 60)
        self.assertEqual(r["rafaga_max"], 50)
        self.assertEqual(r["rafaga_hora"].hour, 3)
        # La vuelta con el mismo viento lo tiene a favor.
        r2 = v.resumir({**viaje, "sentido": "vuelta"}, del_noroeste)
        self.assertEqual(r2["calificacion"], "a favor")

    def test_sin_viento_no_inventa(self):
        viaje = {"salida": datetime(2026, 8, 5, 20), "llegada": None,
                 "salida_real": True, "sentido": "ida"}
        r = v.resumir(viaje, lambda *a: None)
        self.assertEqual(r["estado"], "sin datos")
        self.assertIsNone(r["contra_media"])


class Informe(unittest.TestCase):
    def setUp(self):
        v._MEMORIA.clear()

    def test_pide_una_sola_vez_y_filtra_por_fecha(self):
        pedidos = []
        def pedir(desde, hasta):
            pedidos.append((desde, hasta))
            filas, d = [], desde
            while d <= hasta:
                for p in v.PUNTOS:
                    for h in range(24):
                        filas.append((p["lat"], p["lon"], datetime.combine(d, time(h)),
                                      12.0, 20.0, 90.0))
                d += timedelta(days=1)
            return filas
        hojas = {"viajes": [
            {"hoja": "1", "sentido": "ida", "salida": datetime(2026, 3, 5, 21),
             "salida_real": True, "llegada": datetime(2026, 3, 6, 15), "llegada_real": True},
            {"hoja": "2", "sentido": "vuelta", "salida": datetime(2026, 1, 1, 8),
             "salida_real": False, "llegada": None, "llegada_real": False},
        ], "descartados": 0, "otros": 4, "columnas": {}, "encabezados": []}
        r = v.informe(None, "2026-03-01", "2026-03-31", leer_hojas=lambda: hojas, pedir=pedir)
        self.assertEqual([x["hoja"] for x in r["viajes"]], ["1"])
        self.assertEqual(r["viajes"][0]["estado"], "ok")
        self.assertEqual(pedidos, [(date(2026, 3, 5), date(2026, 3, 6))])
        # La segunda vez sale de memoria.
        v.informe(None, "2026-03-01", "2026-03-31", leer_hojas=lambda: hojas, pedir=pedir)
        self.assertEqual(len(pedidos), 1)

    def test_tramos_de_dias_seguidos(self):
        d = date(2026, 1, 1)
        dias = [d, d + timedelta(1), d + timedelta(5)]
        self.assertEqual(v._tramos(dias), [[d, d + timedelta(1)], [d + timedelta(5)]])


if __name__ == "__main__":
    unittest.main()


class SinBajarElBI(unittest.TestCase):
    """El servidor no baja la planilla del BI: la deja sin memoria."""

    def test_sin_viajes_guardados_avisa_y_no_baja(self):
        bajadas = []
        original = v.hojas
        v.hojas = lambda *a, **k: bajadas.append(1)
        try:
            with self.assertRaises(RuntimeError) as e:
                v.planilla_de(None)
        finally:
            v.hojas = original
        self.assertEqual(bajadas, [])
        self.assertIn("Run workflow", str(e.exception))

    def test_la_memoria_del_viento_tiene_tope(self):
        v._MEMORIA.clear()
        for i in range(v.TOPE_MEMORIA + 1):
            v._MEMORIA[i] = {}
        v.viento_para(None, [date.today()], pedir=lambda d, h: [])
        self.assertLessEqual(len(v._MEMORIA), v.TOPE_MEMORIA)
