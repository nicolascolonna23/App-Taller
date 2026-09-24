# App Taller — Flota Diemar

Tres pantallas HTML estáticas, sin build ni dependencias. Se abren directo desde
GitHub Pages (o desde cualquier servidor de archivos).

| Archivo | Qué es |
|---|---|
| `index.html` | Panel general. Resume services, prefiltros, consumo y emisiones, y lleva a las otras dos pantallas. |
| `control_flota.html` | Control de flota y mantenimiento: services, prefiltros y telemetría por unidad. |
| `stock_repuestos.html` | Stock de repuestos: artículos, movimientos y carga de remitos. |

## De dónde sale cada dato

La información de las unidades —marca, modelo, chasis, chofer, semi,
residencia y uso— vive en Supabase, en la tabla `unidades`, y se edita desde
la pantalla `/unidades`. Ver `gomeria/UNIDADES.md`.

Los tableros la piden a `/api/flota`.

## De dónde salen los datos

De Supabase, y de ningún otro lado. Los tableros no leen planillas de Google:
el maestro de unidades sale de `/api/flota`, los services de `/api/services` y
el consumo de `/api/combustible`.

**El consumo se calcula, no se copia.** Los litros cada 100 km salen de cruzar
dos cosas que ya están en la base: los litros que se cargan en el módulo de
Combustible y los kilómetros que cuenta el satelital, en `v_combustible_flota`.
Entran solo las unidades a las que se les conocen los kilómetros de ese mes:
sumar los litros de una patente sin lecturas da un consumo inventado, más alto
cuanto más combustible haya cargado.

Antes esto venía de dos planillas de Google leídas por CSV público. Se sacaron:
eran una segunda versión de la verdad, dejaban de andar cada vez que alguien
tocaba los permisos de un archivo, y los dos ingredientes del consumo ya
estaban en la base. Con las planillas se fueron tres números que no se pueden
calcular con lo que hay: **% de ralentí**, **kg de CO2** y el seguimiento de
**prefiltros**, que venían de la telemetría de la marca. El CO2 vuelve cuando
esté el módulo de emisiones, calculado desde los litros.

**Alertas** junta en una sola pantalla lo que hay que mirar hoy: documentos
vencidos, services pasados de kilómetros, cargas de combustible más grandes
de lo normal y cubiertas en el mínimo de dibujo. Ordenado por urgencia y no
por módulo. Ver `gomeria/ALERTAS.md`.

**Vencimientos vive adentro de Flota**, como su segunda solapa: la unidad y
sus papeles son lo mismo, y el inicio no puede ser una lista de todo. Lo que
sí queda en la portada es el número: cuántos documentos están vencidos.

La portada avisa además cuántas **cubiertas llegaron al mínimo de dibujo**
(ver `gomeria/DESGASTE.md`), que es lo que puede dejar una unidad parada en
la ruta.

La portada muestra los **kilómetros** y el **consumo en L/100 km** desde la
base: los kilómetros de la tabla `odometros` (ver `gomeria/ODOMETROS.md`) y
los litros del módulo de combustible (ver `gomeria/COMBUSTIBLE.md`). Los
litros entraban antes solo a la planilla de Google; desde que se cargan los
tickets en `/combustible`, la portada no depende de ninguna planilla
compartida.

## Stock de repuestos: dónde se guardan los datos

`stock_repuestos.html` funciona de dos maneras según dónde esté publicado:

- **Dentro de Apps Script** (como estaba): guarda en la planilla mediante
  `google.script.run`, todos ven lo mismo y la carga de remitos por foto anda.
- **Como archivo estático** (como está acá): guarda en el `localStorage` del
  navegador. Anda igual, pero **los datos quedan en esa computadora**: no se
  comparten entre usuarios ni entre dispositivos. La carga de remitos por foto
  no funciona, porque la clave de la API vivía del lado de Apps Script.

Para que el stock vuelva a ser compartido hay que llevarlo a Supabase, como el
resto de los módulos.

## Registrar services desde el tablero

El botón "Registrar service" de `control_flota.html` guarda en Supabase por
`/api/alertas`, y la fila aparece en el tablero sin esperar al refresco.

## Asistente interno y combustible

El asistente de consultas está en `/asistente`, detrás del login. Consultá [la guía de configuración y mejora](docs/ASISTENTE.md) para activar la API, entender sus fuentes y ampliar capacidades.

Combustible abre en Tickets (`/combustible#tickets`), con carga individual/importación y tabla filtrable; el cruce está en `#cruce` y los cálculos existentes de consumo en `#resumen`.

## Quién entra y qué abre

