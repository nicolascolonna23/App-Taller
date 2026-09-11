"""El orden de las direcciones en app.py.

El ruteo es una fila de `if` que se leen de arriba abajo, así que una
dirección con barra —`/api/unidades/exportar`— la puede tapar un
`startswith` más arriba que la lee como un id y contesta que la unidad no
existe. Pasó: el botón de Excel devolvía {"error": "Esa unidad no existe."}
en producción, y no lo vio ningún test porque el navegador simulado
respondía esa dirección por su cuenta, sin pasar por el ruteo de verdad.

Esto mira el archivo, no el servidor: sin base de datos, y falla en el
momento en que alguien agrega una dirección abajo del comodín que le
corresponde.
"""
import os
import re
import unittest

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rutas_por_metodo():
    """Las direcciones que atiende cada do_*, en el orden en que se leen."""
    codigo = open(os.path.join(AQUI, "app.py"), encoding="utf-8").read()
    metodos, actual = {}, None
    for linea in codigo.splitlines():
        m = re.match(r"\s*def (do_[A-Z]+)\(", linea)
        if m:
            actual = m.group(1)
            metodos[actual] = []
            continue
        if actual is None:
            continue
        # Cortamos al salir del método: cualquier def a menos indentación.
        if re.match(r"    def (?!do_)", linea):
            actual = None
            continue
        exacta = re.search(r'ruta == "([^"]+)"', linea)
        if exacta:
            metodos[actual].append(("exacta", exacta.group(1)))
        prefijo = re.search(r'ruta\.startswith\("([^"]+)"\)', linea)
        if prefijo:
            metodos[actual].append(("prefijo", prefijo.group(1)))
    return metodos


class OrdenDeLasRutas(unittest.TestCase):
    def test_ninguna_direccion_queda_tapada_por_un_comodin(self):
        for metodo, rutas in _rutas_por_metodo().items():
            vistos = []
            for clase, ruta in rutas:
                if clase == "exacta":
                    for antes in vistos:
                        self.assertFalse(
                            ruta.startswith(antes),
                            f'En {metodo}, "{ruta}" nunca se alcanza: más '
                            f'arriba está startswith("{antes}"), que se la '
                            f"come y la lee como si fuera un id. Va antes "
                            f"de esa línea.")
                else:
                    vistos.append(ruta)

    def test_exportar_esta_antes_de_la_ficha(self):
        """El caso concreto que se rompió, por si el general afloja."""
        rutas = _rutas_por_metodo()["do_GET"]
        orden = [r for _, r in rutas]
        self.assertIn("/api/unidades/exportar", orden)
        self.assertIn("/api/unidades/", orden)
        self.assertLess(orden.index("/api/unidades/exportar"),
                        orden.index("/api/unidades/"),
                        "El Excel de flota vuelve a estar tapado por la ficha.")


if __name__ == "__main__":
    unittest.main()
