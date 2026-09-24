-- =====================================================================
-- CUPO DEL ASISTENTE
-- ---------------------------------------------------------------------
-- Cada consulta a Pengui que llega al modelo deja una fila: con eso se
-- cuenta cuántas hizo cada uno en la última hora y en el día, y cuántas
-- se hicieron entre todos. Cada consulta se paga a Anthropic; sin tope,
-- una sesión robada o un script podían gastar sin límite.
--
-- No se guarda la pregunta ni la respuesta: solo quién y cuándo.
--
-- Se pega en Supabase → SQL Editor → New query → Run. Se puede correr
-- más de una vez. Sin este script el tope se cuenta en memoria y se
-- pierde al reiniciar el servidor.
-- =====================================================================

create table if not exists consultas_asistente (
  id          bigint generated always as identity primary key,
  usuario_id  bigint not null references usuarios(id) on delete cascade,
  creado      timestamptz not null default now()
);

create index if not exists ix_consultas_asistente on consultas_asistente(usuario_id, creado);
create index if not exists ix_consultas_asistente_creado on consultas_asistente(creado);

alter table consultas_asistente enable row level security;
