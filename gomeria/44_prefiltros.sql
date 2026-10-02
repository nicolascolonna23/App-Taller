-- =====================================================================
-- PREFILTROS
-- =====================================================================
-- El prefiltro de combustible se cambia con la misma lógica que el
-- service: cada tantos kilómetros desde el último cambio. La diferencia
-- es que no lo llevan todas las unidades, y que el que lo lleva tiene
-- además su plan de service. Por eso una unidad puede tener dos planes:
--
--   unidades.mantenimiento_plan_id   el service (como siempre)
--   unidades.prefiltro_plan_id       el prefiltro, solo en las que lo llevan
--
-- Los cambios de prefiltro se anotan en la misma tabla `services`, con
-- `sistema = 'prefiltro'`. Así el historial de la unidad es uno solo,
-- pero un cambio de prefiltro no corre el próximo service ni al revés.
--
-- Se pega en Supabase → SQL Editor → New query → Run. Es idempotente y
-- no borra datos. Va después de 29_parametros.sql.
-- =====================================================================

-- 1. La clase nueva de plan.
alter table mantenimiento_planes
  drop constraint if exists mantenimiento_planes_clase_check;
alter table mantenimiento_planes
  add constraint mantenimiento_planes_clase_check
  check (clase in ('preventivo', 'correctivo', 'prefiltro'));

-- Un prefiltro sin cada cuántos km no puede avisar.
alter table mantenimiento_planes
  drop constraint if exists mantenimiento_planes_prefiltro_check;
alter table mantenimiento_planes
  add constraint mantenimiento_planes_prefiltro_check
  check (clase <> 'prefiltro' or cada_km is not null);

comment on column mantenimiento_planes.clase is
  'preventivo: se agenda por km o por días. correctivo: catálogo de trabajos. '
  'prefiltro: el cambio de prefiltro, por km, solo en las unidades que lo llevan.';

-- 2. El segundo plan de la unidad.
alter table unidades add column if not exists prefiltro_plan_id bigint;

do $$ begin
  alter table unidades add constraint unidades_prefiltro_plan_fk
    foreign key (prefiltro_plan_id) references mantenimiento_planes(id)
    on delete set null;
exception when duplicate_object then null;
end $$;

create index if not exists ix_unidades_prefiltro_plan on unidades(prefiltro_plan_id);

-- 3. De qué es cada registro del historial.
alter table services add column if not exists sistema text not null default 'service';

alter table services drop constraint if exists services_sistema_check;
alter table services add constraint services_sistema_check
  check (sistema in ('service', 'prefiltro'));

create index if not exists ix_services_sistema on services (unidad_id, sistema, fecha desc);

comment on column services.sistema is
  'service: el service del plan de mantenimiento. prefiltro: el cambio de prefiltro.';

-- 4. El service de hoy deja de mirar los cambios de prefiltro. Es la
--    misma vista de 24_asignacion_services_y_km.sql con un solo cambio:
--    el último service es el último con sistema = 'service'.
create or replace view v_services_hoy as
select b.*,
       case
         when b.ultimo_km is null or b.cada_km is null then 'sin_plan'
         when b.km_actual is null then 'sin_odometro'
         when b.km_actual < b.ultimo_km then 'km_dudoso'
         when b.km_restantes < 0 then 'vencido'
         when b.km_restantes < b.service_urgente_km then 'urgente'
         when b.km_restantes < b.service_aviso_km then 'proximo'
         else 'ok'
       end as estado,
       case when b.km_restantes >= 0 and b.km_restantes <= b.cada_km and b.km_dia > 0
            then round(b.km_restantes / b.km_dia) end as dias_restantes
