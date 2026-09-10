-- Asigna a cada patente su único plan de mantenimiento/service y corrige
-- el kilometraje del último service informado. Conserva la fecha existente.
-- Ejecutar después de 22_planes_mantenimiento.sql y 23_baja_ae988uw.sql.

insert into mantenimiento_planes (nombre, descripcion, cada_km, activo)
values ('TRACTORES', 'Service para tractores', 40000, true),
       ('S-WAY', 'Service para unidades S-WAY', 45000, true),
       ('FURGONES', 'Service para furgones', 20000, true),
       ('VEHICULOS CHICOS', 'Service para vehículos chicos', 10000, true),
       ('VERIFICAR (30.000 km)', 'Periodicidad pendiente de validación', 30000, true)
on conflict (nombre) do update
set cada_km = excluded.cada_km, descripcion = excluded.descripcion,
    activo = true, actualizado = now();

with asignacion(patente, plan) as (values
  ('AD247MQ','TRACTORES'), ('AE423IV','TRACTORES'), ('AE423IW','TRACTORES'),
  ('AE588MW','TRACTORES'), ('AE988UW','TRACTORES'), ('AF218HY','TRACTORES'),
  ('AF470UT','TRACTORES'), ('AF533SB','TRACTORES'), ('AF577BD','TRACTORES'),
  ('AF796IX','TRACTORES'), ('AG286TR','TRACTORES'), ('AG708DM','TRACTORES'),
  ('AG865QF','TRACTORES'), ('AG983HW','TRACTORES'), ('AH522SI','S-WAY'),
  ('AH861UB','S-WAY'), ('AH938VO','S-WAY'), ('AH842GQ','S-WAY'),
  ('AF310TU','VERIFICAR (30.000 km)'), ('AG082ZL','FURGONES'),
  ('AG797NJ','VEHICULOS CHICOS'), ('KOF186','FURGONES'), ('KSP007','FURGONES'),
  ('VWL688','FURGONES'), ('VXO389','FURGONES'), ('VYE907','FURGONES'),
  ('NBR784',null), ('HCU499','FURGONES'), ('AD909NU','FURGONES'),
  ('AE116RO','FURGONES'), ('AF103BT','FURGONES'), ('AF591UW','FURGONES'),
  ('AG070OR','VERIFICAR (30.000 km)'), ('DHS534','FURGONES'),
  ('PAN639','FURGONES'), ('CAF865','FURGONES'), ('EWQ717','VEHICULOS CHICOS'),
  ('JEA499','FURGONES'), ('MJF275','FURGONES'), ('MDH784','FURGONES'),
  ('PIQ468','FURGONES'), ('AA823XJ','FURGONES'), ('AG224IE','FURGONES'),
  ('CDZ499','FURGONES'), ('CYD468','FURGONES'), ('ISK266','FURGONES'),
  ('RYN309','FURGONES'), ('PDS082','FURGONES'), ('FLG593','FURGONES'),
  ('GWF267','FURGONES'), ('AE527FA','FURGONES')
)
update unidades u
set mantenimiento_plan_id = p.id, actualizado = now()
from asignacion a
left join mantenimiento_planes p on p.nombre = a.plan
where regexp_replace(upper(u.patente), '[^A-Z0-9]', '', 'g') = a.patente;

with valores(patente, km) as (values
  ('AD247MQ',735933::numeric), ('AE423IV',1652322), ('AE423IW',1295194),
  ('AE588MW',1210648), ('AF218HY',287110), ('AF470UT',525898),
  ('AF533SB',282700), ('AF577BD',34571), ('AF796IX',152968),
  ('AG286TR',586560), ('AG708DM',110381), ('AG865QF',359504),
  ('AG983HW',351250), ('AH522SI',195997), ('AH861UB',139717),
  ('AH842GQ',95740)
), ultimos as (
  select distinct on (u.id) s.id as service_id, v.km
  from valores v
  join unidades u on regexp_replace(upper(u.patente), '[^A-Z0-9]', '', 'g') = v.patente
  join services s on s.unidad_id = u.id
  order by u.id, s.km desc, s.fecha desc, s.id desc
)
update services s set km = ultimos.km
from ultimos where s.id = ultimos.service_id;

-- Si la migración experimental de varios planes llegó a ejecutarse, esta
-- vista vuelve a dejar una sola fila y un solo plan por unidad.
drop view if exists v_services_hoy;
create view v_services_hoy as
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
    and upper(replace(coalesce(u.uso,''), ' ', '')) not like 'SEMI%'
    and upper(coalesce(u.uso,'')) not like '%REMOLQUE%'
) b;

select u.patente, p.nombre as plan, s.ultimo_km
from unidades u
left join mantenimiento_planes p on p.id = u.mantenimiento_plan_id
left join v_services_hoy s on s.unidad_id = u.id
where regexp_replace(upper(u.patente), '[^A-Z0-9]', '', 'g') in
      ('AD247MQ','AE423IV','AE423IW','AE588MW','AF218HY','AF470UT','AF533SB',
       'AF577BD','AF796IX','AG286TR','AG708DM','AG865QF','AG983HW','AH522SI',
       'AH861UB','AH938VO','AH842GQ')
order by u.patente;
