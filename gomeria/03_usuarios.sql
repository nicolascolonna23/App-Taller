-- =====================================================================
-- USUARIOS Y SESIONES
-- ---------------------------------------------------------------------
-- Se pega en Supabase → SQL Editor → New query → Run, después de los
-- otros dos. Se puede correr más de una vez sin romper nada.
-- =====================================================================

create table if not exists usuarios (
  id         bigint generated always as identity primary key,
  usuario    text not null unique,          -- con lo que entra: "ramon"
  nombre     text not null,                 -- como aparece en los partes
  hash       text not null,                 -- la contraseña nunca se guarda en claro
  rol        text not null default 'operario'
             check (rol in ('operario','encargado','admin')),
  activo     boolean not null default true,
  creado     timestamptz not null default now(),
  ultimo_ingreso timestamptz
);

comment on column usuarios.rol is
  'operario: carga partes. encargado: además confirma y corrige. admin: administra usuarios.';

-- Una sesión por cada vez que alguien entra. El token viaja en una cookie
-- y es lo único que guarda el celular: si se pierde, se borra la fila y listo.
create table if not exists sesiones (
  token       text primary key,
  usuario_id  bigint not null references usuarios(id) on delete cascade,
  creado      timestamptz not null default now(),
  ultimo_uso  timestamptz not null default now(),
  expira      timestamptz not null,
  agente      text
);

create index if not exists ix_sesiones_usuario on sesiones(usuario_id);
create index if not exists ix_sesiones_expira  on sesiones(expira);

-- Los partes pasan a quedar firmados por el usuario que los cargó, además
-- del nombre que ya se guardaba como texto.
alter table partes      add column if not exists usuario_id bigint references usuarios(id);
alter table movimientos add column if not exists usuario_id bigint references usuarios(id);

alter table usuarios enable row level security;
alter table sesiones enable row level security;
