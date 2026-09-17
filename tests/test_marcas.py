"""Marcas y medidas de cubierta.

Lo que se prueba es lo que decide si el catálogo se puede creer: que
«FATE» y «Fate» sean la misma marca y no dos, que guardar el nombre no
borre el logo que ya estaba, que lo que se sube sea una imagen y no
cualquier archivo, y que una marca con cubiertas cargadas se dé de baja
en vez de borrarse —borrarla dejaría fichas nombrando algo que no existe.
"""
import base64
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import marcas

# El PNG más chico que un navegador acepta: un pixel.
PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQ"
    "DwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
LOGO = "data:image/png;base64," + base64.b64encode(PIXEL).decode()

JEFE = {"usuario": "nico", "rol": "admin", "administra": True, "gestiona": True}
PEON = {"usuario": "pedro", "rol": "chofer", "gestiona": False}


class Resultado:
    def __init__(self, una=None, muchas=None):
        self.una, self.muchas = una, muchas or []

    def fetchone(self):
        return self.una

    def fetchall(self):
        return self.muchas


class BaseFalsa:
    """Contesta por el prefijo de la consulta. Guarda lo que se le pidió."""

    def __init__(self, marcas_=None, medidas_=None, usadas=0):
        self.marcas = marcas_ if marcas_ is not None else []
        self.medidas = medidas_ if medidas_ is not None else []
        self.usadas = usadas
        self.consultas = []

    def rollback(self):
        pass

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if sql.startswith("select m.id, m.nombre"):
            return Resultado(muchas=self.marcas)
        if sql.startswith("select d.id, d.medida"):
            return Resultado(muchas=self.medidas)
        if sql.startswith("select logo, logo_tipo"):
            fila = next((m for m in self.marcas if m["slug"] == valores[0]), None)
            return Resultado(fila if fila and fila.get("logo") else None)
        if sql.startswith("select * from cubiertas_marcas where id"):
            return Resultado(next((m for m in self.marcas
                                   if m["id"] == valores[0]), None))
        if sql.startswith("select nombre, slug from cubiertas_marcas"):
            return Resultado(next((m for m in self.marcas
                                   if m["id"] == valores[0]), None))
        if sql.startswith("select 1 from cubiertas_marcas where slug = %s and id"):
            return Resultado({"?column?": 1} if any(
                m["slug"] == valores[0] and m["id"] != valores[1]
                for m in self.marcas) else None)
        if sql.startswith("select 1 from cubiertas_marcas where slug"):
            return Resultado({"?column?": 1} if any(
                m["slug"] == valores[0] for m in self.marcas) else None)
        if sql.startswith("select medida from cubiertas_medidas"):
            return Resultado(next((d for d in self.medidas
                                   if d["id"] == valores[0]), None))
        if sql.startswith("select 1 from cubiertas_medidas where medida"):
            return Resultado({"?column?": 1} if any(
                d["medida"] == valores[0] for d in self.medidas) else None)
        if sql.startswith("select count(*) as n from cubiertas"):
            return Resultado({"n": self.usadas})
        if sql.startswith("insert into"):
            return Resultado({"id": 99})
        if "returning" in sql:
            return Resultado({"id": valores[-1], "slug": "x"})
        return Resultado()

    def sql_con(self, texto):
        """Lo que se ejecutó y menciona ese pedazo de SQL."""
        return [c for c in self.consultas if texto in c[0]]


class Slug(unittest.TestCase):
    def test_el_slug_junta_lo_que_es_la_misma_marca(self):
        for nombre in ("FATE", "Fate", " fate ", "F.A.T.E."):
            self.assertEqual(marcas.slug_de(nombre), "fate", nombre)
        self.assertEqual(marcas.slug_de("BF Goodrich"), "bfgoodrich")

    def test_un_nombre_sin_letras_no_es_marca(self):
        cx = BaseFalsa()
        with self.assertRaises(ValueError):
            marcas.guardar(cx, {"nombre": "---"}, JEFE)


