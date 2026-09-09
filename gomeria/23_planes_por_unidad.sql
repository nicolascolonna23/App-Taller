-- =====================================================================
-- UN CAMIÓN, VARIOS PLANES: M1, M2 y M3 corriendo en paralelo
-- ---------------------------------------------------------------------
-- Se pega entero en Supabase → SQL Editor → New query → Run. Se puede
-- correr las veces que haga falta. Va después de
-- gomeria/22_planes_mantenimiento.sql, que es el que crea los planes.
--
-- El 22 dejó los planes parametrizados y uno asignado por patente. Eso
-- alcanza para un auto, que tiene un solo service cada 10.000. No alcanza
-- para un camión: un Hi-Way tiene un M1 cada 45.000, un M2 cada 90.000 y
-- un M3 cada 135.000, y los tres corren por su cuenta. Con un solo plan
-- por unidad, elegir el M3 apaga el aviso del M1.
--
-- Acá la asignación pasa a ser una lista: la unidad tiene los planes que
-- le tocan, y cada uno cuenta y avisa por separado. Lo que ya estaba
-- asignado se conserva: cada unidad arranca con el plan que tenía.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. QUÉ PLANES LE TOCAN A CADA UNIDAD
-- ---------------------------------------------------------------------
create table if not exists unidad_planes (
  unidad_id bigint not null references unidades(id) on delete cascade,
  plan_id   bigint not null references mantenimiento_planes(id) on delete cascade,
  desde     date not null default current_date,
  usuario   text,
  primary key (unidad_id, plan_id)
);

create index if not exists ix_unidad_planes_plan on unidad_planes (plan_id);

comment on table unidad_planes is
  'Los planes de mantenimiento que le corresponden a cada unidad. Varios por unidad: cada uno avisa por su cuenta.';

-- Lo asignado con el modelo viejo pasa a la lista nueva. Se corre las
-- veces que haga falta: el on conflict lo hace inofensivo.
insert into unidad_planes (unidad_id, plan_id)
select u.id, u.mantenimiento_plan_id
from unidades u
where u.mantenimiento_plan_id is not null
on conflict do nothing;

comment on column unidades.mantenimiento_plan_id is
  'Histórico. La asignación de planes vive en unidad_planes desde que una unidad puede tener varios.';


-- ---------------------------------------------------------------------
-- 2. DE QUÉ PLAN FUE CADA SERVICE
-- ---------------------------------------------------------------------
-- Los services que ya están cargados quedan sin plan, y está bien: son la
-- historia que vino de las planillas, donde el tipo no figuraba. Sirven
-- igual como punto de partida, hasta que se registre el primero de cada
-- plan.
alter table services add column if not exists plan_id bigint
  references mantenimiento_planes(id);

create index if not exists ix_services_plan on services (unidad_id, plan_id, km desc);


-- =====================================================================
-- LA VISTA, AHORA POR UNIDAD Y POR PLAN
-- =====================================================================
-- Antes era una fila por unidad. Ahora es una por unidad y plan asignado:
-- un camión con M1, M2 y M3 son tres renglones, cada uno con su propio
-- «cuánto falta». La unidad sin planes entra igual, con el plan en nulo, y
-- se comporta como venía: manda el intervalo de su último service.
--
-- Se tira la vista antes de crearla porque cambia de forma, y «create or
-- replace» no puede reacomodar columnas. Nada más depende de ella: la leen
-- alertas.py y las pantallas, que se recargan solas.
drop view if exists v_services_hoy;

create view v_services_hoy as
select b.*,
       case
         when b.ultimo_km is null then 'sin_service'
         when b.cada_km   is null then 'sin_service'
         when b.km_actual is null then 'sin_odometro'
         -- El satelital marca menos kilómetros de los que la unidad tenía
         -- en su último service. Eso no pasa en la realidad: o le cambiaron
         -- el equipo de GPS y el contador arrancó de nuevo, o la unidad no
         -- está reportando. Los dos números no se pueden restar, y decir
         -- 'ok' sería pintar de verde una unidad que puede estar pasada de
         -- service. Se dice que no se sabe.
         when b.km_actual < b.ultimo_km             then 'km_dudoso'
         when b.km_restantes < 0                    then 'vencido'
         when b.km_restantes < b.service_urgente_km then 'urgente'
         when b.km_restantes < b.service_aviso_km   then 'proximo'
         else 'ok'
       end as estado,
       -- Cuántos días faltan, con lo que anda esa unidad por día. Un
       -- camión de larga distancia se come 15.000 km en un mes; los mismos
       -- kilómetros en un utilitario de reparto son medio año. Solo hacia
       -- adelante: «faltan -518 días» no es una cuenta.
       case when b.km_restantes >= 0 and b.km_restantes <= b.cada_km
                 and b.km_dia > 0
            then round(b.km_restantes / b.km_dia) end as dias_restantes
