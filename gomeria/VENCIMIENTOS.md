# Pasar los vencimientos a la base

Hoy los vencimientos viven en la planilla **VENCIMIENTO DE LICENCIAS**, con
una hoja por sucursal y un panel de Apps Script arriba. La app hace lo mismo
contra Supabase, y la planilla se puede seguir usando en paralelo mientras
tanto: la importación se puede correr las veces que haga falta.

## Qué cambia respecto de la planilla

| En la planilla | En la base |
|---|---|
| Una hoja por sucursal | Una tabla, la sucursal es un campo |
| Una columna por tipo de documento | Una fila por documento, el tipo es un campo |
| Renovar = pisar la fecha vieja | Renovar = fila nueva, la vieja queda de historial |
| Los días que faltan son fórmulas | Los calcula la base contra la fecha de hoy |
| Un chofer que no está en ninguna hoja no existe | La vista de faltantes lo muestra |

Lo último es la diferencia que importa. La planilla solo puede avisar de lo
que alguien cargó; lo que nunca se cargó no aparece en ningún lado, y así es
como se pasan de largo.

## Paso 1 — las tablas

En Supabase, **SQL Editor**, pegar y correr `gomeria/06_vencimientos.sql`.

Vienen cargados los cuatro tipos que se controlan hoy: **VTV**,
**Matafuegos**, **Licencia municipal** y **Licencia profesional**. Seguro,
RUTA, LiNTI y psicofísico quedan cargados pero apagados; si alguna vez se
empiezan a seguir, se prenden con:

```sql
update tipos_vencimiento set activo = true where nombre = 'Seguro';
```

y aparecen solos en la pantalla, sin tocar código.

## Paso 2 — traer la planilla

En Drive: **Archivo → Descargar → Microsoft Excel (.xlsx)**. Después:

```bash
export SUPABASE_DB_URL='...la cadena de Supabase...'

# primero mirar qué haría, sin escribir nada
python gomeria/importar_vencimientos.py "VENCIMIENTO DE LICENCIAS.xlsx" --probar

# y cuando esté bien
python gomeria/importar_vencimientos.py "VENCIMIENTO DE LICENCIAS.xlsx"
```

Se puede correr todas las veces que haga falta: una fecha que ya está no se
duplica, y una fecha nueva entra como renovación arriba de la anterior. Eso
permite seguir cargando en la planilla un tiempo y sincronizar cuando se
quiera.

De la planilla de hoy entran **144 documentos** de 49 chóferes y 66 patentes,
repartidos en las 7 sucursales. Las columnas de días que faltan no se
importan: son fórmulas, y la base las recalcula sola.

## Lo que la importación deja anotado

- **AG979NJ** no estaba en la base de unidades: se da de alta. La planilla de
  licencias tiene camionetas y unidades que la de gomería no tiene.
- **Frutos Javier** no tiene dominio cargado, así que su VTV y su matafuego no
  se pueden colgar de ninguna unidad. Le falta el dominio en la planilla.
- **131 casillas vacías**: documentos que la planilla nunca tuvo cargados.

## Por qué los números no dan exactamente igual que el panel viejo

Contra el panel de Apps Script, coinciden:

- **123 al día**, clavado.
- **49 chóferes y 66 patentes**, y las siete sucursales una por una: Larga
  Distancia 19 y 38, Catamarca 8 y 8, Tucumán 3 y 3, Buenos Aires 8 y 8,
  La Rioja 5 y 5, Córdoba 3 y 2, Belén 3 y 2.
- **Tucumán**: 3 vencidos y 1 por vencer en los dos.

La única diferencia está en dónde cae la raya entre *vencido* y *por vencer*:
el panel muestra 15 y 6, la base 17 y 4. **El total es el mismo, 21.** Son dos
documentos que el panel todavía cuenta como por vencer. Lo más probable es que
el panel lea las columnas de días de la planilla, que quedan con el valor de
la última vez que la planilla recalculó, mientras que la base los cuenta
contra el día de hoy en cada consulta.

El **"sin cargar"** sí es distinto a propósito: el panel dice 86 y la app 130,
porque la app cruza todas las unidades activas contra todos los tipos, no solo
las filas que existen en la planilla. Un camión sin VTV cargada es un hueco
real aunque nadie le haya hecho la fila.
