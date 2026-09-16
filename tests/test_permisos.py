"""Quién abre qué, y las dos formas de quedarse afuera del propio sistema.

Lo que se prueba acá es la lista blanca —lo que no está marcado no se
abre, y lo revisa el servidor, no la pantalla— y las validaciones que
protegen al sistema de sí mismo: una base sin administradores activos no
se arregla desde ninguna pantalla.
"""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "gomeria"))
import permisos


class Resultado:
    def __init__(self, una=None, muchas=None):
        self.una, self.muchas = una, muchas or []

    def fetchone(self):
        return self.una

    def fetchall(self):
        return self.muchas


class BaseFalsa:
    """Lo mínimo de Postgres: roles, usuarios y sus módulos."""

    def __init__(self, roles=None, usuarios=None, sin_tablas=False):
        self.roles = roles or {
            "admin": {"codigo": "admin", "nombre": "Administrador", "gestiona": True,
                      "administra": True, "pide_sucursal": False, "activo": True,
                      "de_sistema": True, "modulos": list(permisos.CODIGOS)},
            "sucursal": {"codigo": "sucursal", "nombre": "Responsable de sucursal",
                         "gestiona": False, "administra": False, "pide_sucursal": True,
                         "activo": True, "de_sistema": True,
                         "modulos": ["solicitudes", "alertas"]},
            "compras": {"codigo": "compras", "nombre": "Compras", "gestiona": True,
                        "administra": False, "pide_sucursal": False, "activo": True,
                        "de_sistema": False, "modulos": ["ordenes"]},
        }
        self.usuarios = usuarios or [
            {"id": 1, "usuario": "nico", "nombre": "Nicolás", "rol": "admin",
             "activo": True, "sucursal_codigo": None},
            {"id": 2, "usuario": "marta", "nombre": "Marta", "rol": "sucursal",
             "activo": True, "sucursal_codigo": "TUC"},
        ]
        self.sin_tablas = sin_tablas
        self.consultas = []

    def rollback(self):
        pass

    def execute(self, consulta, valores=()):
        sql = " ".join(consulta.split())
        self.consultas.append((sql, valores))
        if self.sin_tablas:
            raise RuntimeError('relation "roles" does not exist')

        if sql.startswith("select r.codigo, r.nombre, r.gestiona"):
            return Resultado(self.roles.get(valores[0]))
        if sql.startswith("select * from roles where codigo"):
            return Resultado(self.roles.get(valores[0]))
        if sql.startswith("select administra from roles where codigo"):
            rol = self.roles.get(valores[0])
            return Resultado({"administra": rol["administra"]} if rol else None)
        if sql.startswith("select * from usuarios where id"):
            return Resultado(next((u for u in self.usuarios if u["id"] == valores[0]), None))
        if sql.startswith("select 1 from usuarios where usuario"):
            return Resultado(next(({"?": 1} for u in self.usuarios
                                   if u["usuario"] == valores[0]), None))
        if sql.startswith("select u.id, u.rol from usuarios u"):
            return Resultado(muchas=[u for u in self.usuarios if u["activo"]
                                     and self.roles[u["rol"]]["administra"]])
        if sql.startswith("select 1 from usuarios u join roles r"):
            return Resultado(next(({"?": 1} for u in self.usuarios
                                   if u["activo"] and u["rol"] != valores[0]
                                   and self.roles[u["rol"]]["administra"]), None))
        if sql.startswith("select count(*) as n from usuarios where rol"):
            return Resultado({"n": sum(1 for u in self.usuarios if u["rol"] == valores[0])})
        if sql.startswith("insert into usuarios"):
            return Resultado({"id": 99})
        if sql.startswith(("insert", "update", "delete")):
            return Resultado()
        raise AssertionError(f"Consulta inesperada: {sql}")


ADMIN = {"id": 1, "nombre": "Nicolás", "rol": "admin", "administra": True, "gestiona": True}
SUCURSAL = {"id": 2, "nombre": "Marta", "rol": "sucursal", "administra": False,
            "gestiona": False, "modulos": ["solicitudes", "alertas"]}


