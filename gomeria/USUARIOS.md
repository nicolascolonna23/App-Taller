# Usuarios, roles y módulos

Hasta acá los usuarios se daban de alta desde la terminal
(`python3 gomeria/usuarios.py`) y los roles eran tres, escritos en el
código: operario, encargado y admin. Alcanzaba cuando el sistema era
gomería.

Con flota, combustible, órdenes y solicitudes de orden de compra ya no: el
responsable de una sucursal no es un operario de taller, y no tiene por
qué ver —ni que le pregunten por— el stock del depósito.

Desde acá todo eso se hace en **`/usuarios`**, con la sesión de alguien que
administra.

## Paso 1 — las tablas

En Supabase, **SQL Editor**, pegar y correr `gomeria/27_roles.sql`. Se
puede correr las veces que haga falta: no borra nada y no le devuelve a un
rol un módulo que le sacaste a propósito. Antes tiene que estar corrido
`03_usuarios.sql`.

Hasta que no se corra, la pantalla avisa que falta el script y **el
sistema sigue funcionando como siempre**: todos abren todo, y encargado y
admin siguen siendo los que gestionan. Una migración que no se corrió no
puede dejar a nadie afuera.

## Las tres preguntas que define un rol

**1. ¿Qué módulos abre?** Una casilla por módulo. Lo que no está marcado
no se abre, ni escribiendo la dirección a mano: el permiso lo revisa el
servidor en cada pedido y la pantalla solo esconde el botón.

**2. ¿Qué nivel tiene?** Dos permisos que no son módulos porque
atraviesan todo:

| | Qué habilita |
|---|---|
| **Gestiona** | Aprueba solicitudes, cierra órdenes, carga services y corrige lo que cargó otro. Es el nivel del taller y de mantenimiento. |
| **Administra** | Además: usuarios, roles, borrar y reabrir. Dáselo a los menos que puedas. |

Un rol sin ninguno de los dos **lee** sus módulos y carga lo suyo, pero no
aprueba ni corrige lo ajeno.

**3. ¿Es de una sucursal?** Si lo marcás, a los usuarios de ese rol hay
que asignarles una sucursal, y la pantalla no te deja guardarlos sin ella.
No es un capricho: **la solicitud de orden de compra se numera según quién
la pide**, así que un responsable de boca sin su código cargado abriría el
módulo y no podría usarlo.

## Los cuatro roles con los que arranca

| Rol | Nivel | Qué abre |
|---|---|---|
| **Administrador** | gestiona y administra | Todo, más usuarios y roles. |
| **Encargado de taller** | gestiona | Todo menos usuarios. |
| **Operario** | — | Lo que ya usaba: flota, unidades, gomería, repuestos, órdenes, combustible, alertas, vencimientos y asistente. |
| **Responsable de sucursal** | es de una sucursal | Solicitudes, unidades, alertas y vencimientos. |

Los cuatro se pueden **editar**; no se pueden **borrar**, porque hay gente
colgando de ellos. Los que crees vos se borran cuando no les queda ningún
usuario.

Si querés que un operario siga viendo algo que le sacaste, o que una
sucursal vea el combustible de sus unidades, es marcar la casilla: no hace
falta tocar el código.

## Dar de alta a alguien

En `/usuarios`, **+ Nuevo usuario**:

- **Usuario**: con lo que entra. Minúsculas, sin espacios ni acentos —la
  mitad de las veces se tipea en un teléfono—.
- **Nombre y apellido**: es el que queda firmando los partes y las
  órdenes, congelado, aunque después se vaya.
- **Rol**: de la lista de arriba, o el que hayas creado.
- **Sucursal**: solo si el rol la pide.
- **Contraseña**: al menos 8 caracteres y que no sean solo números. Se la
  decís y listo; nadie más la ve, porque no se guarda: se guarda el
  resultado de pasarla por scrypt.

## Dar de baja

**No se borra a nadie.** Lo que cargó sigue firmado por él, y borrarlo
sería romperle la historia a las órdenes. Se le da de baja: no entra más y
se le cierran las sesiones abiertas en el momento.

Para que vuelva, **Reactivar**. Su usuario, su nombre y su historia
estaban donde los dejó.

## Lo que el sistema no te deja hacer

Dos candados, y los dos protegen al sistema de sí mismo. Una base sin
administradores activos no se arregla desde ninguna pantalla: se arregla
con SQL a mano.

- No podés darte de baja a vos mismo.
- No podés dejar al sistema sin administradores activos: ni dándole de
  baja al último, ni cambiándole el rol, ni sacándole «administra» al
  único rol que lo tiene si hay gente usándolo.

## Cuándo valen los cambios

**En el acto.** Cambiarle el rol a alguien, o cambiarle los módulos a un
rol, cierra las sesiones de los afectados: si le sacaste un módulo, no lo
puede seguir abriendo hasta mañana. Vuelven a entrar con su misma
contraseña.

## La terminal sigue estando

`python3 gomeria/usuarios.py` sigue andando y es la salida de emergencia:
si te quedaste sin administradores, o todavía no corriste el SQL, desde
ahí se crea uno.

```bash
python3 gomeria/usuarios.py listar
python3 gomeria/usuarios.py agregar nico "Nicolás Colonna" --rol admin
python3 gomeria/usuarios.py clave nico
```

Y el primer usuario de todos, cuando la base está vacía, sale de la
variable `USUARIO_INICIAL` (`usuario:Nombre Completo:contraseña`), que
conviene sacar de las variables de entorno una vez usada.
