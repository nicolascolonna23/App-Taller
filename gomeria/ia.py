"""
El cliente de la API de Claude, uno solo para toda la app.

Antes cada pedido creaba el suyo y no lo cerraba. Cada cliente trae su
propio juego de conexiones y buffers, y en el servidor se iban acumulando
hasta pasar el límite de memoria: Render reiniciaba el servicio y mientras
tanto se veía un 503. Uno compartido reusa las mismas conexiones.
"""
import threading

import anthropic

_candado = threading.Lock()
_cliente = None
_fabrica = None


def cliente():
    """El cliente compartido. Se crea la primera vez que hace falta."""
    global _cliente, _fabrica
    with _candado:
        # Si cambió la clase (los tests la reemplazan) se arma uno nuevo.
        if _cliente is None or _fabrica is not anthropic.Anthropic:
            _fabrica = anthropic.Anthropic
            _cliente = _fabrica()
        return _cliente
