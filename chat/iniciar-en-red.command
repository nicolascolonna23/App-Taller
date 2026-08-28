#!/bin/bash
# Doble clic acá para que TODA LA OFICINA pueda usar el chat (macOS).
# Esta computadora queda de servidor: mientras esta ventana esté abierta,
# los demás entran desde el navegador con la dirección que aparece abajo.
cd "$(dirname "$0")"
echo "Chat interno — modo red"
echo
python3 -c "import anthropic, openpyxl" 2>/dev/null || {
  echo "Faltan las librerías. Instalando…"
  pip3 install -r requisitos.txt || { echo; read -n1 -p "Enter para cerrar"; exit 1; }
}
if [ ! -f datos.db ]; then
  echo "Todavía no está armada la base."
  echo "Corré primero:  python3 ingesta.py --clientes ARCHIVO.xlsx --cuenta-corriente ARCHIVO.xlsx"
  echo
  read -n1 -p "Enter para cerrar"; exit 1
fi
python3 servidor.py --host 0.0.0.0
echo
read -n1 -p "Enter para cerrar"
