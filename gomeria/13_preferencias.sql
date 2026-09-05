-- =====================================================================
-- PREFERENCIAS DE CADA USUARIO
-- ---------------------------------------------------------------------
-- Se pega entero en Supabase → SQL Editor → New query → Run.
-- Se puede correr más de una vez sin romper nada.
--
-- Cómo ve cada uno la aplicación: claro u oscuro, con qué color, y con
-- qué foto de portada. Es de cada usuario y no de la empresa: uno la usa
-- de noche en el taller y otro de día en la oficina, y no tienen por qué
-- verla igual.
-- =====================================================================

alter table usuarios
  -- El tema y la paleta. Un jsonb y no dos columnas porque acá van a
  -- entrar más cosas —el módulo con el que arranca, qué columnas mira—
  -- y cada una no merece una migración.
  add column if not exists preferencias jsonb not null default '{}'::jsonb,
  -- La foto de portada, la que sube el usuario. Va en la base y no en un
  -- servicio aparte: son unas pocas fotos de unos pocos usuarios, y una
  -- pieza menos que pueda fallar un domingo.
  add column if not exists fondo bytea,
  add column if not exists fondo_tipo text,
  add column if not exists fondo_desde timestamptz;

comment on column usuarios.preferencias is
  'Cómo ve la aplicación este usuario: tema, paleta y lo que venga.';
comment on column usuarios.fondo is
  'La foto de portada que subió. Nula = se usa la de la empresa.';

-- Cómo quedó.
select usuario, nombre,
       preferencias,
       case when fondo is null then 'la de la empresa'
            else pg_size_pretty(length(fondo)::bigint) || ' · ' || coalesce(fondo_tipo,'?')
       end as portada
  from usuarios order by usuario;
