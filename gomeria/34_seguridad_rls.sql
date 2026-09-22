-- =====================================================================
-- SEGURIDAD: activar RLS en las tablas que quedaron sin protección
-- ---------------------------------------------------------------------
-- Supabase avisa "Table publicly accessible" cuando una tabla no tiene
-- Row-Level Security activado: significa que cualquiera con la URL del
-- proyecto puede leer, editar o borrar esa tabla entera a través de la
-- API pública de Supabase (PostgREST), usando la clave "anon".
--
-- Esta app no usa esa API: todo el acceso real pasa por gomeria/base.py,
-- que se conecta directo a Postgres con SUPABASE_DB_URL (el usuario
-- "postgres", que no está sujeto a RLS). Por eso alcanza con activar RLS
-- y no hace falta crear ninguna política: queda todo bloqueado para la
-- API pública y el backend sigue funcionando exactamente igual.
--
-- Se pega entero en Supabase → SQL Editor → New query → Run. Se puede
-- correr las veces que haga falta.
-- =====================================================================

-- Una tabla que todavía no existe (porque su script no se corrió) se
-- saltea: el script no falla y se puede volver a correr después.
do $$
declare t text;
begin
  foreach t in array array[
    'roles', 'rol_modulos', 'sucursales',
    'repuestos_articulos', 'repuestos_movimientos',
    'ordenes_trabajo', 'ordenes_tareas', 'ordenes_repuestos',
    'mantenimiento_planes',
    'solicitudes_compra', 'solicitudes_ajustes', 'solicitud_eventos',
    'solicitudes_contador',
    'urea_tanques', 'urea_movimientos', 'parametros', 'enganches',
    'cubiertas_marcas', 'cubiertas_medidas', 'proveedores',
    'fluidos', 'fluido_movimientos'
  ] loop
    if to_regclass('public.' || t) is not null then
      execute format('alter table %I enable row level security', t);
    end if;
  end loop;
end $$;
