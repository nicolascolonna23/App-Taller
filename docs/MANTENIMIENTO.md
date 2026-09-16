# Mantenimiento de flota · Expreso Catamarca

> **Borrador sobre `main` 767d784.** La copia local usada inicialmente era anterior al repositorio remoto. El remoto ya tiene órdenes (`gomeria/ordenes.py`), servicios en PostgreSQL y planes (`gomeria/22_planes_mantenimiento.sql`). Esta propuesta se publica para revisión bajo `flota_vales` y `/api/vales`, conservando esos módulos. Antes de fusionar hay que unificar los preventivos propuestos con los planes/services vigentes y definir el vínculo con las órdenes existentes. No aplicar la migración del borrador en producción. Las secciones de inspección e importación siguientes describen la copia local original, no el estado actual de `main`.

> No se trasladaron los cambios locales de `inicio.html` ni `control_flota.html`: hubieran reemplazado mejoras posteriores. El acceso al borrador es directo por `/vales`.

## 1. Negocio, inspección y supuestos

La solicitud es el vale: se crea una sola entidad, con número permanente. La aprobación habilita el gasto y la ejecución. La factura pertenece al vale y su cierre exige aprobación, validación técnica y control del importe.

La aplicación encontrada tiene un servidor Python `ThreadingHTTPServer`, PostgreSQL/Supabase mediante psycopg, usuarios y sesiones con cookie HttpOnly/SameSite y contraseñas scrypt. Las páginas son HTML/JS sin compilación. Se reutilizan `usuarios`, `sesiones`, `unidades`, `odometros`, el login y el servidor de `app.py`. La interfaz conserva fondo oscuro, paneles y acento naranja de las pantallas existentes, sin dependencias de CDN.

Los services existentes se consultaban y registraban en una planilla externa. No hay una tabla de planes de mantenimiento equivalente en el repositorio. Por eso se incorporan planes y services en PostgreSQL, con una importación inicial explícita de fecha, km y objetivo existentes. No se infieren intervalos ni se copia información remota automáticamente. El registro anterior bloquea nuevas cargas para las unidades incorporadas al nuevo módulo; conserva sus otras funciones. La vista histórica `/control` conserva los datos y la telemetría anteriores; `/vales` es la consulta oficial de preventivos para las unidades incorporadas.

El campo `unidades.tipo` distingue vehículo/equipo, por lo que no se modifica su significado. Se agregan categoría y sucursal normalizadas de mantenimiento. El administrador debe clasificar explícitamente larga distancia y semirremolques. Ninguna otra unidad se incorpora automáticamente. No se crean vehículos duplicados.

Supuestos reversibles: un equipo central de mantenimiento, lectura completa para la sucursal propietaria, validación técnica obligatoria, cierre y autorizaciones excepcionales a cargo de Administración inicialmente. Un vale tiene una factura vigente; sus correcciones conservan los valores anteriores en auditoría. Los importes no realizan conversión de monedas.

## 2. Roles, permisos y visibilidad

| Operación | Sucursal | Mantenimiento | Administración |
|---|---|---|---|
| Unidades y preventivos | Propia sucursal | Toda la red | Toda la red |
| Crear vale / borrador | Propia sucursal | No | Sucursal de la unidad |
| Editar borrador / observada | Propia sucursal | No | Sí |
| Consultar detalle y adjuntos | Propia sucursal | Toda la red | Toda la red |
| Consultar resumen de red | Sí | Sí | Sí |
| Aprobar / observar / rechazar | No | Sí | Sí |
| Ejecutar vale aprobado | Propia sucursal | Sí | Sí |
| Factura y documentación | Propia sucursal | Sí | Sí |
| Validar finalización | No | Sí | Sí |
| Regularizar emergencia / diferencia | No | Configurable | Sí por defecto |
| Cerrar | No | Configurable | Sí por defecto |
| Reabrir un estado final | No | No | Con motivo |
| Planes y services | Consulta | Gestión | Gestión |
| Usuarios / sucursales / políticas / corrección de km | No | No | Sí |
| Indicadores y exportación | No | Sí | Sí |

