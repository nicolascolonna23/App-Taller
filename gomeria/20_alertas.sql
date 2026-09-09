-- =====================================================================
-- ALERTAS: todo lo que hay que mirar hoy, en un solo lado
-- ---------------------------------------------------------------------
-- Se pega entero en Supabase → SQL Editor → New query → Run. Se puede
-- correr las veces que haga falta.
--
-- Los avisos estaban repartidos: los vencimientos en su pantalla, los
-- services en una planilla de Google, y las cargas raras de combustible
-- en ningún lado. Nadie mira cuatro pantallas todos los días, así que en
-- la práctica no se miraba ninguna.
--
-- Acá entran las cuatro fuentes, con la misma forma y el mismo orden de
-- urgencia. Lo que arma la lista es alertas.py; la base pone las tres
-- cosas que le faltaban:
--
--   1. La tabla de services, que hasta ahora vivía afuera de la base.
--   2. Los números que definen cuándo algo es una alerta.
--   3. Dónde se anota que una alerta ya se miró.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. LOS SERVICES
-- ---------------------------------------------------------------------
-- Una fila por service hecho. No se pisa el anterior: el historial de
-- cuándo se le hizo cada uno a un camión es la mitad de lo que se mira
-- cuando hay que decidir si un motor está bien cuidado.
--
-- 'cada_km' es cada cuánto le toca a ESA unidad de ahí en más. Va en el
-- service y no en la unidad porque cambia con el tiempo —un camión que
-- pasa a hacer distribución cambia de plan— y así queda registrado desde
-- cuándo rige el nuevo.
create table if not exists services (
  id          bigint generated always as identity primary key,
  unidad_id   bigint not null references unidades(id),
  fecha       date not null default current_date,
  km          numeric not null check (km >= 0),
  tipo        text,                    -- M6, aceite y filtros, correa…
  cada_km     numeric not null default 15000 check (cada_km > 0),
  taller      text,
  observaciones text,
  usuario     text,
  creado      timestamptz not null default now()
);

create index if not exists ix_services_unidad on services (unidad_id, km desc);

comment on table services is
  'Los services hechos. El último de cada unidad, más cada_km, dice cuándo toca el siguiente.';


-- ---------------------------------------------------------------------
-- 2. CUÁNDO ALGO ES UNA ALERTA
-- ---------------------------------------------------------------------
-- Una sola fila, editable desde la pantalla. Los umbrales de service son
-- los mismos que ya usaba el tablero de Services, para que las dos
-- pantallas no digan cosas distintas del mismo camión.
create table if not exists alertas_reglas (
  id                  int primary key default 1 check (id = 1),
  -- Una carga de gasoil más grande que esto es un tanque entero y medio:
  -- o se cargaron dos unidades con un remito, o hay un error de carga, o
  -- alguien se llevó combustible. Las tres cosas hay que mirarlas.
  litros_maximos      numeric not null default 450 check (litros_maximos > 0),
  service_urgente_km  numeric not null default 5000  check (service_urgente_km > 0),
  service_aviso_km    numeric not null default 15000 check (service_aviso_km > 0),
  -- Hasta cuántos días para atrás se miran las cargas de combustible. Una
  -- carga rara de hace dos años no es una alerta, es historia.
  combustible_dias    int     not null default 90 check (combustible_dias > 0),
  check (service_aviso_km >= service_urgente_km)
);

insert into alertas_reglas (id) values (1) on conflict (id) do nothing;


-- ---------------------------------------------------------------------
-- 3. LO QUE YA SE MIRÓ
-- ---------------------------------------------------------------------
-- Sin esto, la carga de 480 litros del camión que sí tiene tanque grande
-- aparece todos los días, para siempre, hasta que la pantalla deja de
-- leerse. Silenciar pide motivo: dentro de seis meses, «alguien la
-- ocultó» no le sirve a nadie.
--
-- 'hasta' en null es para siempre. Con fecha, la alerta vuelve sola: sirve
-- para «ya lo pedí, avisame de nuevo la semana que viene».
create table if not exists alertas_silenciadas (
  id        bigint generated always as identity primary key,
  fuente    text not null check (fuente in ('vencimiento','service','combustible','cubierta')),
  clave     text not null,             -- el id de la fila que originó la alerta
  motivo    text not null,
  hasta     date,
  usuario   text,
  creado    timestamptz not null default now()
);

