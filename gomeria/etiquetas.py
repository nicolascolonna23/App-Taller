"""
La hoja de etiquetas QR de los repuestos, lista para imprimir.

Cada etiqueta lleva un QR con la dirección del repuesto en la app. El
gomero le apunta con la cámara del celular y se abre la salida de ese
repuesto, con la cantidad en 1: no tiene que buscarlo en una lista de
cientos.

El QR guarda la dirección, no el stock. Por eso la etiqueta no se vence:
sirve igual aunque el artículo cambie de cantidad, de rubro o de precio.
El SVG va incrustado en la página, así que la hoja se imprime bien aunque
la impresora esté en una máquina sin internet.

Medidas: 70 × 37 mm, tres columnas por ocho filas, 24 por hoja A4. Es el
tamaño de las hojas autoadhesivas más comunes. Para cambiarlo, están las
constantes de acá abajo.
"""
import io
import html

import qrcode
from qrcode.image.svg import SvgPathImage

ANCHO_MM = 70
ALTO_MM = 37
COLUMNAS = 3
FILAS = 8


def _qr(texto):
    """El QR como SVG, sin cabecera XML, para incrustarlo en la página."""
    img = qrcode.make(texto, image_factory=SvgPathImage, box_size=10, border=1)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode()
    svg = svg[svg.index("<svg"):]
    # El SVG que sale trae un tamaño fijo en milímetros; se lo saca para
    # que ocupe el alto de la etiqueta y no el que decidió la librería.
    for atributo in ('width="', 'height="'):
        while atributo in svg:
            i = svg.index(atributo)
            j = svg.index('"', i + len(atributo)) + 1
            svg = svg[:i] + svg[j:]
    return svg.replace("<svg", '<svg class="qr" preserveAspectRatio="xMidYMid meet"', 1)


def _articulos(cx, rubro=None, codigos=None, solo_activos=True):
    condiciones = []
    valores = []
    if solo_activos:
        condiciones.append("activo")
    if rubro:
        condiciones.append("rubro = %s")
        valores.append(rubro)
    if codigos:
        condiciones.append("codigo = any(%s)")
        valores.append(list(codigos))
    donde = (" where " + " and ".join(condiciones)) if condiciones else ""
    return cx.execute(f"""
        select codigo, descripcion, rubro, codigo_interno
        from repuestos_articulos {donde}
        order by rubro, descripcion, codigo
    """, valores).fetchall()


def rubros(cx):
    return [r["rubro"] for r in cx.execute("""
        select distinct rubro from repuestos_articulos
        where activo order by rubro""").fetchall()]


def hoja(cx, base, rubro=None, codigos=None):
    """La página de etiquetas. `base` es la dirección que ven los celulares."""
    arts = _articulos(cx, rubro, codigos)
    base = base.rstrip("/")

    def etiqueta(a):
        from urllib.parse import quote
        destino = f"{base}/repuestos/{quote(a['codigo'], safe='')}"
        interno = a["codigo_interno"] or ""
        return f"""    <div class="et">
      {_qr(destino)}
      <div class="txt">
        <b>{html.escape(a['codigo'])}</b>
        <span class="desc">{html.escape(a['descripcion'])}</span>
        <span class="pie">{html.escape(a['rubro'])}{' · int. ' + html.escape(interno) if interno else ''}</span>
      </div>
    </div>"""

    cuerpo = "\n".join(etiqueta(a) for a in arts) or \
        '    <p class="vacio">No hay repuestos que entren en ese filtro.</p>'
    titulo = f"{len(arts)} etiqueta{'' if len(arts) == 1 else 's'}"
    if rubro:
        titulo += f" · {html.escape(rubro)}"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Etiquetas de repuestos | Diemar</title>
<style>
  /* En pantalla se ve sobre gris para distinguir las hojas; al imprimir
     solo salen las etiquetas. */
  @page {{ size: A4; margin: 8mm; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #6b7280; color: #111;
    font: 13px Inter, system-ui, -apple-system, sans-serif; }}

  .barra {{ position: sticky; top: 0; z-index: 5; display: flex; gap: 14px;
    align-items: center; padding: 12px 20px; background: #12161a; color: #edf0f2; }}
  .barra b {{ font-size: 14px; }}
  .barra a, .barra button {{ color: #edf0f2; background: #ff7a1a; border: 0;
    border-radius: 9px; padding: 9px 15px; font: inherit; font-weight: 700;
    text-decoration: none; cursor: pointer; }}
  .barra .volver {{ background: #20262c; }}
  .barra .nota {{ margin-left: auto; color: #8d959e; font-size: 12px; }}

  .hoja {{ width: 210mm; margin: 14px auto; padding: 8mm; background: #fff;
    display: grid; grid-template-columns: repeat({COLUMNAS}, {ANCHO_MM}mm);
    grid-auto-rows: {ALTO_MM}mm; justify-content: center; }}

  .et {{ display: flex; align-items: center; gap: 3mm; padding: 2.5mm;
    overflow: hidden; border: 1px dashed #d4d4d8; }}
  .et .qr {{ height: {ALTO_MM - 7}mm; width: {ALTO_MM - 7}mm; flex: none; }}
  .et .txt {{ min-width: 0; display: flex; flex-direction: column; gap: 0.6mm; }}
  .et b {{ font-size: 11pt; font-weight: 800; letter-spacing: .2px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  /* La descripción es lo que más varía de largo: se le dan tres renglones
     y lo que no entra se corta, para que ninguna etiqueta empuje a la de
     al lado y se desarme la grilla. */
  .et .desc {{ font-size: 7.6pt; line-height: 1.25; display: -webkit-box;
    -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
  .et .pie {{ font-size: 6.4pt; color: #52525b; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; }}
  .vacio {{ grid-column: 1 / -1; text-align: center; color: #6b7280; padding: 30mm 0; }}

  @media print {{
    body {{ background: #fff; }}
    .barra {{ display: none; }}
    .hoja {{ width: auto; margin: 0; padding: 0; }}
    /* El borde punteado es la guía para cortar; si molesta, se saca acá. */
    .et {{ border-color: #e4e4e7; break-inside: avoid; }}
  }}
</style>
</head>
<body>

<div class="barra">
  <a class="volver" href="/repuestos">‹ Volver</a>
  <b>{titulo}</b>
  <button onclick="print()">Imprimir</button>
  <span class="nota">{ANCHO_MM} × {ALTO_MM} mm · {COLUMNAS * FILAS} por hoja A4</span>
</div>

<div class="hoja">
{cuerpo}
</div>

</body>
</html>
"""
