-- =====================================================================
-- COMBUSTIBLE — las cargas de la flota
-- ---------------------------------------------------------------------
-- Nuestra planilla de cargas, por lotes: cada archivo que se sube es un
-- lote y un lote se puede borrar entero sin dejar rastro.
--
-- La columna `origen` admite 'estacion' por las filas que quedaron del
-- cruce de remitos, que se sacó; hoy solo entra 'planilla'.
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
  'Las cargas de combustible de nuestra planilla, por lote.';

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

-- El cruce de remitos contra el listado de la estación se sacó. Sus
-- vistas se tiran por si quedaron de antes.
drop view if exists v_combustible_resumen;
drop view if exists v_combustible_cruce;

alter table combustible_lotes  enable row level security;
alter table combustible_cargas enable row level security;
