#!/bin/bash
# Doble clic en este archivo abre el chat (macOS).
cd "$(dirname "$0")"
echo "Chat interno de consultas"
echo
python3 -c "import anthropic, openpyxl" 2>/dev/null || {
  echo "Faltan las librerías. Instalando…"
  pip3 install -r requisitos.txt || { echo; echo "No se pudieron instalar."; read -n1 -p "Enter para cerrar"; exit 1; }
}
if [ ! -f datos.db ]; then
  echo "Todavía no está armada la base."
  echo "Corré primero la ingesta:  python3 ingesta.py --clientes ARCHIVO.xlsx --cuenta-corriente ARCHIVO.xlsx"
  echo
  read -n1 -p "Enter para cerrar"; exit 1
fi
python3 servidor.py
echo
read -n1 -p "Enter para cerrar"
