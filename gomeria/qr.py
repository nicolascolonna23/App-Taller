#!/usr/bin/env python3
"""
Genera la hoja de etiquetas QR para pegar en las unidades.

Cada QR abre la pantalla de gomería de esa unidad. La dirección tiene que
ser la que ven los celulares, no 127.0.0.1.

    python3 qr.py --base http://192.168.1.45:8100
    python3 qr.py --base http://192.168.1.45:8100 --patentes AD247MQ,AE423IV

Deja etiquetas.html; se abre en el navegador y se imprime (Ctrl+P). Salen
en hojas A4, listas para cortar y plastificar.
"""
import argparse, os, sys
import qrcode
from qrcode.image.svg import SvgPathImage

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)


def svg_qr(texto):
    """QR como SVG embebido: no depende de imágenes ni de internet al imprimir."""
    img = qrcode.make(texto, image_factory=SvgPathImage, box_size=10, border=2)
    import io
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode()
    return svg[svg.index("<svg"):]


def fmt_pat(p):
    import re
    m = re.match(r"^([A-Z]{2})(\d{3})([A-Z]{2})$", p or "")
    if m:
        return f"{m[1]} {m[2]} {m[3]}"
    o = re.match(r"^([A-Z]{3})(\d{3})$", p or "")
    return f"{o[1]} {o[2]}" if o else p


HOJA = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<title>Etiquetas QR — Gomería</title>
<style>
  @page {{ size: A4; margin: 12mm; }}
  body {{ font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; margin:0; color:#000; background:#fff; }}
  .aviso {{ padding:10px 0 16px; font-size:12px; color:#555; }}
  @media print {{ .aviso {{ display:none; }} }}
  .hoja {{ display:grid; grid-template-columns: repeat(3, 1fr); gap:8mm; }}
  .et {{
    border:1.5px solid #000; border-radius:4mm; padding:5mm 3mm 4mm;
    text-align:center; break-inside:avoid; page-break-inside:avoid;
  }}
  .et svg {{ width:38mm; height:38mm; display:block; margin:0 auto 3mm; }}
  .pat {{ font-size:15pt; font-weight:800; letter-spacing:.5px; }}
  .sub {{ font-size:8.5pt; color:#333; margin-top:1mm; }}
  .marca {{ font-size:7.5pt; letter-spacing:2px; color:#666; margin-top:2mm;
            text-transform:uppercase; font-weight:700; }}
</style></head><body>
<div class="aviso">{aviso}</div>
<div class="hoja">{etiquetas}</div>
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Etiquetas QR de las unidades")
    ap.add_argument("--base", required=True,
                    help="Dirección del servidor de gomería como la ven los celulares, "
                         "por ejemplo http://192.168.1.45:8100")
    ap.add_argument("--patentes", help="Lista separada por comas. Si no se pasa, todas las activas.")
    ap.add_argument("--salida", default=os.path.join(AQUI, "etiquetas.html"))
    a = ap.parse_args()

    base_url = a.base.rstrip("/")

    if a.patentes:
        filas = [{"patente": p.strip().upper().replace(" ", ""), "interno": None, "sucursal": None}
                 for p in a.patentes.split(",") if p.strip()]
    else:
        import base as bd
        with bd.conectar() as cx:
            filas = cx.execute("""select patente, interno, sucursal from unidades
                                  where activa order by sucursal, patente""").fetchall()
    if not filas:
        raise SystemExit("No hay unidades para generar. Cargá primero las unidades.")

    etiquetas = []
    for f in filas:
        url = f"{base_url}/u/{f['patente']}"
        sub = " · ".join(x for x in [f.get("interno") and f"Interno {f['interno']}",
                                     f.get("sucursal")] if x)
        etiquetas.append(
            f'<div class="et">{svg_qr(url)}'
            f'<div class="pat">{fmt_pat(f["patente"])}</div>'
            f'<div class="sub">{sub}</div>'
            f'<div class="marca">Gomería Diemar</div></div>')

    aviso = (f"{len(filas)} etiquetas · apuntan a {base_url} · "
             f"Ctrl+P para imprimir. Este texto no sale impreso.")
    with open(a.salida, "w", encoding="utf-8") as fh:
        fh.write(HOJA.format(aviso=aviso, etiquetas="\n".join(etiquetas)))
    print(f"Listo: {a.salida} ({len(filas)} etiquetas)")
    print(f"Apuntan a {base_url}/u/PATENTE")


if __name__ == "__main__":
    main()
