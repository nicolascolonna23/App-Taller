-- =====================================================================
-- CAMBIOS DE NEUMÁTICOS — cada cuánto se cambia cada eje, y cuándo toca
-- ---------------------------------------------------------------------
-- Se pega entero en Supabase → SQL Editor → New query → Run.
-- Se puede correr más de una vez sin romper nada: no pisa ninguna regla
-- que ya esté cargada ni ningún cambio registrado.
--
-- Tres piezas:
--
--   1. LOS KM DEL SEMI. Un semi no tiene odómetro: anda lo que anda el
--      tractor que lo lleva. Eso ya lo resuelve el enganche tractor–semi
--      (29_parametros.sql, pantalla Flota → Asociación de equipos): acá se usa esa misma
--      historia, día por día, sin copiarla.
--
--   2. LA REGLA. Por mapa y por eje: en un S-D-D, el eje 1 se cambia a
--      los 150.000 km y el 2 y el 3 a los 220.000. Se puede poner también
--      un tope en días, que es lo único que sirve si un semi no tiene
--      tractor conocido.
--
--   3. EL CAMBIO. De dónde se cuenta. Si la cubierta está cargada y
--      montada, se cuenta desde que entró a ese eje. Si no —porque el
--      inventario de cubiertas todavía no está hecho—, se registra a mano
--      "el eje 2 de tal patente se cambió tal día", y se cuenta desde ahí.
--
-- ANTES tienen que estar corridos 01, 05 (odómetros), 07 (maestro de
-- unidades) y 29 (enganches).
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. EL ENGANCHE DE HOY, SI TODAVÍA NO ESTÁ CARGADO
-- ---------------------------------------------------------------------
-- La ficha de cada tractor dice qué semi lleva hoy, pero la tabla de
-- enganches arranca vacía: hasta que alguien los cargue, los semis no
-- tendrían km. Se toma lo que dice la ficha y se supone que viene desde
-- la primera lectura del satelital de ese tractor. Solo para los semis
-- que nunca tuvieron un enganche cargado; si la fecha no es cierta, se
-- corrige desde Flota → Asociación de equipos.
insert into enganches (tractor_id, semi_id, desde, usuario, nota)
select t.id, s.id,
       coalesce((select min(o.fecha) from odometros o
                 where o.unidad_id = t.id and coalesce(o.fuente, '') <> 'enganche'),
                current_date),
       'sistema',
       'Supuesto al prender los cambios de neumáticos: el enganche de la ficha, '
       'desde la primera lectura del tractor. Corregir si no fue así.'
from unidades t
join unidades s
  on regexp_replace(upper(s.patente), '[^A-Z0-9]', '', 'g')
   = regexp_replace(upper(t.semi), '[^A-Z0-9]', '', 'g')
 and s.id <> t.id
where t.activa and coalesce(t.semi, '') <> ''
  and not exists (select 1 from enganches e where e.semi_id = s.id)
  and not exists (select 1 from enganches e where e.tractor_id = t.id and e.hasta is null)
on conflict do nothing;

update unidades u set es_semi = true
where not u.es_semi and exists (select 1 from enganches e where e.semi_id = u.id);


-- ---------------------------------------------------------------------
-- 2. LOS KILÓMETROS DE CADA DÍA, TAMBIÉN LOS DEL SEMI
-- ---------------------------------------------------------------------
-- El recorrido propio de cada unidad que reporta, y para cada semi el
-- del tractor que lo llevaba ese día (v_km_semi_diario, de 29). Si ese
-- día el semi ya tiene lectura —propia, o la serie que arma el módulo
-- de enganches—, gana la lectura y no se cuenta dos veces.
drop view if exists v_km_dia_efectivo cascade;
create view v_km_dia_efectivo as
select k.unidad_id, k.fecha, k.recorrido as km,
       'propio'::text as fuente, null::bigint as tractor_id
from v_km_diarios k
where k.recorrido is not null
union all
select d.semi_id, d.fecha, d.recorrido, 'tractor', d.tractor_id
from v_km_semi_diario d
where not exists (select 1 from odometros o
                  where o.unidad_id = d.semi_id and o.fecha = d.fecha);

comment on view v_km_dia_efectivo is
  'Km recorridos por día. Los semis heredan los del tractor que los llevaba.';


