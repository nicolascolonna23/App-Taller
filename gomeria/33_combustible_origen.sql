-- =====================================================================
-- CÓMO ENTRA EL COMBUSTIBLE
-- ---------------------------------------------------------------------
-- El kilometraje ya se podía parametrizar: lo trae el satelital o lo
-- carga una persona. El combustible funcionaba de una sola manera —
-- alguien sube un archivo— y no siempre es así: el control se lleva en
-- una planilla de Google que se edita todos los días, y bajarla a mano
-- para volver a subirla es trabajo que la computadora puede hacer sola.
--
--   manual      se anota carga por carga, o se sube el archivo cuando hay.
--   automatico  el sistema entra solo a un link —una hoja de Google
--               publicada, o cualquier dirección que devuelva un CSV— y
--               trae lo que haya.
--
-- Traer de nuevo la misma planilla no duplica nada: cada remito se pisa
-- con su última versión, que es lo que ya hacía subir el archivo a mano.
--
-- Se pega entero en Supabase → SQL Editor → Run. Se puede correr las
-- veces que haga falta.
--
-- ANTES tiene que estar corrido 29_parametros.sql.
-- =====================================================================

alter table parametros
  add column if not exists combustible_origen text not null default 'manual';

do $$
begin
  if not exists (select 1 from pg_constraint
                 where conname = 'parametros_combustible_origen_check') then
    alter table parametros
      add constraint parametros_combustible_origen_check
      check (combustible_origen in ('automatico', 'manual'));
  end if;
end $$;

-- El link del que se trae. Es una dirección que devuelve un CSV: la hoja
-- de Google publicada, o el link normal de la hoja —el sistema lo
-- convierte—, o lo que sirva cualquier otro sistema.
alter table parametros add column if not exists combustible_fuente text;

-- A qué hora entra a buscarla. Informativa: la corrida la agenda GitHub
-- Actions, igual que la del satelital.
alter table parametros
  add column if not exists combustible_hora text not null default '06:00';

-- Cómo salió la última vez. Sin esto, un link que dejó de andar no se
-- nota hasta que alguien busca una carga y no está.
alter table parametros add column if not exists combustible_ultima timestamptz;
alter table parametros add column if not exists combustible_estado text;

comment on column parametros.combustible_origen is
  'manual: se anota o se sube el archivo. automatico: el sistema trae del link.';
comment on column parametros.combustible_fuente is
  'El link del que se trae la planilla. Tiene que devolver un CSV.';
comment on column parametros.combustible_estado is
  'Cómo salió la última traída. Un link que dejó de andar se ve acá.';
