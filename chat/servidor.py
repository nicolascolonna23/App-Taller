#!/usr/bin/env python3
"""
Servidor del chat interno.

Sirve la pantalla del chat y responde las preguntas consultando datos.db.
La clave de la API vive acá, en el servidor: nunca viaja al navegador.

    export ANTHROPIC_API_KEY=sk-ant-...
    python3 servidor.py                 # http://127.0.0.1:8000

Por defecto escucha solo en 127.0.0.1 (esta misma máquina). Para que lo use
la oficina, ver el README: hay que pasar --host 0.0.0.0 y dejarlo detrás del
servidor web interno.
"""
import argparse, json, os, re, sqlite3, sys, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anthropic
from anthropic import beta_tool

AQUI  = os.path.dirname(os.path.abspath(__file__))
DB    = os.path.join(AQUI, "datos.db")
MODEL = "claude-opus-5"

# Tope de filas que puede devolver una herramienta. Existe para que una
# pregunta amplia no meta media base en el contexto del modelo.
MAX_FILAS = 60


def conectar():
    """Conexión de solo lectura: el chat nunca puede modificar los datos."""
    cx = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)
    cx.row_factory = sqlite3.Row
    return cx


def consultar(sql, params=()):
    cx = conectar()
    try:
        return [dict(r) for r in cx.execute(sql, params).fetchall()]
    finally:
        cx.close()


def jstr(dato):
    """Las herramientas le contestan al modelo en JSON."""
    return json.dumps(dato, ensure_ascii=False, default=str)


# Reglas de negocio en un solo lugar, para que todas las herramientas
# calculen la deuda igual.
DEUDA   = "SUM(CASE WHEN cc.tipo IN ('FC','ND') THEN cc.monto_pendiente ELSE 0 END)"
VENCIDO = "SUM(CASE WHEN cc.tipo IN ('FC','ND') AND cc.vencido=1 THEN cc.monto_pendiente ELSE 0 END)"
A_FAVOR = "-SUM(CASE WHEN cc.tipo IN ('REC','OP','NC') THEN cc.monto_pendiente ELSE 0 END)"


# =====================================================================
# HERRAMIENTAS
# =====================================================================

@beta_tool
def buscar_cliente(texto: str, limite: int = 10) -> str:
    """Busca clientes por razón social, alias, CUIT o número de cliente.

    Usala siempre antes de consultar un saldo: el usuario escribe el nombre
    como lo dice en la oficina y hay razones sociales parecidas o duplicadas.

    Args:
        texto: Nombre, alias, CUIT o id a buscar. Alcanza con una parte.
        limite: Cuántos resultados devolver como máximo.
    """
    limite = max(1, min(int(limite), MAX_FILAS))
    like = f"%{texto.strip()}%"
    solo_digitos = re.sub(r"\D", "", texto)
    filas = consultar(f"""
        SELECT c.id, c.razon_social, c.alias, c.nif, c.sucursal, c.provincia,
               c.condicion_pago, c.limite_credito,
               ROUND(COALESCE({DEUDA},0),2) AS deuda,
               ROUND(COALESCE({VENCIDO},0),2) AS vencido
        FROM clientes c
        LEFT JOIN cuenta_corriente cc ON cc.id_cliente = c.id
        WHERE c.razon_social LIKE ? OR c.alias LIKE ? OR c.nif LIKE ?
              OR (? <> '' AND CAST(c.id AS TEXT) = ?)
        GROUP BY c.id
        ORDER BY deuda DESC, c.razon_social
        LIMIT ?""", (like, like, like, solo_digitos, solo_digitos, limite))
    if not filas:
        return jstr({"encontrados": 0,
                     "sugerencia": "Probá con menos letras o con el CUIT."})
    return jstr({"encontrados": len(filas), "clientes": filas})


