"""
Trae la planilla de combustible del link parametrizado y la guarda.

El control de combustible se lleva en una hoja que se edita todos los
días. Bajarla para volver a subirla es trabajo que la computadora puede
hacer sola: el link se carga una vez en Parámetros → Combustible y este
archivo entra a buscarla.

Lo corre GitHub Actions todas las mañanas (ver
`.github/workflows/combustible.yml`) y se puede correr a mano:

    SUPABASE_DB_URL=... python gomeria/traer_combustible.py

Traer de nuevo la misma planilla no duplica nada: cada remito se pisa con
su última versión, igual que subir el archivo a mano.

Sale con 0 si trajo —o si no había nada que traer porque el módulo está
en manual— y con 1 si el link falló. Que falle fuerte es a propósito: un
link que dejó de andar tiene que verse en el mail del job y no seis
semanas después, cuando alguien busque una carga y no esté.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import base
import combustible
import parametros

# El job no es una persona, pero escribe como una: queda su nombre en el
# lote, que es lo que después explica de dónde salió esa fila.
JOB = {"nombre": "Traída automática", "rol": "admin", "gestiona": True}


def main():
    with base.conectar() as cx:
        p = parametros.leer(cx) or {}
        if p.get("combustible_origen") != "automatico":
            print("El combustible está en manual: no hay nada que traer.")
            return 0
        if not p.get("combustible_fuente"):
            print("No hay ningún link cargado en Parámetros → Combustible.")
            return 0

        print(f"Trayendo de {p['combustible_fuente']}")
        try:
            salida = combustible.traer(cx, JOB)
        except Exception as e:
            cx.commit()   # el resultado queda anotado aunque haya fallado
            print(f"ERROR: {e}")
            return 1
        cx.commit()

    print(f"{salida['guardadas']} filas · {salida['nuevas']} nuevas · "
          f"{salida['actualizadas']} corregidas · "
          f"{salida['descartadas']} descartadas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
