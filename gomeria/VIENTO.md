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
