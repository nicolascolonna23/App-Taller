-- =====================================================================
-- VIENTO EN RUTA: los viajes guardados y la hora de cada carga
-- ---------------------------------------------------------------------
-- 1. La hora de la carga de combustible. La planilla de tickets la trae
--    en su columna Hora y hasta acá se tiraba. Con la hora, una carga del
--    día de salida se sabe si fue antes de salir (es del viaje anterior)
--    o ya en la ruta (es de este).
--
-- 2. Los viajes Buenos Aires ↔ Catamarca de la planilla de hojas del BI,
--    guardados. Se traen solos todas las mañanas (ver
--    .github/workflows/viajes.yml) y también con «Releer planilla». La
--    pantalla lee de acá: abre al instante y los viajes quedan aunque el
--    reporte del BI deje de mostrarlos.
--
-- Se pega entero en Supabase → SQL Editor → New query → Run. Se puede
-- correr las veces que haga falta.
-- =====================================================================

alter table combustible_cargas add column if not exists hora time;

create table if not exists viento_viajes (
  hoja          text        not null default '',
  sentido       text        not null check (sentido in ('ida', 'vuelta')),
  salida        timestamp   not null,     -- hora argentina, sin zona
  salida_real   boolean     not null default true,
  llegada       timestamp,
  llegada_real  boolean     not null default false,
  origen        text,
  destino       text,
  patentes      text[]      not null default '{}',
  semi          text,
  chofer        text,
  actualizado   timestamptz not null default now(),
  primary key (hoja, sentido, salida)
);
create index if not exists ix_viento_viajes_salida on viento_viajes (salida);

-- Cómo salió la última traída: la pantalla lo muestra, y un link que dejó
-- de andar se ve ahí y no semanas después.
create table if not exists viento_traidas (
  unica       boolean primary key default true check (unica),
  cuando      timestamptz not null default now(),
  estado      text,
  columnas    jsonb,
  otros       int
);

alter table viento_viajes  enable row level security;
alter table viento_traidas enable row level security;
