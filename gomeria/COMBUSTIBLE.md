# Combustible

> **Módulo en prueba.** Se usa en paralelo con la planilla de siempre hasta
> que los números den. Cada carga se puede borrar entera.

Todo sale de la planilla de cargas que se sube en *Tickets*: cuánto se
cargó, cuánto costó y cuánto consume cada unidad.

> El cruce de remitos contra el listado de la estación se sacó. Para tirar
> sus vistas en una base que ya las tenía, correr
> `gomeria/45_sin_cruce_de_remitos.sql`.

## Combustible de la flota

Hasta acá el módulo era solo un control de facturación. Los litros de la
flota vivían en la planilla de Google, y por eso el consumo de la portada
se leía de ahí y no de la base.

Ahora el consumo se calcula cruzando dos cosas que ya están en Supabase:

    los litros   de la planilla de cargas
    los km       de la serie diaria del satelital (tabla odometros)

Es la primera vez que sale **por unidad y por mes sin que nadie copie un
número a mano**.

Se ve el total del mes —litros, gastado, precio por litro, kilómetros,
L/100 km y $/km— y abajo la misma cuenta unidad por unidad, ordenada por lo
que más gastó.

### Cuándo no hay consumo

Los litros se cuentan siempre; el consumo, solo cuando se sabe cuántos
kilómetros hizo esa unidad. Cuando no se sabe, la fila dice por qué:

| Dice | Qué pasó |
|---|---|
| *la patente no está en el maestro* | la carga se anotó con una patente que no es de ninguna unidad |
| *sin lecturas del satelital ese mes* | el equipo no reportó |
| *el satelital no le contó kilómetros* | reportó, pero todas las lecturas quedaron descartadas |

**Esas unidades quedan fuera del L/100 km de la flota**, y el número de
arriba avisa cuántas son y cuántos litros representan. Sumar litros cuyos
kilómetros no están abajo daría un consumo inventado: más alto cuanto más
combustible haya cargado justo esa unidad.

El consumo de la flota se calcula sobre los totales y no promediando el de
cada unidad: un utilitario que hizo 200 km no puede pesar lo mismo que un
tractor que hizo 12.000.

La portada del sistema muestra este mismo número: lo lee de acá, no de
ninguna planilla.

## Paso 1 — la base

En Supabase → **SQL Editor** → correr los dos, en orden:

    gomeria/10_combustible.sql          las tablas
    gomeria/17_combustible_flota.sql    el combustible de la flota

Se pueden correr las veces que haga falta. El segundo son solo vistas: no
toca ni un dato.

## Paso 2 — subir la planilla

En `/combustible`, solapa *Tickets*. Se arrastra el archivo o se elige. Acepta **.xlsx y .csv**.

Antes de guardar **muestra qué entraría**: cuántos remitos leyó, qué
columnas encontró y las primeras ocho filas. Recién con *Guardar* se
escribe. La primera vez conviene mirarlo: si la planilla cambió el formato,
se ve ahí y no con la tabla ya sucia.

### Qué columnas busca

Por lo que dice el título, no por igualdad, así que la planilla puede
armarse a su manera:

| Dato | Cómo lo puede llamar |
|---|---|
| **remito** | REMITO · COMPROBANTE · TICKET · VALE · NRO REMITO |
| fecha | FECHA · DIA |
| hora | HORA (o la hora pegada a la fecha). Necesita `40_viento_viajes.sql`; sin la columna se guarda igual, sin hora |
| patente | PATENTE · DOMINIO · MOVIL · UNIDAD · CHAPA |
| litros | LITROS · LTS · CANTIDAD · VOLUMEN |
| importe | IMPORTE · TOTAL · MONTO · PRECIO |
| estación | ESTACION · SURTIDOR · PROVEEDOR · RAZON SOCIAL |
| chofer | CHOFER · CONDUCTOR |

La única imprescindible es el **remito**. Los títulos no tienen que estar en
la primera fila: las planillas suelen traer el logo y el período arriba, y se
busca en las primeras quince. Las filas sin remito —totales, subtotales,
renglones en blanco— se descartan solas y se informa cuántas.

### Elegir la columna a mano

La app adivina por el nombre del título, pero **adivinar no alcanza**. Una
planilla de cargas suele traer el número de *ticket* y el de *remito* en dos
columnas distintas. Por eso la vista previa muestra **qué columna eligió para
cada cosa** y deja cambiarla. Al cambiarla vuelve a leer el archivo.

### El número de remito

El remito puede venir con el punto de venta adelante (`0001-00123456`) o
solo el número (`123456`). **Son el mismo remito.**
Lo que va antes del guión se descarta, que es lo que significa, y de lo que
queda se sacan los ceros de adelante:

```
0001-00123456  ->  123456
00123456       ->  123456
123456         ->  123456
R 123.456      ->  123456
```

## Volver a subir

Un remito que ya estaba **se pisa**, no se duplica: subir la planilla
corregida deja la última versión.

La clave es **remito + patente**, no el remito solo. Dos estaciones
distintas repiten numeración, y una planilla de un año trae el mismo número
de dos proveedores. Con la patente adentro conviven sin pisarse. El mismo
camión con el mismo remito dos veces sí es un duplicado: se avisa y queda la
última fila.

## Borrar

Cada archivo subido queda como un lote en `combustible_lotes`. La pantalla
ya no lista ni borra lotes: si hace falta sacar una carga equivocada, se
borra el lote desde el SQL Editor de Supabase y sus remitos se van con él
(`on delete cascade`).

## Lo que todavía no hace

- No lee PDF: hay que pasarlo a Excel o CSV.
- No engancha solo con la planilla de COMBUSTIBLE de Google: el archivo se
  sube a mano. Automatizarlo es el paso siguiente, igual que se hizo con
  los odómetros. Los litros **ya están en la base**, así que lo que falta
  es el enganche, no el dato.
- No guarda la foto del ticket. La planilla trae el enlace a Drive de cada
  uno y por ahora se ignora.
