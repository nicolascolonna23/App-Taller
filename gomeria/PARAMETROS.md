# Parámetros, planes y roles

Lo que antes decidía el código y ahora se carga. Sale de
`gomeria/29_parametros.sql` y `gomeria/31_marcas_medidas.sql`, que se pegan
enteros en Supabase → SQL Editor → Run y se pueden correr las veces que
haga falta.

La pantalla `/parametros` está **separada por módulo** —*Flota*,
*Mantenimiento*, *Gomería*, *Combustible*, *Alertas*—, porque el que va a
cargar una marca de cubierta no tiene por qué pasar por los planes de
mantenimiento para llegar.

En cada solapa se ve primero **lo que ya está cargado**, con qué hacer al
lado: *Editar* abre el formulario —que hasta ahí está guardado— y
*Restablecer* devuelve ese parámetro a lo de fábrica. Un parámetro no se
borra: el sistema tiene que saber de dónde salen los kilómetros aunque
nadie lo haya elegido, así que restablecer es lo más parecido a
eliminarlo que puede existir sin dejarlo mudo. La fila dice con qué venía
de fábrica, para que la decisión se tome sabiendo a qué se vuelve.

Los accesos están **arriba, en todas las pantallas**: *Usuarios* y
*Parámetros*, para el que los tenga habilitados. El permiso lo revisa el
servidor en cada pedido; la barra solo esconde lo que no corresponde.

## 1. De dónde salen los kilómetros

En `/parametros`, solapa **Flota**. Dos opciones y nada más:

| | Qué hace |
|---|---|
| **Automático** | Los trae el satelital todas las mañanas. Es lo que conviene donde hay equipo instalado: nadie se olvida y nadie tipea un número de más. |
| **Manual** | Los carga una persona. **El job deja de escribir**: si escribiera, le pisaría el número al que lo cargó a mano. |

El kilometraje es la base de todo lo demás —el próximo service, el
consumo, el desgaste de las cubiertas, el costo por kilómetro—, así que la
pantalla muestra además cuántas lecturas entraron en las últimas 24 horas.
Si el automático quedó colgado, se ve ahí y no tres semanas después.

Cambiarlo es de quien **administra**.

## 2. Los planes de mantenimiento

Solapa **Mantenimiento**. Un plan tiene **clase**, y la clase decide qué
campos tienen sentido:

**Preventivo.** Se agenda: cada tantos kilómetros, **o cada tantos días**
—el aceite se vence aunque el camión no ruede—. Alcanza con uno de los
dos. Sin ninguno no se guarda, porque un preventivo que no sabe cada
cuánto no puede avisar.

**Correctivo.** No se agenda: una rotura no se agenda. Es el **catálogo de
trabajos** con lo que deberían llevar de tiempo y de plata, para poder
comparar contra lo que salieron. Si se le carga un intervalo, se limpia:
es señal de que se eligió mal la clase.

A una unidad se le asigna un **preventivo**, que es el que reclama
service. Asignarle un correctivo no se puede: no es una agenda.

Tocar los planes es de quien **gestiona** —el responsable de taller—, no
del dueño del sistema.

## 3. Los umbrales de aviso

Solapa **Alertas**: los mismos números que ya usaba ese módulo. A cuántos
kilómetros del service empieza a avisar, cuándo se pone urgente, y qué
carga de combustible es demasiado grande. Subirlos hace que avise antes;
bajarlos, que avise menos. Un aviso que llega tarde no sirve, y uno que
llega siempre deja de mirarse.

## 4. Los roles con los que se trabaja

`29_parametros.sql` agrega tres roles y ajusta uno. Todos se editan desde
`/usuarios`; ninguno se borra, porque hay gente colgando.

| Rol | Nivel | Qué abre |
|---|---|---|
| **Responsable de taller** | gestiona y repara | Todo el taller, más los planes. Aprueba solicitudes, abre y cierra órdenes. |
| **Mecánico** | repara | Carga en la orden lo que hizo y los repuestos que puso. **No aprueba ni cierra.** |
| **Responsable de sucursal** | solo su sucursal | Pide órdenes de trabajo y ve los services y las alertas **de su boca**. |
| **Chofer** | solo su sucursal | Ve su unidad: lo que vence, lo que le toca y lo que se le hizo. |

Los permisos de nivel son cuatro, y no son módulos porque atraviesan todo:

- **repara** — carga trabajos y repuestos en una orden abierta. El que
  gestiona repara también: el que cierra una orden puede cargarle un
  renglón.
