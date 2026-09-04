-- =====================================================================
-- EL MODELO 3D DE CADA UNIDAD
-- ---------------------------------------------------------------------
-- Una columna, nada más: qué modelo 3D se dibuja para esta unidad.
--
-- Se deja vacía en casi todas. Cuando está vacía, la app elige sola por
-- el modelo cargado en el maestro (un S-WAY dibuja el S-Way, un STRALIS
-- dibuja el Hi-Way). Se llena solo cuando esa deducción no acierta y hay
-- que forzarlo a mano desde la pantalla.
--
-- Se pega entero en Supabase → SQL Editor → Run.
-- =====================================================================

alter table unidades add column if not exists modelo_3d text;

comment on column unidades.modelo_3d is
  'Cuál de los modelos 3D se dibuja. Vacío = la app lo deduce del modelo.';

-- La vista tiene que traer la columna nueva o la pantalla no la ve.
drop view if exists v_unidades;
create view v_unidades as
select u.id, u.patente, u.interno, u.tipo, u.marca, u.modelo, u.chasis,
       u.chofer, u.semi, u.sucursal, u.uso, u.nota, u.activa, u.modelo_3d,
       u.km_actual, u.configuracion_id, c.nombre as configuracion,
       (select count(*) from montajes m
         where m.unidad_id = u.id and m.hasta is null) as cubiertas_montadas,
       (select max(o.fecha) from odometros o where o.unidad_id = u.id) as ultima_lectura,
       u.creado, u.actualizado
from unidades u
left join configuraciones c on c.id = u.configuracion_id;

comment on view v_unidades is
  'El maestro con lo que le agrega el resto del sistema. Es lo que lee la pantalla de Flota.';