Los roles del módulo viven en `mt_accesos`; no se amplía el rol de gomería ni se otorgan permisos por semejanza de nombres. El administrador global existente conserva la administración. Los usuarios existentes sin acceso al módulo reciben 403; no adquieren un rol por defecto.

**Lista pública cerrada de la red:** ID, número, sucursal, unidad/dominio, estado, urgencia, condición, emergencia, creación y actualización. No contiene importes, proveedor, ubicación, descripción, factura, archivos ni comentarios. El detalle y la descarga vuelven a verificar la propiedad. Los comentarios internos sólo son visibles a Mantenimiento/Administración. La sucursal ve un historial de estados sin recibir la auditoría íntegra de documentos internos.

## 3. Preventivo y máquina de estados

Cada lectura manual agrega un odómetro, con usuario, origen único, fecha de Argentina y valor anterior. No sobrescribe la lectura del mismo día. Los retrocesos se rechazan; Administración dispone de corrección explícita con motivo. Los registros importados por procesos existentes también disparan auditoría; si no hay sesión su actor queda nulo y conservan el origen, sin atribuirlos a una persona.

`restantes = objetivo vigente - km actual`. Cero o negativo significa vencido. El aviso próximo usa el umbral del plan, o el global. Sin umbral no se inventa un aviso próximo. Sin fecha o con antigüedad superior al parámetro se advierte lectura desactualizada; se identifica lectura menor al último service. El plan por unidad tiene precedencia sobre el plan de categoría. Registrar un service calcula `km del service + intervalo vigente`. Modificar un plan crea una nueva versión lógica y desactiva la anterior; los objetivos ya comprometidos no se reescriben silenciosamente.

| Origen | Destino | Rol / condición |
|---|---|---|
| BORRADOR | PENDIENTE_DE_APROBACION | Sucursal propietaria / Administración |
| PENDIENTE_DE_APROBACION | OBSERVADA / RECHAZADA / APROBADA | Mantenimiento / Administración; motivo obligatorio; aprobación con importe |
| OBSERVADA | PENDIENTE_DE_APROBACION | Sucursal propietaria / Administración, con respuesta |
| APROBADA | EN_REPARACION | Sucursal propietaria / Mantenimiento / Administración |
| PENDIENTE_DE_APROBACION | EN_REPARACION | Sólo emergencia con motivo, ubicación y evidencia adjunta |
| EN_REPARACION | PENDIENTE_DE_FACTURA | Trabajo registrado y finalización informada |
| PENDIENTE_DE_FACTURA | PENDIENTE_DE_CIERRE | Sucursal / Administración; factura, aprobación, validación y diferencias regularizadas |
| PENDIENTE_DE_CIERRE | CERRADA | Roles configurados; se verifican nuevamente todos los requisitos |
| BORRADOR / OBSERVADA / PENDIENTE_DE_APROBACION | CANCELADA | Sucursal propietaria o Administración, con motivo |
| Cualquier estado no final | CANCELADA | Administración, con motivo |
| CERRADA / CANCELADA / RECHAZADA | PENDIENTE_DE_APROBACION | Reapertura excepcional de Administración, con motivo |

Reabrir invalida aprobaciones y validaciones anteriores sin eliminar su historia. La autorización de diferencia pertenece a la factura vigente y se invalida al corregirla. Una corrección de factura devuelve el vale a pendiente de factura. No hay operación de eliminación de solicitudes.

## 4. Modelo, integridad y concurrencia