@beta_tool
def resumen_cliente(id_cliente: int) -> str:
    """Ficha completa de un cliente: datos de contacto, saldo y estado de cobranza.

    Args:
        id_cliente: Número de cliente, el que devuelve buscar_cliente.
    """
    datos = consultar("SELECT * FROM clientes WHERE id = ?", (id_cliente,))
    if not datos:
        return jstr({"error": f"No existe el cliente {id_cliente}."})
    cliente = datos[0]

    saldo = consultar(f"""
        SELECT ROUND(COALESCE({DEUDA},0),2)   AS deuda,
               ROUND(COALESCE({VENCIDO},0),2) AS vencido,
               ROUND(COALESCE({A_FAVOR},0),2) AS a_favor,
               COUNT(*) AS movimientos,
               MIN(cc.fecha_emision) AS primer_movimiento,
               MAX(cc.fecha_emision) AS ultimo_movimiento
        FROM cuenta_corriente cc WHERE cc.id_cliente = ?""", (id_cliente,))[0]

    abiertos = consultar("""
        SELECT nro, tipo, fecha_emision, fecha_vencimiento,
               ROUND(monto_pendiente,2) AS pendiente, vencido, estado
        FROM cuenta_corriente
        WHERE id_cliente = ? AND tipo IN ('FC','ND') AND monto_pendiente > 0
        ORDER BY fecha_vencimiento
        LIMIT 25""", (id_cliente,))

    limite = cliente.get("limite_credito") or 0
    saldo["excede_limite"] = bool(limite and saldo["deuda"] > limite)
    return jstr({"cliente": cliente, "saldo": saldo,
                 "comprobantes_pendientes": abiertos,
                 "nota": "Montos en pesos. deuda = facturas y notas de débito con "
                         "saldo; a_favor = recibos y órdenes de pago sin aplicar."})


@beta_tool
def ranking_deudores(limite: int = 15, solo_vencidos: bool = False,
                     sucursal: str = "", provincia: str = "",
                     monto_minimo: float = 0) -> str:
    """Lista los clientes con más deuda, de mayor a menor.

    Sirve para "quiénes son los que más deben", "deudores vencidos de Catamarca",
    "clientes con más de un millón de deuda".

    Args:
        limite: Cuántos clientes devolver.
        solo_vencidos: Si es True, ordena y filtra por deuda vencida.
        sucursal: Filtra por sucursal del cliente. Vacío = todas.
        provincia: Filtra por provincia del cliente. Vacío = todas.
        monto_minimo: Deja afuera a los que deben menos que este monto.
    """
    limite = max(1, min(int(limite), MAX_FILAS))
    campo = VENCIDO if solo_vencidos else DEUDA
    where, params = ["1=1"], []
    if sucursal:
        where.append("c.sucursal LIKE ?"); params.append(f"%{sucursal}%")
    if provincia:
        where.append("c.provincia LIKE ?"); params.append(f"%{provincia}%")
    params += [float(monto_minimo), limite]
    filas = consultar(f"""
        SELECT c.id, c.razon_social, c.sucursal, c.provincia, c.condicion_pago,
               c.limite_credito, c.contacto_cobro, c.contacto_cobro_email,
               ROUND(COALESCE({DEUDA},0),2)   AS deuda,
               ROUND(COALESCE({VENCIDO},0),2) AS vencido
        FROM clientes c
        JOIN cuenta_corriente cc ON cc.id_cliente = c.id
        WHERE {' AND '.join(where)}
        GROUP BY c.id
        HAVING ROUND(COALESCE({campo},0),2) > ?
        ORDER BY ROUND(COALESCE({campo},0),2) DESC
        LIMIT ?""", params)
    return jstr({"clientes": len(filas), "ranking": filas})


@beta_tool
def comprobantes_cliente(id_cliente: int, tipo: str = "", solo_pendientes: bool = True,
                         desde: str = "", hasta: str = "", limite: int = 30) -> str:
    """Comprobantes de un cliente: facturas, recibos, notas de crédito y débito.

    Args:
        id_cliente: Número de cliente.
        tipo: FC factura, REC recibo, OP orden de pago, NC nota de crédito,
            ND nota de débito. Vacío = todos.
        solo_pendientes: Si es True, solo los que tienen saldo sin compensar.
        desde: Fecha de emisión desde, formato AAAA-MM-DD.
        hasta: Fecha de emisión hasta, formato AAAA-MM-DD.
        limite: Cuántos comprobantes devolver.
    """
    limite = max(1, min(int(limite), MAX_FILAS))
    where, params = ["id_cliente = ?"], [id_cliente]
    if tipo:
        where.append("tipo = ?"); params.append(tipo.upper().strip())
    if solo_pendientes:
        where.append("monto_pendiente <> 0")
    if desde:
        where.append("fecha_emision >= ?"); params.append(desde)
    if hasta:
        where.append("fecha_emision <= ?"); params.append(hasta)
    params.append(limite)
    filas = consultar(f"""
        SELECT nro, tipo, estado, fecha_emision, fecha_vencimiento, concepto,
               ROUND(monto,2) AS monto, ROUND(monto_pendiente,2) AS pendiente,
               vencido, empresa
        FROM cuenta_corriente
        WHERE {' AND '.join(where)}
        ORDER BY fecha_emision DESC
        LIMIT ?""", params)
    return jstr({"comprobantes": len(filas), "detalle": filas})


