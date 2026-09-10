-- =====================================================================
-- CORREGIR EL KILOMETRAJE DEL ÚLTIMO SERVICE
-- ---------------------------------------------------------------------
-- Dieciséis tractores con el kilometraje mal cargado en su último
-- service. No es un service nuevo: es el mismo, con el número corregido.
-- Por eso se hace acá y no desde la pantalla, que solo sabe registrar
-- services nuevos y sumarlos al historial.
--
-- Se pega entero en Supabase → SQL Editor → New query → Run.
--
-- El script muestra lo que va a cambiar ANTES de cambiarlo. Si algún
-- renglón no cierra, se corta ahí: nada de lo que sigue se ejecutó
-- todavía. Correrlo dos veces es inofensivo, el segundo no cambia nada
-- porque los números ya son los que tienen que ser.
--
-- Cuál es «el último service»: el de FECHA más reciente. No el de más
-- kilómetros, que es como lo venía ordenando la vista, porque cuando el
-- número está mal cargado ese orden puede señalar la fila equivocada.
-- Donde los dos criterios no coinciden, el informe lo marca.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. LOS NÚMEROS BUENOS
-- ---------------------------------------------------------------------
-- AE 988 UW y AH 938 VO no están: la primera está dada de baja y la
-- segunda vino sin número. Si hay que corregirlas, se agregan acá.
drop table if exists _km_service;
create temp table _km_service (patente text primary key, km numeric not null);

insert into _km_service (patente, km) values
  ('AD 247 MQ', 735933),
  ('AE 423 IV', 1652322),
  ('AE 423 IW', 1295194),
  ('AE 588 MW', 1210648),
  ('AF 218 HY', 287110),
  ('AF 470 UT', 525898),
  ('AF 533 SB', 282700),
  ('AF 577 BD', 34571),
  ('AF 796 IX', 152968),
  ('AG 286 TR', 586560),
  ('AG 708 DM', 110381),
  ('AG 865 QF', 359504),
  ('AG 983 HW', 351250),
  ('AH 522 SI', 195997),
  ('AH 861 UB', 139717),
  ('AH 842 GQ', 95740);


-- ---------------------------------------------------------------------
-- 2. QUÉ SERVICE LE TOCA A CADA UNA
-- ---------------------------------------------------------------------
drop table if exists _objetivo;
create temp table _objetivo as
select distinct on (u.id)
       u.id            as unidad_id,
       k.patente       as patente_excel,
       u.patente       as patente_base,
       s.id            as service_id,
       s.fecha         as fecha,
       s.km            as km_viejo,
       k.km            as km_nuevo,
       s.tipo          as tipo
from _km_service k
join unidades u
  on regexp_replace(upper(u.patente), '[^A-Z0-9]', '', 'g')
   = regexp_replace(upper(k.patente), '[^A-Z0-9]', '', 'g')
join services s on s.unidad_id = u.id
order by u.id, s.fecha desc, s.id desc;


-- ---------------------------------------------------------------------
-- 3. LO QUE VA A CAMBIAR  ← MIRAR ESTO ANTES DE SEGUIR
-- ---------------------------------------------------------------------
select o.patente_excel        as patente,
       o.fecha,
       o.tipo,
       o.km_viejo,
       o.km_nuevo,
       o.km_nuevo - o.km_viejo as diferencia,
       od.km                   as odometro_hoy,
       case
         when o.km_nuevo = o.km_viejo then 'ya estaba bien'
         when od.km is not null and o.km_nuevo > od.km
           then 'OJO: el service quedaría con más km que el odómetro de hoy'
         when exists (select 1 from services s2
                      where s2.unidad_id = o.unidad_id and s2.km > o.km_viejo)
           then 'OJO: hay otro service de esta unidad con más km que este'
         else 'ok'
       end as revisar
from _objetivo o
left join lateral (
  select km from odometros od where od.unidad_id = o.unidad_id
  order by fecha desc limit 1
) od on true
order by o.patente_excel;


-- Las que no se van a tocar y por qué.
select k.patente,
       case
         when not exists (
           select 1 from unidades u
           where regexp_replace(upper(u.patente), '[^A-Z0-9]', '', 'g')
               = regexp_replace(upper(k.patente), '[^A-Z0-9]', '', 'g')
         ) then 'la patente no está en la base'
         else 'la unidad no tiene ningún service cargado'
       end as motivo
from _km_service k
where not exists (select 1 from _objetivo o where o.patente_excel = k.patente)
order by k.patente;


-- ---------------------------------------------------------------------
-- 4. LA CORRECCIÓN
-- ---------------------------------------------------------------------
-- Solo el kilometraje. La fecha, el taller, quién lo cargó y de qué plan
-- fue quedan como estaban: lo que estaba mal era el número, no el resto.
update services s
set km = o.km_nuevo
from _objetivo o
where s.id = o.service_id and s.km <> o.km_nuevo;


-- =====================================================================
-- CÓMO QUEDÓ
-- =====================================================================
select o.patente_excel as patente, s.fecha, s.km,
       s.km + s.cada_km as proximo_service
from _objetivo o
join services s on s.id = o.service_id
order by o.patente_excel;

-- Y cómo quedaron esas unidades en el tablero.
select patente, plan_nombre, ultimo_km, proximo_km, km_actual,
       km_restantes, estado
from v_services_hoy
where patente in (select regexp_replace(upper(patente), '[^A-Z0-9]', '', 'g')
                  from _km_service)
order by km_restantes nulls last;
