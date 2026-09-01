# Poner la app en la nube

La app corre en un servidor de internet, no en tu computadora. Nadie tiene que
dejar nada prendido y la dirección es siempre la misma, así el QR de gomería no
hay que reimprimirlo nunca.

## Antes de empezar

Necesitás tres cosas a mano:

1. La **cadena de conexión** de Supabase (Connect → Connection String → Session
   pooler), con el `[YOUR-PASSWORD]` ya reemplazado por tu contraseña.
2. Tu **clave de la API de Claude** (console.anthropic.com → API Keys).
3. Que los **tres SQL** ya estén corridos en Supabase: `01_esquema.sql`,
   `02_vistas.sql` y `03_usuarios.sql`.

## Los pasos

1. Entrá a **render.com** y creá una cuenta con tu usuario de GitHub.

2. **New** → **Web Service** → elegí el repositorio `App-Taller` y la rama
   `claude/fleet-html-dashboard-unify-miy4gq`.

3. Render lee el archivo `render.yaml` y completa solo el resto. Verificá que
   diga:

   - Build command: `pip install -r requirements.txt`
   - Start command: `python3 app.py`

4. En **Environment**, cargá estas tres variables:

   | Variable | Qué va |
   |---|---|
   | `SUPABASE_DB_URL` | la cadena de conexión completa |
   | `ANTHROPIC_API_KEY` | la clave que empieza con `sk-ant-` |
   | `USUARIO_INICIAL` | `nico:Nicolás Colonna:TuContraseña` |

   `USUARIO_INICIAL` crea el primer usuario administrador la primera vez que
   arranca. Es la forma de entrar sin tener una terminal en el servidor.

5. **Create Web Service**. El primer arranque tarda unos minutos.

6. Cuando termine, Render te da una dirección tipo
   `https://app-taller.onrender.com`. Abrila, entrá con el usuario que pusiste
   en `USUARIO_INICIAL` y vas a ver la pantalla de inicio.

7. **Borrá `USUARIO_INICIAL`** de las variables de entorno. Ya cumplió su
   función y no conviene dejar una contraseña ahí escrita. De ahí en más los
   usuarios se crean desde el sistema.

## De ahí en adelante

Cada vez que se sube un cambio al repositorio, Render publica la versión nueva
sola. No hay que volver a tocar nada.

## El QR

Ahora que la dirección es fija, el QR se genera apuntando a ella:

```bash
python3 gomeria/qr.py --base https://app-taller.onrender.com --uno
```

Y ese cartel ya no caduca: la dirección no cambia aunque se reinicie el
servicio o se publique una versión nueva.

## Sobre el plan

El plan gratuito de Render duerme el servicio después de un rato sin uso, y la
primera visita después tarda cerca de un minuto en responder. Para algo que
usa el gomero con el celular en la mano, eso molesta. El plan pago más barato
(unos 7 dólares por mes) lo mantiene despierto.

## Qué queda en tu red y qué no

| Módulo | Dónde vive |
|---|---|
| Gomería y usuarios | Supabase |
| Panel y control de flota | planillas de Google, se leen desde el navegador |
| Chat de clientes y cuenta corriente | **tu red, no se sube** |

El chat sigue corriendo donde vos digas, con la base local. Los datos de los
30.306 clientes no salen de tu red, que es lo que definimos al principio.

## Seguridad

- Todo pide usuario y contraseña, incluidas las pantallas de flota.
- La cookie de sesión viaja marcada como `Secure` cuando la conexión es https,
  que es siempre en Render.
- Después de 8 intentos fallidos desde la misma dirección, el ingreso se
  bloquea 15 minutos. Expuesto a internet hace falta: en una red interna
  alcanzaba con que probar una contraseña fuera lento.
- Las claves de la base y de la API viven en las variables de entorno de
  Render, nunca en el repositorio.
