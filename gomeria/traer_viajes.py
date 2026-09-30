"""
Trae la planilla de hojas de ruta del BI y guarda los viajes a Catamarca.

Es lo mismo que el botón «Releer planilla» de Viento en ruta, sin nadie
que lo toque. De paso deja bajado el viento de los viajes nuevos, así la
pantalla abre sin esperar a Open-Meteo.

Lo corre GitHub Actions todas las mañanas (ver
`.github/workflows/viajes.yml`) y se puede correr a mano:

    SUPABASE_DB_URL=... python gomeria/traer_viajes.py

Traer de nuevo la misma planilla no duplica nada: cada viaje se pisa con
su última versión.

Sale con 1 si el BI no contestó o si falta la tabla. Que falle fuerte es a
propósito: un reporte que dejó de andar tiene que verse en el mail del job.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import base
import viento

# El viento de los viajes de estos últimos días se deja bajado. Más atrás
# ya se bajó en corridas anteriores.
DIAS_DE_VIENTO = 45


def main():
    with base.conectar() as cx:
        print(f"Trayendo {viento.URL_HOJAS}")
        try:
            datos = viento.hojas(forzar=True)
        except Exception as e:
            viento.anotar_traida(cx, f"Falló: {e}")
            print(f"ERROR: {e}")
            return 1

        n = viento.guardar_viajes(cx, datos)
        if n is None:
            print("ERROR: falta la tabla viento_viajes. Correr gomeria/40_viento_viajes.sql en Supabase.")
            return 1
        print(f"{n} viajes Buenos Aires ↔ Catamarca guardados · "
              f"{datos['otros']} de otros tramos · {datos['descartados']} sin fecha legible")

        desde = date.today() - timedelta(days=DIAS_DE_VIENTO)
        dias = set()
        for v in datos["viajes"]:
            if v["salida"].date() < desde:
                continue
            llegada, _ = viento.llegada_estimada(v)
            d = v["salida"].date()
            while d <= llegada.date():
                dias.add(d)
                d += timedelta(days=1)
        w = viento.viento_para(cx, dias)
        for aviso in w.avisos:
            print(f"Viento: {aviso}")
        print(f"Viento al día para {len(dias)} días de viaje.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
