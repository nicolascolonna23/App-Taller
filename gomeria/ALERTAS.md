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

Los services terminados se guardan en la tabla `services` de Supabase. Una
orden de trabajo o reparación externa marcada como **preventiva** genera además
una fila vinculada en esa tabla; una correctiva queda solamente en el historial
de órdenes. La vinculación se instala con `21_ordenes_preventivas.sql`.

`odometros` es otra cosa: conserva una lectura diaria por unidad que llega de
Hawk. `v_services_hoy` cruza el último registro de `services` con la lectura más
reciente de `odometros` para calcular cuántos kilómetros faltan. Una orden nunca
inventa ni reemplaza una lectura de Hawk.

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

### Cuando los kilómetros no cierran

Si el satelital marca **menos** kilómetros de los que la unidad tenía en su
último service, la resta no significa nada: o le cambiaron el equipo de GPS
y el contador arrancó de nuevo, o la unidad dejó de reportar.

Esas unidades quedan en estado **«Km no coinciden»** y avisan como alerta
leve, diciendo los dos números. No se las pinta de «al día»: una unidad que
puede estar pasada de service mostrada en verde es peor que no tener la
pantalla. Y no se las esconde: mientras el odómetro no se arregle, esa
unidad no puede avisar de su service, y eso hay que saberlo.

En la carga inicial de la flota aparecieron nueve así, con diferencias de
hasta 870.000 km contra la planilla.

### La carga inicial

Para arrancar con la historia que ya está en las planillas. Se le pasan
todas juntas —una por residencia es lo normal— porque validarlas de a una
obliga a acordarse de cuál ya se cargó:

```bash
python3 gomeria/cargar_services.py ServicesLAD.csv ServicesBUE.csv --simular
python3 gomeria/cargar_services.py ServicesLAD.csv ServicesBUE.csv
```

Está hecho para leer las planillas **como son**, no como habría que
escribirlas:

- **La tabla no arranca en la primera fila.** Las planillas traen arriba un
  título, la fecha de la última carga y filas en blanco. Busca dónde
  empieza la tabla en vez de pedir que la limpien.
- **Hay encabezados repetidos.** La de larga distancia tiene dos columnas
  que se llaman PATENTE, porque Google mete un salto de línea adentro de
  una celda; la segunda son los kilómetros de hoy. Gana la primera.
- **Los números vienen a la argentina.** `1.719.118` y `"281.964,00"`.
- **Las fechas también**, y de un solo dígito: `20/7/26`, `28/8/2026`.

**De dónde sale el «cada cuántos km».** Ninguna planilla lo tiene como
columna, pero todas tienen el próximo service: el intervalo se saca de
*próximo menos último*. En las planillas de Diemar eso da 40.000 y 45.000
km según el camión, y 10.000, 20.000 o 30.000 en los de distribución —
justo lo que un valor fijo por defecto se comería.

Una unidad que está en la planilla pero todavía no tiene service se
saltea y se cuenta aparte: no es un error del archivo, es una unidad sin
service.

Antes de escribir nada valida **todos** los archivos. Si una patente no
existe en el maestro no carga nada de ninguno: una patente que no está es
señal de que el maestro quedó viejo, y cargar el resto lo taparía.

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
