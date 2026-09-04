-- =====================================================================
-- COMBUSTIBLE — cruce de remitos  (MÓDULO EN PRUEBA)
-- ---------------------------------------------------------------------
-- La estación manda un listado de remitos y la factura. Nosotros tenemos
-- nuestra planilla de cargas. Hoy alguien compara las dos a ojo antes de
-- pagar; esto lo hace por número de remito.
--
-- Las dos puntas viven en la misma tabla, separadas por `origen`. Así el
-- cruce es una sola consulta y no dos tablas que se parecen.
--
-- Está en prueba: se usa en paralelo con lo de siempre hasta que los
-- números den. Por eso todo se carga por lotes y un lote se puede borrar
-- entero sin dejar rastro.
--
-- Se pega entero en Supabase -> SQL Editor -> Run.
-- =====================================================================

-- Cada archivo que se sube es un lote. Sirve para deshacer una carga
-- equivocada de una sola vez y para saber de dónde salió cada fila.
create table if not exists combustible_lotes (
  id          bigint generated always as identity primary key,
  origen      text not null check (origen in ('estacion','planilla')),
  archivo     text not null,
  estacion    text,                       -- quién mandó el listado
  periodo     text,                       -- "2026-08", como lo llama el que carga
  filas       int  not null default 0,
  subido      timestamptz not null default now(),
  usuario     text,
  nota        text
);

create table if not exists combustible_cargas (
  id          bigint generated always as identity primary key,
  lote_id     bigint not null references combustible_lotes(id) on delete cascade,
  origen      text not null check (origen in ('estacion','planilla')),
  remito      text not null,              -- normalizado: solo dígitos
  remito_bruto text,                      -- como venía escrito, para mostrarlo
  fecha       date,
  patente     text,                       -- normalizada, puede no engancharse
  unidad_id   bigint references unidades(id),
  litros      numeric,
  importe     numeric,
  estacion    text,
  chofer      text,
  detalle     text,
  creado      timestamptz not null default now()
);

-- El número de remito NO alcanza como clave: dos estaciones distintas
-- repiten numeración, y una planilla de un año trae el mismo número de
-- dos proveedores. La patente lo desambigua. Si el mismo camión aparece
-- dos veces con el mismo remito, eso sí es un duplicado y se pisa.
drop index if exists ux_combustible_remito;
create unique index if not exists ux_combustible_carga
  on combustible_cargas (origen, remito, coalesce(patente, ''));

create index if not exists ix_combustible_lote    on combustible_cargas(lote_id);
create index if not exists ix_combustible_fecha   on combustible_cargas(fecha);
create index if not exists ix_combustible_patente on combustible_cargas(patente);

comment on table combustible_cargas is
  'Las cargas de combustible por las dos puntas: el listado de la estación y nuestra planilla. Se cruzan por remito.';

-- La patente se resuelve al insertar, igual que en odometros: la fila
-- entra igual si no engancha con ninguna unidad, pero queda marcada.
create or replace function _combustible_al_dia() returns trigger as $$
begin
  new.remito := regexp_replace(coalesce(new.remito,''), '[^0-9]', '', 'g');
  new.patente := nullif(upper(regexp_replace(coalesce(new.patente,''),
                                             '[^A-Za-z0-9]', '', 'g')), '');
  if new.patente is not null then
    select u.id into new.unidad_id from unidades u where u.patente = new.patente;
  end if;
  return new;
end $$ language plpgsql;

drop trigger if exists tg_combustible_al_dia on combustible_cargas;
create trigger tg_combustible_al_dia before insert or update on combustible_cargas
  for each row execute function _combustible_al_dia();

-- ---------------------------------------------------------------------
-- EL CRUCE
-- ---------------------------------------------------------------------
-- Una fila por remito, con lo que dice cada lado y en qué no coinciden.
-- El estado es lo único que se mira: 'ok' se paga, el resto se revisa.
-- Las dos se tiran juntas y en orden inverso al que se crean: resumen
-- lee de cruce, así que cruce no se puede tirar primero. Correr este
-- archivo por segunda vez fallaba justo acá.
drop view if exists v_combustible_resumen;
drop view if exists v_combustible_cruce;

