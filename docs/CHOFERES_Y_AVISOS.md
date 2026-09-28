# Vencimientos y reportes de choferes

Cambios para `claude/serene-planck-kf271l`, PR #69.

## Puesta en marcha

1. Respaldar la base y ejecutar `gomeria/30_avisos_y_reportes.sql` después de las migraciones 06, 15, 21, 26 y 27. Conserva los datos existentes; recrea las vistas de vencimientos dentro de una transacción. No ejecutar de nuevo 06 después de 30 porque restablecería las vistas anteriores.
2. Desplegar el código Python y los archivos de `choferes/` y reiniciar el servidor.
3. En Usuarios y roles, habilitar **Reportar fallas** para los roles que deban cargar. La migración habilita el rol de sistema `chofer` si existe. Asignar sucursal al usuario; debe coincidir con `unidades.sucursal`. Sin sucursal el chofer no recibe un catálogo de unidades.
4. Para decidir sobre fallas, otorgar **Solicitudes** y nivel **gestiona**. Para crear una OT también hace falta **Órdenes**. La consulta de un chofer se limita a sus propios reportes; la del gestor respeta la restricción de sucursal del rol.
5. En el teléfono, abrir `/choferes/` con HTTPS e iniciar sesión al menos una vez con conexión. Esperar que carguen cuenta y unidades. Agregar a la pantalla de inicio desde el navegador. El enlace está en `/movil`; el nuevo módulo también figura en el catálogo de permisos.
6. Abrir **Solicitudes → Fallas de choferes** (`/fallas`) en el taller.

## Vencimientos

En `/vencimientos`, **Configurar vigencia y avisos** permite configurar por tipo:

- Meses de vigencia (1–120), o vacío para ingreso manual.
- Anticipación del aviso (0–3650 días).

En una carga o renovación, la fecha explícita de vencimiento prevalece sobre el cálculo desde la emisión. El cálculo respeta fines de mes y años bisiestos. **Avisar desde** permite una fecha particular; vacío usa la anticipación del tipo. Se rechaza un aviso posterior al vencimiento o emisión posterior al vencimiento. La tabla muestra la fecha de aviso efectiva.

Cambiar la vigencia no modifica fechas ya registradas. Cambiar la anticipación actualiza la clasificación de registros sin aviso propio. Las alertas que leen las vistas usan la misma regla. Estos son avisos dentro del sistema: no se agregó correo ni push.

## Falla → solicitud → OT

El reporte conserva UUID, autor, unidad, descripción, urgencia, fecha del hecho, fecha de recepción y hasta tres fotos. Es independiente de la solicitud de compra y de su circuito de aprobación de gastos.

El taller puede desestimar con motivo, o crear una OT interna correctiva informando kilometraje. Se conserva quién resolvió, cuándo y el enlace a la orden. Las fotos permanecen accesibles en la bandeja. La creación y el cambio de estado se confirman en una sola transacción. Si la unidad ya tiene una OT interna abierta, el sistema explica el conflicto; no crea otra ni agrega trabajos a una orden existente automáticamente.

La recepción bloquea el UUID durante la transacción: si se perdió la respuesta después de guardar, el reintento devuelve el mismo reporte. La decisión bloquea el reporte; los reintentos de creación devuelven la OT existente. Las altas de OT comparten un bloqueo por patente para evitar aperturas concurrentes.

## Funcionamiento sin conexión

IndexedDB conserva reportes y fotos antes de intentar enviarlos. Se reintenta al recuperar señal, abrir o volver a la app, cada 30 segundos mientras esté visible, y con el botón de reintento. Background Sync complementa esto en navegadores compatibles. Un reporte sólo pasa a enviado tras recibir la confirmación del servidor con su UUID. Después se quitan las copias locales de las fotos; quedan guardadas en el servidor.

Los pendientes están asociados a la cuenta original y nunca se envían bajo otra cuenta. Una sesión vencida exige volver a iniciarla. El shell offline no contiene datos de sesión y el service worker sólo guarda recursos estáticos de `/choferes/`; no cachea APIs, login ni pantallas administrativas. El dispositivo conserva el último catálogo para cargar sin señal. Los dispositivos compartidos deben tratarse como almacenamiento local de trabajo: esta versión no cifra IndexedDB y borrar los datos del navegador elimina pendientes no enviados.

Las fotos se reducen a JPEG de hasta 1600 píxeles; el servidor admite como máximo 3 fotos de 2 MB. Se validan tamaño y firma del formato. El formulario conserva texto y adjuntos si falla la escritura local.

## Voz y tiendas

Esta entrega es una PWA, no un binario publicado en Google Play o App Store. El botón de dictado usa el reconocimiento disponible en el navegador; si no está disponible indica usar el micrófono del teclado. No se garantiza dictado sin conexión. La disponibilidad de reconocimiento local depende del navegador, del sistema y de los paquetes de idioma instalados ([MDN: reconocimiento de voz](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)).

El envío con la app cerrada depende del soporte y de las decisiones del sistema operativo. La alternativa es abrir la app con conexión; no se promete un servicio permanente en segundo plano ([MDN: sincronización en segundo plano](https://developer.mozilla.org/en-US/docs/Web/API/Background_Synchronization_API)).

Para las tiendas queda una etapa específica: cliente móvil empaquetado/nativo, identidad de aplicación y firma con las cuentas del titular, permisos de cámara/micrófono, política de privacidad y retención, pruebas en Android/iPhone y revisión de cada tienda. Si el requisito es dictado totalmente offline, seleccionar y probar un motor local como parte de esa etapa.

## Validación

- Resultado local: 227 pruebas aprobadas y 5 omitidas por falta de PostgreSQL de servidor. Pasaron ambas pruebas de navegador y la migración sobre PostgreSQL WASM.
- `node tests/avisos_bandeja_smoke.cjs`: configuración de fechas, motivo obligatorio, desestimación, vínculo a OT y pantallas de escritorio/teléfono.
- `python3 -m unittest discover -s tests -p 'test_*.py'`: incluye permisos, fechas, reintentos, validación de fotos y decisiones.
- `node tests/choferes_offline.cjs` con Playwright y Chrome: servidor local simulado, service worker real, recarga offline, foto persistida, cambio de cuenta, error de subida y reintento confirmado, viewport móvil.
- `PGLITE_MODULE=/ruta/a/@electric-sql/pglite node tests/reportes_migracion.cjs`: migración repetida sobre PostgreSQL WASM y validación de estados/constraints. No sustituye un ensayo de concurrencia con PostgreSQL de servidor.

No se aplicó la migración a producción ni se verificaron cámara y dictado en teléfonos físicos. Las cinco pruebas de integración PostgreSQL preexistentes requieren `MT_TEST_DATABASE_URL` y se omiten sin ella.
