# Viento en ruta

La pantalla `/viento` muestra, para cada viaje Buenos Aires ↔ Catamarca, el
viento que encontró el camión en la ruta hora por hora. Pasa por Córdoba capital.

## De dónde sale cada cosa

| Qué | De dónde |
|---|---|
| Los viajes | `reporte_hojas.xlsx` del BI. Lo baja el servidor y lo guarda media hora en memoria. El botón **Releer planilla** lo vuelve a bajar. |
| El viento | Open-Meteo, reanálisis ERA5: viento medio y ráfaga a 10 m, hora por hora. Tarda unos cinco días en publicarse. |
| El recorrido | `RUTA` en `gomeria/viento.py`: RN 9 hasta Córdoba, Deán Funes, Recreo, Chumbicha, Catamarca. Unos 1.120 km. |

El camión se ubica **suponiendo velocidad pareja** entre la salida y la
llegada. Hawk no guarda la traza, solo el odómetro. Los casos que se estiman:

- Viaje sin hora de salida: se supone que salió a las 8:00.
- Viaje sin llegada, con una llegada imposible o con una de más de 48 horas:
  se estima a 60 km/h de promedio.

La pantalla avisa cuántos viajes cayeron en cada caso.

## Cómo se lee

- **En contra**: la parte del viento que le pega de frente al camión, en km/h.
  Positivo frena y negativo empuja. El viento cruzado no suma ni resta.
- **Cómo le fue**: en contra fuerte (15 km/h o más), en contra (6 o más),
  neutro, a favor (−6 o menos).
- **Frente · costado · cola**: qué parte de las horas del viaje tuvo el viento
  dentro de los 45° de cada lado.

## Las tres solapas

| Solapa | Qué hay |
|---|---|
| **Viajes** | la lista, un viaje por renglón, con el detalle hora por hora |
| **Indicadores** | combustible y viento, horarios, meses, tramos y seguridad |
| **Mapa del viaje** | se busca por número de hoja; se ve la ruta sobre el mapa y el viento de toda la ruta a cada hora |

Se puede entrar directo a un viaje: `/viento#mapa=1234`.

## Indicadores

El cálculo está en `gomeria/viento_indicadores.py`.

### Combustible y viento

No hay un número de litros por viaje en ningún lado, así que se arma con las
cargas de `combustible_cargas` (nuestra planilla). La idea es que el camión
sale con el tanque lleno y que lo que carga después es lo que gastó en ese
viaje:

- El viaje se queda con las cargas de su patente **después del día de salida
  y hasta el día siguiente a la llegada**.
- Si la misma patente vuelve a salir antes, el viaje corta ese día. La carga
  del día de salida corresponde al viaje anterior.
- Los km son los del recorrido.
- Se descartan los viajes con un consumo que no es creíble (menos de 18 o
  más de 70 L/100 km): son cargas parciales o viajes que se mezclaron.

Con eso sale:

- **La relación (r)** entre el viento en contra y el consumo. Solo se toma
  como **confiable** con 10 viajes o más y un t de Student de 2 o más (≈95%).
- **Cada 10 km/h en contra**: cuántos L/100 km suma, y cuántos litros por
  viaje.
- **Lo que costó el viento en contra** en el período, en litros y en pesos (al
  precio promedio de esas mismas cargas). También lo que devolvió el viento a
  favor.
- **El consumo sin viento**, por camión y por chofer: el que habría tenido
  con viento neutro. Es la comparación justa entre choferes.

### Los que salen solo del viento

- **Según la hora de salida**, en franjas de 3 horas, de ida y de vuelta.
  Dice cuál es la franja con menos viento en contra (hacen falta 3 viajes
  o más en la franja). Solo cuentan los viajes con hora de salida real.
- **Mes a mes**: en qué época cuesta más cada sentido.
- **Tramo por tramo**: dónde pega más fuerte.
- **Seguridad**: horas con ráfagas de 70 km/h o más, o con viento cruzado de
  40 km/h o más, y la lista de los viajes que las tuvieron. Los umbrales
  están al principio de `viento_indicadores.py`.

## La patente de cada viaje

La planilla trae en una sola columna varias patentes: el tractor, el semi
y a veces otra. Se leen todas, con cualquier separador, y **se cruzan con
Flota**. La que manda es la primera que es de larga distancia (sucursal
`LAD` o un uso que diga LARGA, el mismo criterio que el resto del sistema) y
que no es un semi. Con esa patente se buscan las cargas de combustible.

Un viaje sin ninguna patente de larga distancia se ve igual, con el viento,
pero no entra en los indicadores de combustible. La pantalla avisa cuáles
patentes trajeron esas hojas, para catalogarlas en Flota si corresponde.

Si la columna de patentes no se reconoce por el nombre, se buscan patentes
en la fila entera.

## Si la planilla no se lee

Las columnas se reconocen por el nombre: fecha y hora de salida, fecha y hora
de llegada, origen, destino (o una sola columna de recorrido), patente, chofer
y número de hoja. Si falta la fecha de salida o el origen y el destino, la
pantalla muestra el error junto con las columnas que encontró. El arreglo es
agregar ese nombre en `COLUMNAS`, en `gomeria/viento.py`.

El origen y el destino se reconocen con las listas `BUENOS_AIRES` y `CATAMARCA`
del mismo archivo.

## Puesta en marcha

1. Correr `gomeria/39_viento.sql` en Supabase. Crea la tabla donde se guarda el
   viento ya bajado y le habilita el módulo a admin y encargado. Sin la tabla
   la pantalla anda igual, pero vuelve a pedir el viento después de cada
   reinicio.
2. Uso comercial: el Open-Meteo gratuito es solo para uso no comercial. Con
   una suscripción (desde USD 29/mes), la clave va en la variable
   `OPEN_METEO_APIKEY` de Render.
3. Opcional: `VIENTO_HOJAS_URL`, si la planilla cambia de dirección.
