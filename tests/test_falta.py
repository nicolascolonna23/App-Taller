"""Qué le falta a la base, dicho con nombre y apellido.

El cartel viejo mandaba a correr el script del módulo que se estaba
mirando. Cuando lo que falta es de otro —abrir Solicitudes con el maestro
de unidades sin la columna `chofer`— eso manda a correr un script que ya
se corrió y esconde el problema real.
"""
import pathlib, sys, unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "gomeria"))

import base  # noqa: E402


class Diagnostico:
    def __init__(self, texto):
        self.message_primary = texto


class ErrorDeLaBase(Exception):
    def __init__(self, texto):
        super().__init__(texto)
        self.diag = Diagnostico(texto)


RESPALDO = ("Falta crear las tablas de solicitudes. Ejecutar "
            "gomeria/26_solicitudes.sql en el SQL Editor de Supabase.")


class QueFalta(unittest.TestCase):
    def test_una_columna_de_otro_modulo(self):
        dicho = base.que_falta(ErrorDeLaBase('column "chofer" does not exist'), RESPALDO)
        self.assertIn("«chofer»", dicho)
        self.assertIn("07_unidades.sql", dicho)
        self.assertNotIn("26_solicitudes.sql", dicho)

    def test_una_vista_del_modulo(self):
        dicho = base.que_falta(
            ErrorDeLaBase('relation "v_solicitudes" does not exist'), RESPALDO)
        self.assertIn("«v_solicitudes»", dicho)
        self.assertIn("26_solicitudes.sql", dicho)

    def test_la_columna_puede_venir_con_la_tabla_adelante(self):
        dicho = base.que_falta(
            ErrorDeLaBase('column "u.km_actual" does not exist'), RESPALDO)
        self.assertIn("«km_actual»", dicho)

    def test_lo_que_no_esta_en_ningun_script_deja_el_cartel_viejo(self):
        dicho = base.que_falta(ErrorDeLaBase('column "invento_23" does not exist'), RESPALDO)
        self.assertIn("«invento_23»", dicho)
        self.assertIn("26_solicitudes.sql", dicho)

    def test_sin_nombre_queda_el_cartel_viejo(self):
        self.assertEqual(base.que_falta(ErrorDeLaBase("algo raro"), RESPALDO), RESPALDO)

    def test_el_catalogo_sale_de_los_scripts_que_hay(self):
        catalogo = base._catalogo()
        self.assertEqual(catalogo.get("v_fluidos_saldo"), "32_fluidos.sql")
        self.assertEqual(catalogo.get("combustible_origen"), "33_combustible_origen.sql")
        # Un script nuevo entra solo: no hay lista escrita a mano que actualizar.
        self.assertGreater(len(catalogo), 200)


if __name__ == "__main__":
    unittest.main()