- `mt_sucursales`, `mt_prefijos`: catálogo, prefijos reservados e historial de reserva. Un prefijo utilizado no puede pasar a otra sucursal.
- `mt_accesos`: vínculo a usuarios existentes y rol/sucursal del módulo.
- `mt_categorias`: catálogo extensible; sólo larga distancia y semirremolque habilitados inicialmente.
- `unidades`: dos nuevas claves foráneas; conserva el maestro existente.
- `odometros`: conserva lecturas existentes, agrega usuario del módulo y valor anterior.
- `mt_planes`, `mt_services`: planes versionados, objetivo vigente y cumplimiento histórico.
- `mt_solicitudes`: identidad inmutable, estados, importes, autorizaciones y reparación. Los detalles del trabajo son JSON validado por backend, dentro del mismo vale.
- `mt_adjuntos`: múltiples archivos, UUID, categoría, MIME, SHA-256, versión, reemplazo, retiro lógico y usuario. Binario privado en PostgreSQL para mantener archivo, metadatos y auditoría en una transacción. No se expone por almacenamiento estático.
- `mt_facturas`: factura vigente por vale, documento asociado, datos fiscales y duplicados justificados.
- `mt_comentarios`, `mt_auditoria`: comentarios con visibilidad y bitácora append-only. El historial de estados se obtiene de cambios de la solicitud en la bitácora, sin duplicar eventos.
- `mt_checklists`: inspección independiente enlazada por FK única desde el vale; una novedad origina como máximo un vale.
- `mt_notificaciones`, `mt_notificaciones_leidas`: eventos del sistema y lectura por usuario; las alertas de services se calculan con la información vigente. Permiten agregar consumidores para correo/mensajería después.
- `mt_config`, `mt_migraciones`: políticas y versión del esquema.

La asignación del número ocurre en un trigger `BEFORE INSERT`: incrementa la fila de sucursal, obtiene el prefijo y rellena un mínimo de cinco dígitos. PostgreSQL bloquea esa fila hasta confirmar la transacción. Si falla la solicitud, se revierte también el contador. Hay índice único de número y un trigger que impide cambiar número, sucursal, unidad y solicitante. Los prefijos no viven en el frontend.

Las mutaciones del vale bloquean su fila con `FOR UPDATE`. La detección de factura duplicada toma además un bloqueo transaccional por identidad fiscal/tipo/número, para serializar cargas de distintos vales. Compara total decimal exacto. Las políticas son bloqueo o advertencia con confirmación y justificación. La normalización elimina espacios de número y puntuación de identificación fiscal; no interpreta numeraciones fiscales locales equivalentes.

Los triggers de auditoría conservan valores anteriores/nuevos, usuario, motivo y fecha; excluyen el binario del archivo. Se prohíbe actualizar o eliminar la bitácora y borrar registros históricos del módulo. Los triggers de integridad comprueban requisitos de ejecución y cierre. Las transiciones y roles se validan en backend. Las tablas del módulo tienen RLS sin permisos públicos; el backend usa la conexión privilegiada ya utilizada por el proyecto. No entregar esas credenciales al navegador. Un propietario de PostgreSQL puede modificar triggers: la inmutabilidad operativa no sustituye backups ni controles del administrador de base.

Las fechas de evento son `timestamptz`; se muestran en `America/Argentina/Buenos_Aires`. Las lecturas y comprobantes usan fecha local. Los importes son `numeric`/Decimal, sin cálculo financiero con float en backend.

## 5. Vistas concretas

- **Inicio:** vencidos, próximos, unidades, preventivos y solicitudes con acciones pendientes; nueva solicitud siempre accesible para Sucursal/Administración.
- **Nueva solicitud:** unidad, desperfecto, urgencia, condición, ubicación; datos adicionales plegables. Permite borrador y emergencia. Adjuntos desde el detalle inmediatamente después de crear el vale.
- **Mis solicitudes / Toda la red:** búsqueda por vale/dominio, sucursal, estado, urgencia, período, orden y páginas de 30. Los filtros por unidad también están disponibles en API.
- **Taller:** misma bandeja global, priorizada por emergencia, inmovilización, urgencia y antigüedad.
- **Detalle:** datos, transiciones, adjuntos, aprobación con presupuesto elegido, ejecución, factura, comentarios, historial y auditoría para roles autorizados. Impresión resumida A4 con enlace verificable autenticado; el detalle extenso permanece online.
- **Preventivos:** lectura, fecha, último service, objetivo y restante; carga de km y service. En teléfono se muestran tarjetas en lugar de obligar a desplazar una tabla horizontal.
- **Planes:** creación y versionado por categoría o unidad para Mantenimiento y Administración.
- **Checklist:** frenos, luces, neumáticos y fluidos con correcto/revisar/no aplica; una novedad exige descripción y permite abrir un vale precargado. Los ítems actuales son una base técnica a revisar con operaciones.
- **Notificaciones:** cambios del vale, lectura de avisos y alertas preventivas vigentes.
- **Administración:** sucursales/prefijos, alta de usuario, permisos, asignaciones, corrección de km, planes, importación inicial y políticas.
- **Indicadores:** agrupación por sucursal/unidad/estado/proveedor/tipo/emergencia, cantidades, tiempos y diferencias; exportación CSV sin fórmulas ejecutables. Cumplimiento preventivo en tabla adicional.

