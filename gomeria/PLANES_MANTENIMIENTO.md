# Planes de mantenimiento

## Instalación

En Supabase → **SQL Editor**, ejecutar completo
`gomeria/22_planes_mantenimiento.sql`. Es idempotente y no elimina el
historial existente.

## Dónde queda cada dato

- `mantenimiento_planes`: nombre, descripción e intervalo en kilómetros de
  cada plan reutilizable (M1, M2, Autos 10K, etc.).
- `unidades.mantenimiento_plan_id`: plan actualmente asignado a cada patente.
- `services`: historial real de services realizados. Conserva fecha, km, tipo
  e intervalo usado en ese momento.
- `odometros`: lecturas históricas de kilometraje importadas del satelital.
- `v_services_hoy`: combina el último service, el plan actual y el último
  odómetro para calcular próximo service y kilómetros restantes.

El plan asignado manda para el próximo vencimiento. Si una unidad todavía no
tiene plan, se conserva la compatibilidad: se usa el intervalo del último
service y, si tampoco existe, 15.000 km.

La aplicación consulta Supabase al abrir la pantalla y luego se actualiza de
forma periódica. Eso no convierte al satelital en un flujo en tiempo real: el
kilometraje disponible sigue dependiendo de la frecuencia con que se importen
las lecturas a `odometros`.
