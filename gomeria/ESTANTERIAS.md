# Estanterías del depósito de repuestos

Pestaña **Estanterías** de `/repuestos`. Tres columnas: repuestos a la
izquierda, plano del depósito (visto desde arriba) en el centro y la
estantería elegida vista de frente, piso por piso, a la derecha.

## Base

Correr `gomeria/47_estanterias.sql` en el SQL Editor de Supabase. Crea:

- `repuestos_estanterias`: nombre, pasillo, posición en el plano (`x_cm`,
  `y_cm`), largo, profundidad, alto, pisos, módulos por piso y frente
  (norte, sur, este u oeste: el lado del pasillo).
- `repuestos_ubicaciones`: una fila por repuesto con estantería, piso y
  módulo. Un repuesto tiene una sola ubicación; moverlo la reemplaza.

Sin el script, la pestaña muestra qué falta correr y el resto del módulo
sigue funcionando.

## Armar depósito (permiso «gestiona»)

- **+ Estantería**: una sola, con sus medidas, pisos y módulos.
- **+ Pasillo**: una fila o dos filas enfrentadas de N estanterías iguales,
  con el ancho del pasillo y la separación entre estanterías. Nombres
  correlativos (A1…A4 frente a A5…A8). Vista previa antes de crear.
- En el plano, las estanterías se arrastran (saltos de 25 cm). Desde la
  ficha: editar, girar 90°, duplicar y borrar. Borrar deja sin ubicación lo
  que tenía; no toca el stock. No se puede quitar pisos o módulos ocupados.

## Ubicar repuestos

- Arrastrar un repuesto de la lista a un casillero, o a una estantería del
  plano (pide piso y módulo).
- Sin arrastrar (celular): elegir el repuesto y tocar el casillero.
- Siempre se confirma antes de guardar; si ya tenía ubicación, se muestra
  la actual y la nueva.
- La búsqueda resalta en el plano las estanterías con repuestos que
  coinciden. La tabla de **Repuestos** muestra la ubicación (`A1 · P2 · M3`).

## Verificación

- `python3 -m unittest tests.test_estanterias`
- `node tests/estanterias_smoke.cjs` (Playwright; API simulada).