create unique index if not exists ux_alerta_silenciada
  on alertas_silenciadas (fuente, clave);

comment on column alertas_silenciadas.hasta is
  'Nulo = para siempre. Con fecha, la alerta vuelve sola ese día.';


-- =====================================================================
-- LA VISTA DE SERVICES
-- =====================================================================
-- Una fila por unidad activa: cuándo fue el último service, en qué
-- kilómetro está hoy según el satelital, y cuántos le faltan para el
-- próximo. Los estados son los mismos que ya usa el tablero de Services.
create or replace view v_services_hoy as
select b.*,
       case
         when b.ultimo_km   is null then 'sin_plan'
         when b.km_actual   is null then 'sin_odometro'
         when b.km_restantes < 0                        then 'vencido'
         when b.km_restantes < b.service_urgente_km     then 'urgente'
         when b.km_restantes < b.service_aviso_km       then 'proximo'
         else 'ok'
       end as estado,
       -- Cuántos días faltan, con lo que anda esa unidad por día. Un
       -- camión de larga distancia se come 15.000 km en un mes; el mismo
       -- número de kilómetros en un utilitario de reparto es medio año.
       -- Solo hacia adelante: «faltan -518 días» no es una cuenta, es un
       -- número que hay que interpretar. Lo que está pasado se dice en
       -- kilómetros, que es como se mide un service.
       case when b.km_restantes >= 0 and b.km_dia > 0
            then round(b.km_restantes / b.km_dia) end as dias_restantes
from (
  select u.id as unidad_id, u.patente, u.interno, u.sucursal, u.uso,
         s.id as service_id, s.fecha as ultimo_fecha, s.km as ultimo_km,
         s.tipo, s.cada_km, s.taller,
         s.km + s.cada_km            as proximo_km,
         o.km                        as km_actual,
         o.fecha                     as km_fecha,
         (s.km + s.cada_km) - o.km   as km_restantes,
         d.km_dia,
         r.service_urgente_km, r.service_aviso_km
  from unidades u
  cross join alertas_reglas r
  left join lateral (
    select * from services sv where sv.unidad_id = u.id
    order by sv.km desc, sv.fecha desc, sv.id desc limit 1
  ) s on true
  left join lateral (
    select od.km, od.fecha from odometros od where od.unidad_id = u.id
    order by od.fecha desc limit 1
  ) o on true
  left join lateral (
    select round((max(od.km) - min(od.km)) / nullif(max(od.fecha) - min(od.fecha), 0)) as km_dia
    from odometros od
    where od.unidad_id = u.id and od.fecha >= current_date - 60
    having max(od.fecha) > min(od.fecha) and max(od.km) >= min(od.km)
  ) d on true
  where u.activa
) b;

comment on view v_services_hoy is
  'Una fila por unidad: último service, km de hoy y cuánto falta para el próximo.';


-- =====================================================================
-- LAS CARGAS GRANDES DE COMBUSTIBLE
-- =====================================================================
-- Las que pasan del máximo, dentro de la ventana que dicen las reglas.
-- Se toman las de la planilla propia y no las del listado de la estación:
-- las dos describen la misma carga, y contarla dos veces sería mostrar
-- dos alertas de un solo hecho.
create or replace view v_cargas_grandes as
select c.id as carga_id, c.remito, c.remito_bruto, c.fecha,
       c.patente, c.unidad_id, u.interno,
       c.litros, c.importe, c.estacion, c.chofer,
       r.litros_maximos,
       round(c.litros - r.litros_maximos, 2) as litros_de_mas
from combustible_cargas c
cross join alertas_reglas r
left join unidades u on u.id = c.unidad_id
where c.origen = 'planilla'
  and c.litros is not null
  and c.litros > r.litros_maximos
  and (c.fecha is null or c.fecha >= current_date - r.combustible_dias);


-- =====================================================================
-- SEGURIDAD
-- =====================================================================
alter table services            enable row level security;
alter table alertas_reglas      enable row level security;
alter table alertas_silenciadas enable row level security;


-- =====================================================================
-- CÓMO QUEDÓ
-- =====================================================================
select litros_maximos as "carga máxima (L)",
       service_urgente_km as "service urgente (km)",
       service_aviso_km   as "service aviso (km)",
       combustible_dias   as "días de combustible"
from alertas_reglas;

select estado, count(*) as unidades from v_services_hoy group by estado order by 2 desc;

select count(*) as cargas_grandes from v_cargas_grandes;