-- ---------------------------------------------------------------------
-- 3. LA REGLA: cada cuánto se cambia cada eje de cada mapa
-- ---------------------------------------------------------------------
create table if not exists neumaticos_reglas (
  id               bigint generated always as identity primary key,
  configuracion_id bigint not null references configuraciones(id) on delete cascade,
  eje              int    not null check (eje > 0),
  -- direccion, traccion, portante, arrastre. Vacío = se deduce del mapa.
  tipo_eje         text   check (tipo_eje in ('direccion','traccion','portante','arrastre')),
  cada_km          numeric check (cada_km > 0),
  cada_dias        int     check (cada_dias > 0),
  aviso_km         numeric not null default 15000 check (aviso_km >= 0),
  aviso_dias       int     not null default 30    check (aviso_dias >= 0),
  nota             text,
  actualizado      timestamptz not null default now(),
  actualizado_por  text,
  unique (configuracion_id, eje),
  check (cada_km is not null or cada_dias is not null)
);

comment on table neumaticos_reglas is
  'Cada cuántos km (y/o días) se cambian las cubiertas de un eje de un mapa.';

-- Los tractores: dirección a los 150.000, tracción y tercer eje a los
-- 220.000. El resto de los mapas se cargan desde la pantalla.
insert into neumaticos_reglas (configuracion_id, eje, tipo_eje, cada_km, nota)
select c.id, v.eje, v.tipo, v.km, 'Valor inicial'
from configuraciones c
join (values (1, 'direccion', 150000),
             (2, 'traccion',  220000),
             (3, 'portante',  220000)) as v(eje, tipo, km) on true
where c.nombre = 'S-D-D'
on conflict (configuracion_id, eje) do nothing;


-- ---------------------------------------------------------------------
-- 4. EL CAMBIO REGISTRADO A MANO
-- ---------------------------------------------------------------------
-- Para las unidades sin inventario de cubiertas: "al eje 2 de AD 247 MQ
-- se le pusieron gomas nuevas el 3 de marzo". Marca y modelo son
-- opcionales, pero sin ellos ese cambio no entra en la comparación de
-- marcas. No se borra: se anula, y queda quién y por qué.
create table if not exists neumaticos_cambios (
  id            bigint generated always as identity primary key,
  unidad_id     bigint not null references unidades(id),
  eje           int    not null check (eje > 0),
  fecha         date   not null,
  km_unidad     numeric check (km_unidad >= 0),   -- el odómetro ese día, si se sabe
  marca         text,
  modelo        text,
  medida        text,
  nota          text,
  usuario       text,
  creado        timestamptz not null default now(),
  anulado       boolean not null default false,
  anulado_por   text,
  anulado_motivo text
);

create index if not exists ix_neumaticos_cambios
  on neumaticos_cambios(unidad_id, eje, fecha desc) where not anulado;


-- ---------------------------------------------------------------------
-- 5. LOS EJES DE CADA MAPA, CON SU REGLA
-- ---------------------------------------------------------------------
-- La grilla que se parametriza: una fila por eje de cada mapa. El tipo de
-- eje se deduce igual que en desgaste —el primer eje simple dobla, el
-- mapa que no arranca con S es un semi— salvo que la regla diga otro.
drop view if exists v_neumaticos_mapa_ejes cascade;
create view v_neumaticos_mapa_ejes as
select e.*,
       coalesce(r.tipo_eje, e.tipo_deducido) as tipo_eje,
       r.id as regla_id, r.cada_km, r.cada_dias, r.aviso_km, r.aviso_dias,
       r.nota, r.actualizado, r.actualizado_por,
       (select count(*)::int from unidades u
         where u.configuracion_id = e.configuracion_id and u.activa) as unidades
from (
  select cfg.id as configuracion_id, cfg.nombre as mapa, cfg.descripcion,
         p.eje,
         case when bool_and(p.montaje = 'unica') then 'S' else 'D' end as rodado,
         count(*)::int as cubiertas,
         case when p.eje = 1 and bool_and(p.montaje = 'unica') then 'direccion'
              when cfg.nombre not like 'S%'                    then 'arrastre'
              else 'traccion' end as tipo_deducido
  from configuraciones cfg
  join configuracion_posiciones p
    on p.configuracion_id = cfg.id and not p.es_auxilio and p.eje > 0
  group by cfg.id, cfg.nombre, cfg.descripcion, p.eje
) e
left join neumaticos_reglas r
  on r.configuracion_id = e.configuracion_id and r.eje = e.eje;


