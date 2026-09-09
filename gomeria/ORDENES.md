# Órdenes de trabajo

La hoja que se abre cuando una unidad entra al taller y se cierra cuando
sale. Es la que hoy se llena a mano en papel: lo que pidió el chofer, lo
que se encontró, lo que se le hizo y lo que se le puso.

Dos clases de orden, la misma tabla:

| | Interna | Externa |
|---|---|---|
| Quién hizo el trabajo | El taller propio | Un tercero |
| Cómo se carga | Se abre, se le van sumando trabajos y repuestos, se cierra | Patente, fecha, número de factura y monto |
| Cuándo se cierra | Cuando la unidad sale | Nace cerrada: lo que pasó ya pasó |
| Toca el stock | Sí | No |

Las dos aparecen juntas en el historial de la unidad, que es la pregunta
que se hace de verdad: *¿qué le hicimos a este camión y cuánto nos costó?*

## Paso 1 — las tablas

En Supabase, **SQL Editor**, pegar y correr `gomeria/15_ordenes.sql`. Se
puede correr las veces que haga falta: no borra nada.

En una base que ya tenía órdenes y services, correr además
`gomeria/21_ordenes_preventivas.sql`. Agrega la clasificación y vincula la
orden con su registro de service sin modificar los datos anteriores.

Hasta que no se corra, la pantalla `/ordenes` avisa que falta el script en
lugar de romper, y el resto de la aplicación sigue andando igual.

## Preventivo o correctivo

Toda orden nueva y todo servicio externo pide la clasificación, la fecha y
los kilómetros. Una orden interna preventiva se registra también en `services`
cuando se cierra; un servicio externo preventivo lo hace al guardarse porque
nace cerrado. Los correctivos quedan en el historial de órdenes, pero no
reemplazan el último service programado.

La tabla `odometros` no guarda services: contiene las lecturas diarias de Hawk.
La vista `v_services_hoy` combina el último `services` con el odómetro más
reciente para calcular cuándo toca el próximo mantenimiento.

## Cargar un servicio externo sacándole una foto a la factura

En el formulario de servicio externo hay un botón para subir la factura
—una foto del celular o el PDF que mandó el taller, hasta cuatro hojas— y
que se complete sola: taller, número, fecha, monto, kilómetros, qué se
hizo y de qué unidad es.

**Lo que lee no se guarda solo.** Llena el formulario de siempre, marca en
naranja los campos que completó y avisa arriba qué no pudo leer con
seguridad. Después hay que mirarlo y apretar Guardar. Una factura mal
leída que entra sola al historial de una unidad es peor que no tener la
foto: nadie sabe después si el número está bien.

Dos cosas que hace y conviene saber:

- **La patente se valida contra la flota.** Claude recibe el listado de
  patentes y elige entre esas. Si lo que está escrito en la factura no se
  parece a ninguna, el campo queda vacío y lo elige la persona: puede ser
  el auto de otro cliente del taller.
- **Las fotos se achican en el navegador** antes de subirlas. Una foto de
  celular son 4 MB de los cuales sobra el 90%, y subirla entera desde el
  taller con media barra de señal es la diferencia entre que ande y que no.

Necesita `ANTHROPIC_API_KEY` configurada. Si no está, el botón lo dice y
la carga a mano sigue funcionando igual.

## El enganche con el stock

Es lo único delicado del módulo, así que conviene tenerlo claro.

Cada repuesto que se carga a una orden **escribe una Salida real** en
`repuestos_movimientos`, que es de donde sale el stock de todo el sistema.
No hay una cuenta del depósito y otra del taller: hay una sola.

- La salida queda con la **patente** de la unidad y `OT <número>` en las
  observaciones, así en la pantalla de Repuestos se entiende de dónde
  salió sin tener que venir hasta acá.
- **Sacar el renglón** de la orden borra ese movimiento y el repuesto
  vuelve al estante.
- **Anular** la orden devuelve todos sus repuestos de una.
- Un renglón cargado **sin código** (algo que se compró para ese trabajo y
  nunca estuvo en el depósito) se anota en la orden pero no toca el stock.

Una orden cerrada no se toca. Si hay que corregirla, un administrador la
reabre, la corrige y la vuelve a cerrar.

## Quién puede qué

| | Chofer / lectura | Encargado | Admin |
|---|---|---|---|
| Ver las órdenes y el historial | Sí | Sí | Sí |
| Abrir, cargar y cerrar | No | Sí | Sí |
| Cargar un servicio externo | No | Sí | Sí |
| Anular | No | Sí | Sí |
| Reabrir una cerrada | No | No | Sí |
| Borrar | No | No | Sí |

## Imprimir

Al cerrar una orden la pantalla ofrece imprimirla; el botón **Imprimir**
está siempre, también en las que ya están cerradas. La hoja se arma en el
navegador con el formato del papel que se usa hoy —datos del vehículo,
requerimiento, insumos, trabajos, total y firmas— y sale en blanco y negro
sin importar el tema con el que se esté mirando la aplicación.

## Reglas que hacen ruido a propósito

- Una unidad **no puede tener dos órdenes internas abiertas**: si no, los
  repuestos de un mismo trabajo terminan repartidos en dos hojas.
- Una orden **sin ningún trabajo, repuesto ni diagnóstico no se cierra**.
  Cerrar en blanco es la forma de que el historial no sirva para nada.
- La **misma factura** de la misma unidad no se carga dos veces.
- Al cerrar, si el kilometraje de la orden es mayor que el del maestro,
  el maestro se pone al día solo.
