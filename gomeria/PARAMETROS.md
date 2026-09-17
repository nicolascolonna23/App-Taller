# Parámetros, planes y roles

Tres cosas que antes decidía el código y ahora se cargan, y una pantalla
nueva para cada una. Todo sale de `gomeria/29_parametros.sql`, que se pega
entero en Supabase → SQL Editor → Run y se puede correr las veces que
haga falta.

Los accesos están **arriba, en todas las pantallas**: *Usuarios* y
*Parámetros*, para el que los tenga habilitados. El permiso lo revisa el
servidor en cada pedido; la barra solo esconde lo que no corresponde.

## 1. De dónde salen los kilómetros

En `/parametros`, primera solapa. Dos opciones y nada más:

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

Segunda solapa. Un plan tiene **clase**, y la clase decide qué campos
tienen sentido:

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

Tercera solapa: los mismos números que ya usaba Alertas. A cuántos
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
