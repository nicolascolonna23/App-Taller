-- =====================================================================
-- VIENTO EN RUTA: lo ya bajado de Open-Meteo, para no pedirlo de nuevo
-- ---------------------------------------------------------------------
-- Una fila por punto del recorrido y por hora. El punto va por
-- coordenadas y no por número: si mañana se corre la ruta, lo guardado
-- sigue valiendo para los puntos que no se movieron.
--
-- La hora es la argentina, sin zona: así la devuelve Open-Meteo y así
-- vienen las hojas de ruta.
--
-- Sin esta tabla la pantalla anda igual: guarda en memoria y vuelve a
-- preguntar después de cada reinicio.
--
-- Se pega entero en Supabase → SQL Editor → New query → Run. Se puede
-- correr las veces que haga falta.
-- =====================================================================
create table if not exists viento_horas (
  lat        numeric(5,2) not null,
  lon        numeric(5,2) not null,
  hora       timestamp    not null,
  velocidad  real         not null,   -- km/h, media a 10 m
  rafaga     real,                    -- km/h
  direccion  real         not null,   -- de dónde viene: 0 norte, 90 este
  primary key (lat, lon, hora)
);
create index if not exists ix_viento_horas_hora on viento_horas (hora);

-- La tabla se lee solo desde el servidor; la API pública, cerrada.
alter table viento_horas enable row level security;

-- El módulo nuevo, a los que ven todo. El que administra lo abre igual.
insert into rol_modulos (rol_codigo, modulo)
select r, 'viento' from unnest(array['admin','encargado']) as r
where exists (select 1 from roles where codigo = r)
on conflict do nothing;
