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

Verificación: `python3 -m unittest discover -s tests -v`. Las pruebas de navegador se ejecutan con Playwright instalado: `node tests/browser_smoke.cjs` (opcionalmente `BROWSER_PATH` indica el ejecutable de Chrome). Ambas pruebas usan datos simulados, no credenciales ni la base de producción.
