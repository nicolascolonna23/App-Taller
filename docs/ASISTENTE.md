# Asistente interno de Diemar

El chat vive en `/asistente`, detrás del mismo inicio de sesión que el resto del sistema. Se abre desde el muñeco Pengui. Usa la API Messages de Anthropic con herramientas de consulta del servidor. El chat de clientes de la carpeta `chat/` es una aplicación anterior independiente y no se modifica.

## Activarlo después del merge

1. Crear una clave en Anthropic y habilitar la facturación de la API. No pegar la clave en el chat ni en GitHub.
2. En las variables de entorno del servicio de Render, agregar `ANTHROPIC_API_KEY`. `ANTHROPIC_MODEL` es opcional y tiene como valor predeterminado `claude-opus-5`; se puede elegir otro modelo de la cuenta que soporte herramientas. La clave se usa exclusivamente en el servidor.
3. Mantener la conexión `SUPABASE_DB_URL` existente. El asistente consulta las mismas tablas y vistas que los módulos. No requiere migraciones nuevas. Deben estar aplicadas las migraciones de los módulos utilizados, incluidas `04_repuestos.sql`, `06_vencimientos.sql`, `07_unidades.sql` y las de combustible. Si falta una fuente, debe informar indisponibilidad, no stock cero.
4. Desplegar la rama principal después de mergear. Entrar al sistema y tocar el muñeco Pengui. Sin clave, el chat muestra “Pendiente de configuración”; los otros módulos siguen funcionando.
5. Probar con un código de goma conocido, una patente con VTV registrada y un repuesto cuyo stock esté comprobado. Comparar los valores con el módulo correspondiente antes de habilitar su uso habitual.
6. Configurar alertas y límites de gasto en el proyecto de API. El servidor limita a cuatro consultas simultáneas por proceso, una activa por usuario, tres segundos entre inicios, cuatro rondas de modelo y ocho herramientas por pregunta. Estos límites no reemplazan el control de gastos del proveedor ni una cuota global si se ejecutan varios procesos.

## Qué significa “entrenarlo”

Para stock, ubicación de cubiertas y vencimientos, los datos cambian todos los días. No conviene guardarlos en los pesos del modelo: el agente los consulta en la base en cada turno. Si se desmonta la goma 300, la próxima pregunta toma el montaje actual, sin reentrenamiento ni exportaciones.

Hay tres capas que se mejoran por separado:

| Capa | Dónde se modifica | Ejemplo |
| --- | --- | --- |
| Datos operativos | En el módulo correspondiente | Registrar un desmontaje, corregir stock o renovar VTV. |
| Reglas del negocio y vocabulario | `gomeria/asistente_reglas.md`, mediante PR | “Goma” significa cubierta; “stock” excluye reparación y recapado. |
| Capacidades de consulta | `gomeria/asistente.py`, con pruebas | Agregar una herramienta de historial de services cuando exista una fuente central confiable. |

Decirle “aprendé esto” en el chat no cambia las reglas permanentes ni la base. La conversación solo da contexto temporal, nunca autoriza escrituras. No hay aprendizaje automático a partir de respuestas de usuarios.

## Cómo ir mejorándolo, paso a paso

1. Elegir entre 20 y 30 preguntas reales de la oficina. Incluir sinónimos, códigos inexistentes, patentes con espacios, preguntas de seguimiento y datos faltantes. `docs/asistente_evaluaciones.json` incluye una lista inicial.
2. Para cada pregunta, verificar en el sistema la fuente, los filtros y el resultado esperado. Usar una base de prueba con datos ficticios para almacenar respuestas exactas en el repositorio. Las cantidades de producción no son resultados permanentes.
3. Si la respuesta falla, identificar la causa: dato mal cargado, búsqueda incorrecta, definición ambigua o interpretación equivocada. Corregir la capa correspondiente; no agregar una cantidad fija al prompt para tapar un error de datos.
4. Si una regla se repite, escribirla claramente en `asistente_reglas.md`. Ejemplo: “Acoples hidráulicos: buscar acople en repuestos, mostrar desglose por código y sumar unidades, no artículos”. Revisar con la persona responsable de stock antes de generalizarla.
5. Ejecutar `python3 -m unittest discover -s tests -v` y las preguntas de evaluación en un entorno de prueba con la API configurada. Revisar exactitud, selección de fuente, manejo de ambigüedades, costos y tiempo de respuesta. Las pruebas automáticas con proveedor simulado no sustituyen la evaluación del modelo real.
6. Versionar cambios en un PR. Si el modelo empeora, revertir reglas o cambiar `ANTHROPIC_MODEL` al modelo previamente validado.

No se implementa fine-tuning en esta versión. Si más adelante hay muchos ejemplos revisados de una tarea estable y las reglas/herramientas no alcanzan, se puede evaluar esa opción por separado. Los inventarios y fechas seguirían consultándose en vivo incluso con un modelo ajustado.

## Alcance y significado de las respuestas

- **Cubiertas:** código exacto, montaje abierto y estado actual. Cantidad en stock se calcula sobre todos los registros, sin contar montadas, reparación, recapado o baja.
- **Repuestos:** stock central por código, descripción o rubro. Se suman unidades de artículos activos. Se muestran variantes por separado y se advierten saldos negativos. No lee stock que exista únicamente en el localStorage de una computadora.
- **Unidades:** patente, interno, modelo, marca, sucursal y asociación de semi. El maestro no tiene disponibilidad de acoplados: “activa” no significa “disponible”. Si “acople” significa un semirremolque, hace falta aclararlo y registrar esa disponibilidad antes de prometer esa respuesta.
- **Vencimientos:** últimas renovaciones de unidades activas; busca VTV/RTO por patente. Sin fecha cargada no significa vigente. No envía datos de personas ni documentos adjuntos al modelo.
- **Combustible:** tickets propios, filtrables por patente, remito y período. No duplica con el listado de la estación. Los importes pueden ser parciales. El consumo por kilómetro sigue disponible en Resumen de combustible, con los cálculos existentes; no se infiere en el chat sin una herramienta de kilómetros.
- **Fuera de alcance inicial:** acciones de escritura, GPS en vivo, historial de services, archivos adjuntos y preguntas arbitrarias sobre fuentes que no están conectadas. Ampliar herramientas según prioridad; no hay SQL libre generado por el modelo.

## Acceso, datos y límites

Los tres roles existentes pueden consultar, al igual que en los endpoints de lectura de los módulos. Se exige sesión, JSON y origen del mismo sitio. Las consultas SQL son fijas, parametrizadas y corren en transacciones READ ONLY, con límite de cinco segundos por sentencia y una muestra máxima de 50 filas. Los agregados incluyen todos los registros coincidentes dentro de la misma instantánea de base.

La respuesta muestra fuentes verificadas por el servidor, fecha de consulta, filtros y si la muestra está truncada. Los valores de tablas y el historial se tratan como datos, no como instrucciones. El HTML de mensajes se muestra como texto, sin ejecutarlo.

El navegador guarda el contexto únicamente en memoria (hasta seis intercambios previos, recortados por longitud). No se comparten conversaciones ni se guardan en localStorage o tablas. Recargar borra el chat. El servidor no registra texto de preguntas ni resultados. Anthropic recibe preguntas, contexto y los resultados necesarios para responder. Revisar los controles de datos de la cuenta antes de usar información sensible.

La integración usa las herramientas de la API Messages de Anthropic mediante el SDK de Python ya incluido en la aplicación.
