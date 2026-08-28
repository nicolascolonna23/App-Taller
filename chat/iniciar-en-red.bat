@echo off
REM Doble clic aca para que TODA LA OFICINA pueda usar el chat (Windows).
REM Esta computadora queda de servidor: mientras esta ventana este abierta,
REM los demas entran desde el navegador con la direccion que aparece abajo.
cd /d "%~dp0"
echo Chat interno - modo red
echo.
python -c "import anthropic, openpyxl" 2>NUL
if errorlevel 1 (
  echo Faltan las librerias. Instalando...
  pip install -r requisitos.txt || goto :fin
)
if not exist datos.db (
  echo Todavia no esta armada la base.
  echo Core primero:  python ingesta.py --clientes ARCHIVO.xlsx --cuenta-corriente ARCHIVO.xlsx
  goto :fin
)
python servidor.py --host 0.0.0.0
:fin
echo.
pause