from (
  select u.id as unidad_id, u.patente, u.interno, u.sucursal, u.uso,
         u.mantenimiento_plan_id, p.nombre as plan_nombre,
         s.id as service_id, s.fecha as ultimo_fecha, s.km as ultimo_km,
         s.tipo, coalesce(p.cada_km, s.cada_km) as cada_km, s.taller,
         s.km + coalesce(p.cada_km, s.cada_km) as proximo_km,
         o.km as km_actual, o.fecha as km_fecha,
         (s.km + coalesce(p.cada_km, s.cada_km)) - o.km as km_restantes,
         d.km_dia, r.service_urgente_km, r.service_aviso_km
  from unidades u
  cross join alertas_reglas r
  left join mantenimiento_planes p on p.id = u.mantenimiento_plan_id and p.activo
  left join lateral (
    select * from services sv
    where sv.unidad_id = u.id and sv.sistema = 'service'
    order by sv.fecha desc, sv.km desc, sv.id desc limit 1
  ) s on true
  left join lateral (
    select od.km, od.fecha from odometros od where od.unidad_id = u.id
    order by od.fecha desc limit 1
  ) o on true
  left join lateral (
    select round((max(od.km) - min(od.km)) /
                 nullif(max(od.fecha) - min(od.fecha), 0)) as km_dia
    from odometros od
    where od.unidad_id = u.id and od.fecha >= current_date - 60
    having max(od.fecha) > min(od.fecha) and max(od.km) >= min(od.km)
  ) d on true
  where u.activa
    and upper(replace(coalesce(u.uso,''), ' ', '')) not like 'SEMI%'
    and upper(coalesce(u.uso,'')) not like '%REMOLQUE%'
) b;

-- 5. Los prefiltros de hoy: una fila por unidad que lleva prefiltro, con
--    los mismos estados y los mismos umbrales que el service.
create or replace view v_prefiltros_hoy as
select b.*,
       case
         when b.cada_km is null then 'sin_plan'
         when b.ultimo_km is null then 'sin_cambio'
         when b.km_actual is null then 'sin_odometro'
         when b.km_actual < b.ultimo_km then 'km_dudoso'
         when b.km_restantes < 0 then 'vencido'
         when b.km_restantes < b.service_urgente_km then 'urgente'
         when b.km_restantes < b.service_aviso_km then 'proximo'
         else 'ok'
       end as estado,
       case when b.km_restantes >= 0 and b.km_restantes <= b.cada_km and b.km_dia > 0
            then round(b.km_restantes / b.km_dia) end as dias_restantes
from (
  select u.id as unidad_id, u.patente, u.interno, u.sucursal, u.uso,
         u.prefiltro_plan_id, p.nombre as plan_nombre,
         s.id as service_id, s.fecha as ultimo_fecha, s.km as ultimo_km,
         s.tipo, p.cada_km, s.taller,
         s.km + p.cada_km as proximo_km,
         o.km as km_actual, o.fecha as km_fecha,
         (s.km + p.cada_km) - o.km as km_restantes,
         d.km_dia, r.service_urgente_km, r.service_aviso_km
  from unidades u
  cross join alertas_reglas r
  join mantenimiento_planes p on p.id = u.prefiltro_plan_id and p.activo
  left join lateral (
    select * from services sv
    where sv.unidad_id = u.id and sv.sistema = 'prefiltro'
    order by sv.fecha desc, sv.km desc, sv.id desc limit 1
  ) s on true
  left join lateral (
    select od.km, od.fecha from odometros od where od.unidad_id = u.id
    order by od.fecha desc limit 1
  ) o on true
  left join lateral (
    select round((max(od.km) - min(od.km)) /
                 nullif(max(od.fecha) - min(od.fecha), 0)) as km_dia
    from odometros od
    where od.unidad_id = u.id and od.fecha >= current_date - 60
    having max(od.fecha) > min(od.fecha) and max(od.km) >= min(od.km)
  ) d on true
  where u.activa
) b;

comment on view v_prefiltros_hoy is
  'Una fila por unidad con plan de prefiltro: último cambio, próximo y estado.';

-- La vista es para el backend, que entra como "postgres". La API pública
-- de Supabase no tiene por qué verla (ver 34_seguridad_rls.sql).
do $$ begin
  revoke all on v_prefiltros_hoy from anon, authenticated;
exception when undefined_object then null;
end $$;
