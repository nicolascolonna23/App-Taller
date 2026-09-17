# Urea — el tacho propio

Combustible es plata que se controla **contra un tercero**: la estación
manda su listado y el sistema cruza remitos. La urea no: el tacho es
nuestro, así que no hay nada que cruzar con nadie. Lo que hay que
controlar es un **stock**.

Por eso la urea no se parece al cruce de combustible: se parece al
depósito de repuestos. **Nadie edita el saldo.** El saldo es el resultado
de los movimientos, y se calcula cada vez que se mira.

Vive en `/combustible#urea`, la cuarta solapa de Combustible.

## Paso 1 — las tablas

En Supabase, **SQL Editor**, pegar y correr `gomeria/28_urea.sql`. Se
puede correr las veces que haga falta: no borra nada. Antes tienen que
estar corridos `01_esquema.sql` y `03_usuarios.sql`.

Crea un tacho de 1.000 litros para que la pantalla no arranque vacía: la
capacidad, el mínimo y el nombre se corrigen desde el botón **Editar
tacho**.

Con `10_combustible.sql` y `05_odometros.sql` corridos, además sale el
porcentaje de urea sobre gasoil por unidad. Sin ellos, los litros de urea
se ven igual y esa columna queda en blanco.

## Los tres movimientos

| | Qué es | Quién |
|---|---|---|
| **Carga** | Llegó el proveedor y se descargó en el tacho. Fecha, litros, proveedor, remito e importe. | El que gestiona |
| **Despacho** | Se le puso urea a una unidad. Fecha, litros y kilómetros. | Cualquiera que tenga el módulo |
| **Medición** | Se midió el tacho y no da. Se anota la diferencia con su motivo. | El que gestiona |

Despachar es el acto de todos los días y por eso no le pide permiso a
nadie: anotarlo tiene que costar menos que no anotarlo. Comprar y ajustar
sí, porque son la plata que entró y la diferencia que hubo.

**Los litros van siempre en positivo**: el signo lo pone el tipo de
movimiento, no quien carga. El único que lleva signo es el ajuste, porque
un ajuste es una diferencia.

## La medición es la parte que importa

La merma de un tacho de urea es real: evaporación, derrames, lo que se
carga y no se anota. Corregir el saldo a mano sería tapar justo el dato
que la explica.

Por eso no hay ningún lugar donde escribir el saldo. Se carga **cuántos
litros hay de verdad** y el sistema anota la diferencia como un
movimiento más, con su motivo, que es obligatorio. Si la medición da
exacto, no escribe nada.

## Lo que sale del tacho sin ir a una unidad

Un derrame, un préstamo a un tercero, una devolución: también salieron
del tacho. Se anotan como despacho, con el motivo escrito en vez de la
patente. Lo que no puede pasar es que salga urea y no quede el renglón:
ahí el saldo deja de ser creíble, y con él el aviso.

## Cuándo avisa

Dos formas de quedarse sin urea, y las dos avisan en `/alertas`:

- **Por litros**: el saldo bajó del mínimo del tacho. Si el mínimo se
  deja vacío, es el 20% de la capacidad.
- **Por días**: al ritmo de los últimos 30 días, lo que queda alcanza
  para menos de 7 (aviso) o menos de 3 (urgente).

El segundo es el que sirve de verdad: un tacho de 1.000 litros con 200
está bien en Catamarca y es una urgencia en Córdoba. Un tacho en cero no
es un aviso, es una parada: el camión que pide urea y no hay, no sale.

## Saldo negativo

No se bloquea. El que está despachando tiene la manguera en la mano y lo
que pasó, pasó. Lo que hace el sistema es decirlo: un saldo negativo es
una entrada que no se anotó, y la pantalla pide medir el tacho.

## Urea por unidad

Teniendo los litros de urea por patente, y ya teniendo los de gasoil y
los kilómetros del satelital, salen dos números que antes no tenía nadie:

- **% de urea sobre gasoil.** Un camión moderno anda entre **3% y 6%**.
  El que da mucho menos tiene el sistema anulado —y eso es una multa
  esperando, además de un motor sin tratar—; el que da mucho más pierde,
  o alguien se está llevando bidones. Lo que cae fuera de la banda se
  marca en rojo.
- **Litros cada 100 km**, la misma medida con la que ya se mira el
  combustible.

La unidad sin cargas de gasoil o sin lecturas del satelital queda con esa
columna en blanco. No se rellena con un número inventado.

## Lo que no hace

No lee archivos del proveedor ni cruza remitos: la urea se carga a mano
porque son dos o tres movimientos por día, no doscientos. Si algún día el
proveedor manda listado, se le agrega el lector que ya existe en
combustible.
