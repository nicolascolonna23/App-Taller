# Vales de taller

El registro nace antes de la reparación, no después.

El mantenimiento **preventivo** ya estaba procedimentado: intervalos por
kilometraje, check list del chofer, planilla de servicios. El
**correctivo**, en cambio, se hacía y se rendía como un gasto más de la
sucursal: la plata quedaba anotada, la intervención técnica no.

El vale corrige eso con una sola idea: **ninguna compra ni trabajo de
taller se hace sin un vale aprobado, y ninguna factura se rinde sin el
número de vale escrito**.

El circuito tiene cuatro pasos —**pedir, aprobar, reparar, rendir**—, un
formulario de seis campos y un botón por parte del taller. Si a una
sucursal le lleva más de dos minutos cargar un vale, el módulo está mal
hecho y lo van a esquivar.

## Paso 1 — las tablas

En Supabase, **SQL Editor**, pegar y correr `gomeria/26_vales.sql`. Se
puede correr las veces que haga falta: no borra nada. Antes tienen que
estar corridos `01_esquema.sql`, `03_usuarios.sql`, `15_ordenes.sql` y
`20_alertas.sql`.

Crea las siete sucursales con su código de tres letras —CAT, TUC, SAL,
LAR, COR, ROS, BUE—, que es el mismo que ya usa el maestro de unidades.

Hasta que no se corra, la pantalla `/vales` avisa que falta el script en
lugar de romper, y el resto de la aplicación sigue andando igual.

## Paso 2 — la sucursal de cada usuario

El vale se numera según **quién lo pide**, así que cada responsable de
sucursal tiene que tener la suya cargada:

```sql
update usuarios set sucursal_codigo = 'CAT' where usuario = 'ramon';
```

Al que la tenga cargada la pantalla no se la pregunta: es un campo menos
y una discusión menos. Al que no —administración, mantenimiento— se la
pide en el formulario.

## El número

Lo genera el sistema, nunca el usuario: `CAT-00001`, `COR-00047`.

- El correlativo es **por sucursal**, no global, y no se reinicia por año.
- Es **inmutable**: el número de un vale rechazado o anulado no se
  reutiliza. Por eso en el módulo no hay ningún borrado de vales.
- Se toma bloqueando la fila del contador de esa sucursal (`select …
  for update`) dentro de la misma transacción que inserta el vale. Dos
  sucursales cargando en el mismo segundo no se estorban —son dos filas—
  y dos usuarios de la misma sucursal esperan uno al otro.

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

- **No se compra ni se repara con el vale en `SOLICITADO` o
  `RECHAZADO`.**
- **No se rinde una factura de taller sin un vale `CERRADO`.** La
  validación vive en el módulo de gastos —acá, los servicios externos de
  `/ordenes`—: el formulario pide el vale y el servidor lo verifica.
- Un vale rechazado es **terminal**. Si la sucursal insiste, carga uno
  nuevo citando el anterior, y así queda a la vista cuántas veces se
  insistió.
- El taller tiene **24 horas hábiles** para contestar. Con
  `urgencia = UNIDAD_PARADA` la respuesta es inmediata y el vale aparece
  arriba de la bandeja, marcado.

## El historial

Cada cambio de estado escribe su renglón en `vale_eventos`, en la misma
transacción: quién, cuándo y con qué comentario. **No se edita ni se
borra**, y no por convención: un trigger de la base lo impide.

Es la parte del módulo que parece burocracia hasta el día en que hay que
contestar quién autorizó un gasto que ya se hizo.

## Lo que no necesita vale

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
verbalmente y el vale se carga después, marcando *«se autorizó en ruta»*.
El sistema acepta la fecha del hecho anterior a la de carga, y cuenta las
regularizaciones por sucursal y por mes.

Es un **indicador, no un castigo**: sirve para ver dónde el circuito no
llega, no para retar a nadie.

Las 48 horas hábiles no bloquean la carga —un vale cargado tarde es
mejor que un vale no cargado—: la pantalla avisa que quedó fuera de
término y el indicador lo cuenta.

## Las vistas

| Vista | Para qué |
|---|---|
| Nuevo vale | Seis campos. La sucursal no elige el número ni el estado. |
| Bandeja del taller | Los `SOLICITADO` de toda la red, por urgencia y antigüedad, con aprobar o rechazar en un clic. |
| Mi sucursal | Los propios, con su estado. |
| Toda la red | Lectura para cualquier sucursal, con filtros. Que cada responsable vea el resto no es un detalle: compara tiempos de respuesta y ordena solo. |
| Ficha de unidad | El historial por patente. Es la vista que detecta la unidad que entra tres veces por la misma falla. |
| Indicadores | Por sucursal y por mes. |
| Vale imprimible | Una carilla con número, unidad, km, falla, taller, monto, quién pidió y quién autorizó, más las firmas. Es lo que se grapa a la factura. |

## Los indicadores

- **% de facturas de taller rendidas con vale** (objetivo 100%).
- **Reparaciones rendidas sin vale previo** (objetivo 0).
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

- Un vale **preventivo** cerrado registra el service de la unidad y
  recalcula el próximo, igual que una orden preventiva. Si la unidad no
  tiene plan de mantenimiento asignado, el vale **cierra igual** y la
  pantalla avisa: la sucursal que tiene la factura en la mano no puede
  quedar trabada por una parametrización que no depende de ella. Se
  asigna el plan y se registra el service desde `/control`.
- La factura del taller entra como **servicio externo** en `/ordenes`,
  eligiendo el vale de la lista de cerrados sin rendir. Ahí quedan atados
  el gasto y la intervención técnica.

## Si hace falta aflojar el candado

Mientras la red se acostumbra, se puede permitir rendir sin vale:

```sql
update vales_ajustes set exigir_vale = false;
```

Y para volver a exigirlo:

```sql
update vales_ajustes set exigir_vale = true;
```

Es a propósito que sea una línea de SQL y no un botón en la pantalla:
apagar el circuito tiene que costar más que usarlo.
