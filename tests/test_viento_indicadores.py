"""Los indicadores del viento, sin red y sin base.

Lo delicado es repartir las cargas entre viajes: una carga contada en dos
viajes, o la del día de salida puesta en el viaje que empieza, daría una
correlación que no existe.
"""
import sys
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import viento as vto
import viento_indicadores as ind


def viaje(pat, salida, horas=20, contra=0.0, sentido="ida", hoja="1", chofer="X"):
    s = datetime.fromisoformat(salida)
    return {"hoja": hoja, "patente": pat, "chofer": chofer, "sentido": sentido,
            "salida": s, "llegada": s + timedelta(hours=horas), "salida_real": True,
            "contra_media": contra,
            "calificacion": vto.calificar(contra), "detalle": []}


def carga(pat, dia, litros, importe=None):
    return {"patente": pat, "fecha": date.fromisoformat(dia), "litros": litros,
            "importe": importe}


class RepartirCargas(unittest.TestCase):
    def test_la_carga_del_dia_de_salida_es_del_viaje_anterior(self):
        viajes = [viaje("AA111AA", "2026-08-01T20:00", hoja="1"),
                  viaje("AA111AA", "2026-08-03T20:00", sentido="vuelta", hoja="2")]
        cargas = [carga("AA111AA", "2026-08-01", 500),   # sale lleno: no es de nadie acá
                  carga("AA111AA", "2026-08-02", 150),   # en el camino, viaje 1
                  carga("AA111AA", "2026-08-03", 250),   # antes de volver: repone el 1
                  carga("AA111AA", "2026-08-05", 400)]   # al volver: viaje 2
        f = {x["hoja"]: x for x in ind.litros_por_viaje(viajes, cargas)}
        self.assertEqual(f["1"]["litros"], 400)
        self.assertEqual(f["2"]["litros"], 400)

    def test_no_mezcla_patentes_y_normaliza(self):
        viajes = [viaje("aa 111 aa", "2026-08-01T20:00")]
        cargas = [carga("AA111AA", "2026-08-02", 400), carga("BB222BB", "2026-08-02", 999)]
        self.assertEqual(ind.litros_por_viaje(viajes, cargas)[0]["litros"], 400)

    def test_consumo_imposible_se_descarta(self):
        viajes = [viaje("AA111AA", "2026-08-01T20:00")]
        f = ind.litros_por_viaje(viajes, [carga("AA111AA", "2026-08-02", 40)])[0]
        self.assertIsNone(f["consumo"])
        self.assertIn("no es creíble", f["motivo"])


class Recta(unittest.TestCase):
    def test_recta_exacta(self):
        r = ind.recta([(x, 30 + 0.2 * x) for x in range(-10, 20)])
        self.assertAlmostEqual(r["pendiente"], 0.2, places=4)
        self.assertAlmostEqual(r["ordenada"], 30, places=2)
        self.assertEqual(r["r"], 1.0)
        self.assertTrue(r["firme"])

    def test_pocos_viajes_no_es_firme(self):
        self.assertFalse(ind.recta([(0, 30), (10, 33), (20, 35.5), (5, 31)])["firme"])
        self.assertIsNone(ind.recta([(0, 30)])["r"])


class CombustibleYViento(unittest.TestCase):
    def test_el_viento_en_contra_se_nota_en_el_consumo(self):
        viajes, cargas = [], []
        d = datetime(2026, 5, 1, 20)
        for i in range(24):
            contra = -8 + i
            s = d + timedelta(days=3 * i)
            pat = "AA111AA" if i % 2 else "BB222BB"
            viajes.append(viaje(pat, s.isoformat(), contra=contra, hoja=str(i),
                                chofer="Pérez" if i % 3 else "Gómez"))
            consumo = 32 + 0.25 * contra                      # L/100 km
            cargas.append(carga(pat, (s + timedelta(days=1)).date().isoformat(),
                                consumo * vto.KM_TOTAL / 100, 1000.0 * consumo * vto.KM_TOTAL / 100))
        r = ind.combustible_y_viento(viajes, cargas)
        self.assertTrue(r["ajuste"]["firme"])
        self.assertAlmostEqual(r["ajuste"]["pendiente"], 0.25, places=2)
        self.assertAlmostEqual(r["costo"]["precio_litro"], 1000.0, delta=1)
        self.assertGreater(r["costo"]["litros_en_contra"], r["costo"]["litros_a_favor"])
        # Sin el viento, todos consumen lo mismo.
        for fila in r["por_chofer"]:
            self.assertAlmostEqual(fila["sin_viento"], 32, delta=0.2)
        grupos = {g["grupo"]: g for g in r["grupos"]}
        self.assertLess(grupos["a favor"]["consumo"], grupos["en contra fuerte"]["consumo"])