@beta_tool
def resumen_general(empresa: str = "") -> str:
    """Totales de toda la cartera: deuda, vencido, cantidad de clientes y período cargado.

    Args:
        empresa: 'Expreso Catamarca SRL' o 'Diemar'. Vacío = las dos juntas.
    """
    where, params = ["1=1"], []
    if empresa:
        where.append("cc.empresa LIKE ?"); params.append(f"%{empresa}%")
    w = " AND ".join(where)
    tot = consultar(f"""
        SELECT ROUND(COALESCE({DEUDA},0),2)   AS deuda_total,
               ROUND(COALESCE({VENCIDO},0),2) AS vencido_total,
               ROUND(COALESCE({A_FAVOR},0),2) AS a_favor_total,
               COUNT(*) AS movimientos,
               COUNT(DISTINCT cc.id_cliente) AS clientes_con_movimientos,
               MIN(cc.fecha_emision) AS desde, MAX(cc.fecha_emision) AS hasta
        FROM cuenta_corriente cc WHERE {w}""", params)[0]
    deudores = consultar(f"""
        SELECT COUNT(*) AS n FROM (
          SELECT cc.id_cliente FROM cuenta_corriente cc WHERE {w}
          GROUP BY cc.id_cliente HAVING {DEUDA} > 0)""", params)[0]["n"]
    por_empresa = consultar(f"""
        SELECT cc.empresa, COUNT(*) AS movimientos,
               ROUND(COALESCE({DEUDA},0),2) AS deuda
        FROM cuenta_corriente cc GROUP BY cc.empresa""")
    tot["clientes_que_deben"] = deudores
    tot["clientes_en_maestro"] = consultar("SELECT COUNT(*) n FROM clientes")[0]["n"]
    tot["por_empresa"] = por_empresa

    # El reporte trae alguna fecha suelta cargada mal (por ejemplo una nota de
    # credito con anio 2027). Tomar el MAX a secas haria decir que hay datos
    # hasta 2027. "hasta" es el ultimo mes con volumen real; "hasta_absoluto"
    # queda por si alguien pregunta por el maximo crudo.
    meses = consultar(f"""
        SELECT substr(cc.fecha_emision,1,7) AS mes, COUNT(*) AS n
        FROM cuenta_corriente cc
        WHERE {w} AND cc.fecha_emision IS NOT NULL
        GROUP BY mes ORDER BY mes""", params)
    tot["hasta_absoluto"] = tot["hasta"]
    if meses:
        piso = max(m["n"] for m in meses) * 0.05
        reales = [m["mes"] for m in meses if m["n"] >= piso]
        if reales:
            tot["desde"], ultimo = reales[0] + "-01", reales[-1]
            tot["hasta"] = consultar(f"""
                SELECT MAX(cc.fecha_emision) AS f FROM cuenta_corriente cc
                WHERE {w} AND substr(cc.fecha_emision,1,7) = ?""", params + [ultimo])[0]["f"]
            tot["meses_cargados"] = len(reales)
    return jstr(tot)


PROHIBIDO = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|PRAGMA|VACUUM)\b", re.I)


@beta_tool
def consultar_sql(sql: str) -> str:
    """Corre un SELECT contra la base para preguntas que las otras herramientas no cubren.

    Tablas y columnas:
      clientes(id, razon_social, alias, nif, telefono, email, provincia, localidad,
               direccion, codigo_postal, tarifario, condicion_pago, sucursal,
               limite_credito, contacto_cobro, contacto_cobro_email,
               contacto_cobro_telefono, condicion_iva, vto_poliza, monto_poliza)
      cuenta_corriente(id_cliente, nif, estado, empresa, nro, tipo, fecha_emision,
               fecha_vencimiento, concepto, monto, neto, iva, monto_pendiente, vencido)

    Las fechas son texto AAAA-MM-DD, así que se comparan y ordenan directo.
    tipo: FC, REC, OP, NC, ND. vencido: 1 o 0. Solo lectura: un INSERT o un
    UPDATE es rechazado.

    Args:
        sql: La consulta SELECT. Ponele siempre un LIMIT.
    """
    limpio = sql.strip().rstrip(";")
    if not re.match(r"^\s*(SELECT|WITH)\b", limpio, re.I):
        return jstr({"error": "Solo se aceptan consultas SELECT."})
    if PROHIBIDO.search(limpio):
        return jstr({"error": "La consulta tiene una palabra que modifica datos."})
    if ";" in limpio:
        return jstr({"error": "Mandá una sola consulta."})
    if not re.search(r"\bLIMIT\b", limpio, re.I):
        limpio += f" LIMIT {MAX_FILAS}"
    cx = conectar()
    try:
        # Corta sola si una consulta se va de mano, en vez de colgar el chat.
        pasos = [0]
        def freno():
            pasos[0] += 1
            return 1 if pasos[0] > 400_000 else 0
        cx.set_progress_handler(freno, 1000)
        filas = [dict(r) for r in cx.execute(limpio).fetchall()][:MAX_FILAS]
        return jstr({"filas": len(filas), "datos": filas})
    except sqlite3.OperationalError as e:
        return jstr({"error": f"La consulta falló: {e}"})
    finally:
        cx.close()


