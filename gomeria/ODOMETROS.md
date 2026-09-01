# Los km del satelital en la base

El scraper de Hawk ya existe: vive en el repo **ServiceDM**, corre todos los
días a las 08:00 (workflow `hawk_km.yml`) y escribe el kilometraje de cada
móvil en la planilla de services.

Lo que falta es que esa misma lectura quede también en Supabase. No para
reemplazar la planilla —ahí sigue igual— sino porque la planilla **pisa la
celda**: guarda el último kilometraje y pierde el de ayer. Sin la serie no
se puede saber cuántos kilómetros rodó una cubierta, que es el número del
que cuelga todo el módulo de gomería.

## Qué se agrega

| Dónde | Qué |
|---|---|
| Supabase | tabla `odometros` + 3 vistas (`05_odometros.sql`) |
| ServiceDM | `subir_odometros.py` y 5 líneas en `hawk_km.py` |
| ServiceDM | el secret `SUPABASE_DB_URL` |

## Paso 1 — la tabla

En Supabase, **SQL Editor**, pegar y correr `gomeria/05_odometros.sql`.
Se puede correr las veces que haga falta: no borra datos.

Deja armado:

- **`odometros`** — una fila por unidad y por día. Si el job se corre dos
  veces en el día, la segunda pisa a la primera.
- Un disparador que actualiza `unidades.km_actual`, **solo si el número
  sube**. Un odómetro no vuelve para atrás; una lectura mala no puede
  bajar el kilometraje bueno.
- **`v_km_diarios`** — lo que recorrió entre lecturas, con la cantidad de
  días. Ojo: el scraper corre de lunes a viernes, así que la lectura del
  lunes trae el fin de semana entero.
- **`v_km_por_montaje`** — los km que rodó cada cubierta entre que se
  montó y que se sacó. Esto es lo que hoy depende de que el gomero
  escriba el kilometraje a mano.
- **`v_odometro_ultimo`** — la última lectura de cada unidad y hace
  cuántos días que no reporta.

## Paso 2 — el secret

En ServiceDM: **Settings → Secrets and variables → Actions → New secret**

- Nombre: `SUPABASE_DB_URL`
- Valor: la cadena de conexión de Supabase

**Importante:** tiene que ser la de **Connection pooling**, no la directa.
Las máquinas de GitHub Actions no tienen IPv6 y la conexión directa de
Supabase sí, así que la directa no conecta desde ahí. La del pooler se
copia en Supabase → *Project Settings* → *Database* → *Connection pooling*
y se reconoce porque el host termina en `pooler.supabase.com`.

## Paso 3 — el script

Copiar `subir_odometros.py` a la raíz de ServiceDM, al lado de `hawk_km.py`.

En `hawk_km.py`, al final de `main()`, después del bloque que actualiza la
planilla:

```python
    try:
        actualizar_sheets(df)
    except Exception:
        print("\n[sheets] error al actualizar la planilla:")
        traceback.print_exc()

    # ---- agregar de acá para abajo ----
    try:
        import subir_odometros
        subir_odometros.subir(df)
    except Exception:
        print("\n[supabase] error al subir los odometros:")
        traceback.print_exc()
```

Va con su propio `try` igual que la planilla: los Excel ya están escritos y
un problema de red con la base no tiene que voltear el job.

En `hawk_km.yml`, agregar `psycopg[binary]` a las dependencias y el secret
al paso que corre el scraper:

```yaml
      - name: Instalar dependencias
        run: pip install selenium requests pandas openpyxl gspread google-auth psycopg[binary]

      - name: Correr scraper
        env:
          HAWK_USER: ${{ secrets.HAWK_USER }}
          HAWK_PASS: ${{ secrets.HAWK_PASS }}
          SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}     # <-- nueva
          ...
```

Sin el secret el script avisa y no hace nada, así que el scraper sigue
andando igual mientras tanto.

## Paso 4 — cargar lo que ya hay

El repo viene guardando `data/historico.csv` desde el 29 de julio. Eso se
sube de una:

```bash
export SUPABASE_DB_URL='...la del pooler...'
python subir_odometros.py data/historico.csv
```

Son unas 1.700 lecturas, 27 días de 69 unidades.

## Lo que no engancha, y está bien

Algunas lecturas no corresponden a ninguna unidad de la flota. Se guardan
igual (la tabla no las rechaza) pero quedan sin `unidad_id`:

- **`PORTATIL0134` y compañía** — equipos portátiles, no son vehículos.
- **`DZM638`, `LCC752`, `LCC754`, `STR530`, `VUX564`** — patentes viejas
  que no están en `unidades`. Si son unidades que siguen andando, hay que
  darlas de alta; si no, se ignoran solas.
- **`AE527AE` / `AF527AE`** — es AE527FA mal escrita. El scraper ya la
  corrige, así que solo aparece en las filas viejas del histórico.

El satelital devuelve algunas patentes con un `HC` pegado atrás
(`AC538KWHC`). El script lo saca solo.
