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

Los tableros la piden a `/api/flota`; si la base no contesta, vuelven a leer
la planilla, que queda como respaldo.

## Planillas de origen

El panel y el control de flota leen en vivo las dos planillas de Google, y la
portada lee de COMBUSTIBLE el consumo del mes:

- **Services** `10xcMyBI6T4fxLidVu0strLV_tqrKrHJsdPi0y2SP0cU`
  - `gid=743729287` maestro de unidades · `gid=0` services larga distancia
  - `gid=1026354276` services de toda la flota · `gid=1669414303` prefiltros
- **Combustible** `1u7cckay0IJ60bfoKk2OZo-TjCvTbH9O1wKxNFdSKDCQ`
  - `gid=0` consumo larga distancia · `gid=1044040871` consumo de toda la flota
  - `gid=882343299` % ralentí y kg de CO2

Se leen por CSV público (`gviz`), así que **cada planilla tiene que estar
compartida como "cualquier persona con el enlace puede ver"**. Si no, la pantalla
muestra "Sin acceso a las planillas" en lugar de datos.

Los ID y los gid están al principio del `<script>` de cada archivo, en `CFG`.

La portada muestra los **kilómetros** desde la base (tabla `odometros`, ver
`gomeria/ODOMETROS.md`) y el **consumo en L/100 km** desde la planilla, porque
los litros nunca entraron a Supabase. Si la planilla deja de estar compartida,
la tarjeta de consumo simplemente no aparece y el resto de la portada sigue
andando.

## Stock de repuestos: dónde se guardan los datos

`stock_repuestos.html` funciona de dos maneras según dónde esté publicado:

- **Dentro de Apps Script** (como estaba): guarda en la planilla mediante
  `google.script.run`, todos ven lo mismo y la carga de remitos por foto anda.
- **Como archivo estático** (como está acá): guarda en el `localStorage` del
  navegador. Anda igual, pero **los datos quedan en esa computadora**: no se
  comparten entre usuarios ni entre dispositivos. La carga de remitos por foto
  no funciona, porque la clave de la API vivía del lado de Apps Script.

Para que el stock vuelva a ser compartido hay que dejar el Apps Script publicado
como aplicación web y que la página le pegue por `fetch`, igual que hace
`control_flota.html` con `CFG.webapp`.

## Registrar services desde el tablero

El botón "Registrar service" de `control_flota.html` escribe en la planilla a
través de la aplicación web de Apps Script configurada en `CFG.webapp`. Si esa
URL deja de existir, el botón no aparece y el tablero queda de sólo lectura.