HERRAMIENTAS = [buscar_cliente, resumen_cliente, ranking_deudores,
                comprobantes_cliente, resumen_general, consultar_sql]

NOMBRES = {
    "buscar_cliente": "buscando el cliente",
    "resumen_cliente": "leyendo la ficha del cliente",
    "ranking_deudores": "armando el ranking de deuda",
    "comprobantes_cliente": "revisando los comprobantes",
    "resumen_general": "sumando la cartera",
    "consultar_sql": "consultando la base",
}


# =====================================================================
# INSTRUCCIONES DEL ASISTENTE
# =====================================================================
def instrucciones():
    """El prompt se arma con datos reales de la base para que el asistente
    sepa de entrada qué período tiene cargado y de cuándo son los datos."""
    d = json.loads(resumen_general())
    return f"""Sos el asistente interno de Expreso Diemar / Expreso Catamarca.
Contestás preguntas sobre clientes y cuenta corriente a la gente de
administración, cobranzas y comercial. Hablás en castellano rioplatense,
directo y sin vueltas, como un compañero de oficina que conoce los números.

QUÉ TENÉS
Una copia de dos reportes del sistema, cargada en una base que consultás con
las herramientas. Cubre movimientos entre {d['desde']} y {d['hasta']}:
{d['movimientos']:,} comprobantes de {d['clientes_con_movimientos']:,} clientes,
sobre un maestro de {d['clientes_en_maestro']:,}.

CÓMO SE MIDE LA DEUDA
- deuda: saldo pendiente de facturas (FC) y notas de débito (ND).
- vencido: la parte de esa deuda cuya fecha de vencimiento ya pasó.
- a_favor: recibos (REC) y órdenes de pago (OP) todavía sin aplicar.
No sumes el "monto pendiente" de todos los tipos juntos: los pagos vienen en
negativo y el total daría negativo, que no es la deuda de nadie.

CÓMO TRABAJÁS
- Antes de dar un saldo, buscá el cliente. Hay razones sociales duplicadas y
  registros marcados "NO USAR": si hay más de un candidato razonable,
  mostrale las opciones al usuario en vez de elegir vos.
- Los montos son pesos argentinos. Escribilos como $1.234.567, sin decimales
  salvo que hagan falta.
- Cuando listes varios clientes, usá una tabla en markdown.
- Si un cliente pasó su límite de crédito, decilo aunque no te lo pregunten.
- No inventes: si un dato no está en la base, decí que no está. Si una
  pregunta necesita algo que no tenés (cobranzas de hoy, remitos, viajes),
  decí qué reporte haría falta.
- Nombrá el número de cliente cuando des un saldo, así lo pueden buscar en
  el sistema.

LÍMITE IMPORTANTE
Los datos son una foto del momento en que se corrió la ingesta, no están en
vivo. Si te preguntan por algo de hoy o de esta semana, aclarales hasta qué
fecha llega lo que tenés cargado."""


def responder(mensajes, emitir):
    """Corre el loop de herramientas y va avisando qué está haciendo.

    emitir(tipo, dato) manda un evento al navegador: 'herramienta' mientras
    consulta y 'texto' con la respuesta final.
    """
    cliente = anthropic.Anthropic()
    runner = cliente.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=8000,
        system=instrucciones(),
        thinking={"type": "adaptive"},
        tools=HERRAMIENTAS,
        messages=mensajes,
    )

    respuesta = []
    for mensaje in runner:
        for bloque in mensaje.content:
            if bloque.type == "tool_use":
                emitir("herramienta", NOMBRES.get(bloque.name, bloque.name))
            elif bloque.type == "text" and bloque.text.strip():
                respuesta.append(bloque.text)
        # El último mensaje sin tool_use es la respuesta; los anteriores son
        # comentarios del modelo mientras consulta, que no queremos duplicar.
        if mensaje.stop_reason != "tool_use":
            return respuesta[-1] if respuesta else "No pude armar una respuesta."
    return respuesta[-1] if respuesta else "No pude armar una respuesta."


