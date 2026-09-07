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

Hasta que no se corra, la pantalla `/ordenes` avisa que falta el script en
lugar de romper, y el resto de la aplicación sigue andando igual.

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