class Permisos(unittest.TestCase):
    def test_el_que_no_gestiona_no_toca_el_catalogo(self):
        cx = BaseFalsa()
        for llamada in (
                lambda: marcas.guardar(cx, {"nombre": "Kumho"}, PEON),
                lambda: marcas.borrar(cx, {"id": 1}, PEON),
                lambda: marcas.borrar_logo(cx, {"id": 1}, PEON),
                lambda: marcas.guardar_medida(cx, {"medida": "295"}, PEON),
                lambda: marcas.borrar_medida(cx, {"id": 1}, PEON)):
            with self.assertRaises(PermissionError):
                llamada()
        self.assertEqual(cx.consultas, [], "no tendría que haber tocado la base")

    def test_sin_usuario_tampoco(self):
        with self.assertRaises(PermissionError):
            marcas.guardar(BaseFalsa(), {"nombre": "Kumho"}, None)


class Logo(unittest.TestCase):
    def test_lo_que_no_es_imagen_no_entra(self):
        cx = BaseFalsa()
        with self.assertRaises(ValueError):
            marcas.guardar(cx, {"nombre": "Kumho", "logo": "logo.png"}, JEFE)
        with self.assertRaises(ValueError):
            marcas.guardar(cx, {"nombre": "Kumho",
                                "logo": "data:application/pdf;base64,QQ=="}, JEFE)

    def test_una_foto_subida_por_error_no_va_a_la_base(self):
        pesado = base64.b64encode(b"a" * (marcas.LOGO_MAXIMO + 1)).decode()
        with self.assertRaises(ValueError) as e:
            marcas.guardar(BaseFalsa(), {"nombre": "Kumho",
                                         "logo": "data:image/png;base64," + pesado}, JEFE)
        self.assertIn("máximo", str(e.exception))

    def test_guardar_el_nombre_no_borra_el_logo_que_ya_estaba(self):
        cx = BaseFalsa([{"id": 7, "nombre": "Kumho", "slug": "kumho",
                         "logo": PIXEL, "logo_tipo": "image/png"}])
        marcas.guardar(cx, {"id": 7, "nombre": "Kumho Tyres"}, JEFE)
        update = cx.sql_con("update cubiertas_marcas")[0][0]
        self.assertNotIn("logo", update, "el update pisó el logo sin que suban uno")

    def test_subir_uno_nuevo_si_lo_reemplaza(self):
        cx = BaseFalsa([{"id": 7, "nombre": "Kumho", "slug": "kumho",
                         "logo": PIXEL, "logo_tipo": "image/png"}])
        marcas.guardar(cx, {"id": 7, "nombre": "Kumho", "logo": LOGO}, JEFE)
        sql, valores = cx.sql_con("update cubiertas_marcas")[0]
        self.assertIn("logo=%s", sql)
        self.assertEqual(valores[2], PIXEL)

    def test_el_logo_de_una_marca_sin_logo_no_es_un_error(self):
        cx = BaseFalsa([{"id": 7, "nombre": "Kumho", "slug": "kumho", "logo": None}])
        self.assertIsNone(marcas.logo_de(cx, "Kumho"))
        self.assertIsNone(marcas.logo_de(cx, "noexiste"))