# =====================================================================
class QueProtegeCadaDireccion(unittest.TestCase):
    def test_la_pantalla_y_su_api_son_el_mismo_modulo(self):
        """Dejar abierta la API es dejar abierto el módulo."""
        for ruta, modulo in (("/repuestos", "repuestos"), ("/api/repuestos", "repuestos"),
                             ("/solicitudes", "solicitudes"),
                             ("/api/solicitudes", "solicitudes"),
                             ("/ordenes", "ordenes"), ("/api/ordenes", "ordenes")):
            with self.subTest(ruta=ruta):
                self.assertEqual(permisos.modulo_de(ruta), modulo)

    def test_las_direcciones_con_barra_caen_en_su_modulo(self):
        self.assertEqual(permisos.modulo_de("/api/unidades/exportar"), "unidades")
        self.assertEqual(permisos.modulo_de("/gomeria/u/AD247MQ"), "gomeria")

    def test_la_portada_y_la_apariencia_no_piden_permiso(self):
        """Entrar y no poder ver ni tu nombre no es un sistema con permisos."""
        for ruta in ("/", "/configuracion", "/favicon.png", "/api/yo"):
            with self.subTest(ruta=ruta):
                self.assertIsNone(permisos.modulo_de(ruta))

    def test_todos_los_modulos_tienen_su_pantalla(self):
        for codigo, _, ruta, _ in permisos.MODULOS:
            with self.subTest(modulo=codigo):
                self.assertEqual(permisos.modulo_de(ruta), codigo)


class LoQueAbreCadaRol(unittest.TestCase):
    def test_la_sucursal_abre_lo_suyo_y_nada_mas(self):
        self.assertTrue(permisos.puede_ver(SUCURSAL, "solicitudes"))
        self.assertFalse(permisos.puede_ver(SUCURSAL, "repuestos"))
        self.assertFalse(permisos.puede_ver(SUCURSAL, "usuarios"))

    def test_el_que_administra_no_se_cierra_afuera_solo(self):
        """Aunque se le olvide marcarse un módulo, lo abre igual."""
        admin = {"administra": True, "modulos": []}
        self.assertTrue(permisos.puede_ver(admin, "usuarios"))

    def test_sin_el_sql_corrido_nadie_se_queda_afuera(self):
        """27_roles.sql sin correr no puede dejar a la gente sin sistema."""
        cx = BaseFalsa(sin_tablas=True)
        usuario = permisos.con_permisos(cx, {"id": 1, "rol": "encargado"})
        self.assertEqual(sorted(usuario["modulos"]), sorted(permisos.CODIGOS))
        self.assertTrue(usuario["gestiona"])
        self.assertFalse(usuario["administra"])

    def test_el_nivel_sale_del_rol_y_no_de_su_nombre(self):
        """Un rol nuevo con «gestiona» aprueba, sin tocar ningún módulo."""
        compras = {"rol": "compras", "gestiona": True, "administra": False}
        self.assertTrue(permisos.gestiona(compras))
        self.assertFalse(permisos.administra(compras))

    def test_un_rol_que_no_existe_no_abre_nada(self):
        cx = BaseFalsa()
        usuario = permisos.con_permisos(cx, {"id": 9, "rol": "inventado"})
        self.assertEqual(usuario["modulos"], [])


# =====================================================================
class AltaDeUsuarios(unittest.TestCase):
    def test_solo_un_administrador_toca_usuarios(self):
        with self.assertRaises(PermissionError):
            permisos.panel(BaseFalsa(), SUCURSAL)
        with self.assertRaises(PermissionError):
            permisos.crear(BaseFalsa(), {"usuario": "x"}, SUCURSAL)

    def test_el_usuario_va_en_minusculas_y_sin_espacios(self):
        for nombre in ("Ramón Gómez", "ra", "ramon gomez"):
            with self.subTest(usuario=nombre), self.assertRaises(ValueError):
                permisos.crear(BaseFalsa(), {"usuario": nombre, "nombre": "Ramón",
                                             "clave": "taller2026"}, ADMIN)

    def test_el_usuario_repetido_no_entra(self):
        with self.assertRaises(ValueError):
            permisos.crear(BaseFalsa(), {"usuario": "marta", "nombre": "Otra",
                                         "clave": "taller2026"}, ADMIN)

    def test_una_contrasena_floja_no_pasa(self):
        with self.assertRaises(ValueError):
            permisos.crear(BaseFalsa(), {"usuario": "pedro", "nombre": "Pedro",
                                         "clave": "1234"}, ADMIN)

    def test_un_rol_de_sucursal_necesita_sucursal(self):
        """Sin su código no puede pedir: la solicitud se numera por quién pide."""
        with self.assertRaises(ValueError) as e:
            permisos.crear(BaseFalsa(), {"usuario": "pedro", "nombre": "Pedro",
                                         "rol": "sucursal", "clave": "taller2026"}, ADMIN)
        self.assertIn("sucursal", str(e.exception).lower())

    def test_con_sucursal_entra_y_queda_en_mayusculas(self):
        cx = BaseFalsa()
        salida = permisos.crear(cx, {"usuario": "pedro", "nombre": "Pedro Luna",
                                     "rol": "sucursal", "sucursal_codigo": "tuc",
                                     "clave": "taller2026"}, ADMIN)
        self.assertEqual(salida["usuario"], "pedro")
        insercion = next(v for sql, v in cx.consultas if sql.startswith("insert into usuarios"))
        self.assertEqual(insercion[-1], "TUC")
        self.assertTrue(insercion[2].startswith("scrypt$"))   # nunca en claro