create view v_combustible_cruce as
-- El cruce va por dos caminos, en este orden:
--
--   1. Por número de remito. Es el ideal: el número está en la factura.
--   2. Por patente + fecha + litros. Es el que salva el caso real: la
--      numeración de la estación y la de nuestra planilla muchas veces no
--      tienen nada que ver —la estación numera 958 y nosotros anotamos
--      142575— porque cada uno numera su propio comprobante. Pero el mismo
--      camión, el mismo día, cargando los mismos litros es la misma carga
--      aunque el papel se llame distinto.
--
-- El segundo camino solo empareja lo que quedó suelto del primero, y solo
-- cuando hay una sola candidata de cada lado: si el mismo camión cargó dos
-- veces el mismo día los mismos litros, no se adivina, quedan sueltas.
--
-- La columna `emparejado_por` dice cuál de los dos lo unió, para poder
-- mirar con desconfianza los que salieron por el segundo.
with ventana as (
  -- La estación manda un lote —una factura, un mes— y nuestra planilla
  -- tiene todo el historial. Lo de afuera de ese período no es un hallazgo:
  -- son los otros meses.
  select min(fecha) as desde, max(fecha) as hasta
  from combustible_cargas where origen = 'estacion' and fecha is not null
),
por_remito as (
  select e.id as eid, p.id as pid
  from combustible_cargas e
  join combustible_cargas p
    on p.origen = 'planilla' and p.remito = e.remito
  where e.origen = 'estacion' and e.remito <> ''
),
-- Lo que el remito no pudo emparejar, de cada lado.
suelta_e as (
  select * from combustible_cargas e
  where e.origen = 'estacion'
    and not exists (select 1 from por_remito x where x.eid = e.id)
    and e.patente is not null and e.fecha is not null
),
suelta_p as (
  select * from combustible_cargas p
  where p.origen = 'planilla'
    and not exists (select 1 from por_remito x where x.pid = p.id)
    and p.patente is not null and p.fecha is not null
),
candidatas as (
  -- Se emparejan por camión y día, sin mirar los litros. Que difieran es
  -- justamente lo que hay que ver: si además se exigiera que coincidan, la
  -- carga mal facturada quedaría como dos renglones sueltos y el error se
  -- perdería, que es lo contrario de lo que este módulo tiene que hacer.
  select e.id as eid, p.id as pid
  from suelta_e e
  join suelta_p p on p.patente = e.patente and p.fecha = e.fecha
),
-- Solo se empareja lo que es inequívoco: una candidata de cada lado.
por_carga as (
  select c.eid, c.pid from candidatas c
  where (select count(*) from candidatas x where x.eid = c.eid) = 1
    and (select count(*) from candidatas x where x.pid = c.pid) = 1
),
pares as (
  select eid, pid, 'remito' as emparejado_por from por_remito
  union all
  select eid, pid, 'carga'  from por_carga
),
-- Un renglón por par, más lo que quedó solo de cada lado.
renglones as (
  select par.eid, par.pid, par.emparejado_por from pares par
  union all
  select e.id, null, null from combustible_cargas e
   where e.origen = 'estacion'
     and not exists (select 1 from pares x where x.eid = e.id)
  union all
  select null, p.id, null from combustible_cargas p
   where p.origen = 'planilla'
     and not exists (select 1 from pares x where x.pid = p.id)
)
select coalesce(e.remito, p.remito)             as remito,
       e.id as estacion_id, p.id as planilla_id,
       r.emparejado_por,
       e.remito_bruto                           as remito_estacion,
       p.remito_bruto                           as remito_planilla,
       coalesce(e.remito_bruto, p.remito_bruto) as remito_bruto,
       coalesce(e.fecha, p.fecha)               as fecha,
       coalesce(e.patente, p.patente)           as patente,
       coalesce(e.unidad_id, p.unidad_id)       as unidad_id,
       e.litros  as litros_estacion,  p.litros  as litros_planilla,
       e.importe as importe_estacion, p.importe as importe_planilla,
       coalesce(e.estacion, p.estacion)         as estacion,
       -- Redondeo a dos decimales antes de comparar: la estación factura
       -- con dos y la planilla a veces arrastra más, y esa diferencia de
       -- milésimas no es una diferencia real.
       round(coalesce(e.litros,0)  - coalesce(p.litros,0),  2) as dif_litros,
       round(coalesce(e.importe,0) - coalesce(p.importe,0), 2) as dif_importe,
       case
         when p.id is null then 'solo_estacion'   -- nos facturan algo que no tenemos
         when e.id is null and v.desde is not null
              and (p.fecha is null or p.fecha < v.desde or p.fecha > v.hasta)
           then 'fuera_de_periodo'                -- de otro mes: no es un hallazgo
         when e.id is null then 'solo_planilla'   -- cargamos algo que no vino
         when abs(round(coalesce(e.litros,0) - coalesce(p.litros,0), 2)) > 0.5
           then 'difiere_litros'
         when abs(round(coalesce(e.importe,0) - coalesce(p.importe,0), 2)) > 1
           then 'difiere_importe'
         else 'ok'
       end as estado
from renglones r
cross join ventana v
left join combustible_cargas e on e.id = r.eid
left join combustible_cargas p on p.id = r.pid;

comment on view v_combustible_cruce is
  'Un renglón por remito. solo_estacion = nos lo facturan y no lo tenemos. '
  'solo_planilla = lo cargamos y no vino, dentro del período que mandó la estación. '
  'fuera_de_periodo = de nuestra planilla pero de otro mes: no es parte de este control. '
  'emparejado_por dice si los unió el número de remito o la carga (patente + fecha + litros).';

create view v_combustible_resumen as
select estado, count(*)::int as remitos,
       round(sum(coalesce(litros_estacion, litros_planilla)), 2)  as litros,
       round(sum(coalesce(importe_estacion, importe_planilla)), 2) as importe
from v_combustible_cruce group by estado;

alter table combustible_lotes  enable row level security;
alter table combustible_cargas enable row level security;
