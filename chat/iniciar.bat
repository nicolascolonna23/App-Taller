@echo off
REM Doble clic en este archivo abre el chat (Windows).
cd /d "%~dp0"
echo Chat interno de consultas
echo.
python -c "import anthropic, openpyxl" 2>NUL
if errorlevel 1 (
  echo Faltan las librerias. Instalando...
  pip install -r requisitos.txt || goto :fin
)
if not exist datos.db (
  echo Todavia no esta armada la base.
  echo Core primero la ingesta:  python ingesta.py --clientes ARCHIVO.xlsx --cuenta-corriente ARCHIVO.xlsx
  goto :fin
)
python servidor.py
:fin
echo.
pause
