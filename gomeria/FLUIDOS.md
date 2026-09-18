# Fluidos — el depósito propio

Combustible es plata que se controla **contra un tercero**: la estación
manda su listado y el sistema cruza remitos. Los fluidos no: el envase es
nuestro, así que no hay nada que cruzar con nadie. Lo que hay que
controlar es un **stock**.

Por eso esta solapa no se parece al cruce de combustible: se parece al
depósito de repuestos. **Nadie edita el saldo.** El saldo es el resultado
de los movimientos, y se calcula cada vez que se mira.

Vive en `/combustible#fluidos`, la cuarta solapa de Combustible. Antes era
*Urea*, y la urea sigue estando: ahora es uno de los fluidos.

## Paso 1 — las tablas

En Supabase, **SQL Editor**, pegar y correr `gomeria/32_fluidos.sql`. Se
puede correr las veces que haga falta. Antes tienen que estar corridos
`01_esquema.sql` y `03_usuarios.sql`.

Arranca con los seis del taller: **urea** (bin de 1.000), **aceite
15W40** y **20W50** (tambor de 205), **refrigerante concentrado**,
**líquido hidráulico** (tambor de 205) y **grasa** (balde de 20 kilos).
Se corrigen y se agregan otros desde `/parametros` → *Combustible*.

Si estaba corrido `28_urea.sql`, el tacho y **todos sus movimientos se
migran solos**, una sola vez: cada movimiento migrado deja anotado de cuál
salió, así que correr el script de nuevo no duplica nada. Las tablas
viejas no se tocan; si algo saliera mal, el dato original sigue donde
estaba.

Con `10_combustible.sql` y `05_odometros.sql` corridos, además sale el
porcentaje de urea sobre gasoil por unidad. Sin ellos, los litros se ven
igual y esa columna queda en blanco.

## El envase es la mitad del asunto

Un bin de 1.000 litros y un tambor de 205 no se miran igual, y un balde de
grasa se mide en kilos. Cada fluido dice **en qué viene** y **cuánto entra
en uno**, y de ahí sale lo que se ve:

- El envase abierto se dibuja con lo que le queda adentro. Un bin al 12%
  se entiende antes que «140 litros».
- Los que están **sin abrir se cuentan al lado**: con 1.602 litros de
  15W40 hay un tambor por la mitad y **siete sellados**.
- El mínimo con el que avisa es por fluido. Sin cargarlo, es el 20% de un
  envase.

La capacidad **es la de un envase, no la del depósito**. Comprar ocho
tambores no es un error ni llena nada de más: son ocho envases.

## Los tres movimientos

| | Qué es | Quién |
|---|---|---|
| **Carga** | Llegó el proveedor y se descargó. Fecha, cantidad, proveedor, remito e importe. | El que gestiona |
| **Despacho** | Se le puso a una unidad. Fecha, cantidad y kilómetros. | Cualquiera que tenga el módulo |
| **Medición** | Se midió y no da. Se anota la diferencia con su motivo. | El que gestiona |

Despachar es el acto de todos los días y por eso no le pide permiso a
nadie: anotarlo tiene que costar menos que no anotarlo. Comprar y ajustar
sí, porque son la plata que entró y la diferencia que hubo.

**La cantidad va siempre en positivo**: el signo lo pone el tipo de
movimiento, no quien carga. El único que lleva signo es el ajuste, porque
un ajuste es una diferencia.

## La medición es la parte que importa

La merma es real: evaporación, derrames, lo que se carga y no se anota.
Corregir el saldo a mano sería tapar justo el dato que la explica.

Por eso no hay ningún lugar donde escribir el saldo. Se carga **cuánto hay
de verdad** y el sistema anota la diferencia como un movimiento más, con
su motivo, que es obligatorio. Si la medición da exacto, no escribe nada.

## Lo que sale sin ir a una unidad

Un derrame, un préstamo a un tercero, una devolución: también salieron del
depósito. Se anotan como despacho, con el motivo escrito en vez de la
patente. Lo que no puede pasar es que salga algo y no quede el renglón:
ahí el saldo deja de ser creíble, y con él el aviso.

## Cuándo avisa

Dos formas de quedarse sin, y las dos avisan en `/alertas`:

- **Por cantidad**: el saldo bajó del mínimo del fluido.
- **Por días**: al ritmo de los últimos 30 días, lo que queda alcanza para
  menos de 7 (aviso) o menos de 3 (urgente).

El segundo es el que sirve de verdad: un tambor con 40 litros está bien si
se usan dos por mes y es una urgencia si se usan dos por semana. Un fluido
en cero no es un aviso, es una parada: el camión que pide urea y no hay,
no sale.

**El que nunca se cargó no avisa.** No está vacío: está sin estrenar. Si
fueran lo mismo, el día que se corre el script saltarían cinco alarmas de
algo que nadie compró todavía.

## Saldo negativo

No se bloquea. El que está despachando tiene la manguera en la mano y lo
que pasó, pasó. Lo que hace el sistema es decirlo: un saldo negativo es
una entrada que no se anotó, y la pantalla pide medir.

## Los proveedores

Hasta acá el proveedor era un texto que cada uno escribía como quería en
cada carga, así que no se podía sumar lo que se le compró a nadie. Ahora
son filas, con su CUIT, su contacto y **qué rubros provee** —combustible,
urea, aceites, grasa, repuestos—. Se cargan en `/parametros` →
*Combustible*, y se eligen de una lista al cargar una compra. Al que ya se
le compró no se borra: se da de baja.

## Por unidad

Teniendo lo despachado por patente, y ya teniendo el gasoil y los
kilómetros del satelital, salen dos números que antes no tenía nadie:

- **% de urea sobre gasoil.** Un camión moderno anda entre **3% y 6%**. El
  que da mucho menos tiene el sistema anulado —y eso es una multa
  esperando, además de un motor sin tratar—; el que da mucho más pierde, o
  alguien se está llevando bidones. Lo que cae fuera de la banda se marca
  en rojo. En un aceite ese porcentaje no dice nada, así que no se muestra.
- **Cada 100 km**, la misma medida con la que ya se mira el gasoil. En los
  aceites es el número a mirar: un motor que toma aceite se ve acá antes
  que en la varilla.

La unidad sin cargas de gasoil o sin lecturas del satelital queda con esa
columna en blanco. No se rellena con un número inventado.

## Lo que no hace

No lee archivos del proveedor ni cruza remitos: los fluidos se cargan a
mano porque son dos o tres movimientos por día, no doscientos. Si algún
día el proveedor manda listado, se le agrega el lector que ya existe en
combustible.

No lleva cuenta de cada envase por separado. El saldo es del fluido y el
envase es cómo se dibuja: el que despacha no tiene que decir de qué tambor
sacó.
