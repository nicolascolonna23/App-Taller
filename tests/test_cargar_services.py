"""Que el importador lea las planillas del taller como son.

Las de Diemar traen arriba un título y la fecha de la última carga antes
de la tabla, dos columnas que se llaman PATENTE, números con puntos de mil
y fechas de un dígito. Todo eso lo rompió una vez y por eso está acá.
"""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "gomeria"))
import cargar_services as cs


def archivo(texto):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                    encoding="utf-8", newline="")
    f.write(texto)
    f.close()
    return f.name


# La de larga distancia: el encabezado arranca en la primera fila pero
# ocupa dos líneas, porque Google mete un salto adentro de una celda. Eso
# deja DOS columnas que se llaman PATENTE, y la segunda son los km de hoy.
LAD = ('PATENTE,MARCA,CHOFER,RESIDENCIA,FECHA ULTIMO SERVICE,KM ULTIMO SERVICE,'
       'FECHA/KM PROXIMO SERVICE,"\nPATENTE",FALTA\n'
       'AD 247 MQ,SCANIA,PEREIRA NICOLAS,LAD,20/7/26,1.719.118,1.759.118,1.751.201,7.917\n'
       'AH 522 SI,IVECO,CABRERA GUILLERMO,LAD,10/6/26,200.226,245.226,242.227,2.999\n')

# La de Buenos Aires: cinco filas de título y blancos antes de la tabla,
# números entre comillas con coma decimal, y filas vacías abajo de todo.
BUE = (',,TOCAR EL ICONO DE DM PARA VOLVER,,,HOY ES:,FECHA ULT CARGA:,,,\n'
       ',,,,,9/9/26,10/3/26,,,\n'
       ',,,,,,,,,\n'
       ',,,,,,,,,\n'
       ',,,,,,,,,\n'
       'PATENTE,MARCA,CHOFER,RESIDENCIA,FECHA ULTIMO SERVICE,KM ULTIMO SERVICE,'
       'FECHA/KM PROXIMO SERVICE,KM ACTUAL,FALTA,\n'
       'AG 797 NJ,TOYOTA,FRUTOS JAVIER,BUE,26/2/26,"30.081,70","40.081,70","41.742,80","-1.661,10",\n'
       'NBR 784,DFM,,BUE,,,,"5435,3",,\n'
       ',,,,,,,,-,\n'
       ',,,,,,,,-,\n')


class Encabezado(unittest.TestCase):
    def test_encuentra_la_tabla_debajo_del_titulo(self):
        """El encabezado de BUE está en la fila 6. Leer la 1 da basura."""
        encabezados, filas = cs.leer(archivo(BUE))
        self.assertEqual(encabezados[0], "PATENTE")
        self.assertEqual(encabezados[5], "KM ULTIMO SERVICE")
        self.assertEqual(filas[0][0], "AG 797 NJ")

    def test_con_dos_columnas_patente_gana_la_primera(self):
        """La segunda PATENTE de LAD son los km de hoy. Engancharla ahí
        cargaría el kilometraje de la unidad como si fuera su patente."""
        encabezados, _ = cs.leer(archivo(LAD))
        mapa = cs.mapear(encabezados)
        self.assertEqual(mapa["patente"], 0)

    def test_el_proximo_service_no_se_lo_lleva_el_tipo(self):
        """«FECHA/KM PROXIMO SERVICE» tiene la palabra service adentro: si la
        agarrara «tipo», el tipo de service sería una fecha."""
        encabezados, _ = cs.leer(archivo(LAD))
        mapa = cs.mapear(encabezados)
        self.assertEqual(encabezados[mapa["proximo_km"]], "FECHA/KM PROXIMO SERVICE")
        self.assertIsNone(mapa.get("tipo"))

    def test_la_fecha_del_ultimo_no_se_confunde_con_la_del_proximo(self):
        encabezados, _ = cs.leer(archivo(LAD))
        mapa = cs.mapear(encabezados)
        self.assertEqual(encabezados[mapa["fecha"]], "FECHA ULTIMO SERVICE")


class Numeros(unittest.TestCase):
    def test_puntos_de_mil_y_coma_decimal(self):
        self.assertEqual(cs.numero("1.719.118"), 1719118)
        self.assertEqual(cs.numero("281.964,00"), 281964)
        self.assertEqual(cs.numero("30.081,70"), 30081.7)
        self.assertEqual(cs.numero("5435,3"), 5435.3)
        self.assertEqual(cs.numero("845034"), 845034)

    def test_lo_que_no_es_un_numero_no_inventa_uno(self):
        for basura in ("", None, "-", "s/d", "20/7/26"):
            self.assertIsNone(cs.numero(basura))


class Fechas(unittest.TestCase):
    def test_las_formas_que_usa_una_planilla_argentina(self):
        self.assertEqual(cs.fecha_de("20/7/26"), date(2026, 7, 20))
        self.assertEqual(cs.fecha_de("28/8/2026"), date(2026, 8, 28))
        self.assertEqual(cs.fecha_de("21/10/25"), date(2025, 10, 21))
        self.assertEqual(cs.fecha_de("2026-08-28"), date(2026, 8, 28))

    def test_vacia_es_vacia_y_rara_es_rara(self):
        """Distinguir las dos importa: sin fecha se usa hoy, pero una fecha
        que no se entiende tiene que frenar el archivo."""
        self.assertIsNone(cs.fecha_de(""))
        self.assertIsNone(cs.fecha_de(None))
        self.assertEqual(cs.fecha_de("malafecha"), "?")


class Intervalo(unittest.TestCase):
    def test_sale_del_proximo_menos_el_ultimo(self):
        """Ninguna planilla tiene el intervalo como columna, pero todas
        tienen el próximo service. En LAD da 40.000 y 45.000 según el
        camión: un valor fijo por defecto se comería esa diferencia."""
        encabezados, filas = cs.leer(archivo(LAD))
        mapa = cs.mapear(encabezados)
        intervalos = [cs.numero(cs.valor(f, mapa, "proximo_km")) -
                      cs.numero(cs.valor(f, mapa, "km")) for f in filas]
        self.assertEqual(intervalos, [40000, 45000])


class Valor(unittest.TestCase):
    def test_una_fila_mas_corta_que_el_encabezado_no_explota(self):
        encabezados, _ = cs.leer(archivo(LAD))
        mapa = cs.mapear(encabezados)
        self.assertIsNone(cs.valor(["AD 247 MQ"], mapa, "km"))


if __name__ == "__main__":
    unittest.main()