class SoloViento(unittest.TestCase):
    def test_hora_de_salida_ignora_las_supuestas(self):
        a = viaje("A", "2026-08-01T20:00", contra=10)
        b = {**viaje("A", "2026-08-02T08:00", contra=-5), "salida_real": False}
        f = {x["desde"]: x for x in ind.por_hora_salida([a, b])}
        self.assertEqual(f[18]["ida"], {"viajes": 1, "contra": 10})
        self.assertEqual(f[6]["ida"]["viajes"], 0)

    def test_seguridad(self):
        v = viaje("A", "2026-08-01T20:00")
        v["detalle"] = [{"hora": datetime(2026, 8, 1, 21), "lugar": "Rosario", "rafaga": 82,
                         "cruzado": 10, "velocidad": 30},
                        {"hora": datetime(2026, 8, 1, 22), "lugar": "Córdoba", "rafaga": 50,
                         "cruzado": 45, "velocidad": 45}]
        s = ind.seguridad([v, viaje("B", "2026-08-01T20:00")])
        self.assertEqual(s["viajes"], 1)
        self.assertEqual((s["horas_rafaga"], s["horas_cruzado"]), (1, 1))
        self.assertEqual(s["lista"][0]["rafaga_lugar"], "Rosario")

    def test_tramos_en_orden_de_ruta(self):
        tramos = ind.por_tramo([])
        self.assertEqual(tramos[0]["tramo"], "Buenos Aires")
        self.assertEqual(tramos[-1]["tramo"], "Catamarca")


class Mapa(unittest.TestCase):
    def setUp(self):
        vto._MEMORIA.clear()

    def pedir(self, desde, hasta):
        filas, d = [], desde
        while d <= hasta:
            for p in vto.PUNTOS:
                for h in range(24):
                    filas.append((p["lat"], p["lon"], datetime.combine(d, time(h)),
                                  20.0, 35.0, 0.0))
            d += timedelta(days=1)
        return filas

    def test_busca_por_hoja_sin_ceros_adelante(self):
        hojas = {"viajes": [
            {"hoja": "00123", "sentido": "ida", "salida": datetime(2026, 3, 5, 21),
             "salida_real": True, "llegada": datetime(2026, 3, 6, 15), "llegada_real": True},
            {"hoja": "999", "sentido": "vuelta", "salida": datetime(2026, 3, 9, 21),
             "salida_real": True, "llegada": None, "llegada_real": False}],
            "descartados": 0, "otros": 0, "columnas": {}, "encabezados": []}
        r = ind.viaje_en_mapa(None, "123", leer_hojas=lambda: hojas, pedir=self.pedir)
        self.assertEqual(len(r["viajes"]), 1)
        v = r["viajes"][0]
        self.assertEqual(len(v["campo"]), len(v["detalle"]))
        self.assertEqual(len(v["campo"][0]), len(vto.PUNTOS))
        # Viento del norte y yendo al noroeste: en contra en todos lados.
        self.assertTrue(all(c[3] > 0 for c in v["campo"][0] if c))
        with self.assertRaises(ValueError):
            ind.viaje_en_mapa(None, "5", leer_hojas=lambda: hojas, pedir=self.pedir)


if __name__ == "__main__":
    unittest.main()