-- ---------------------------------------------------------------------
-- 6. LOS TRAMOS: cuánto estuvo cada cubierta en cada eje
-- ---------------------------------------------------------------------
-- Una rotación dentro del mismo eje (2IE ↔ 2II) no es un cambio: la goma
-- sigue gastándose en el mismo lugar. Por eso se juntan los montajes
-- seguidos de una misma cubierta en la misma unidad y el mismo eje. Un
-- tramo termina cuando la cubierta sale de ese eje.
drop view if exists v_neumaticos_tramos cascade;
create view v_neumaticos_tramos as
with m as (
  select m.id, m.cubierta_id, m.unidad_id, m.posicion_id, p.eje, m.desde, m.hasta,
         lag(m.unidad_id) over w as unidad_prev,
         lag(p.eje)       over w as eje_prev
  from montajes m
  join configuracion_posiciones p on p.id = m.posicion_id
  where not p.es_auxilio and p.eje > 0
  window w as (partition by m.cubierta_id order by m.desde, m.id)
), g as (
  select m.*,
         sum(case when m.unidad_prev = m.unidad_id and m.eje_prev = m.eje
                  then 0 else 1 end)
           over (partition by m.cubierta_id order by m.desde, m.id) as grupo
  from m
)
select g.cubierta_id, g.unidad_id, g.eje, g.grupo,
       min(g.desde) as desde,
       case when bool_and(g.hasta is not null) then max(g.hasta) end as hasta,
       (array_agg(g.posicion_id order by g.desde desc, g.id desc))[1] as posicion_actual_id,
       count(*)::int as montajes
from g
group by g.cubierta_id, g.unidad_id, g.eje, g.grupo;


