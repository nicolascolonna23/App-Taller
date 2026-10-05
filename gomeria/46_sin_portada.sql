-- =====================================================================
-- Se saca la foto de portada propia de cada usuario.
-- ---------------------------------------------------------------------
-- La imagen vivía en la fila del usuario, que se lee en cada pedido, y
-- dejaba al servidor sin memoria. Correr DESPUÉS de desplegar la versión
-- que ya no usa estas columnas.
--
-- Se pega entero en Supabase -> SQL Editor -> Run.
-- =====================================================================
alter table usuarios drop column if exists fondo;
alter table usuarios drop column if exists fondo_tipo;
alter table usuarios drop column if exists fondo_desde;
