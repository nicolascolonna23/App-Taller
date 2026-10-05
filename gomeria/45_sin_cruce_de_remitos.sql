-- =====================================================================
-- Se saca el cruce de remitos contra el listado de la estación.
-- ---------------------------------------------------------------------
-- Tira las dos vistas del cruce. Las cargas quedan como están: las de
-- nuestra planilla siguen siendo los tickets, y las que se habían subido
-- del listado de la estación (origen = 'estacion') no se borran solas;
-- si se quieren sacar, al final hay una línea comentada.
--
-- Se pega entero en Supabase -> SQL Editor -> Run.
-- =====================================================================
drop view if exists v_combustible_resumen;
drop view if exists v_combustible_cruce;

-- delete from combustible_lotes where origen = 'estacion';
