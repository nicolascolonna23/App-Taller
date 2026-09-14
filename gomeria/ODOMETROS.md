# Los km del satelital en la base

Todos los días la app entra sola a Hawk, le pide el odómetro de cada móvil
y lo guarda en Supabase. Una fila por unidad y por día, para siempre.

Eso último es el punto. La planilla de services también tiene el
kilometraje, pero **pisa la celda**: guarda el último y pierde el de ayer.
Sin la serie no se puede saber cuántos kilómetros rodó una cubierta, que es
el número del que cuelga todo el módulo de gomería.

## Cómo funciona

| Pieza | Qué hace |
|---|---|
| `gomeria/hawk.py` | entra a Hawk, lee el odómetro de cada móvil |
| `gomeria/subir_odometros.py` | deja esas lecturas en la tabla `odometros` |
| `.github/workflows/odometros.yml` | los corre a los dos, 05:00 ART, todos los días |
| `gomeria/05_odometros.sql` | la tabla y las tres vistas |

Hawk no tiene una API abierta. Hay que loguearse con un navegador de verdad
—por eso el job instala Chrome— y recién con las cookies de esa sesión se le
puede pedir la flota al mismo endpoint que usa su propia página. Eso es lo
que hace `hawk.py`, y es la razón por la que esto corre en GitHub Actions y
no en el server de la app.

**Antes esto llegaba rebotado.** El scraper vivía en el repo ServiceDM,
dejaba un `historico.csv` commiteado y App-Taller se lo bajaba con curl.
Andaba, pero ataba la serie a que el otro repo corriera: ServiceDM está
programado de lunes a viernes, así que sábado y domingo acá no entraba nada.
Y el día que allá cambió el orden de las columnas del CSV, de este lado se
guardaron dos campos en blanco sin que nadie se enterara.

ServiceDM sigue como está: es el que escribe la planilla de services y no
hay que tocarlo. Son dos lecturas distintas del mismo satelital —esta a las
05:00, la de ServiceDM a las 08:00— y si un día se cae una, la otra sigue.

## Lo que hay que tener configurado

En **App-Taller** → Settings → Secrets and variables → Actions:

| Secret | Qué es |
|---|---|
| `HAWK_USER` | el usuario del satelital |
| `HAWK_PASS` | su contraseña |
| `SUPABASE_DB_URL` | la cadena de conexión de Supabase |
| `EMAIL_FROM` | la casilla de Gmail que manda y recibe el aviso |
| `EMAIL_PASSWORD` | una **contraseña de aplicación** de esa cuenta, no la del mail |

La contraseña de aplicación se saca en la cuenta de Google → *Seguridad* →
*Verificación en dos pasos* → *Contraseñas de aplicaciones*. La contraseña
común de Gmail no sirve: Google no deja que un programa entre con ella.

**La de Supabase tiene que ser la de Connection pooling**, no la directa.
Las máquinas de GitHub Actions no tienen IPv6 y la conexión directa de
Supabase sí, así que desde ahí no conecta. Se copia en Supabase →
*Project Settings* → *Database* → *Connection pooling*, y se reconoce porque
el host termina en `pooler.supabase.com`.

Y en Supabase, **SQL Editor**, correr `gomeria/05_odometros.sql`. Se puede
correr las veces que haga falta: no borra datos. Deja armado:

- **`odometros`** — una fila por unidad y por día. Si el job se corre dos
  veces en el día, la segunda pisa a la primera.
- Un disparador que actualiza `unidades.km_actual`, **solo si el número
  sube**. Un odómetro no vuelve para atrás; una lectura mala no puede bajar
  el kilometraje bueno.
- **`v_km_diarios`** — lo que recorrió entre lecturas, con la cantidad de
  días. Normalmente son 24 horas, pero si Hawk o el job fallan la siguiente
  lectura puede abarcar más de un día.
- **`v_km_por_montaje`** — toma la primera lectura desde la fecha de montaje
  y la última hasta el siguiente movimiento en esa posición. La diferencia
  es lo que rodó la cubierta; el gomero no carga kilómetros.
- **`v_odometro_ultimo`** — la última lectura de cada unidad y hace cuántos
  días que no reporta.

## Cómo saber si está entrando

Sin hacer nada: **te llega un mail en cada corrida**, salga bien o salga
mal. El que avisa que salió bien no es de adorno — si un día no llega
ninguno de los dos, es que el job ni arrancó, y eso no se nota de ninguna
otra manera.

Y si querés mirarlo vos, tres lugares del más cómodo al más detallado:

1. **La portada de la app.** La tarjeta *Kilómetros de la flota* dice abajo
   `última lectura 11/09`. Si esa fecha se atrasa más de un día, algo se
   cortó.
2. **La ficha de la unidad.** Las últimas diez lecturas, con fecha y km.
3. **GitHub → Actions → _Odometros a Supabase_.** El resumen de cada corrida
   dice cuántos móviles se leyeron y cuántas lecturas nuevas entraron.

Correr el job de más no rompe nada: la lectura del día se pisa en vez de
duplicarse. Si hace falta a mano, es **Actions** → *Odometros a Supabase* →
**Run workflow**, y ahí se puede filtrar por empresa si se quiere probar con
pocos móviles.

Para cargar un archivo viejo —el `historico.csv` que quedó de la época de
ServiceDM, por ejemplo— sirve todavía:

    python gomeria/subir_odometros.py historico.csv

## Cómo queda el cálculo en la app

Al confirmar un montaje, rotación o desmontaje se guarda su fecha y hora. La
ficha de la cubierta cruza ese intervalo con `odometros`: primera lectura
diaria dentro del intervalo contra la última. Cuando al día siguiente entra
una lectura nueva, el valor se actualiza solo.

Si todavía no hay dos días de lecturas, la app muestra **Esperando lecturas
de Hawk**. Dos movimientos de una misma cubierta en el mismo día pueden dar
0 km porque el satelital aporta un único odómetro diario; para conocer
recorridos dentro del día harían falta lecturas con hora.

## En la portada

El centro operativo muestra arriba de todo los **kilómetros de la flota**,
con el selector *Ayer · 7 días · 30 días*. El número sale de esta misma
tabla: por unidad se toma la última lectura del período menos la primera,
que es más robusto que sumar día contra día —si un equipo no reportó un día,
el tramo se cierra igual con la lectura siguiente en vez de perderse— y se
descartan los retrocesos, que son cambios de módulo GPS y no viajes.

Al lado va la variación contra el período anterior, pero solo cuando el
anterior tiene una cobertura parecida. La serie arranca el 29 de julio, así
que hasta que haya historia suficiente ese porcentaje sería un espejismo y
la portada directamente no lo muestra.

## Lo que no engancha, y está bien

Algunas lecturas no corresponden a ninguna unidad de la flota. Se guardan
igual (la tabla no las rechaza) pero quedan sin `unidad_id`:

- **`PORTATIL0134` y compañía** — equipos portátiles, no son vehículos.
- **`DZM638`, `LCC752`, `LCC754`, `STR530`, `VUX564`** — patentes viejas que
  no están en `unidades`. Si son unidades que siguen andando, hay que darlas
  de alta; si no, se ignoran solas.
- **`AE527AE` / `AF527AE`** — es AE527FA mal escrita. `hawk.py` la corrige,
  así que solo aparece en las filas viejas del histórico.

El satelital devuelve algunas patentes con un `HC` pegado atrás
(`AC538KWHC`). También se saca solo.
