# El maestro de unidades

De acá sale la información de un vehículo para todo el sistema: la gomería,
los vencimientos, el control de flota y el panel general. La planilla sigue
existiendo, pero deja de ser la que manda.

## Qué se agrega

| Dónde | Qué |
|---|---|
| Supabase | `07_unidades.sql`: cuatro columnas nuevas y dos vistas |
| App | la pantalla `/unidades`, con alta, cambio y baja |
| App | `importar_unidades.py`, para la carga inicial y las de después |

## Paso 1 — la base

En Supabase → **SQL Editor** → pegar y correr `gomeria/07_unidades.sql`. Se
puede correr las veces que haga falta: no borra nada.

La tabla `unidades` ya existía; lo que le faltaba era lo que solo estaba en
la planilla:

| Columna | Qué |
|---|---|
| `chasis` | número de chasis |
| `chofer` | quién la maneja |
| `semi` | la patente del semi asociado |
| `tipo` | `vehiculo` o `equipo` |

Y quedan armadas dos vistas:

- **`v_unidades`** — el maestro más lo que le agrega el resto del sistema:
  cómo está armada, cuántas cubiertas tiene montadas y cuándo fue la última
  lectura del satelital. Es lo que lee la pantalla.
- **`v_unidades_a_revisar`** — lo que no cierra. No son errores: es la lista
  de lo que falta completar.

## Paso 2 — cargar la planilla

```
python3 gomeria/importar_unidades.py gomeria/unidades_maestro.tsv --simular
python3 gomeria/importar_unidades.py gomeria/unidades_maestro.tsv
```

Con `--simular` dice qué haría y no escribe nada. Conviene mirarlo antes.

Se puede correr las veces que haga falta. **Un campo vacío en el archivo no
pisa lo que ya está cargado**, así que se puede importar una planilla
incompleta sin perder lo que se completó a mano desde la pantalla. Y **nada
se borra**: si una unidad está en la base y no en el archivo, queda como
está y el script lo avisa al final. Sacarla es una decisión, no un efecto de
haber importado.

`gomeria/unidades_maestro.tsv` es la planilla tal como se copia. Para
actualizarla, se pega de nuevo y se vuelve a correr.

## La pantalla

`/unidades`. Buscador, filtros por residencia, uso y estado, y la tabla
ordenable por cualquier columna. Se hace clic en una fila y se abre la
ficha.

La patente se escribe como salga —`ad 247 mq`, `AD-247-MQ`— y se guarda
siempre igual, pegada, que es como la manda el satelital. El buscador hace
lo mismo, así que encuentra la unidad se escriba como se escriba.

Para editar hace falta ser **encargado o administrador**. Un operario ve
todo pero no toca nada.

### Los equipos

Los autoelevadores y apiladores no tienen patente: van con su código
(`AUTCAT01`, `HELROD01`) en el lugar de la patente y `tipo = equipo`. Están
en la misma lista que en la planilla. **No entran a los tableros de flota**,
porque no tienen service ni telemetría y aparecían como unidades sin datos.

### Eliminar

Una unidad con cubiertas montadas, lecturas del satelital o documentos
cargados **no se borra**: borrarla dejaría huérfano todo eso. En ese caso se
la da de baja, que es lo que en la práctica se quiere decir con sacarla:
deja de contar en los tableros y la historia queda. La pantalla lo avisa
cuando pasa.

Una unidad recién cargada, sin nada colgando, sí se borra de verdad.

## Qué lee de acá

El panel general y el control de flota piden el maestro a `/api/flota`. Si
la base no contesta —la pantalla abierta sin sesión, un despliegue a
medias— vuelven a leer la planilla, que queda de respaldo. El chip de
fuentes dice cuál está usando.

## Lo que no cierra hoy

`v_unidades_a_revisar` junta cuatro cosas. Al importar quedaron así:

- **53 sin mapa de cubiertas** — ninguna unidad tiene todavía asignada su
  configuración de ejes. Se asigna desde gomería.
- **8 sin chofer** — la planilla los trae vacíos.
- **2 con chasis repetido** — `AE 423 IW` y `AE 527 FA` comparten el número
  `+9BSG4X200++L3975860+`. Es casi seguro un copiar y pegar en la planilla:
  son un Scania G360 y un Iveco Daily, no pueden tener el mismo chasis.
- **Patentes que reportan al satelital y no están en el maestro** — las
  viejas (`DZM638`, `LCC752`, `LCC754`, `STR530`, `VUX564`) y los equipos
  portátiles. Si alguna sigue andando, se le da de alta desde la pantalla.