class Marcas(unittest.TestCase):
    def test_no_entra_dos_veces_la_misma_marca(self):
        cx = BaseFalsa([{"id": 1, "nombre": "Fate", "slug": "fate"}])
        with self.assertRaises(ValueError) as e:
            marcas.guardar(cx, {"nombre": "FATE "}, JEFE)
        self.assertIn("ya está cargada", str(e.exception))

    def test_ni_renombrando_otra_encima(self):
        cx = BaseFalsa([{"id": 1, "nombre": "Fate", "slug": "fate"},
                        {"id": 2, "nombre": "Kumho", "slug": "kumho"}])
        with self.assertRaises(ValueError):
            marcas.guardar(cx, {"id": 2, "nombre": "Fate"}, JEFE)

    def test_el_alta_devuelve_el_slug_con_el_que_se_sirve_el_logo(self):
        cx = BaseFalsa()
        self.assertEqual(marcas.guardar(cx, {"nombre": "BF Goodrich"}, JEFE),
                         {"ok": True, "id": 99, "slug": "bfgoodrich"})

    def test_la_marca_con_cubiertas_se_da_de_baja_no_se_borra(self):
        cx = BaseFalsa([{"id": 1, "nombre": "Fate", "slug": "fate"}], usadas=14)
        with self.assertRaises(ValueError) as e:
            marcas.borrar(cx, {"id": 1}, JEFE)
        self.assertIn("dar de baja", str(e.exception))
        self.assertEqual(cx.sql_con("delete from cubiertas_marcas"), [])

        # Darla de baja sí: deja de ofrecerse y las fichas siguen diciendo Fate.
        marcas.guardar(cx, {"id": 1, "nombre": "Fate", "activa": False}, JEFE)
        self.assertIn(False, cx.sql_con("update cubiertas_marcas")[0][1])

    def test_la_que_no_usa_nadie_se_borra(self):
        cx = BaseFalsa([{"id": 1, "nombre": "Kumho", "slug": "kumho"}], usadas=0)
        self.assertEqual(marcas.borrar(cx, {"id": 1}, JEFE), {"ok": True})
        self.assertEqual(len(cx.sql_con("delete from cubiertas_marcas")), 1)

    def test_la_que_no_existe_lo_dice(self):
        cx = BaseFalsa()
        with self.assertRaises(ValueError):
            marcas.borrar(cx, {"id": 3}, JEFE)
        with self.assertRaises(ValueError):
            marcas.guardar(cx, {"id": 3, "nombre": "Kumho"}, JEFE)


class Medidas(unittest.TestCase):
    def test_la_familia_sale_del_primer_numero(self):
        cx = BaseFalsa()
        marcas.guardar_medida(cx, {"medida": "295/80R22.5", "clase": "camion"}, JEFE)
        valores = cx.sql_con("insert into cubiertas_medidas")[0][1]
        self.assertEqual(valores[0], "295/80R22.5")
        self.assertEqual(valores[1], "295")

    def test_se_puede_escribir_a_mano_el_numero_que_identifica(self):
        cx = BaseFalsa()
        marcas.guardar_medida(cx, {"medida": "11R22.5", "corta": "1100",
                                   "clase": "camion"}, JEFE)
        self.assertEqual(cx.sql_con("insert into cubiertas_medidas")[0][1][1], "1100")

    def test_la_familia_es_una_de_las_tres(self):
        with self.assertRaises(ValueError):
            marcas.guardar_medida(BaseFalsa(), {"medida": "295", "clase": "tractor"}, JEFE)

    def test_no_entra_dos_veces_la_misma_medida(self):
        cx = BaseFalsa(medidas_=[{"id": 1, "medida": "600x9"}])
        with self.assertRaises(ValueError):
            marcas.guardar_medida(cx, {"medida": "600x9"}, JEFE)

    def test_la_medida_con_cubiertas_se_da_de_baja_no_se_borra(self):
        cx = BaseFalsa(medidas_=[{"id": 1, "medida": "295/80R22.5"}], usadas=8)
        with self.assertRaises(ValueError) as e:
            marcas.borrar_medida(cx, {"id": 1}, JEFE)
        self.assertIn("dar de baja", str(e.exception))
        self.assertEqual(cx.sql_con("delete from cubiertas_medidas"), [])


class Catalogo(unittest.TestCase):
    def test_el_catalogo_de_las_pantallas_no_trae_las_de_baja(self):
        cx = BaseFalsa()
        marcas.catalogo(cx)
        self.assertTrue(all("where" in c[0] for c in cx.consultas),
                        "el catálogo tendría que filtrar las de baja")

    def test_la_parametrizacion_las_ve_todas(self):
        cx = BaseFalsa()
        marcas.listar(cx, incluir_inactivas=True)
        self.assertNotIn("where m.activa", cx.consultas[0][0])

    def test_una_operacion_que_no_existe_se_rechaza(self):
        with self.assertRaises(ValueError):
            marcas.aplicar(BaseFalsa(), {"op": "volar_todo"}, JEFE)


if __name__ == "__main__":
    unittest.main()