- **gestiona** — aprueba, cierra y corrige.
- **administra** — usuarios, roles, parámetros, borrar y reabrir.
- **solo su sucursal** — las unidades y las alertas de su boca, no las de
  toda la red. Lo que no es suyo le ensucia la pantalla donde busca lo
  propio. Sin sucursal asignada no recorta nada: antes que dejar a alguien
  mirando una pantalla vacía sin entender por qué, se le muestra todo.

## 5. El usuario maestro

Uno, el dueño del sistema. **No se le da de baja ni se le cambia el rol
desde la pantalla**, ni él mismo, y administra siempre aunque alguien le
toque los permisos a su rol. Es el seguro contra quedarse afuera del
propio sistema, que es lo único que después no se arregla desde ninguna
pantalla.

El script lo pone en el primer administrador activo. Para moverlo:

```sql
update usuarios set es_maestro = false;
update usuarios set es_maestro = true where usuario = 'elquesea';
```

## 6. Tractor y semi

En Flota, solapa **Tractor y semi**. Un semi no tiene satelital: no tiene
motor, no reporta, y sin embargo sus cubiertas se gastan, sus frenos se
ajustan y sus papeles vencen. Hasta acá el sistema sabía de él lo que
decía una columna de texto en el tractor, que solo puede decir el de hoy y
borra el de ayer.

Ahora el enganche es una fila con fechas, y de eso salen dos cosas:

- **El historial**: qué semi llevó cada tractor y cuándo.
- **Los kilómetros del semi**: los que hizo el tractor mientras lo llevaba
  puesto. Se escriben en `odometros` con fuente `enganche`, así el semi
  entra en services, en cubiertas y en alertas como cualquier otra unidad,
  sin que ningún módulo tenga que enterarse de nada.

Detalles que importan:

- **El día del enganche no cuenta.** El recorrido de una fecha es el tramo
  entre la lectura anterior y esa fecha, y ese tramo lo hizo el tractor
  solo, o con otro semi atrás.
- **Un semi va atrás de un tractor y un tractor lleva un semi**, los dos de
  a uno por vez. Si alguno venía enganchado a otro, ese enganche se cierra
  solo: los kilómetros de esos días tienen que ir a uno solo.
- **La serie se rehace entera**, no se va sumando. Un enganche que se
  corrige o se borra cambia el pasado, y una serie acumulada a mano
  quedaría diciendo kilómetros que el semi no hizo.
- El punto de partida es el kilometraje que el semi ya tuviera cargado,
  así el número no arranca de cero cuando tiene medio millón encima.

## 7. Gomería: marcas y medidas

Solapa **Gomería**. Sale de `gomeria/31_marcas_medidas.sql`.

Hasta acá la marca de una cubierta era un texto que cada uno escribía como
quería —*FATE*, *Fate*, *fate*— y el logo era un archivo que había que
dejar en la carpeta `marcas/` del repositorio: sumar una marca era hacer
un deploy.

**Las marcas** ahora son filas, con su logo subido desde la pantalla. El
logo se guarda **en la base y no en el disco**, porque el disco de Render
se borra en cada publicación: un archivo subido a mano duraría hasta el
próximo deploy. PNG, JPG, WEBP, GIF o SVG, hasta 300 KB —más que eso es
una foto subida por error—.

- El nombre se junta por lo que es: *FATE*, *Fate* y *F.A.T.E.* son una
  sola marca. De ahí sale también el nombre con el que se sirve el logo
  (`/marcas/fate.png`).
- **Guardar el nombre no borra el logo.** Solo lo pisa una imagen nueva, y
  hay un botón aparte para sacarlo.
- La marca con cubiertas cargadas **se da de baja, no se borra**: deja de
  ofrecerse al cargar una cubierta, y las fichas que ya la nombran siguen
  diciendo lo mismo. Borrarla dejaría fichas nombrando algo que no existe.
- Sin logo cargado se sigue mostrando el nombre en texto. Que falte no
  rompe nada.

**Las medidas** son con cuáles se trabaja y de qué familia es cada una. Lo
que identifica es el **primer número** —una 295/80R22.5 es una **295**—,
porque el perfil y la llanta cambian de una marca a otra y no hacen a la
cuestión de si la goma entra o no en esa unidad.

La familia es la que **corta el movimiento**: montar una 700x12 en un
camión se rechaza en el momento, no después, cuando ya quedó anotado y hay
que rastrearlo. Eso el sistema ya lo hacía, pero con la regla escrita en
el código: sumar una medida era tocar un archivo. Ahora sale de esta
tabla, y sumar la 315 a los camiones es cargarla y elegirle la familia.
Darla de baja la saca de la regla.

