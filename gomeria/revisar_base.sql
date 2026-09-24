-- =====================================================================
-- ¿QUÉ LE FALTA A LA BASE?
-- ---------------------------------------------------------------------
-- No cambia nada: solo mira. Se pega entero en Supabase → SQL Editor →
-- New query → Run, en el MISMO proyecto que usa la app en Render.
--
-- Devuelve un renglón por cada script al que le falta algo, con lo que
-- falta. Hay que correr esos scripts en orden, de menor a mayor. Si un
-- script da error, abajo en rojo dice por qué: en Supabase, si una línea
-- falla no se guarda nada del script, aunque lo de arriba parezca andar.
--
-- Si devuelve «Está todo», la base de este proyecto está completa.
-- =====================================================================

with esperado(script, objeto, columna) as (values
  ('01_esquema.sql', 'configuracion_posiciones', null),
  ('01_esquema.sql', 'configuraciones', null),
  ('01_esquema.sql', 'cubiertas', null),
  ('01_esquema.sql', 'mediciones', null),
  ('01_esquema.sql', 'montajes', null),
  ('01_esquema.sql', 'movimientos', null),
  ('01_esquema.sql', 'partes', null),
  ('01_esquema.sql', 'unidades', null),
  ('02_vistas.sql', 'v_historial_cubierta', null),
  ('02_vistas.sql', 'v_mapa_unidad', null),
  ('02_vistas.sql', 'v_posiciones_vacias', null),
  ('02_vistas.sql', 'v_stock', null),
  ('03_usuarios.sql', 'movimientos', 'usuario_id'),
  ('03_usuarios.sql', 'partes', 'usuario_id'),
  ('03_usuarios.sql', 'sesiones', null),
  ('03_usuarios.sql', 'usuarios', null),
  ('04_repuestos.sql', 'repuestos_articulos', null),
  ('04_repuestos.sql', 'repuestos_movimientos', null),
  ('04_repuestos.sql', 'v_repuestos_stock', null),
  ('05_odometros.sql', 'odometros', null),
  ('05_odometros.sql', 'v_km_diarios', null),
  ('05_odometros.sql', 'v_km_por_montaje', null),
  ('05_odometros.sql', 'v_odometro_ultimo', null),
  ('06_vencimientos.sql', 'personas', null),
  ('06_vencimientos.sql', 'tipos_vencimiento', null),
  ('06_vencimientos.sql', 'v_vencimientos_faltantes', null),
  ('06_vencimientos.sql', 'v_vencimientos_hoy', null),
  ('06_vencimientos.sql', 'v_vencimientos_pendientes', null),
  ('06_vencimientos.sql', 'vencimientos', null),
  ('07_unidades.sql', 'unidades', 'actualizado'),
  ('07_unidades.sql', 'unidades', 'chasis'),
  ('07_unidades.sql', 'unidades', 'chofer'),
  ('07_unidades.sql', 'unidades', 'nota'),
  ('07_unidades.sql', 'unidades', 'semi'),
  ('07_unidades.sql', 'unidades', 'tipo'),
  ('07_unidades.sql', 'v_unidades', null),
  ('07_unidades.sql', 'v_unidades_a_revisar', null),
  ('08_modelo3d.sql', 'unidades', 'modelo_3d'),
  ('10_combustible.sql', 'combustible_cargas', null),
  ('10_combustible.sql', 'combustible_lotes', null),
  ('10_combustible.sql', 'v_combustible_cruce', null),
  ('10_combustible.sql', 'v_combustible_resumen', null),
  ('15_ordenes.sql', 'ordenes_repuestos', null),
  ('15_ordenes.sql', 'ordenes_tareas', null),
  ('15_ordenes.sql', 'ordenes_trabajo', null),
  ('15_ordenes.sql', 'v_ordenes', null),
  ('17_combustible_flota.sql', 'v_combustible_flota', null),
  ('17_combustible_flota.sql', 'v_combustible_mes', null),
  ('18_desgaste.sql', 'criterios_desgaste', null),
  ('18_desgaste.sql', 'dibujos_nuevos', null),
  ('18_desgaste.sql', 'v_alertas_cubiertas', null),
  ('18_desgaste.sql', 'v_funcion_posicion', null),
  ('18_desgaste.sql', 'v_km_dia_unidad', null),
  ('18_desgaste.sql', 'v_km_montaje', null),
  ('18_desgaste.sql', 'v_km_vida', null),
  ('18_desgaste.sql', 'v_rendimiento_cubiertas', null),
  ('18_desgaste.sql', 'v_rendimiento_marcas', null),
  ('18_desgaste.sql', 'v_stock_gastado', null),
  ('18_desgaste.sql', 'v_vidas', null),
  ('18_desgaste.sql', 'vidas_cubierta', null),
  ('18_desgaste.sql', 'vidas_cubierta', 'remanente_fin_mm'),
  ('19_historial.sql', 'movimientos', 'deshecho'),
  ('19_historial.sql', 'v_grupos_movimiento', null),
  ('20_alertas.sql', 'alertas_reglas', null),
  ('20_alertas.sql', 'alertas_silenciadas', null),
  ('20_alertas.sql', 'services', null),
  ('20_alertas.sql', 'v_cargas_grandes', null),
  ('20_alertas.sql', 'v_services_hoy', null),
  ('21_ordenes_preventivas.sql', 'ordenes_trabajo', 'mantenimiento'),
  ('21_ordenes_preventivas.sql', 'services', 'orden_id'),
  ('22_planes_mantenimiento.sql', 'mantenimiento_planes', null),
  ('22_planes_mantenimiento.sql', 'unidades', 'mantenimiento_plan_id'),
  ('26_solicitudes.sql', 'ordenes_trabajo', 'gestion'),
  ('26_solicitudes.sql', 'ordenes_trabajo', 'solicitud_id'),
  ('26_solicitudes.sql', 'services', 'solicitud_id'),
  ('26_solicitudes.sql', 'solicitud_eventos', null),
  ('26_solicitudes.sql', 'solicitudes_ajustes', null),
  ('26_solicitudes.sql', 'solicitudes_compra', null),
  ('26_solicitudes.sql', 'solicitudes_contador', null),
  ('26_solicitudes.sql', 'sucursales', null),
  ('26_solicitudes.sql', 'usuarios', 'sucursal_codigo'),
  ('26_solicitudes.sql', 'v_solicitudes', null),
  ('27_roles.sql', 'rol_modulos', null),
  ('27_roles.sql', 'roles', null),
  ('28_urea.sql', 'urea_movimientos', null),
  ('28_urea.sql', 'urea_tanques', null),
  ('28_urea.sql', 'v_urea_movimientos', null),
  ('28_urea.sql', 'v_urea_saldo', null),
  ('28_urea.sql', 'v_urea_unidad', null),
  ('29_parametros.sql', 'enganches', null),
  ('29_parametros.sql', 'mantenimiento_planes', 'cada_dias'),
  ('29_parametros.sql', 'mantenimiento_planes', 'clase'),
  ('29_parametros.sql', 'mantenimiento_planes', 'costo_estimado'),
  ('29_parametros.sql', 'mantenimiento_planes', 'horas_estimadas'),
  ('29_parametros.sql', 'mantenimiento_planes', 'tareas'),
  ('29_parametros.sql', 'parametros', null),
  ('29_parametros.sql', 'roles', 'repara'),
  ('29_parametros.sql', 'roles', 'solo_su_sucursal'),
  ('29_parametros.sql', 'unidades', 'es_semi'),
  ('29_parametros.sql', 'usuarios', 'es_maestro'),
  ('29_parametros.sql', 'v_km_semi_diario', null),
  ('29_parametros.sql', 'v_semis', null),
  ('30_avisos_y_reportes.sql', 'reporte_fotos', null),
  ('30_avisos_y_reportes.sql', 'reportes_chofer', null),
  ('30_avisos_y_reportes.sql', 'vencimientos', 'aviso_fecha'),
  ('31_marcas_medidas.sql', 'cubiertas_marcas', null),
  ('31_marcas_medidas.sql', 'cubiertas_medidas', null),
  ('32_fluidos.sql', 'fluido_movimientos', null),
  ('32_fluidos.sql', 'fluidos', null),
  ('32_fluidos.sql', 'proveedores', null),
  ('32_fluidos.sql', 'v_fluido_movimientos', null),
  ('32_fluidos.sql', 'v_fluidos_saldo', null),
  ('32_fluidos.sql', 'v_fluidos_unidad', null),
  ('33_combustible_origen.sql', 'parametros', 'combustible_estado'),
  ('33_combustible_origen.sql', 'parametros', 'combustible_fuente'),
  ('33_combustible_origen.sql', 'parametros', 'combustible_hora'),
  ('33_combustible_origen.sql', 'parametros', 'combustible_origen'),
  ('33_combustible_origen.sql', 'parametros', 'combustible_ultima'),
  ('35_seguridad.sql', 'desafios_2fa', null),
  ('35_seguridad.sql', 'intentos_login', null),
  ('35_seguridad.sql', 'sesiones', 'con_2fa'),
  ('35_seguridad.sql', 'usuarios', 'totp_activo'),
  ('35_seguridad.sql', 'usuarios', 'totp_respaldo'),
  ('35_seguridad.sql', 'usuarios', 'totp_secreto'),
  ('35_seguridad.sql', 'usuarios', 'totp_ultimo'),
  ('37_asistente_cupo.sql', 'consultas_asistente', null)
),
faltan as (
  select script,
         coalesce(objeto || '.' || columna, objeto) as que
  from esperado e
  where (columna is null and to_regclass('public.' || objeto) is null)
     or (columna is not null and not exists (
           select 1 from information_schema.columns c
           where c.table_schema = 'public' and c.table_name = e.objeto
             and c.column_name = e.columna))
)
select script as "script a correr", string_agg(que, ', ' order by que) as "lo que falta"
from faltan group by script
union all
select 'Está todo', 'La base tiene todo lo que crean los scripts.'
where not exists (select 1 from faltan)
order by 1;