class NadieSeQuedaSinAdministradores(unittest.TestCase):
    def test_no_puedo_darme_de_baja_a_mi_mismo(self):
        with self.assertRaises(ValueError):
            permisos.estado(BaseFalsa(), {"id": 1, "activo": False}, ADMIN)

    def test_no_se_puede_bajar_al_ultimo_administrador(self):
        cx = BaseFalsa()
        otro = dict(ADMIN, id=3)
        with self.assertRaises(ValueError):
            permisos.estado(cx, {"id": 1, "activo": False}, otro)

    def test_no_se_le_puede_cambiar_el_rol_al_ultimo_administrador(self):
        with self.assertRaises(ValueError):
            permisos.guardar(BaseFalsa(), {"id": 1, "rol": "sucursal",
                                           "sucursal_codigo": "TUC"}, ADMIN)

    def test_dar_de_baja_a_otro_le_corta_las_sesiones(self):
        cx = BaseFalsa()
        salida = permisos.estado(cx, {"id": 2, "activo": False}, ADMIN)
        self.assertFalse(salida["activo"])
        self.assertTrue(any(sql.startswith("delete from sesiones") for sql, _ in cx.consultas))


class Roles(unittest.TestCase):
    def test_el_codigo_no_lleva_mayusculas_ni_acentos(self):
        with self.assertRaises(ValueError):
            permisos.guardar_rol(BaseFalsa(), {"codigo": "Depósito", "nombre": "Depósito",
                                               "modulos": []}, ADMIN)

    def test_un_modulo_que_no_existe_no_se_guarda(self):
        with self.assertRaises(ValueError):
            permisos.guardar_rol(BaseFalsa(), {"codigo": "compras", "nombre": "Compras",
                                               "modulos": ["contabilidad"]}, ADMIN)

    def test_los_modulos_se_escriben_enteros(self):
        """La pantalla manda la lista final: lo viejo se borra, no se suma."""
        cx = BaseFalsa()
        permisos.guardar_rol(cx, {"codigo": "compras", "nombre": "Compras",
                                  "gestiona": True,
                                  "modulos": ["ordenes", "solicitudes"]}, ADMIN)
        self.assertTrue(any(sql.startswith("delete from rol_modulos") for sql, _ in cx.consultas))
        puestos = [v[1] for sql, v in cx.consultas
                   if sql.startswith("insert into rol_modulos")]
        self.assertEqual(sorted(puestos), ["ordenes", "solicitudes"])

    def test_cambiarle_el_rol_a_alguien_vale_ya_y_no_manana(self):
        cx = BaseFalsa()
        permisos.guardar_rol(cx, {"codigo": "compras", "nombre": "Compras",
                                  "modulos": ["ordenes"]}, ADMIN)
        self.assertTrue(any("delete from sesiones" in sql for sql, _ in cx.consultas))

    def test_un_rol_de_fabrica_no_se_borra(self):
        with self.assertRaises(ValueError) as e:
            permisos.borrar_rol(BaseFalsa(), {"codigo": "sucursal"}, ADMIN)
        self.assertIn("sistema", str(e.exception))

    def test_un_rol_con_gente_adentro_no_se_borra(self):
        cx = BaseFalsa(usuarios=[
            {"id": 1, "usuario": "nico", "nombre": "N", "rol": "admin", "activo": True,
             "sucursal_codigo": None},
            {"id": 5, "usuario": "ana", "nombre": "Ana", "rol": "compras", "activo": True,
             "sucursal_codigo": None}])
        with self.assertRaises(ValueError) as e:
            permisos.borrar_rol(cx, {"codigo": "compras"}, ADMIN)
        self.assertIn("1 usuario", str(e.exception))

    def test_un_rol_vacio_se_borra(self):
        salida = permisos.borrar_rol(BaseFalsa(), {"codigo": "compras"}, ADMIN)
        self.assertEqual(salida["codigo"], "compras")


if __name__ == "__main__":
    unittest.main()