## 6. Etapas

**MVP integrado en este cambio:** esquema, permisos, vales, estados, archivos privados, facturas, emergencia, auditoría, preventivo, checklist, avisos internos, administración, indicadores CSV y pantallas responsive.

**Puesta en marcha:** ejecutar integración PostgreSQL en base aislada; migrar con backup; acordar catálogos/políticas; importar objetivos vigentes; asignar usuarios/unidades; ensayar un circuito completo por rol; habilitar operaciones.

**Mejoras posteriores:** responsables de mantenimiento por zona, transporte externo de notificaciones, análisis antivirus asíncrono, almacenamiento privado de objetos si el volumen exige sacarlos de PostgreSQL, varios comprobantes por vale, catálogos de proveedor/tipo de reparación, exportación XLSX. No son dependencias de la operación básica.

## 7. Implementación en el repositorio

- `app.py`: pantalla y API integradas con sesión existente.
- `inicio.html`: acceso a Mantenimiento.
- `control_flota.html`: evita registrar services paralelos de unidades incorporadas.
- `flota_vales/service.py`: políticas, lecturas y comandos transaccionales.
- `flota_vales/http.py`: HTTP, protección de origen, descarga autorizada, CSV y errores.
- `flota_vales/index.html`, `app.js`, `style.css`: interfaz sin build.

No se aplicaron cambios a una base de producción ni se reemplazaron datos existentes.

## 8. Migraciones, pruebas y demo

Migración `flota_vales/001_mantenimiento.sql`, aplicada con runner versionado `python3 -m flota_vales.migrar`. Requiere tablas existentes de usuarios, unidades y odómetros (scripts originales 01, 03, 05 y maestro 07). El runner comprueba versión y bloquea aplicaciones simultáneas. No ejecutar el SQL a mano dos veces: la idempotencia está en el runner.

Pruebas locales:

```sh
python3 -m unittest discover -s tests -v
node --check flota_vales/app.js
python3 -m py_compile app.py flota_vales/service.py flota_vales/http.py
```

Para ejecutar las cinco pruebas de integración con un solo comando, abrí Docker Desktop, esperá que termine de iniciar y, desde la carpeta del proyecto, ejecutá:

```sh
python3 scripts/probar_mantenimiento.py
```

El comando descarga PostgreSQL 17 si hace falta, crea una base temporal accesible sólo desde esta computadora, ejecuta la suite y elimina su contenedor al terminar. No usa la configuración de producción. El resultado esperado es `Ran 5 tests` y `OK`, sin `skipped`.

Si ya tenés una base PostgreSQL de prueba, podés definir `MT_TEST_DATABASE_URL`; el mismo comando la usará sin iniciar Docker. El usuario debe poder crear y eliminar esquemas. No apuntar a producción.

Integración real, exclusivamente contra una base de prueba explícita:

```sh
MT_TEST_DATABASE_URL='postgresql://usuario:clave@localhost/flota_test' python3 -m unittest discover -s tests -p 'test_vales_postgres.py' -v
```

La suite crea un esquema aleatorio, instala estructuras base mínimas y la migración, prueba concurrencia con 16 solicitudes en 8 conexiones, identidad inmutable, aislamiento entre sucursales, aprobación auditada, circuito de cierre con diferencia y reapertura, y emergencia originada en checklist. Elimina exclusivamente el esquema creado por la prueba.

Smoke de interfaz (requiere Node, Playwright y Chrome; se puede definir `PLAYWRIGHT_MODULE` con la ruta al módulo):

```sh
node tests/vales_ui.cjs
```

Usa API simulada: verifica escritorio/celular y formulario sin errores JavaScript ni desborde. No demuestra funcionamiento del backend ni de la base.

