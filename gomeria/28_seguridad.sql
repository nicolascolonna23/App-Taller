-- =====================================================================
-- SEGURIDAD: FRENO A LA FUERZA BRUTA Y SEGUNDO FACTOR
-- ---------------------------------------------------------------------
-- Se pega en Supabase → SQL Editor → New query → Run. Se puede correr
-- más de una vez sin romper nada.
--
-- Mientras no se corra, la app sigue andando como antes: los intentos
-- fallidos se cuentan en memoria y los administradores entran sin
-- segundo factor (el servidor lo avisa al arrancar).
-- =====================================================================

-- Cada intento fallido de entrar deja una fila. Se cuentan por origen
-- ('ip:…'), por usuario ('usuario:…') y por código del segundo factor
-- ('2fa:…'). En la base y no en memoria: un reinicio del servidor no
-- tiene que regalarle intentos nuevos a quien está probando contraseñas.
create table if not exists intentos_login (
  id      bigint generated always as identity primary key,
  clave   text not null,
  creado  timestamptz not null default now()
);

create index if not exists ix_intentos_login on intentos_login(clave, creado);

-- Segundo factor con una app autenticadora (Google Authenticator, Authy,
-- 1Password…). Obligatorio para los roles que administran.
alter table usuarios add column if not exists totp_secreto  text;
alter table usuarios add column if not exists totp_activo   boolean not null default false;
-- El último paso de 30 segundos usado: un código no sirve dos veces.
alter table usuarios add column if not exists totp_ultimo   bigint;
-- Códigos de respaldo por si se pierde el celular. Solo el hash; cada uno
-- sirve una vez y se borra al usarlo.
alter table usuarios add column if not exists totp_respaldo text[] not null default '{}';

comment on column usuarios.totp_secreto is
  'Semilla del autenticador. Para resetearlo: update usuarios set totp_secreto = null, totp_activo = false, totp_respaldo = ''{}'' where usuario = ''…'';';

-- La sesión recuerda si pasó por el segundo factor. La de un administrador
-- que no pasó no sirve: al correr este script, los administradores tienen
-- que volver a entrar.
alter table sesiones add column if not exists con_2fa boolean not null default false;

-- El paso intermedio: la contraseña ya se verificó, falta el código.
-- Dura diez minutos y guarda el hash del token, no el token.
create table if not exists desafios_2fa (
  token       text primary key,
  usuario_id  bigint not null references usuarios(id) on delete cascade,
  destino     text not null default '/',
  expira      timestamptz not null
);

create index if not exists ix_desafios_2fa_expira on desafios_2fa(expira);

alter table intentos_login enable row level security;
alter table desafios_2fa   enable row level security;
