-- Planes reutilizables de mantenimiento y su asignación a cada unidad.
-- Ejecutar completo en Supabase > SQL Editor. Es idempotente y no borra datos.

create table if not exists mantenimiento_planes (
  id          bigint generated always as identity primary key,
  nombre      text not null unique,
  descripcion text,
  cada_km     numeric not null check (cada_km > 0),
  activo      boolean not null default true,
  creado      timestamptz not null default now(),
  actualizado timestamptz not null default now()
);

alter table unidades add column if not exists mantenimiento_plan_id bigint;

do $$ begin
  alter table unidades add constraint unidades_mantenimiento_plan_fk
    foreign key (mantenimiento_plan_id) references mantenimiento_planes(id)
    on delete set null;
exception when duplicate_object then null;
end $$;

create index if not exists ix_unidades_mantenimiento_plan
  on unidades(mantenimiento_plan_id);

-- La periodicidad asignada hoy manda para el próximo vencimiento. El valor
-- guardado en services queda como foto histórica del criterio usado entonces.
--
-- Se tira la vista antes de crearla: «create or replace» exige que las
-- columnas se llamen igual que antes y en el mismo orden, y esta versión
-- agrega mantenimiento_plan_id en el medio. Postgres contesta «cannot change
-- name of view column». Tirarla no pierde nada, es una vista: se vuelve a
-- armar acá abajo con los mismos datos.
drop view if exists v_services_hoy;
create view v_services_hoy as
select b.*,
       case
         when b.ultimo_km is null then 'sin_plan'
         when b.cada_km is null then 'sin_plan'
         when b.km_actual is null then 'sin_odometro'
         when b.km_actual < b.ultimo_km then 'km_dudoso'
         when b.km_restantes < 0 then 'vencido'
         when b.km_restantes < b.service_urgente_km then 'urgente'
         when b.km_restantes < b.service_aviso_km then 'proximo'
         else 'ok'
       end as estado,
       case when b.km_restantes >= 0 and b.km_restantes <= b.cada_km
                 and b.km_dia > 0
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
    select * from services sv where sv.unidad_id = u.id
    order by sv.km desc, sv.fecha desc, sv.id desc limit 1
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

