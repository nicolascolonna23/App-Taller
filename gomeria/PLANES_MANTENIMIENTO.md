# Planes de service

Cada cuánto le toca el service a una unidad no es un número que se escribe
al cargarlo: es un **plan**. El plan dice qué service es y cada cuántos
kilómetros se hace, se define una vez y después se le asigna a las patentes.

Así el criterio no depende de lo que escriba el que carga el service. Antes,
un cero de más en «cada 45000» cambiaba cuándo le tocaba a esa unidad y nadie
se enteraba.

## Instalación

En Supabase → **SQL Editor**, ejecutar completos y en este orden:

1. `gomeria/22_planes_mantenimiento.sql` — crea los planes.
2. `gomeria/23_planes_por_unidad.sql` — permite que una unidad tenga varios.

Los dos son idempotentes y no borran historial: se pueden correr las veces
que haga falta. Lo que ya estaba asignado con un solo plan por patente pasa
solo a la lista nueva.

## Varios planes por unidad

Un auto tiene un solo service, cada 10.000. Un camión no: un Hi-Way tiene un
M1 cada 45.000, un M2 cada 90.000 y un M3 cada 135.000, y **cada uno cuenta
y avisa por su cuenta**. Por eso la asignación es una lista y no una sola
opción: con un solo plan por unidad, elegir el M3 apagaba el aviso del M1.

En la pantalla de services eso se ve como un renglón por unidad y plan: un
camión con los tres planes son tres renglones, cada uno con su propio
«cuánto falta».

## Dónde se toca

| Dónde | Qué se hace |
|---|---|
| **Control de service** → `Parametrización` | crear, modificar y eliminar planes; asignarlos a una patente o a todas las de un modelo |
| **Flota** → ficha de la unidad | marcar qué planes le tocan a esa patente |
| **Alertas → Services** → `registrar` | anotar un service diciendo de qué plan es |

Asignar por modelo existe porque el plan lo fija la fábrica por modelo: con
cien unidades, hacerlo de a una es media tarde. Reemplaza lo que las
unidades de ese modelo tuvieran.

## Dónde queda cada dato

- `mantenimiento_planes`: nombre, descripción e intervalo en kilómetros de
  cada plan (M1, M2, Autos 10K…).
- `unidad_planes`: qué planes le tocan a cada patente.
- `services`: el historial real. Guarda fecha, km, taller, de qué plan fue
  (`plan_id`) y una foto del intervalo usado entonces (`cada_km`), para que
  el historial no cambie si después se reasigna el plan.
- `odometros`: las lecturas de kilometraje del satelital.
- `v_services_hoy`: una fila por unidad y plan, con el último service de ese
  tipo, el próximo y cuánto falta.

## Qué pasa con lo que ya estaba

Los services que vinieron de las planillas quedan sin plan: ahí el tipo no
figuraba. Sirven igual como **punto de partida**: mientras no haya ningún
service registrado de un plan, la cuenta arranca del último service que
haya, y la pantalla lo aclara con «punto de partida prestado». Cuando se
registra el primer M1 de verdad, esa unidad empieza a contar su M1 desde ahí.

Una unidad sin ningún plan asignado sigue funcionando como venía: manda el
intervalo de su último service y, si tampoco hay, 15.000 km.

## Eliminar un plan

Si nunca se usó, se borra. Si ya tiene services cargados, se apaga: deja de
aparecer en las listas y se les saca a las unidades, pero el historial de lo
que se hizo bajo ese plan no se toca. Borrarlo sería perder de qué fue cada
service.