-- ---------------------------------------------------------------------
-- 7. EL AVISO, POSICIÓN POR POSICIÓN
-- ---------------------------------------------------------------------
-- Para cada lugar de cada unidad: desde cuándo se cuenta, cuántos km y
-- días lleva, cuánto le falta según la regla de su eje.
--
-- Se cuenta desde lo más nuevo entre el día que la cubierta entró al eje
-- y el último cambio registrado a mano para ese eje.
--
-- 'km_parcial' avisa que el satelital empezó a reportar después de esa
-- fecha: los km son un piso, no el total.
drop view if exists v_neumaticos_posiciones cascade;
create view v_neumaticos_posiciones as
with km as materialized (
  select unidad_id, fecha, km, fuente, tractor_id from v_km_dia_efectivo
), ritmo as materialized (
  -- Cuánto anda por día, con los últimos 60 días.
  select unidad_id,
         round(sum(km) / greatest(current_date - min(fecha), 1)) as km_dia,
         min(fecha) as desde
  from km where fecha > current_date - 60
  group by unidad_id
), primero as materialized (
  select unidad_id, min(fecha) as primer_dato from km group by unidad_id
), pos as materialized (
  select u.id as unidad_id, u.patente, u.interno, u.sucursal, u.uso,
         u.configuracion_id, me.mapa, me.tipo_eje,
         p.id as posicion_id, p.codigo as posicion, p.eje, p.orden,
         me.regla_id, me.cada_km, me.cada_dias, me.aviso_km, me.aviso_dias
  from unidades u
  join configuracion_posiciones p
    on p.configuracion_id = u.configuracion_id and not p.es_auxilio and p.eje > 0
  join v_neumaticos_mapa_ejes me
    on me.configuracion_id = u.configuracion_id and me.eje = p.eje
  where u.activa
), base as materialized (
  select pos.*,
         t.cubierta_id, c.codigo as cubierta, c.marca, c.modelo, c.medida,
         t.desde::date as en_eje_desde,
         mc.id as cambio_id, mc.fecha as cambio_fecha, mc.km_unidad as cambio_km,
         case when mc.fecha is not null
                   and (t.desde is null or mc.fecha >= t.desde::date) then 'cambio'
              when t.desde is not null then 'montaje' end as origen,
         greatest(t.desde::date, mc.fecha) as base_fecha
  from pos
  left join v_neumaticos_tramos t
    on t.unidad_id = pos.unidad_id and t.posicion_actual_id = pos.posicion_id
   and t.hasta is null
  left join cubiertas c on c.id = t.cubierta_id
  left join lateral (
    select nc.id, nc.fecha, nc.km_unidad from neumaticos_cambios nc
    where nc.unidad_id = pos.unidad_id and nc.eje = pos.eje and not nc.anulado
    order by nc.fecha desc, nc.id desc limit 1
  ) mc on true
), sumado as materialized (
  select b.posicion_id, b.unidad_id,
         sum(k.km) as km_suma
  from base b
  join km k on k.unidad_id = b.unidad_id and k.fecha > b.base_fecha
  group by b.posicion_id, b.unidad_id
), calc as materialized (
  select b.*,
         -- Si al registrar el cambio se anotó el odómetro, y la unidad tiene
         -- odómetro propio, la resta es exacta y no depende de que el
         -- satelital haya reportado todos los días.
         case when b.origen = 'cambio' and b.cambio_km is not null
                   and o.km is not null and o.km >= b.cambio_km
              then o.km - b.cambio_km
              when b.base_fecha is not null then coalesce(s.km_suma, 0) end as km,
         (current_date - b.base_fecha) as dias,
         case when b.base_fecha is null then null
              when b.origen = 'cambio' and b.cambio_km is not null and o.km is not null then false
              else (pr.primer_dato is null or pr.primer_dato > b.base_fecha + 3) end as km_parcial,
         r.km_dia,
         (select e.tractor_id from enganches e
           where e.semi_id = b.unidad_id and e.hasta is null) as tractor_id
  from base b
  left join sumado s  on s.posicion_id = b.posicion_id and s.unidad_id = b.unidad_id
  left join ritmo r   on r.unidad_id = b.unidad_id
  left join primero pr on pr.unidad_id = b.unidad_id
  left join lateral (
    select od.km from odometros od where od.unidad_id = b.unidad_id
    order by od.fecha desc limit 1
  ) o on true
)
select c.*,
       tr.patente as tractor,
       case when c.cada_km   is not null and c.km   is not null then c.cada_km   - c.km   end as km_restantes,
       case when c.cada_dias is not null and c.dias is not null then c.cada_dias - c.dias end as dias_por_edad,
       -- Cuándo toca, en días: lo que llegue primero entre los km (al ritmo
       -- de los últimos 60 días) y la edad.
       least(
         case when c.cada_km is not null and c.km is not null and c.km_dia > 0
              then round((c.cada_km - c.km) / c.km_dia) end,
         case when c.cada_dias is not null and c.dias is not null
              then c.cada_dias - c.dias end
       ) as dias_restantes,
       case
         when c.regla_id is null   then 'sin_regla'
         when c.base_fecha is null then 'sin_dato'
         when (c.cada_km is not null and c.km >= c.cada_km)
           or (c.cada_dias is not null and c.dias >= c.cada_dias) then 'vencido'
         when (c.cada_km is not null and c.km >= c.cada_km - c.aviso_km)
           or (c.cada_dias is not null and c.dias >= c.cada_dias - c.aviso_dias) then 'proximo'
         else 'ok'
       end as estado
from calc c
left join unidades tr on tr.id = c.tractor_id;

comment on view v_neumaticos_posiciones is
  'Cada posición de cada unidad, con los km y días que lleva y cuánto le falta para el cambio.';


-- ---------------------------------------------------------------------
-- 8. EL AVISO POR EJE
-- ---------------------------------------------------------------------
-- Lo que se mira en la pantalla. Un eje está como su peor cubierta: si
-- una de las cuatro ya pasó, hay que ir.
drop view if exists v_neumaticos_ejes cascade;
create view v_neumaticos_ejes as
select p.unidad_id, p.patente, p.interno, p.sucursal, p.uso, p.mapa,
       p.configuracion_id, p.eje, p.tipo_eje, p.regla_id,
       p.cada_km, p.cada_dias, p.aviso_km, p.aviso_dias,
       max(p.tractor) as tractor,
       count(*)::int                                   as posiciones,
       count(p.base_fecha)::int                        as con_dato,
       min(p.base_fecha)                               as desde,
       max(p.km)                                       as km,
       max(p.dias)                                     as dias,
       min(p.km_restantes)                             as km_restantes,
       min(p.dias_restantes)                           as dias_restantes,
       bool_or(p.km_parcial)                           as km_parcial,
       max(p.km_dia)                                   as km_dia,
       string_agg(distinct p.origen, ',')              as origen,
       string_agg(distinct nullif(concat_ws(' ', p.marca, p.modelo), ''), ' / ') as cubiertas,
       case
         when bool_or(p.estado = 'vencido')  then 'vencido'
         when bool_or(p.estado = 'proximo')  then 'proximo'
         when bool_or(p.estado = 'sin_regla') then 'sin_regla'
         when bool_or(p.estado = 'sin_dato') then 'sin_dato'
         else 'ok'
       end as estado
