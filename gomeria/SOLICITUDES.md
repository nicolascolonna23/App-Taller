# Solicitudes de orden de compra

El registro nace antes de la reparación, no después.

El mantenimiento **preventivo** ya estaba procedimentado: intervalos por
kilometraje, check list del chofer, planilla de servicios. El
**correctivo que resolvía una sucursal**, en cambio, se hacía y se rendía
como un gasto más: la plata quedaba anotada, la intervención técnica no.

La solicitud corrige eso con una sola idea: **una sucursal no manda a
hacer un trabajo de taller sin una solicitud aprobada, y no rinde la
factura sin el número de solicitud escrito**.

## Qué queda adentro y qué queda afuera

Lo que manda a hacer **mantenimiento** no pasa por el circuito. El área
que decide el gasto es la misma que lo controla: pedirse una solicitud a
sí misma sería papeleo, y el papeleo se esquiva. Su servicio externo se
carga como siempre, con la factura y nada más.

Lo que manda a hacer **una sucursal** va con su solicitud. Ese es el gasto
que antes se resolvía lejos del taller y llegaba a la administración como
un número sin historia.

Por eso el formulario de servicio externo pregunta una sola cosa nueva:
**quién lo mandó a hacer**. De esa respuesta depende si pide la solicitud
o no.

El circuito tiene cuatro pasos —**pedir, aprobar, reparar, rendir**—, un
formulario de seis campos y un botón por parte del taller. Si a una
sucursal le lleva más de dos minutos cargar una solicitud, el módulo está
mal hecho y lo van a esquivar.

## Paso 1 — las tablas

En Supabase, **SQL Editor**, pegar y correr `gomeria/26_solicitudes.sql`.
Se puede correr las veces que haga falta: no borra nada. Antes tienen que
estar corridos `01_esquema.sql`, `03_usuarios.sql`, `15_ordenes.sql` y
`20_alertas.sql`.

Crea las siete sucursales con su código de tres letras —CAT, TUC, SAL,
LAR, COR, ROS, BUE—, que es el mismo que ya usa el maestro de unidades.

Hasta que no se corra, la pantalla `/solicitudes` avisa que falta el
script en lugar de romper, y el resto de la aplicación sigue andando
igual.

## Paso 2 — la sucursal de cada usuario

La solicitud se numera según **quién la pide**, así que cada responsable
de sucursal tiene que tener la suya cargada:

```sql
update usuarios set sucursal_codigo = 'CAT' where usuario = 'ramon';
```

Al que la tenga cargada la pantalla no se la pregunta: es un campo menos
y una discusión menos. Al que no —administración, mantenimiento— se la
pide en el formulario.

## El número

Lo genera el sistema, nunca el usuario: `CAT-00001`, `COR-00047`.

- El correlativo es **por sucursal**, no global, y no se reinicia por año.
- Es **inmutable**: el número de una solicitud rechazada o anulada no se
  reutiliza. Por eso en el módulo no hay ningún borrado de solicitudes.
- Se toma bloqueando la fila del contador de esa sucursal (`select …
  for update`) dentro de la misma transacción que inserta la solicitud.
  Dos sucursales cargando en el mismo segundo no se estorban —son dos
  filas— y dos usuarios de la misma sucursal esperan uno al otro.

Nunca con `max(numero) + 1`: sin bloqueo, dos cargas leen el mismo máximo
y escriben el mismo número.

## Los estados

```
SOLICITADO ──aprobar──▶ APROBADO ──iniciar──▶ EN_EJECUCION ──cerrar──▶ CERRADO
     │                      │                                   ▲
     └──rechazar──▶ RECHAZADO└──────────── cerrar directo ───────┘
```

| Transición | Quién | Qué necesita |
|---|---|---|
| crear → `SOLICITADO` | responsable de sucursal | patente, km, tipo, origen, detalle |
| `SOLICITADO` → `APROBADO` | taller o mantenimiento | puede cargar monto autorizado y taller |
| `SOLICITADO` → `RECHAZADO` | taller o mantenimiento | el motivo, obligatorio |
| `APROBADO` → `EN_EJECUCION` | taller o sucursal | |
| `APROBADO` o `EN_EJECUCION` → `CERRADO` | sucursal o administración | número de factura, obligatorio |

Reglas duras:

- **No se compra ni se repara con la solicitud en `SOLICITADO` o
  `RECHAZADO`.**
- **Una sucursal no rinde una factura de taller sin una solicitud
  `CERRADA`.** La validación vive en el módulo de gastos —acá, los
  servicios externos de `/ordenes`—: el formulario pregunta quién lo mandó
  a hacer y, si fue una sucursal, pide la solicitud; el servidor lo
  verifica igual, no alcanza con la pantalla.
- Una solicitud rechazada es **terminal**. Si la sucursal insiste, carga
  una nueva citando la anterior, y así queda a la vista cuántas veces se
  insistió.
