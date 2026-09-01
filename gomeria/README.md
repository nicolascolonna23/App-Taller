# Gomería

El gomero escanea el QR pegado en la unidad, escribe en castellano lo que hizo,
y el sistema lo traduce a movimientos de cubiertas sobre el mapa real de esa
unidad. Antes de guardar nada, le muestra qué entendió y espera que confirme.

```
QR en la unidad ──► pantalla del celular ──► lo que escribe ──► Claude
                                                                  │
                                          "Esto entendí: 2IE → 3IE, 3IE → 2IE"
                                                                  │
                                                            [Confirmar]
                                                                  │
                                                             Supabase
```

Los datos viven en Supabase (PostgreSQL en la nube), con respaldo automático.

## 1. Crear la base en Supabase

Nunca usaste Supabase, así que va paso a paso. Es gratis para este tamaño.

1. Entrá a **supabase.com** y creá una cuenta.
2. **New project**. Ponele un nombre (`diemar-gomeria`), elegí la región
   **South America (São Paulo)** —es la más cerca, y menos distancia es menos
   demora en cada consulta— y definí una **contraseña de base de datos**.
   Guardala: la vas a necesitar en el paso 4 y no se puede volver a ver.
3. Cuando el proyecto termine de crearse, andá a **SQL Editor** → **New query**.
   Pegá el contenido de `01_esquema.sql` y apretá **Run**. Después hacé lo mismo
   con `02_vistas.sql` y con `03_usuarios.sql`, cada uno en una consulta nueva.
   Si no dan error, la base quedó lista.
4. Arriba de todo, al lado de donde dice `main PRODUCTION`, está el botón verde
   **Connect**. Hacé clic ahí → **Connection String** → **Session pooler**.
   Copiá esa línea, que es algo así como
   `postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres`.
5. En la computadora, corré esto y pegá la línea cuando te la pida:

   ```bash
   pip3 install -r gomeria/requisitos.txt
   python3 gomeria/configurar.py
   ```

   Revisa que la cadena sea la correcta, prueba que entre a la base y la guarda
   en `gomeria/conexion.txt`. No hay que crear ningún archivo a mano. Si algo
   está mal —la contraseña, el pooler equivocado, las tablas sin crear— te dice
   qué corregir y no guarda nada.

> Elegí **Session pooler**, no **Transaction pooler**. El de transacción usa el
> puerto 6543 y no soporta algunas cosas que el programa necesita. Si ves 6543
> en la línea, elegiste el que no va.

> El plan gratis pausa el proyecto si no lo tocás por una semana. Se despausa
> solo desde el panel, pero la primera consulta después de eso tarda unos
> segundos.

## 2. Cargar las unidades y sus mapas

El mapa de una unidad se escribe con una letra por eje, de adelante hacia atrás:

| Letra | Qué es | Cubiertas |
|---|---|---|
| `S` | eje simple, una cubierta por lado | 2 |
| `D` | eje dual, dos cubiertas por lado | 4 |

Ejemplos:

- `S-D-D` → direccional + 2 traseros duales = **10 cubiertas**. Es el tractor
  típico: cuatro por lado atrás.
- `S-D` → chasis de reparto = 6 cubiertas.
- `S-S` → utilitario = 4 cubiertas.
- `D-D-D` → semirremolque de 3 ejes = 12 cubiertas.

En `unidades.csv` están las 53 unidades de la planilla de flota, con patente,
interno, marca y sucursal ya cargados. **La columna `mapa` viene sugerida según
el uso y hay que revisarla unidad por unidad** — yo no puedo saber cuántos ejes
tiene cada camión. Cuando esté corregida:

```bash
python3 gomeria/cargar_unidades.py gomeria/unidades.csv --simular   # muestra qué haría
python3 gomeria/cargar_unidades.py gomeria/unidades.csv             # lo hace
```

Se puede correr las veces que quieras: actualiza las que ya están y agrega las
nuevas, sin tocar las cubiertas montadas.

## 3. Crear los usuarios

Al módulo se entra con usuario y contraseña: cada parte queda firmado por
quien lo cargó. Creá el primero, que conviene que sea admin:

```bash
python3 gomeria/usuarios.py agregar nico "Nicolás Colonna" --rol admin
```

