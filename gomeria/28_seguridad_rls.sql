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

alter table roles                enable row level security;
alter table rol_modulos          enable row level security;
alter table sucursales           enable row level security;
alter table repuestos_articulos  enable row level security;
alter table repuestos_movimientos enable row level security;
alter table ordenes_trabajo      enable row level security;
alter table ordenes_tareas       enable row level security;
alter table ordenes_repuestos    enable row level security;
alter table mantenimiento_planes enable row level security;
alter table solicitudes_compra   enable row level security;
alter table solicitudes_ajustes  enable row level security;
alter table solicitud_eventos    enable row level security;
alter table solicitudes_contador enable row level security;
