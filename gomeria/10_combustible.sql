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

-- Un mismo remito no puede entrar dos veces por el mismo lado. Si el
-- listado se sube de nuevo, la fila se pisa en vez de duplicarse.
create unique index if not exists ux_combustible_remito
  on combustible_cargas (origen, remito);

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
with remitos as (
  select distinct remito from combustible_cargas where remito <> ''
)
select r.remito,
       e.id as estacion_id, p.id as planilla_id,
       coalesce(e.remito_bruto, p.remito_bruto) as remito_bruto,
       coalesce(e.fecha, p.fecha)     as fecha,
       coalesce(e.patente, p.patente) as patente,
       coalesce(e.unidad_id, p.unidad_id) as unidad_id,
       e.litros  as litros_estacion,  p.litros  as litros_planilla,
       e.importe as importe_estacion, p.importe as importe_planilla,
       coalesce(e.estacion, p.estacion) as estacion,
       -- Redondeo a dos decimales antes de comparar: la estación factura
       -- con dos y la planilla a veces arrastra más, y esa diferencia de
       -- milésimas no es una diferencia real.
       round(coalesce(e.litros,0)  - coalesce(p.litros,0),  2) as dif_litros,
       round(coalesce(e.importe,0) - coalesce(p.importe,0), 2) as dif_importe,
       case
         when p.id is null then 'solo_estacion'   -- nos facturan algo que no tenemos
         when e.id is null then 'solo_planilla'   -- cargamos algo que no vino
         when abs(round(coalesce(e.litros,0) - coalesce(p.litros,0), 2)) > 0.5
           then 'difiere_litros'
         when abs(round(coalesce(e.importe,0) - coalesce(p.importe,0), 2)) > 1
           then 'difiere_importe'
         else 'ok'
       end as estado
from remitos r
left join combustible_cargas e on e.remito = r.remito and e.origen = 'estacion'
left join combustible_cargas p on p.remito = r.remito and p.origen = 'planilla';

comment on view v_combustible_cruce is
  'Un renglón por remito. solo_estacion = nos lo facturan y no lo tenemos. solo_planilla = lo cargamos y no vino en el listado.';

create view v_combustible_resumen as
select estado, count(*)::int as remitos,
       round(sum(coalesce(litros_estacion, litros_planilla)), 2)  as litros,
       round(sum(coalesce(importe_estacion, importe_planilla)), 2) as importe
from v_combustible_cruce group by estado;

alter table combustible_lotes  enable row level security;
alter table combustible_cargas enable row level security;