Demo: sólo sobre una base aparte ya migrada. `MT_DEMO_DATABASE_URL` debe contener test/demo/dev en el nombre, y `MT_DEMO_PASSWORD` aporta la clave. Ejecutar `python3 -m flota_vales.demo`. Crea una sucursal y unidad claramente ficticias y un vale; no asigna catálogos reales ni fija tolerancias de negocio. La carga falla si ya existe el usuario demo.

## 9. Instalación, configuración y validación

1. Conservar una copia de la base y aplicar las migraciones existentes requeridas.
2. Instalar las dependencias originales con `python3 -m pip install -r requirements.txt`.
3. Definir `SUPABASE_DB_URL` o `DATABASE_URL` como ya requiere el sistema.
4. Aplicar `python3 -m flota_vales.migrar` y reiniciar `python3 app.py`.
5. Ingresar con el administrador existente y abrir `/vales`.
6. Crear sucursales y prefijos; asignar las unidades y los roles de usuarios. El rol del módulo se otorga por separado del alta de usuario.
7. Configurar umbral de km, antigüedad de lectura y tolerancia. Inicialmente son nulos: no se inventan umbrales y el cierre queda bloqueado hasta definir tolerancia. La política inicial de duplicados bloquea, los archivos admitidos son PDF/PNG/JPEG/WebP de hasta 5 MB, configurables hasta 10 MB. No se admiten documentos de oficina ni SVG.
8. Configurar planes e importar explícitamente el último service y objetivo vigente de cada unidad. Cotejar con el registro actual antes de darlo por migrado.
9. Ensayar creación, observación, respuesta, aprobación, ejecución, factura, validación y cierre. Repetir emergencia y diferencia superior a tolerancia. Validar con dos sucursales que nunca se descarguen archivos de la otra.
10. Ejecutar pruebas PostgreSQL y smoke móvil. Comprobar también el login y los módulos anteriores.

Deshabilitación reversible: retirar el acceso del menú mientras se corrige la puesta en marcha. No borrar tablas ni volver a escribir preventivos de unidades incorporadas en otro registro. Mantener backups con la política existente, incluyendo binarios de adjuntos.

## 10. Decisiones pendientes y validación no completada

Confirmar sucursales/prefijos, equipo central o zonal, umbrales de km y antigüedad, tolerancia, autorizadores de emergencia/diferencia/cierre, tamaño permitido de archivos, lista pública de la red, ítems del checklist y tratamiento de facturas sin CUIT (se exige identificación fiscal equivalente). Validar el supuesto de una factura vigente por vale y moneda única.

**Evidencia local:** ocho pruebas unitarias pasaron; sintaxis Python y JavaScript verificada. Smoke de escritorio (1440 px) y teléfono (390 px) pasó con API simulada, y se inspeccionaron capturas. Las cinco pruebas PostgreSQL quedaron omitidas porque no hay servidor local ni `MT_TEST_DATABASE_URL` configurada. Se intentó iniciar PostgreSQL temporal en Docker: la descarga terminó con `unexpected EOF` y el daemon dejó de responder. No se ejecutó migración ni concurrencia contra una base real. Esto impide dar por demostrados los 15 criterios de aceptación o declarar la implementación lista para producción.

**Limitaciones funcionales a revisar durante aceptación:** los filtros de urgencia de indicadores se reciben por API; la pantalla expone sucursal, unidad, estado y período. La navegación no mantiene historial completo del navegador. No hay pruebas de carga/conexión lenta ni ensayo de todos los roles en navegador. Las notificaciones preventivas se calculan al consultar; no hay un proceso programado de entrega externa.

## Verificación sobre el repositorio remoto

La rama se preparó sobre `main` 767d784. La suite completa `python3 -m unittest discover -s tests -p "test_*.py"` ejecutó 106 pruebas: 101 aprobadas y 5 de PostgreSQL omitidas por falta de `MT_TEST_DATABASE_URL`. Se verificó sintaxis de Python y JavaScript. La prueba de navegador documentada anteriormente corresponde a la copia local anterior; no se repitió contra la integración con el estilo global del remoto.