from v_neumaticos_posiciones p
group by p.unidad_id, p.patente, p.interno, p.sucursal, p.uso, p.mapa,
         p.configuracion_id, p.eje, p.tipo_eje, p.regla_id,
         p.cada_km, p.cada_dias, p.aviso_km, p.aviso_dias;


-- ---------------------------------------------------------------------
-- 9. CUÁNTO DURARON: la base de las métricas
-- ---------------------------------------------------------------------
-- Una fila por cubierta que ya salió de un eje (o por eje que ya tuvo dos
-- cambios registrados a mano), con los días y los km que duró.
--
-- Los cambios a mano entran solo si en ese período no hay cubiertas
-- cargadas en ese eje: si no, se contaría dos veces lo mismo.
drop view if exists v_neumaticos_duraciones cascade;
create view v_neumaticos_duraciones as
with km as materialized (
  select unidad_id, fecha, km from v_km_dia_efectivo
), primero as materialized (
  select unidad_id, min(fecha) as primer_dato from km group by unidad_id
), tramos as (
  select 'montaje'::text as fuente, t.unidad_id, t.eje,
         t.cubierta_id, c.codigo as cubierta, c.marca, c.modelo, c.medida,
         t.desde::date as desde, t.hasta::date as hasta
  from v_neumaticos_tramos t
  join cubiertas c on c.id = t.cubierta_id
  where t.hasta is not null
), manuales as (
  select 'cambio'::text as fuente, x.unidad_id, x.eje,
         null::bigint as cubierta_id, null::text as cubierta,
         x.marca, x.modelo, x.medida, x.fecha as desde, x.hasta
  from (
    select nc.*, lead(nc.fecha) over (partition by nc.unidad_id, nc.eje
                                      order by nc.fecha, nc.id) as hasta
    from neumaticos_cambios nc where not nc.anulado
  ) x
  where x.hasta is not null and x.hasta > x.fecha
    and not exists (
      select 1 from v_neumaticos_tramos t
      where t.unidad_id = x.unidad_id and t.eje = x.eje
        and t.desde::date < x.hasta
        and coalesce(t.hasta::date, current_date) > x.fecha)
), todo as materialized (
  select row_number() over () as fila, x.*
  from (select * from tramos union all select * from manuales) x
), sumas as materialized (
  select d.fila, sum(k.km) as km
  from todo d
  join km k on k.unidad_id = d.unidad_id and k.fecha > d.desde and k.fecha <= d.hasta
  group by d.fila
)
select d.fuente, d.unidad_id, d.eje, d.cubierta_id, d.cubierta, d.marca,
       d.modelo, d.medida, d.desde, d.hasta,
       u.patente, u.interno, cfg.nombre as mapa, me.tipo_eje,
       (d.hasta - d.desde) as dias,
       sm.km,
       -- Si el satelital no cubre todo el período, los km no son el total.
       (pr.primer_dato is null or pr.primer_dato > d.desde + 3) as km_parcial
from todo d
join unidades u on u.id = d.unidad_id
left join configuraciones cfg on cfg.id = u.configuracion_id
left join v_neumaticos_mapa_ejes me
       on me.configuracion_id = u.configuracion_id and me.eje = d.eje
left join primero pr on pr.unidad_id = d.unidad_id
left join sumas sm on sm.fila = d.fila;

comment on view v_neumaticos_duraciones is
  'Cuánto duró cada cubierta en su eje, en días y en km. De acá salen los promedios.';


-- =====================================================================
-- SEGURIDAD: igual que el resto, nadie entra con la clave pública.
-- =====================================================================
alter table neumaticos_reglas  enable row level security;
alter table neumaticos_cambios enable row level security;
