# Combustible — cruce de remitos

> **Módulo en prueba.** Se usa en paralelo con lo de siempre hasta que los
> números den. Nada de lo que se carga acá afecta al resto del sistema:
> vive en sus propias tablas y cada carga se borra entera.

La estación manda un listado de remitos y después la factura. Nosotros
tenemos nuestra planilla de cargas. Hoy alguien compara las dos a ojo antes
de pagar. Esto lo hace por número de remito y deja a la vista lo que no
coincide.

## Paso 1 — la base

En Supabase → **SQL Editor** → correr `gomeria/10_combustible.sql`. Se puede
correr las veces que haga falta.

## Paso 2 — subir los dos archivos

En `/combustible`, dos zonas: el listado de la estación y nuestra planilla.
Se arrastra el archivo o se elige. Acepta **.xlsx y .csv**.

Antes de guardar **muestra qué entraría**: cuántos remitos leyó, qué
columnas encontró y las primeras ocho filas. Recién con *Guardar* se
escribe. La primera vez conviene mirarlo: si la estación cambió el formato,
se ve ahí y no con la tabla ya sucia.

### Qué columnas busca

Por lo que dice el título, no por igualdad, así que cada estación puede
armarlo a su manera:

| Dato | Cómo lo puede llamar |
|---|---|
| **remito** | REMITO · COMPROBANTE · TICKET · VALE · NRO REMITO |
| fecha | FECHA · DIA |
| patente | PATENTE · DOMINIO · MOVIL · UNIDAD · CHAPA |
| litros | LITROS · LTS · CANTIDAD · VOLUMEN |
| importe | IMPORTE · TOTAL · MONTO · PRECIO |
| estación | ESTACION · SURTIDOR · PROVEEDOR · RAZON SOCIAL |
| chofer | CHOFER · CONDUCTOR |

La única imprescindible es el **remito**. Los títulos no tienen que estar en
la primera fila: los listados suelen traer el logo y el período arriba, y se
busca en las primeras quince. Las filas sin remito —totales, subtotales,
renglones en blanco— se descartan solas y se informa cuántas.

### Elegir la columna a mano

La app adivina por el nombre del título, pero **adivinar no alcanza**. Una
planilla de cargas suele traer el número de *ticket* y el de *remito* en dos
columnas distintas, y el que cruza con la factura es uno solo. Si agarra el
que no era, no cruza nada: todo cae en *solo la estación* y *solo nuestra
planilla*, con numeraciones que ni se parecen.

Por eso la vista previa muestra **qué columna eligió para cada cosa** y deja
cambiarla. Al cambiarla vuelve a leer el archivo, así se ve al instante si
ahora sí son los números que están en la factura.

Es lo primero que hay que mirar cuando un cruce da todo en rojo.

### El cruce va por dos caminos

**1. Por número de remito.** Es el ideal: el número está en la factura.

**2. Por camión, fecha y litros.** Es el que salva el caso real. La
numeración de la estación y la de nuestra planilla muchas veces **no tienen
nada que ver**, porque cada uno numera su propio comprobante:

```
estación:  958, 959, 961, 962, 964
planilla:  142575, 152659, 36360, 20196, 156373
```

No es un error de nadie: son dos papeles distintos de la misma carga. Pero
el mismo camión, el mismo día, es la misma carga aunque el papel se llame
distinto.

El segundo camino solo mira lo que quedó suelto del primero, y **solo
empareja cuando hay una sola candidata de cada lado**. Si el mismo camión
cargó dos veces el mismo día, no se adivina: quedan sueltas.

Empareja **sin mirar los litros**, a propósito. Que difieran es justamente
lo que hay que ver: exigiendo que coincidan, la carga mal facturada quedaría
como dos renglones sueltos y el error se perdería.

Los renglones que salieron por este camino van marcados **por carga** en la
tabla, para poder mirarlos con más desconfianza que los que cruzaron por
número.

### El número de remito

La estación factura con el punto de venta adelante (`0001-00123456`) y
nuestra planilla anota solo el número (`123456`). **Son el mismo remito.**
Lo que va antes del guión se descarta, que es lo que significa, y de lo que
queda se sacan los ceros de adelante:

```
0001-00123456  ->  123456
00123456       ->  123456
123456         ->  123456
R 123.456      ->  123456
```

Sin esto no cruzaría nada: todo caería en *solo la estación* y *solo nuestra
planilla*.

## Qué muestra

Una tarjeta por estado, y la tabla debajo. Se toca una tarjeta para filtrar.

| Estado | Qué significa |
|---|---|
| **Coinciden** | el remito está en los dos y los números dan. Se paga. |
| **Solo la estación** | nos lo facturan y no lo tenemos cargado |
| **Solo nuestra planilla** | lo cargamos y no vino en el listado |
| **Difieren los litros** | más de medio litro de diferencia |
| **Difiere el importe** | más de un peso de diferencia |
| **De otro período** | de nuestra planilla, fuera del mes que mandó la estación |

Los márgenes son a propósito: la estación factura con dos decimales y la
planilla a veces arrastra más, y esa diferencia de milésimas no es una
diferencia real. Se comparan redondeados a dos.

Lo que hay que mirar va arriba; *coinciden* queda al final.

**Por qué existe "de otro período".** La estación manda un lote —una
factura, un mes— y nuestra planilla tiene todo el historial. Cruzarlos
enteros daría mil renglones de *solo nuestra planilla* que no son un
hallazgo: son los otros meses. Se toma el período que abarca lo que mandó la
estación y lo de afuera queda aparte, sin ensuciar el control.

## Volver a subir

Un remito que ya estaba **se pisa**, no se duplica: subir el listado
corregido deja la última versión.

La clave es **remito + patente**, no el remito solo. Dos estaciones
distintas repiten numeración, y una planilla de un año trae el mismo número
de dos proveedores. Con la patente adentro conviven sin pisarse. El mismo
camión con el mismo remito dos veces sí es un duplicado: se avisa y queda la
última fila.

## Borrar

Cada archivo subido es un lote y se borra entero, con sus remitos. No toca
los del otro archivo. Subir y borrar pide ser encargado o administrador.

## Lo que todavía no hace

- No lee PDF. Si la estación manda el listado en PDF hay que pasarlo a Excel.
- No engancha con la planilla de COMBUSTIBLE de Google: se sube el archivo
  a mano. Automatizarlo es el paso siguiente, igual que se hizo con los
  odómetros.
- No guarda la factura ni marca "pagado". Valida y muestra; la decisión
  sigue siendo de una persona.
