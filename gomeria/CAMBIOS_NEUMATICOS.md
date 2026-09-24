# Cambios de neumáticos por eje

Una solapa de Gomería, **Cambios por eje**, que contesta tres preguntas:

| Pregunta | Dónde |
|---|---|
| ¿A qué eje de qué patente le toca cambiar las gomas? | la lista de arriba, ordenada por urgencia |
| ¿Cada cuánto se cambia cada eje? | *Cada cuánto se cambia cada eje*, por mapa |
| ¿Cuánto dura una goma de verdad? | *Cuánto dura una goma*, por patente, marca, modelo, tipo de eje o mapa |

Se prende corriendo **`38_cambios_neumaticos.sql`** (después de `29_parametros.sql`) en Supabase → SQL
Editor → Run. Hasta que no se corra, la solapa lo avisa y el resto de
Gomería sigue igual.

## La regla: por mapa y por eje

Todas las unidades con el mismo mapa de ejes comparten la regla. Viene
cargada la del tractor:

| Mapa | Eje | Tipo | Se cambia cada |
|---|---|---|---|
| S-D-D | 1 | Dirección | 150.000 km |
| S-D-D | 2 | Tracción | 220.000 km |
| S-D-D | 3 | Portante | 220.000 km |

**El resto de los mapas (los semis D-D-D y D-D, el S-D) vienen sin regla**
y se cargan desde la pantalla, con la sesión de un encargado o
administrador. Cada eje puede tener:

- **km**, **días**, o las dos cosas: avisa lo que llegue primero.
- un **aviso previo** en km y en días (por defecto 15.000 km y 30 días).
- un **tipo**: dirección, tracción, portante o arrastre. Si no se toca, se
  deduce del mapa. Es el que usan las métricas "por tipo de eje".

## Los semis no tienen odómetro

Un semi anda lo que anda el tractor que lo lleva. Para contar sus km hace
falta saber qué tractor lo llevaba **cada día**, no solo hoy. Esa historia
es la de los **enganches** (`29_parametros.sql`), que se cargan en
**Flota → Asociación de equipos**. Este módulo la lee, no la copia: los km
del semi son los del tractor mientras lo llevó, día por día
(`v_km_semi_diario`).

El día que se corre `38_cambios_neumaticos.sql`, a cada semi que nunca
tuvo un enganche cargado se le crea uno con el tractor que dice la ficha,
**supuesto desde la primera lectura del satelital de ese tractor**. Queda
firmado por `sistema` con una nota que lo dice. Si la fecha no es cierta,
se corrige en Asociación de equipos.

Si algún día el semi ya tiene lectura —propia, o la serie que arma el
módulo de enganches—, gana la lectura y no se cuenta dos veces.

## Desde cuándo se cuenta

Para cada posición, lo más nuevo entre:

1. **El día que la cubierta entró a ese eje**, si está cargada y montada
   en el mapa. Una rotación dentro del mismo eje (2IE → 2II) no reinicia
   la cuenta: la goma sigue gastándose en el mismo lugar.
2. **El último cambio registrado a mano** para ese eje, con el botón
   *Registrar cambio*. Es lo que se usa mientras no esté hecho el
   inventario de cubiertas. Se pueden marcar varios ejes a la vez.

Si al registrar el cambio se anota el odómetro, y la unidad tiene
satelital propio, los km salen de la resta y no dependen de que el
satelital haya reportado todos los días.

Un eje está como **su peor cubierta**: si una de las cuatro ya pasó, hay
que ir.

| Estado | Qué quiere decir |
|---|---|
| Pasado | llegó a los km o a los días de la regla |
| Próximo | entró en el aviso previo |
| Sin dato | no se sabe cuándo se cambió: registrar el último cambio |
| Sin regla | ese eje de ese mapa no tiene regla cargada |

Los km marcados **parcial** son un piso: el satelital empezó a reportar
después de la fecha desde la que se cuenta.

## Las métricas

Entran las gomas que **ya terminaron** su tiempo en un eje:

- una cubierta montada que salió del eje (fuente: montajes), o
- el período entre dos cambios registrados a mano del mismo eje, siempre
  que en ese período no haya cubiertas cargadas en ese eje (si no, se
  contaría dos veces).

Se muestra, para cada grupo: cantidad de cambios, días promedio, km
promedio y el mínimo y máximo de km. Los períodos con km parciales entran
al promedio de días pero no al de km. Un cambio registrado a mano sin
marca ni modelo entra como "(sin marca)".

## Lo que queda guardado

| Tabla / vista | Qué es |
|---|---|
| `enganches` (de 29) | qué tractor llevó a cada semi y entre qué fechas |
| `neumaticos_reglas` | cada cuánto se cambia cada eje de cada mapa |
| `neumaticos_cambios` | cambios registrados a mano. No se borran: se anulan, con quién y por qué |
| `v_km_dia_efectivo` | km por día de cada unidad; los semis heredan los del tractor |
| `v_neumaticos_tramos` | cuánto estuvo cada cubierta en cada eje |
| `v_neumaticos_posiciones` / `v_neumaticos_ejes` | el aviso |
| `v_neumaticos_duraciones` | la base de las métricas |

## Quién puede qué

- Registrar un cambio: cualquiera que abra Gomería. Queda firmado.
- Reglas y anular un cambio: encargado o administrador.
