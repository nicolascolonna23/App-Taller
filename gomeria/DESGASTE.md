# Desgaste, costo y rendimiento de las cubiertas

Tres preguntas que hasta ahora no se podían contestar con la base:

| Pregunta | Dónde se contesta |
|---|---|
| ¿A cuál hay que bajarla? | solapa **Desgaste y costos**, arriba de todo |
| ¿Cuánto sale el kilómetro de goma? | la ficha de cada cubierta, vida por vida |
| ¿Qué marca y qué banda rinden más? | el ranking, en la misma solapa |

Se prende corriendo **`18_desgaste.sql`** en Supabase → SQL Editor → Run.
Hasta que no se corra, la solapa lo dice y el resto de Gomería sigue igual.

## La idea: una goma vive varias vidas

Una cubierta no es una sola cosa. Es la goma como se compró, después el
primer recapado, después el segundo. Cada una tiene **su banda, su costo y
sus kilómetros**, y comparar marcas mezclando todo no compara nada: le
suma a la Michelin los kilómetros de la banda que le pusieron encima tres
años después.

Por eso la unidad de medida es la **vida**, no la cubierta:

```
cubierta 4522  ──┬── vida 0   original    MICHELIN X Multi Z   $600.000
                 ├── vida 1   recapado    BANDAG BDR-HT        $180.000
                 └── vida 2   recapado    VIPAL VT-100         $195.000
```

Las vidas se abren solas: el alta de una cubierta abre la vida 0, y cada
recapado registrado cierra la que corría y abre la siguiente. De las vidas
anteriores a este módulo no hay registro y no se inventan; el rendimiento
se empieza a contar desde acá.

## Los cuatro datos que hacen falta

| Dato | De dónde sale | Si falta |
|---|---|---|
| Dibujo de goma nueva | tabla por medida, marca y banda | no hay "milímetros gastados" |
| Remanente | medición del gomero | no hay alerta ni desgaste |
| Kilómetros | serie diaria del satelital (Hawk) | no hay $/km |
| Costo | costo de compra, o el del recapado | hay rendimiento pero no plata |

La pantalla dice, arriba del ranking, **cuántas cubiertas están afuera de
la cuenta y por qué**. Un tablero que muestra doce de ciento diez sin decir
por qué es un tablero que engaña.

## La alerta

El mínimo no es uno solo: depende de dónde va puesta la goma, y eso sale
del mapa de la unidad.

| Función del eje | Cómo se deduce | Mínimo | Aviso |
|---|---|---|---|
| Direccional | primer eje de rueda simple | 4 mm | 6 mm |
| Tracción | duales de un tractor o chasis | 3 mm | 5 mm |
| Arrastre | ejes de un semi | 3 mm | 5 mm |
| Auxilio | la posición AUX | 3 mm | 5 mm |

Los cuatro se cambian desde la misma pantalla, si sos encargado o admin.

> El mínimo legal en Argentina es 1,6 mm. El de la empresa es más alto a
> propósito: una goma gastada de más ya no se puede recapar, y **la
> carcasa vale más que el dibujo**. Esperar hasta el límite legal es
> ahorrar unos milímetros y perder una carcasa.

### No espera a que llegue

Con el desgaste de esa misma goma —cuántos kilómetros le lleva gastar un
milímetro— la pantalla dice **cuántos kilómetros y cuántos días le faltan
para llegar al mínimo**. Un aviso que llega cuando la goma ya está en el
mínimo no sirve para comprar nada.

Los días salen de cuánto anda esa unidad por día, según el satelital de los
últimos 60 días. Si la goma todavía no tiene desgaste propio medido se usa
el promedio de su marca y banda, y la fila lo aclara con un **est.**

## Los números

Por vida, y sumados por marca y banda:

| Número | Cuenta | Para qué sirve |
|---|---|---|
| **Km por mm** | km ÷ mm gastados | comparar gomas **sin que el precio moleste** |
| **Dura** | km/mm × (dibujo nuevo − mínimo) | lo que va a rendir esa goma entera |
| **$/km** | costo de la vida ÷ km | el número de la plata |
| **$/mm** | costo ÷ mm gastados | lo que cuesta cada milímetro |

**Km por mm es el que decide.** Una goma barata que rinde la mitad no es
barata: el $/km lo dice recién cuando ya se gastó, y km/mm lo dice antes.

Al ranking solo entran las vidas con datos suficientes: más de 5.000 km
recorridos y más de 1 mm gastado. Con menos que eso, dos mediciones
parecidas y un redondeo mandan el número a la luna.

## Lo que hay que hacer cada día

1. **Medir.** Desde la ficha de la cubierta, botón *Medir dibujo*. Es el
   dato del que cuelga todo lo demás.
2. **Registrar el recapado** cuando la goma vuelve: banda, recapador,
   costo y con cuántos milímetros volvió. De acá sale la comparación entre
   bandas, y es el único dato que no se puede reconstruir después.
3. **Cargar el dibujo de goma nueva** de cada medida, una vez. Las medidas
   de la flota vienen con un valor típico de la industria marcado como
   *estimado*: la cuenta se hace igual, pero conviene medir una nueva y
   corregirlo.

## Dónde aparece

- **Portada**: el aviso naranja dice cuántas cubiertas llegaron al mínimo,
  antes de entrar a ningún lado.
- **Mapa de la unidad**: la goma se pinta con el mínimo que le toca por su
  posición, no con un número fijo igual para todas.
- **Solapa Desgaste y costos**: la lista completa, el ranking y la
  configuración.
- **Ficha de la cubierta**: sus vidas, con lo que rindió y costó cada una.
