# Mesa de montaje de cubiertas

La solapa **Flota y mapas** de Gomería organiza la tarea en tres columnas:

- Izquierda: stock disponible, búsqueda por código/marca/medida y zona de devolución.
- Centro: modelo 3D de la unidad, selección de rueda y mapa completo de posiciones, incluido auxilio.
- Derecha: cubierta seleccionada, marca, medida, remanente y acciones. El dibujo de esta columna es una ilustración del neumático; el modelo interactivo del vehículo permanece en el centro.

La selección de unidad está arriba, en **Elegir unidad**. En pantallas angostas las columnas se apilan y las operaciones siguen disponibles por clic, sin depender de arrastrar.

## Montar

Seleccionar una cubierta del stock, elegir un casillero vacío y pulsar **Montar en posición elegida**. También se puede arrastrar del stock al casillero o directamente sobre una rueda del modelo. Cuando la rueda representa dos cubiertas, el formulario exige elegir la posición interior/exterior. Confirmar registra el montaje con la API existente.

## Retirar

Seleccionar una posición ocupada y pulsar **Retirar cubierta**, o arrastrar su casillero a la zona de devolución del stock. Para arrastrar la rueda desde el propio 3D, activar **Mover cubiertas desde el 3D**; desactivado conserva el giro habitual. En ejes duales, elegir primero el casillero exacto.

El retiro siempre abre un formulario para indicar destino —stock, reparación, recapado o baja definitiva— y motivo obligatorio. Cancelar no modifica nada. Devolver al stock no significa dar de baja definitivamente.

## Integridad

El backend verifica permisos de gestión, pertenencia de la posición a la unidad, medida de la cubierta y disponibilidad. El cliente envía la cubierta que esperaba encontrar; si otro operador cambió la posición, se rechaza el movimiento y se solicita actualizar. La mesa no reemplaza una cubierta ocupada silenciosamente. Los bloqueos de unidad y cubierta serializan las operaciones de esta API. Se utiliza la misma transacción, stock, montajes e historial de movimientos existentes; no se crean tablas adicionales.

El motivo también se exige en el formulario de retiro de **Unidades**, que comparte la API. La búsqueda del stock consulta el servidor, con hasta 200 coincidencias por búsqueda.

## Verificación

- `python3 -m unittest discover -s tests -p 'test_mesa_cubiertas.py'`: motivo, destino, rechazo por posición cambiada, estado no disponible, posición ocupada y rol sin permiso.
- `node tests/gomeria_mesa.cjs` con Playwright y Chrome: carga del OBJ real y WebGL; montaje por clic; arrastres nativos de stock a casillero y al 3D; retiro desde casillero y desde la rueda 3D; elección dual; cancelación; motivo; destino reparación; modo consulta y tamaños 1600/390 px. Las respuestas de la API son simuladas.

No requiere migración. Se publica desplegando los archivos actualizados de la rama. No se realizaron movimientos sobre datos de producción ni una prueba concurrente contra PostgreSQL real.
