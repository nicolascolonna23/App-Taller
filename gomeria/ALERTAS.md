# Alertas

Todo lo que hay que mirar hoy, en un solo lado.

Los avisos estaban repartidos: los vencimientos en su pantalla, los
services en una planilla de Google, las cargas raras de combustible en
ningún lado y las gomas al límite en Gomería. Nadie mira cuatro pantallas
todos los días, así que en la práctica no se miraba ninguna.

Se prende corriendo **`20_alertas.sql`** en Supabase → SQL Editor → Run.

## Las cuatro fuentes

| Qué avisa | De dónde sale | Cuándo |
|---|---|---|
| **Vencimientos** | `v_vencimientos_hoy` | vencido, o dentro del aviso de ese tipo de documento |
| **Services** | tabla `services` + el odómetro del satelital | pasado de km, o faltando menos de 15.000 |
| **Combustible** | `combustible_cargas` | una carga sola de más de 450 litros |
| **Cubiertas** | `v_alertas_cubiertas` | al mínimo de dibujo o cerca (ver `DESGASTE.md`) |

## Cómo se ordena

Por urgencia, no por fuente. Al que abre la pantalla a la mañana no le
importa si lo que tiene encima es una VTV o un service: le importa cuál lo
deja tirado primero.

Primero por gravedad —rojo, amarillo, gris— y adentro de cada nivel por
**consecuencia**, que es este orden fijo:

```
vencimiento  →  cubierta  →  service  →  combustible
```

El papel para el camión hoy en un control de ruta. La goma al mínimo puede
reventar. El service pasado lo rompe en algún momento. La carga rara ya
pasó y lo que queda es entender qué fue.

No se ordena por el número de cada fuente porque **días, milímetros,
kilómetros y litros no están en la misma escala**: comparar "faltan 5 días"
con "faltan 5.000 km" no compara nada.

## Silenciar

Sin esto, la carga de 480 litros del camión que sí tiene tanque grande
aparece todos los días, para siempre, hasta que la pantalla deja de
leerse.

Silenciar **pide motivo**, y queda con el nombre de quien la silenció.
Dentro de seis meses, *"alguien la ocultó"* no le sirve a nadie; lo que
sirve es *"el tanque de este camión es de 600 litros, la carga estaba
bien"*.

Se puede silenciar para siempre o hasta una fecha: sirve para *"ya lo
pedí, avisame de nuevo la semana que viene"*. Lo silenciado se ve con **ver
las silenciadas** y se puede reactivar.

Un service nuevo reactiva solo la alerta de esa unidad: es un hecho nuevo,
lo que se había silenciado del anterior ya no aplica.

## Los services

Hasta ahora vivían en la planilla de Google. Ahora están en la base, así
las alertas no dependen de que una planilla siga compartida.

Cada fila es un service hecho: unidad, fecha, kilómetros, qué se hizo y
**cada cuántos km le toca de ahí en más**. No se pisa el anterior: el
historial de cuándo se le hizo cada uno a un camión es la mitad de lo que
se mira cuando hay que decidir si un motor está bien cuidado.

`cada_km` va en el service y no en la unidad porque cambia con el tiempo
—un camión que pasa a hacer distribución cambia de plan— y así queda
registrado desde cuándo rige el nuevo.

Los kilómetros de hoy salen del satelital, así que el "faltan X km" se
actualiza solo todas las mañanas sin que nadie toque nada.

### La carga inicial

Para arrancar con la historia que ya está en la planilla:

```bash
python3 gomeria/cargar_services.py services.csv --simular   # muestra qué haría
python3 gomeria/cargar_services.py services.csv             # lo hace
```

Reconoce los nombres de columna como suelen venir ("Dominio", "Km del
service", "Cada cuántos km"), sin importar mayúsculas ni acentos, y las
fechas en cualquiera de las formas que usa una planilla argentina. Antes
de escribir nada valida el archivo entero: si hay una patente que no
existe o un kilometraje que no se entiende, lo dice y no carga nada.

Se puede correr dos veces sin duplicar: se saltea el service que ya esté
con la misma unidad, la misma fecha y el mismo kilometraje.

## Cuándo avisar

Los cuatro números se cambian desde la pantalla, en la solapa **Cuándo
avisar**, si sos encargado o admin:

| Número | Por defecto | Qué hace |
|---|---|---|
| Carga máxima | 450 litros | más que esto en una sola carga se avisa |
| Días de combustible | 90 | hasta cuándo para atrás se miran las cargas |
| Service urgente | 5.000 km | menos que esto para el próximo es rojo |
| Aviso de service | 15.000 km | desde acá se avisa, en amarillo |

Los dos de service son los mismos que ya usaba el tablero de Services,
para que las dos pantallas no digan cosas distintas del mismo camión.

Los días de aviso de cada vencimiento no están acá: son de cada tipo de
documento y se cambian en Vencimientos, donde siempre estuvieron.

## Si falta una fuente

Los módulos se prenden de a uno y el SQL se corre a mano. Si falta la
tabla de una fuente, la pantalla **dice cuál falta** en lugar de mostrar
una lista corta como si estuviera todo bien. Un tablero que se calla lo
que no sabe es peor que no tener tablero.