- El taller tiene **24 horas hábiles** para contestar. Con
  `urgencia = UNIDAD_PARADA` la respuesta es inmediata y la solicitud
  aparece arriba de la bandeja, marcada.

## El historial

Cada cambio de estado escribe su renglón en `solicitud_eventos`, en la
misma transacción: quién, cuándo y con qué comentario. **No se edita ni se
borra**, y no por convención: un trigger de la base lo impide.

Es la parte del módulo que parece burocracia hasta el día en que hay que
contestar quién autorizó un gasto que ya se hizo.

## Lo que no necesita solicitud

No pasa por el circuito. Se resuelve y se informa en el control mensual:

- lámparas, fusibles y plumillas
- aceite, agua y refrigerante de reposición
- inflado, parche o auxilio en ruta
- ajuste de tuercas y controles sin repuesto

**La lista decide, no el monto.** No hay umbrales de plata a propósito:
generan interpretación, discusión y esquive del circuito. Si algún día se
quiere un tope, que sea un aviso y no un bloqueo.

## Unidad parada en ruta

Falla de seguridad o unidad detenida fuera de la sucursal: se autoriza
verbalmente y la solicitud se carga después, marcando *«se autorizó en
ruta»*. El sistema acepta la fecha del hecho anterior a la de carga, y
cuenta las regularizaciones por sucursal y por mes.

Es un **indicador, no un castigo**: sirve para ver dónde el circuito no
llega, no para retar a nadie.

Las 48 horas hábiles no bloquean la carga —una solicitud cargada tarde es
mejor que una solicitud no cargada—: la pantalla avisa que quedó fuera de
término y el indicador lo cuenta.

## Las vistas

| Vista | Para qué |
|---|---|
| Nueva solicitud | Seis campos. La sucursal no elige el número ni el estado. |
| Bandeja del taller | Las `SOLICITADO` de toda la red, por urgencia y antigüedad, con aprobar o rechazar en un clic. |
| Mi sucursal | Las propias, con su estado. |
| Toda la red | Lectura para cualquier sucursal, con filtros. Que cada responsable vea el resto no es un detalle: compara tiempos de respuesta y ordena solo. |
| Ficha de unidad | El historial por patente. Es la vista que detecta la unidad que entra tres veces por la misma falla. |
| Indicadores | Por sucursal y por mes. |
| Solicitud imprimible | Una carilla con número, unidad, km, falla, taller, monto, quién pidió y quién autorizó, más las firmas. Es lo que se grapa a la factura. |

## Los indicadores

- **% de facturas de sucursal rendidas con solicitud** (objetivo 100%).
  Se mide sobre las que necesitan solicitud: meter adentro lo que mandó a
  hacer mantenimiento bajaría el número sin que nadie haya esquivado
  nada. Las de mantenimiento se cuentan aparte, para ver por dónde pasa
  el gasto.
- **Reparaciones de sucursal rendidas sin solicitud previa** (objetivo 0).
- **Tiempo promedio entre solicitado y aprobado**, por sucursal.
- **Correctivos sin aviso previo del check list**: hoy se calcula con lo
  que hay —un correctivo cuyo origen no es el check list del chofer—.
  Cuando exista el módulo de check list se podrá cruzar contra el ítem
  concreto. Un número alto dice que el control diario no se está
  haciendo, o que falta un ítem en la planilla.
- **Regularizaciones de ruta** por sucursal.
- **Gasto de correctivo por unidad y por 1.000 km**. Los kilómetros son
  los del satelital: la unidad sin lecturas queda sin peso por kilómetro,
  no se rellena con un número inventado.

## El enganche con lo que ya existe

- Una solicitud **preventiva** cerrada registra el service de la unidad y
  recalcula el próximo, igual que una orden preventiva. Si la unidad no
  tiene plan de mantenimiento asignado, la solicitud **cierra igual** y la
  pantalla avisa: la sucursal que tiene la factura en la mano no puede
  quedar trabada por una parametrización que no depende de ella. Se
  asigna el plan y se registra el service desde `/control`.
- La factura del taller entra como **servicio externo** en `/ordenes`.
  Si la mandó a hacer una sucursal, se elige la solicitud de la lista de
  cerradas sin rendir: ahí quedan atados el gasto y la intervención
  técnica. La orden guarda las dos cosas, `gestion` y `solicitud_id`.

## Si hace falta apagar el candado

Mientras la red se acostumbra, se puede permitir que una sucursal rinda
sin solicitud:

```sql
update solicitudes_ajustes set exigir_solicitud = false;
```

Y para volver a exigirla:

```sql
update solicitudes_ajustes set exigir_solicitud = true;
```

Nunca hace falta apagarlo para cargar lo de mantenimiento: eso no pasa
por acá. Y es a propósito que sea una línea de SQL y no un botón en la
pantalla: apagar el circuito tiene que costar más que usarlo.