Dos recaudos, porque una regla que se puede vaciar no es una regla:

- Sin el script corrido, o sin ninguna medida con familia cargada, rige la
  regla de siempre —295 en camiones, 600x9 y 700x12 en autoelevadores—.
- La clase que nadie cargó conserva la suya. Cargar solo las de camión no
  deja al autoelevador aceptando cualquier cosa.

Arranca con la 295 de los camiones y las dos de los autoelevadores, más
las que ya estuvieran cargadas en las cubiertas, que entran como *otro* y
se corrigen desde la pantalla.

Tocar las marcas y las medidas es de quien **gestiona**. Verlas, de
cualquiera: las pantallas de gomería las leen para sus desplegables.

**En la mesa de montaje**, el inspector de la derecha muestra el **logo**
en lugar del nombre, y la goma **rueda**: los tacos corren por la banda y
las tuercas giran con la llanta. Quien pidió menos movimiento en su
sistema no ve ninguno.

## 8. Combustible: cómo entra, proveedores y fluidos

Solapa **Combustible**. Sale de `gomeria/32_fluidos.sql` y
`gomeria/33_combustible_origen.sql`.

**Cómo entra el combustible.** Dos maneras, como con el kilometraje:

| | Qué hace |
|---|---|
| **Manual** | Se anota carga por carga, o se sube el archivo cuando la estación manda el listado. Es como venía funcionando. |
| **Automático** | El sistema entra solo a un **link** —una hoja de Google, o cualquier dirección que devuelva un CSV— y trae lo que haya, todas las mañanas. |

El link se pega tal como está en la barra de direcciones: el sistema lo
convierte solo a la dirección de exportación. La hoja tiene que estar
compartida como «cualquiera con el enlace»; si no, Google devuelve la
pantalla de login y el sistema lo dice con todas las letras en vez de
decir que la planilla no tiene remitos.

**Traer de nuevo la misma planilla no duplica nada**: cada remito se pisa
con su última versión, que es lo que ya hacía subir el archivo a mano. Por
eso se puede traer todos los días sin pensar, y por eso hay un botón
*Traer la planilla ahora* al lado del parámetro: sirve para probar el link
recién cargado y para cuando alguien corrigió la planilla y no quiere
esperar a mañana.

La corrida de todos los días la agenda GitHub Actions
(`.github/workflows/combustible.yml`, que llama a
`gomeria/traer_combustible.py`). La hora que se elige en la pantalla es
informativa: si se cambia, hay que cambiar el cron. Cómo salió la última
vez queda a la vista —un link que dejó de andar se ve ahí y no seis
semanas después, cuando alguien busque una carga y no esté—.

El link lo revisa el servidor antes de guardarlo: tiene que ser `https` y
no puede apuntar a la red interna. El que sale a buscar es el servidor, y
una dirección interna lo convertiría en la puerta de entrada a lo que él
ve y nadie más.

**Los proveedores.** A quién se le compra. Hasta acá el proveedor era un
texto que cada uno escribía como quería en cada carga —«YPF», «ypf»,
«Y.P.F.»—, así que no se podía sumar lo que se le compró a nadie. Ahora
son filas con su CUIT, su contacto y **qué rubros provee** —combustible,
urea, aceites, grasa, repuestos—: el rubro es para ofrecer solo los que
corresponden, porque al que trae gasoil no tiene sentido ofrecerlo para la
grasa. Al que ya se le compró **se lo da de baja, no se lo borra**.

**Los fluidos.** Qué se guarda en el depósito y **en qué viene**. La
capacidad es la de **un** envase —un bin de 1.000, un tambor de 205, un
balde de 20—, y es lo que se dibuja lleno en la pantalla: con 1.700 litros
hay un tambor abierto y siete sellados al lado. El mínimo es cuándo
empieza a avisar; sin cargarlo, avisa al 20% de un envase.

- Se mide en **litros o en kilos**: la grasa se compra por kilo.
- El envase es bin, tambor, tacho, balde o tanque. No es decoración: es lo
  que se dibuja y cómo lo mira el que va al depósito.
- El fluido con movimientos se da de baja, no se borra: borrarlo dejaría
  los movimientos sin decir de qué eran.

Arranca con los seis del taller —urea, aceite 15W40, aceite 20W50,
refrigerante concentrado, líquido hidráulico y grasa— y se agregan los que
hagan falta. El detalle de cómo se cargan y se despachan está en
[la guía de fluidos](FLUIDOS.md).

Tocar los proveedores y los fluidos es de quien **gestiona**.