Te pide la contraseña en el momento y te la hace escribir dos veces, así no
queda en el historial de la terminal. Después, uno por cada persona que vaya a
cargar partes:

```bash
python3 gomeria/usuarios.py agregar ramon "Ramón Gómez"
python3 gomeria/usuarios.py listar
```

| Rol | Qué puede |
|---|---|
| `operario` | cargar partes de gomería |
| `encargado` | además confirmar y corregir |
| `admin` | además administrar usuarios |

Cuando alguien se va, `usuarios.py baja ramon` le corta el acceso y le cierra
las sesiones abiertas, sin borrar lo que cargó. Si se olvidó la contraseña,
`usuarios.py clave ramon`.

Las contraseñas no se guardan: se guarda el resultado de pasarlas por scrypt
con una sal distinta para cada una. Aunque alguien se lleve la tabla entera, no
puede volver a las contraseñas.

## 4. Levantar el módulo

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # o dejalo en chat/clave.txt
python3 gomeria/servidor.py --host 0.0.0.0
```

Imprime la dirección que ven los celulares. La pantalla de una unidad es
`http://IP:8100/u/PATENTE`.

## 5. Imprimir el QR

Hay dos formas, según cómo quieras trabajar.

**Un solo QR para toda la gomería** (lo más simple). Se imprime un cartel, se
pega en la pared del taller, y el gomero escribe la patente dentro del texto:

```bash
python3 gomeria/qr.py --base http://192.168.1.45:8100 --uno
```

**Una etiqueta por unidad**, pegada en cada camión. Al escanear ya sabe de qué
unidad se trata y no hay que escribir la patente:

```bash
python3 gomeria/qr.py --base http://192.168.1.45:8100
```

Las dos conviven: si algún día pegás etiquetas por unidad, el cartel general
sigue funcionando igual.

Usá la IP que imprimió el servidor, no `127.0.0.1`: el QR lo escanea un celular,
no esta computadora. Deja `etiquetas.html`; se abre en el navegador y se imprime
con Ctrl+P.

Si la IP del servidor cambia, hay que reimprimir. Por eso conviene pedir una IP
fija antes de imprimir 53 etiquetas.

## Cómo está guardada la información

| Tabla | Qué guarda |
|---|---|
| `configuraciones` + `configuracion_posiciones` | los mapas: qué posiciones tiene cada tipo de armado |
| `unidades` | patente, interno, sucursal y qué mapa usa |
| `cubiertas` | la ficha de cada cubierta: código, marca, medida, km, recapados, estado |
| `montajes` | qué cubierta está en qué posición y desde cuándo. Las viejas quedan con fecha de baja: es el historial |
| `partes` | lo que escribió el gomero, tal cual, más lo que entendió Claude |
| `movimientos` | el libro mayor: todo lo que le pasó a cada cubierta |
| `mediciones` | profundidad de dibujo a lo largo del tiempo |

Dos reglas las hace cumplir la base misma, no el código: **una posición no puede
tener dos cubiertas al mismo tiempo**, y **una cubierta no puede estar montada en
dos lugares a la vez**. Si un movimiento mal interpretado intentara romper alguna,
la transacción entera se cancela y no queda nada a medias.

El texto original del parte se guarda siempre, aunque después se descarte o falle
la interpretación. Si algún día hay una discusión sobre qué se hizo, está lo que
escribió el gomero, lo que entendió el sistema y quién confirmó.

## Seguridad

Las tablas tienen RLS prendido sin políticas: la clave pública de Supabase no
puede leer ni escribir nada. Solo el servidor, que usa la cadena de conexión
directa, entra a los datos. Por eso `conexion.txt` no va al repo.

## Lo que falta

- **Montar las cubiertas que ya están puestas.** Hoy las unidades están cargadas
  con las posiciones vacías. Hay que hacer un inventario inicial: recorrer la
  flota anotando qué cubierta hay en cada posición. Se puede hacer desde la
  pantalla, o con un CSV si preferís cargarlo de una.
- **Reportes**: costo por kilómetro por marca, cubiertas por vencer, ranking de
  rendimiento. Con la base así armada salen de una consulta.