Las altas, las bajas, las contraseñas y los roles se manejan en
**`/usuarios`**, con la sesión de alguien que administra. El rol dejó de
ser una constante del código: es una fila que se edita, con **los módulos
que abre** marcados uno por uno.

Vienen cuatro roles hechos —administrador, encargado de taller, operario y
responsable de sucursal— y se pueden crear otros. El de sucursal es el que
faltaba: abre solicitudes y la ficha de sus unidades, y necesita tener su
sucursal asignada, porque la solicitud se numera según quién la pide.

Lo que un rol no tiene marcado **no se abre**, ni escribiendo la dirección
a mano: el permiso lo revisa el servidor en cada pedido y la pantalla solo
esconde el botón. El detalle está en
[la guía de usuarios](gomeria/USUARIOS.md); las tablas salen de
`gomeria/27_roles.sql`. Sin ese script corrido el sistema anda como
siempre: todos abren todo.

## Ingreso seguro

- **Verificación en dos pasos para los que administran.** Además de la
  contraseña piden el código de 6 dígitos de una app autenticadora
  (Google Authenticator, Authy, 1Password). La primera vez que entran, la
  app muestra un QR para darla de alta y 10 códigos de respaldo de un solo
  uso. Si alguien pierde el celular y los códigos, otro administrador le
  hace **Resetear 2FA** desde Usuarios y roles. Si no queda ningún otro
  administrador, se resetea desde el SQL Editor de Supabase (la sentencia
  está en el comentario de `usuarios.totp_secreto`).
- **Freno a la fuerza bruta.** Se cuentan los intentos fallidos en una
  ventana de 15 minutos: 20 por IP, 8 por usuario y 5 códigos de
  verificación. Pasado eso hay que esperar. La IP sale de la cabecera que
  pone Cloudflare en Render (`True-Client-IP`), no de `X-Forwarded-For`,
  que la puede inventar cualquiera. Fuera de Render se indica la cabecera
  del proxy propio con `IP_CABECERA`.

Las tablas salen de `gomeria/28_seguridad.sql`. Sin ese script el sistema
anda como antes (sin segundo factor, con los intentos contados en memoria)
y lo avisa al arrancar. Al correrlo, los administradores tienen que volver
a entrar y dar de alta el autenticador.

## Solicitudes de orden de compra

Una sucursal no manda a hacer un trabajo de taller sin una **solicitud
aprobada**, y no rinde la factura sin el número de solicitud escrito. El
registro nace antes de la reparación, no después: el correctivo que
resolvía una boca dejaba plata anotada y ninguna constancia de la
intervención técnica.

**Lo que manda a hacer mantenimiento queda afuera del circuito**: el área
que decide el gasto es la misma que lo controla. Por eso el servicio
externo pregunta quién lo mandó a hacer, y solo pide la solicitud cuando
fue una sucursal.

El circuito son cuatro pasos —**pedir, aprobar, reparar, rendir**— y vive
en `/solicitudes`. El número lo da el sistema y sale de quién pide:
`CAT-00001`, correlativo por sucursal. Cada cambio de estado deja su
renglón en un historial que no se edita ni se borra.

El detalle —los estados, la lista blanca de lo que no necesita solicitud,
la excepción de ruta y los indicadores— está en
[la guía de solicitudes](gomeria/SOLICITUDES.md). Las tablas salen de
`gomeria/26_solicitudes.sql`.

## Costos del taller en la portada

La portada muestra los KPI de las órdenes de los últimos doce meses: total
gastado por patente y pesos por kilómetro separados en preventivo y
correctivo. La cuenta está en `gomeria/kpi_ordenes.py`, sale de las vistas
que ya existen (`v_ordenes` y `v_km_diarios`) y no pide SQL nuevo. El
detalle de cómo se calcula y qué queda afuera está en
[la guía de órdenes](gomeria/ORDENES.md).

Verificación: `python3 -m unittest discover -s tests -v`. Las pruebas de navegador se ejecutan con Playwright instalado: `node tests/browser_smoke.cjs`, `node tests/costos_smoke.cjs`, `node tests/solicitudes_smoke.cjs` y `node tests/usuarios_smoke.cjs` (opcionalmente `BROWSER_PATH` indica el ejecutable de Chrome). Todas usan datos simulados, no credenciales ni la base de producción.

## Vales auditables (borrador de integración)

La propuesta de vales se revisa en `/vales`, sin reemplazar `/ordenes`, `/control`
ni `/api/mantenimiento`. Ver [diseño y pendientes antes de fusionar](docs/MANTENIMIENTO.md).
No aplicar la migración hasta resolver la unificación con los planes existentes.
