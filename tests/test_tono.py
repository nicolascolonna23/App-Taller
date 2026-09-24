"""El sistema no habla como el taller.

Los tres lugares donde el sistema redacta un texto con un modelo —el que
traduce los partes de gomería, Pengui y el asistente de cuenta corriente—
tienen que pedir un castellano neutro. Es una prueba sobre el prompt: no
garantiza cada respuesta, pero sí que la instrucción esté y que nadie la
borre sin querer al tocar el archivo.
"""
import pathlib, sys, unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Las muletillas que aparecían en pantalla y no tienen que volver.
MULETILLAS = ("che", "dale", "mirá", "ojo")


class ElSistemaNoTutea(unittest.TestCase):
    def test_el_que_lee_los_partes_escribe_sobrio(self):
        from gomeria import interpretar
        texto = interpretar.instrucciones(
            {"patente": "AD900UK", "interno": "13"},
            [{"posicion": "1I", "eje": 1, "lado": "I", "montaje": "unica",
              "es_auxilio": False, "cubierta": None}])
        self.assertIn("CÓMO ESCRIBÍS", texto)
        for muletilla in MULETILLAS:
            self.assertIn(muletilla, texto.lower(),
                          f"el prompt ya no prohíbe «{muletilla}»")
        self.assertIn("neutro", texto)

    def test_el_ejemplo_del_resumen_no_es_de_taller(self):
        from gomeria import interpretar
        resumen = interpretar.HERRAMIENTA["input_schema"]["properties"]["resumen"]
        self.assertIn("sin modismos", resumen["description"])

    def test_pengui_tambien(self):
        reglas = (RAIZ / "gomeria" / "asistente_reglas.md").read_text(encoding="utf-8")
        self.assertIn("neutro", reglas)
        for muletilla in MULETILLAS:
            self.assertIn(muletilla, reglas.lower())

    def test_el_asistente_de_cuenta_corriente_tambien(self):
        chat = (RAIZ / "chat" / "servidor.py").read_text(encoding="utf-8")
        self.assertIn("neutro", chat)
        for muletilla in MULETILLAS:
            self.assertIn(muletilla, chat.lower())


if __name__ == "__main__":
    unittest.main()
