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


CARTEL = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<title>QR - Gomeria</title><style>
  @page {{ size: A4; margin: 15mm; }}
  body {{ font-family: system-ui,-apple-system,'Segoe UI',sans-serif; margin:0; color:#000;
         text-align:center; background:#fff; }}
  .aviso {{ font-size:12px; color:#555; padding-bottom:8mm; }}
  @media print {{ .aviso {{ display:none; }} }}
  h1 {{ font-size:32pt; margin:0 0 2mm; letter-spacing:2px; }}
  h2 {{ font-size:13pt; font-weight:400; color:#333; margin:0 0 8mm; }}
  svg {{ width:100mm; height:100mm; }}
  .pasos {{ text-align:left; max-width:120mm; margin:6mm auto 0; font-size:12pt; line-height:1.7; }}
  .pasos b {{ display:inline-block; width:7mm; }}
  .ej {{ font-style:italic; color:#444; }}
  .pie {{ margin-top:8mm; font-size:8.5pt; letter-spacing:3px; color:#666; text-transform:uppercase; }}
</style></head><body>
<div class="aviso">Apunta a {base_url} &middot; Ctrl+P para imprimir. Este texto no sale impreso.</div>
<h1>GOMER&Iacute;A</h1>
<h2>Escane&aacute; para cargar un movimiento de cubiertas</h2>
{qr}
<div class="pasos">
  <div><b>1.</b> Escane&aacute; el c&oacute;digo con la c&aacute;mara del celular.</div>
  <div><b>2.</b> Escrib&iacute; la patente y qu&eacute; hiciste, como lo dir&iacute;as.</div>
  <div style="margin-left:7mm" class="ej">&ldquo;AD 247 MQ gir&eacute; las dos de afuera del lado izquierdo&rdquo;</div>
  <div><b>3.</b> Revis&aacute; lo que entendi&oacute; y confirm&aacute;.</div>
</div>
<div class="pie">Expreso Diemar</div>
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Etiquetas QR de las unidades")
    ap.add_argument("--base", required=True,
                    help="Dirección del servidor de gomería como la ven los celulares, "
                         "por ejemplo http://192.168.1.45:8100")
    ap.add_argument("--patentes", help="Lista separada por comas. Si no se pasa, todas las activas.")
    ap.add_argument("--uno", action="store_true",
                    help="Un solo cartel con un QR para toda la gomería, en vez de una "
                         "etiqueta por unidad. La patente se escribe dentro del texto.")
    ap.add_argument("--salida", default=os.path.join(AQUI, "etiquetas.html"))
    a = ap.parse_args()

    base_url = a.base.rstrip("/")

    if a.uno:
        with open(a.salida, "w", encoding="utf-8") as fh:
            fh.write(CARTEL.format(base_url=base_url, qr=svg_qr(base_url + "/gomeria#register")))
        print(f"Listo: {a.salida}")
        print(f"Un cartel A4 con un solo QR, apuntando a {base_url}/gomeria#register")
        return

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
        url = f"{base_url}/gomeria/u/{f['patente']}"
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
