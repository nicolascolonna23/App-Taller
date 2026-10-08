-- =====================================================================
-- LO QUE SE LE ENSEÑA A TITÁN, EL ASISTENTE
-- =====================================================================
-- Vocabulario, definiciones y criterios del taller que Titán suma a sus
-- reglas fijas (gomeria/asistente_reglas.md) en cada consulta. No son
-- datos operativos: cantidades, fechas y ubicaciones siguen saliendo de
-- la base en cada pregunta.
--
-- Estados:
--   activa     Titán la usa.
--   pendiente  propuesta desde el chat por alguien que no administra;
--              espera que un administrador la apruebe.
--   inactiva   guardada pero sin usar.
--
-- Se pega entero en Supabase -> SQL Editor -> Run. Se puede correr más
-- de una vez.
-- =====================================================================

create table if not exists titan_ensenanzas (
  id              bigint generated always as identity primary key,
  tema            text not null default 'General',
  texto           text not null check (char_length(texto) between 3 and 600),
  estado          text not null default 'activa'
                  check (estado in ('activa', 'pendiente', 'inactiva')),
  -- De dónde salió: la pantalla de conocimiento o una respuesta del chat.
  origen          text not null default 'pantalla'
                  check (origen in ('pantalla', 'chat')),
  -- Si salió del chat: la pregunta y la respuesta que se corrigieron.
  pregunta        text,
  respuesta       text,
  usuario_id      bigint references usuarios(id) on delete set null,
  revisado_por    bigint references usuarios(id) on delete set null,
  creado_en       timestamptz not null default now(),
  actualizado_en  timestamptz not null default now()
);

create index if not exists titan_ensenanzas_estado on titan_ensenanzas (estado);

-- La aplicación entra con su propio usuario de base; la API pública de
-- Supabase no tiene que leer ni escribir esta tabla.
alter table titan_ensenanzas enable row level security;
