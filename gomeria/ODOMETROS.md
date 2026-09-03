# Los km del satelital en la base

El scraper de Hawk ya existe: vive en el repo **ServiceDM**, corre todos los
días a las 08:00 (workflow `hawk_km.yml`) y escribe el kilometraje de cada
móvil en la planilla de services.

Lo que falta es que esa misma lectura quede también en Supabase. No para
reemplazar la planilla —ahí sigue igual— sino porque la planilla **pisa la
celda**: guarda el último kilometraje y pierde el de ayer. Sin la serie no
se puede saber cuántos kilómetros rodó una cubierta, que es el número del
que cuelga todo el módulo de gomería.

## Qué se agrega

| Dónde | Qué |
|---|---|
| Supabase | tabla `odometros` + 3 vistas (`05_odometros.sql`) |
| App-Taller | el workflow `odometros.yml`, que corre solo |
| App-Taller | el secret `SUPABASE_DB_URL` |

## Paso 1 — la tabla

En Supabase, **SQL Editor**, pegar y correr `gomeria/05_odometros.sql`.
Se puede correr las veces que haga falta: no borra datos.

Deja armado:

- **`odometros`** — una fila por unidad y por día. Si el job se corre dos
  veces en el día, la segunda pisa a la primera.
- Un disparador que actualiza `unidades.km_actual`, **solo si el número
  sube**. Un odómetro no vuelve para atrás; una lectura mala no puede
  bajar el kilometraje bueno.
- **`v_km_diarios`** — lo que recorrió entre lecturas, con la cantidad de
  días. El scraper queda programado los siete días; si Hawk o el job fallan,
  la siguiente lectura puede abarcar más de un día.
- **`v_km_por_montaje`** — toma la primera lectura de Hawk desde la fecha de
  montaje y la última hasta la fecha del siguiente movimiento en esa posición.
  La diferencia es lo que rodó la cubierta; el gomero no carga kilómetros.
- **`v_odometro_ultimo`** — la última lectura de cada unidad y hace
  cuántos días que no reporta.

## Paso 2 — el secret, en GitHub

En **App-Taller**: Settings → Secrets and variables → Actions → New
repository secret.

- Nombre: `SUPABASE_DB_URL`
- Valor: la cadena de conexión de Supabase

**Importante:** tiene que ser la de **Connection pooling**, no la directa.
Las máquinas de GitHub Actions no tienen IPv6 y la conexión directa de
Supabase sí, así que la directa no conecta desde ahí. La del pooler se
copia en Supabase → *Project Settings* → *Database* → *Connection pooling*
y se reconoce porque el host termina en `pooler.supabase.com`.

## Paso 3 — apretar el botón

El workflow `.github/workflows/odometros.yml` hace todo: se baja
`data/historico.csv` del repo ServiceDM y lo pasa a la base.

En App-Taller → pestaña **Actions** → *Odometros a Supabase* → **Run
workflow**. La primera corrida carga las ~1.700 lecturas que hay desde el
29 de julio; después queda programado todos los días a las 09:00 de
Argentina, una hora después del scraper.

No hace falta tocar nada en ServiceDM. El scraper ya deja el histórico
commiteado en el repo en cada corrida, y este workflow lo lee de ahí.

`historico.csv` es acumulativo, así que todos los días se manda entero y
la base se queda solo con lo que no tenía: por eso correrlo de más no
duplica nada, y el resumen del workflow dice cuántas entraron nuevas.

## Cómo queda el cálculo en la app

Al confirmar un montaje, rotación o desmontaje se guarda su fecha y hora. La
ficha de la cubierta cruza ese intervalo con `odometros`: primera lectura
diaria dentro del intervalo contra la última. Cuando al día siguiente entra
una lectura nueva de Hawk, el valor se actualiza solo.

Si todavía no hay dos días de lecturas, la app muestra **Esperando lecturas
de Hawk**. Dos movimientos de una misma cubierta en el mismo día pueden dar
0 km porque Hawk aporta un único odómetro diario; para conocer recorridos
dentro del día harían falta lecturas con hora.

## En la portada

El centro operativo muestra arriba de todo los **kilómetros de la flota**,
con el selector *Ayer · 7 días · 30 días*. El número sale de esta misma
tabla: por unidad se toma la última lectura del período menos la primera,
que es más robusto que sumar día contra día —si un equipo no reportó un
día, el tramo se cierra igual con la lectura siguiente en vez de perderse—
y se descartan los retrocesos, que son cambios de módulo GPS y no viajes.

Al lado va la variación contra el período anterior, pero solo cuando el
anterior tiene una cobertura parecida. La serie arranca el 29 de julio: hoy
los 30 días previos tienen apenas cuatro días cargados, así que ese
porcentaje sería un espejismo y la portada directamente no lo muestra. Se
va a prender solo cuando haya historia suficiente.

## Lo que no engancha, y está bien

Algunas lecturas no corresponden a ninguna unidad de la flota. Se guardan
igual (la tabla no las rechaza) pero quedan sin `unidad_id`:

- **`PORTATIL0134` y compañía** — equipos portátiles, no son vehículos.
- **`DZM638`, `LCC752`, `LCC754`, `STR530`, `VUX564`** — patentes viejas
  que no están en `unidades`. Si son unidades que siguen andando, hay que
  darlas de alta; si no, se ignoran solas.
- **`AE527AE` / `AF527AE`** — es AE527FA mal escrita. El scraper ya la
  corrige, así que solo aparece en las filas viejas del histórico.

El satelital devuelve algunas patentes con un `HC` pegado atrás
(`AC538KWHC`). El script lo saca solo.
