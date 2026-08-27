# Chat interno de consultas

Un asistente al que le preguntás en castellano por clientes y cuenta corriente,
y contesta consultando los reportes del sistema.

> Ejemplos: *¿cuánto debe CONFECAT?* · *los 10 con más deuda vencida* ·
> *qué clientes de Catamarca se pasaron del límite de crédito* ·
> *cuánto facturamos en marzo*

## Cómo está armado

```
reporte_clientes.xlsx  ─┐
reporte_deuda.xlsx     ─┴─► ingesta.py ──► datos.db (SQLite)
                                               ▲
navegador ──► servidor.py ──► herramientas ────┘
                    │
                    └──► API de Claude   (la clave vive acá, nunca en el navegador)
```

Dos decisiones que conviene entender:

**El modelo no ve las planillas.** Ve seis herramientas (`buscar_cliente`,
`resumen_cliente`, `ranking_deudores`, `comprobantes_cliente`, `resumen_general`
y `consultar_sql`) y las usa para consultar. Por eso puede trabajar sobre 71.000
movimientos: nunca se le manda la tabla entera, solo el resultado de la consulta.

**La ingesta baja los xlsx desde el servidor, no desde el navegador.** Una
página web no puede leer `bi.sistemaexpreso.com.ar` directamente: el navegador
lo bloquea por CORS y por mezclar http con https. Un proceso del servidor sí
puede, y de paso los datos nunca pasan por la máquina del usuario.

## Probarlo

```bash
pip install -r chat/requisitos.txt

# 1. Armar la base a partir de los reportes
python3 chat/ingesta.py --clientes ruta/reporte_clientes.xlsx \
                        --cuenta-corriente ruta/reporte_cuenta_corriente.xlsx

# 2. Levantar el chat
export ANTHROPIC_API_KEY=sk-ant-...        # en Windows: set ANTHROPIC_API_KEY=...
python3 chat/servidor.py
```

Y abrir http://127.0.0.1:8000.

Con `config.json` (copiá `config.json.ejemplo`) alcanza con `python3 chat/ingesta.py`
y los baja solo de las URLs del BI.

## Ponerlo en el servidor de la empresa

1. **Ingesta programada.** Que `ingesta.py` corra solo cuando se actualizan los
   reportes. En Linux, un cron; en Windows, el Programador de tareas:

   ```
   0 7 * * *  cd /opt/chat && /usr/bin/python3 ingesta.py >> ingesta.log 2>&1
   ```

   La ingesta reescribe las tablas de cero, así que se puede correr las veces
   que haga falta. Tarda menos de un minuto con estos volúmenes.

2. **El servicio.** `python3 servidor.py --host 0.0.0.0 --puerto 8000` y dejarlo
   como servicio (systemd en Linux, NSSM en Windows) para que levante solo.

3. **Detrás del servidor web interno.** Conviene que Apache/Nginx/IIS haga de
   proxy hacia el 8000 y sea el que resuelve el login. El chat no trae usuarios:
   asume que quien llega ya está autorizado.

4. **Que no salga a internet.** El servidor necesita alcanzar `api.anthropic.com`,
   nada más. La pantalla en sí tiene que quedar solo en la red interna o detrás
   de la VPN: muestra deuda, márgenes y datos de contacto de todos los clientes.

## Conectarlo a la base de verdad

Hoy la fuente son dos xlsx exportados. Cuando quieras leer el sistema en vivo,
**no hay que reescribir el chat**: todas las consultas pasan por una sola
función en `servidor.py`.

```python
def conectar():
    cx = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)
    cx.row_factory = sqlite3.Row
    return cx
```

Para apuntar al motor real se cambia esa función y nada más. Según qué tengan:

| Motor | Paquete | Conexión |
|---|---|---|
| SQL Server | `pip install pyodbc` | `pyodbc.connect("DRIVER={ODBC Driver 18 for SQL Server};SERVER=...;DATABASE=...;UID=...;PWD=...")` |
| MySQL / MariaDB | `pip install PyMySQL` | `pymysql.connect(host=..., user=..., password=..., database=...)` |
| PostgreSQL | `pip install psycopg[binary]` | `psycopg.connect("host=... dbname=... user=... password=...")` |

Tres cosas a tener en cuenta al hacer el cambio:

- **Usuario de solo lectura.** Creá un usuario que solo pueda hacer `SELECT`
  sobre las tablas de clientes y cuenta corriente. El chat nunca escribe, y con
  un usuario limitado eso queda garantizado por la base y no por el código.
- **Los `?` de los parámetros cambian según el motor.** SQLite y ODBC usan `?`;
  PyMySQL y psycopg usan `%s`. Son las consultas de las seis herramientas.
- **Las vistas.** Lo más prolijo es crear en la base dos vistas llamadas
  `clientes` y `cuenta_corriente` con exactamente las columnas que usa hoy el
  chat (están listadas en el docstring de `consultar_sql`). Así las consultas
  quedan igual y toda la traducción de nombres vive en la base.

Mientras tanto, la ingesta desde xlsx sirve de puente: funciona hoy y no
condiciona el paso siguiente.

## Cosas que conviene saber de estos datos

- **La deuda no es la suma de "Monto Pendiente".** Los recibos y las órdenes de
  pago vienen en negativo: sumando todo junto da −$1.400 millones. El chat
  calcula `deuda` como el pendiente de facturas (FC) y notas de débito (ND), y
  muestra aparte lo que hay `a_favor` sin aplicar. Si en la empresa la cuentan
  distinto, se cambia en las tres constantes del principio de `servidor.py`.
- **Hay clientes duplicados** ("CONFECAT SA" y "CONFECAT S.A.") y registros
  marcados `NO USAR`. Por eso el asistente muestra las opciones en vez de
  elegir por su cuenta cuando hay más de un candidato.
- **Hay fechas cargadas mal** (una nota de crédito con año 2027). El resumen
  informa hasta el último mes con volumen real, no hasta esa fecha suelta.
- **Los límites de crédito están desactualizados** o no se respetan: varios de
  los que más deben tienen límites de $3 a $5 millones contra deudas de
  cientos de millones. Vale la pena revisarlo antes de usar ese campo para
  decidir algo.