# =====================================================================
# SERVIDOR HTTP
# =====================================================================
class Handler(BaseHTTPRequestHandler):
    server_version = "ChatDiemar/1.0"

    def log_message(self, formato, *args):
        sys.stderr.write("  %s\n" % (formato % args))

    def _cabeceras(self, tipo, largo=None):
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        if largo is not None:
            self.send_header("Content-Length", str(largo))
        # Sin caché: los datos cambian con cada ingesta.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        ruta = self.path.split("?")[0]
        if ruta in ("/", "/index.html", "/chat.html"):
            archivo = os.path.join(AQUI, "chat.html")
            if not os.path.exists(archivo):
                self.send_error(404, "Falta chat.html")
                return
            cuerpo = open(archivo, "rb").read()
            self._cabeceras("text/html; charset=utf-8", len(cuerpo))
            self.wfile.write(cuerpo)
        elif ruta == "/logo.png":
            archivo = os.path.join(AQUI, os.pardir, "logo_diemar4.png")
            if not os.path.exists(archivo):
                self.send_error(404)
                return
            cuerpo = open(archivo, "rb").read()
            self._cabeceras("image/png", len(cuerpo))
            self.wfile.write(cuerpo)
        elif ruta == "/api/estado":
            try:
                cuerpo = resumen_general().encode()
            except Exception as e:
                cuerpo = jstr({"error": str(e)}).encode()
            self._cabeceras("application/json; charset=utf-8", len(cuerpo))
            self.wfile.write(cuerpo)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.split("?")[0] != "/api/chat":
            self.send_error(404)
            return
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            datos = json.loads(self.rfile.read(largo) or b"{}")
            mensajes = datos.get("mensajes") or []
            if not mensajes:
                raise ValueError("No llegó ningún mensaje.")
        except Exception as e:
            self.send_error(400, str(e))
            return

        # Server-Sent Events: el navegador ve el progreso en vez de esperar
        # callado a que el modelo termine de consultar.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def emitir(tipo, dato):
            try:
                self.wfile.write(f"data: {jstr({'tipo': tipo, 'dato': dato})}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        try:
            emitir("texto", responder(mensajes, emitir))
        except anthropic.APIStatusError as e:
            emitir("error", f"La API respondió {e.status_code}. Revisá la clave o el saldo de la cuenta.")
        except anthropic.APIConnectionError:
            emitir("error", "No se pudo conectar con la API. Revisá la salida a internet del servidor.")
        except Exception as e:
            traceback.print_exc()
            emitir("error", f"Error inesperado: {e}")
        emitir("fin", "")


def main():
    ap = argparse.ArgumentParser(description="Chat interno sobre clientes y cuenta corriente")
    ap.add_argument("--host", default="127.0.0.1",
                    help="127.0.0.1 = solo esta máquina; 0.0.0.0 = toda la red interna")
    ap.add_argument("--puerto", type=int, default=8000)
    ap.add_argument("--sin-navegador", action="store_true",
                    help="No abrir el navegador. Usalo cuando corre como servicio.")
    a = ap.parse_args()

    if not os.path.exists(DB):
        raise SystemExit(f"Falta {DB}. Corré primero: python3 ingesta.py")
    # La clave puede venir del entorno o de chat/clave.txt. El archivo existe
    # para poder arrancar con doble clic, donde no hay variables de entorno.
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        archivo_clave = os.path.join(AQUI, "clave.txt")
        if os.path.exists(archivo_clave):
            clave = open(archivo_clave, encoding="utf-8").read().strip()
            if clave:
                os.environ["ANTHROPIC_API_KEY"] = clave
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit(
            "Falta la clave de la API.\n"
            "  Opcion 1: export ANTHROPIC_API_KEY=sk-ant-...\n"
            f"  Opcion 2: guardala en {os.path.join(AQUI, 'clave.txt')}")

    d = json.loads(resumen_general())
    print(f"Base: {d['movimientos']:,} movimientos · {d['clientes_en_maestro']:,} clientes "
          f"· datos hasta {d['hasta']}")
    print(f"Chat en http://{a.host}:{a.puerto}")
    if a.host == "0.0.0.0":
        print("  OJO: escuchando en toda la red. No lo expongas a internet sin login.")
    print("  Para cortarlo: Ctrl+C")

    servidor = ThreadingHTTPServer((a.host, a.puerto), Handler)
    if not a.sin_navegador:
        import threading, webbrowser
        destino = f"http://{'127.0.0.1' if a.host == '0.0.0.0' else a.host}:{a.puerto}"
        threading.Timer(1.0, lambda: webbrowser.open(destino)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nChat cerrado.")


if __name__ == "__main__":
    main()