from (
  select a.unidad_id, a.patente, a.interno, a.sucursal, a.uso, a.modelo,
         a.plan_id, a.plan_nombre, a.plan_descripcion,
         s.id as service_id, s.fecha as ultimo_fecha, s.km as ultimo_km,
         s.tipo, s.taller,
         -- El plan manda sobre el número suelto de la fila: para eso se
         -- parametriza. Sin plan, sigue mandando el del último service.
         coalesce(a.plan_cada_km, s.cada_km)                 as cada_km,
         -- Si el último service es de ese plan, o es uno viejo sin plan que
         -- se está usando de punto de partida. La pantalla lo aclara: no es
         -- lo mismo «el último M1 fue a los 500.000» que «no hay ningún M1
         -- registrado y se cuenta desde el último service que haya».
         coalesce(s.del_plan, false)                         as referencia_del_plan,
         s.km + coalesce(a.plan_cada_km, s.cada_km)          as proximo_km,
         o.km                                                as km_actual,
         o.fecha                                             as km_fecha,
         (s.km + coalesce(a.plan_cada_km, s.cada_km)) - o.km as km_restantes,
         d.km_dia,
         r.service_urgente_km, r.service_aviso_km
  from (
    select u.id as unidad_id, u.patente, u.interno, u.sucursal, u.uso, u.modelo,
           p.id as plan_id, p.nombre as plan_nombre,
           p.descripcion as plan_descripcion, p.cada_km as plan_cada_km
    from unidades u
    left join unidad_planes up on up.unidad_id = u.id
    left join mantenimiento_planes p on p.id = up.plan_id and p.activo
    where u.activa
  ) a
  cross join alertas_reglas r
  left join lateral (
    select sv.*, (sv.plan_id is not null) as del_plan
    from services sv
    where sv.unidad_id = a.unidad_id
      and (sv.plan_id = a.plan_id or sv.plan_id is null)
    -- Primero el de ese plan; si no hay ninguno, el más reciente sin plan.
    order by (sv.plan_id = a.plan_id) desc nulls last,
             sv.km desc, sv.fecha desc, sv.id desc
    limit 1
  ) s on true
  left join lateral (
    select od.km, od.fecha from odometros od where od.unidad_id = a.unidad_id
    order by od.fecha desc limit 1
  ) o on true
  left join lateral (
    select round((max(od.km) - min(od.km)) /
                 nullif(max(od.fecha) - min(od.fecha), 0)) as km_dia
    from odometros od
    where od.unidad_id = a.unidad_id and od.fecha >= current_date - 60
    having max(od.fecha) > min(od.fecha) and max(od.km) >= min(od.km)
  ) d on true
) b;

comment on view v_services_hoy is
  'Una fila por unidad y plan: cuándo fue el último service de ese tipo y cuánto falta para el próximo.';


-- =====================================================================
-- SEGURIDAD
-- =====================================================================
alter table unidad_planes enable row level security;


-- =====================================================================
-- CÓMO QUEDÓ
-- =====================================================================
select count(*) as planes_activos from mantenimiento_planes where activo;
select count(*) as asignaciones from unidad_planes;
select estado, count(*) as renglones from v_services_hoy group by estado order by 2 desc;

-- Las unidades que todavía no tienen ningún plan. Siguen funcionando con
-- el intervalo de su último service, pero mientras estén acá el criterio
-- no está parametrizado.
select count(*) as unidades_sin_plan
from unidades u
where u.activa and not exists (select 1 from unidad_planes up where up.unidad_id = u.id);
