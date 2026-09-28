-- =====================================================================
-- MARCAS Y MEDIDAS DE CUBIERTAS
-- ---------------------------------------------------------------------
-- Hasta acá la marca era un texto libre en la ficha de la cubierta y el
-- logo era un archivo que alguien tenía que dejar en la carpeta
-- `marcas/` del repositorio. Eso quiere decir dos cosas malas: que
-- "FATE", "Fate" y "FATE " son tres marcas distintas para el sistema, y
-- que sumar una marca nueva era hacer un deploy.
--
-- Desde acá son filas:
--
--   cubiertas_marcas    la marca, con su logo cargado desde la pantalla.
--   cubiertas_medidas   las medidas con las que se trabaja, y de qué
--                       familia es cada una: la del camión (295) no entra
--                       en un autoelevador (600x9) y el sistema ya lo
--                       sabía, pero lo sabía escrito en el código.
--
-- El logo se guarda en la base y no en un archivo: el disco de Render se
-- borra en cada deploy, así que un logo subido a mano duraría hasta la
-- próxima publicación. Son imágenes de unos pocos KB.
--
-- Se pega entero en Supabase → SQL Editor → Run. Se puede correr las
-- veces que haga falta: no pisa lo que se haya editado.
--
-- ANTES tiene que estar corrido 01_esquema.sql.
-- =====================================================================

create table if not exists cubiertas_marcas (
  id          bigint generated always as identity primary key,
  nombre      text not null,
  -- Con lo que se la busca y con lo que se nombra su logo. Se arma sola
  -- del nombre: fate, bf goodrich → bfgoodrich.
  slug        text not null unique,
  logo        bytea,
  logo_tipo   text,
  activa      boolean not null default true,
  creado      timestamptz not null default now(),
  actualizado timestamptz not null default now()
);

-- "FATE" y "Fate" son la misma marca. Sin esto son dos.
create unique index if not exists ux_marcas_nombre
  on cubiertas_marcas (lower(nombre));

comment on table cubiertas_marcas is
  'Las marcas de cubierta, con su logo. Se editan desde /parametros.';
comment on column cubiertas_marcas.logo is
  'La imagen, en la base: el disco de Render se borra en cada deploy.';


create table if not exists cubiertas_medidas (
  id          bigint generated always as identity primary key,
  medida      text not null unique,        -- 295/80R22.5
  -- El primer número, que es el que identifica a la familia. Lo que
  -- viene después —el perfil, la llanta— cambia de una marca a otra y no
  -- hace a la cuestión de si la goma entra o no en esa unidad.
  corta       text,
  clase       text check (clase is null or clase in ('camion', 'autoelevador', 'otro')),
  descripcion text,
  activa      boolean not null default true,
  orden       integer not null default 0,
  creado      timestamptz not null default now()
);

comment on table cubiertas_medidas is
  'Las medidas con las que se trabaja y de qué familia es cada una.';


-- ---------------------------------------------------------------------
-- LO QUE YA ESTABA
-- ---------------------------------------------------------------------
-- Las marcas que vienen con logo en el repositorio. El logo se deja en
-- null a propósito: mientras nadie suba uno nuevo, se sigue sirviendo el
-- archivo de siempre. Cargar uno desde la pantalla lo reemplaza.
insert into cubiertas_marcas (nombre, slug) values
  ('Fate', 'fate'),
  ('Bridgestone', 'bridgestone'),
  ('Michelin', 'michelin'),
  ('BF Goodrich', 'bfgoodrich'),
  ('Aplus', 'aplus')
on conflict do nothing;

-- Y las que ya están escritas en las cubiertas cargadas, que son las que
-- se usan de verdad. Si alguna coincide con las de arriba, no entra dos
-- veces.
insert into cubiertas_marcas (nombre, slug)
select distinct on (lower(regexp_replace(lower(c.marca), '[^a-z0-9]', '', 'g')))
       btrim(c.marca),
       regexp_replace(lower(c.marca), '[^a-z0-9]', '', 'g')
from cubiertas c
where coalesce(btrim(c.marca), '') <> ''
  and regexp_replace(lower(c.marca), '[^a-z0-9]', '', 'g') not in
      (select slug from cubiertas_marcas)
on conflict do nothing;


-- Las medidas con las que arranca: la del camión y las de los
-- autoelevadores, que son las dos familias que el sistema ya distinguía.
insert into cubiertas_medidas (medida, corta, clase, descripcion, orden) values
  ('295/80R22.5', '295', 'camion', 'La medida de los camiones de la flota.', 1),
  ('600x9',  '600', 'autoelevador', 'Autoelevador chico.', 10),
  ('700x12', '700', 'autoelevador', 'Autoelevador grande.', 11)
on conflict (medida) do nothing;

-- Y las que ya estén cargadas en las cubiertas, con su familia deducida
-- del primer número. Lo que no se puede deducir queda como 'otro' y se
-- corrige desde la pantalla.
insert into cubiertas_medidas (medida, corta, clase, orden)
select distinct btrim(c.medida),
       (regexp_match(c.medida, '(\d+)'))[1],
       case (regexp_match(c.medida, '(\d+)'))[1]
         when '295' then 'camion'
         when '600' then 'autoelevador'
         when '700' then 'autoelevador'
         else 'otro'
       end,
       50
from cubiertas c
where coalesce(btrim(c.medida), '') <> ''
  and btrim(c.medida) not in (select medida from cubiertas_medidas)
on conflict (medida) do nothing;
