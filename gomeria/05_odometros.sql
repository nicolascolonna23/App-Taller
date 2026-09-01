-- =====================================================================
-- ODÓMETROS: el kilometraje diario que llega del satelital
-- =====================================================================
-- Todos los días a las 08:00 el scraper de Hawk (repo ServiceDM) lee el
-- odómetro de cada móvil y hoy lo escribe en la planilla. Acá queda
-- además la serie completa, que es lo que la planilla no guarda: ahí se
-- pisa la celda y el valor de ayer se pierde.
--
-- Con esto la gomería puede responder lo que hoy no puede: cuántos
-- kilómetros rodó una cubierta entre que se montó y se sacó, y cuánto
-- sale el kilómetro de goma en cada unidad.
-- =====================================================================

create table if not exists odometros (
  id              bigint generated always as identity primary key,
  unidad_id       bigint references unidades(id),
  patente         text not null,               -- normalizada sin espacios
  fecha           date not null,               -- día de la lectura, hora ARG
  km              numeric not null check (km >= 0),
  ultimo_reporte  timestamptz,                 -- cuándo reportó el equipo
  id_gps          text,
  fuente          text not null default 'hawk',
  leido           timestamptz not null default now()
);

-- Una lectura por unidad y por día. Si el job se corre dos veces (o se
-- dispara a mano después del horario), la segunda pisa a la primera en
-- vez de duplicar el día.
create unique index if not exists ux_odometro_dia
  on odometros(patente, fecha, fuente);

create index if not exists ix_odometro_unidad on odometros(unidad_id, fecha desc);

-- ---------------------------------------------------------------------
-- Al guardar una lectura se actualiza el km de la unidad, pero solo si
-- avanza: un odómetro no vuelve para atrás. Una lectura mala (equipo
-- reiniciado, cambio de módulo) no puede bajar el kilometraje bueno.
-- ---------------------------------------------------------------------
create or replace function _odometro_al_dia() returns trigger as $$
begin
  if new.unidad_id is null then
    select id into new.unidad_id from unidades where patente = new.patente;
  end if;

  if new.unidad_id is not null then
    update unidades
       set km_actual = new.km
     where id = new.unidad_id
       and (km_actual is null or km_actual < new.km);
  end if;

  return new;
end $$ language plpgsql;

drop trigger if exists tg_odometro_al_dia on odometros;
create trigger tg_odometro_al_dia
  before insert or update on odometros
  for each row execute function _odometro_al_dia();

-- ---------------------------------------------------------------------
-- KILÓMETROS ENTRE LECTURAS
-- ---------------------------------------------------------------------
-- La diferencia contra la lectura anterior de esa misma unidad. Ojo que
-- no siempre son 24 horas: el scraper corre de lunes a viernes, así que
-- la lectura del lunes trae el fin de semana entero. Por eso va también
-- la cantidad de días, y el tope de lo creíble se mide por día y no por
-- lectura. Un retroceso es un cambio de equipo, no un dato.
-- ---------------------------------------------------------------------
-- Se borra antes de crearla porque 'create or replace' no admite
-- cambiarle las columnas, y este archivo se vuelve a correr cada vez
-- que la vista cambia.
drop view if exists v_km_diarios;
create view v_km_diarios as
select o.unidad_id,
       o.patente,
       o.fecha,
       o.km,
       lag(o.km)    over w as km_anterior,
       lag(o.fecha) over w as fecha_anterior,
       (o.fecha - lag(o.fecha) over w) as dias,
       case
         when lag(o.km) over w is null then null
         when o.km - lag(o.km) over w < 0 then null
         when o.km - lag(o.km) over w > 1200 * (o.fecha - lag(o.fecha) over w) then null
         else o.km - lag(o.km) over w
       end as recorrido
from odometros o
where o.unidad_id is not null
window w as (partition by o.unidad_id order by o.fecha);

-- ---------------------------------------------------------------------
-- CUÁNTO RODÓ CADA CUBIERTA
-- ---------------------------------------------------------------------
-- Los km de la unidad entre la fecha en que la cubierta se montó y la
-- fecha en que se sacó (o hoy, si sigue puesta). Esto es lo que hasta
-- ahora dependía de que el gomero escribiera el kilometraje a mano.
-- ---------------------------------------------------------------------
drop view if exists v_km_por_montaje;
create view v_km_por_montaje as
select m.id            as montaje_id,
       m.unidad_id,
       m.cubierta_id,
       c.codigo        as cubierta,
       c.marca,
       p.codigo        as posicion,
       m.desde::date   as desde,
       m.hasta::date   as hasta,
       (select min(o.km) from odometros o
         where o.unidad_id = m.unidad_id and o.fecha >= m.desde::date) as km_desde,
       (select max(o.km) from odometros o
         where o.unidad_id = m.unidad_id
           and o.fecha <= coalesce(m.hasta::date, current_date))       as km_hasta
from montajes m
join cubiertas c on c.id = m.cubierta_id
join configuracion_posiciones p on p.id = m.posicion_id;

-- ---------------------------------------------------------------------
-- ÚLTIMA LECTURA DE CADA UNIDAD
-- ---------------------------------------------------------------------
-- Con los días que pasaron desde que reportó: si una unidad deja de
-- reportar, acá se ve, cosa que en la planilla no se ve porque la celda
-- queda con el último valor bueno y parece al día.
-- ---------------------------------------------------------------------
drop view if exists v_odometro_ultimo;
create view v_odometro_ultimo as
select distinct on (o.unidad_id)
       o.unidad_id, o.patente, o.fecha, o.km, o.ultimo_reporte,
       (current_date - o.fecha) as dias_sin_leer
from odometros o
where o.unidad_id is not null
order by o.unidad_id, o.fecha desc;

alter table odometros enable row level security;
