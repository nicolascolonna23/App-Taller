-- =====================================================================
-- GOMERÍA — esquema para Supabase (PostgreSQL)
-- ---------------------------------------------------------------------
-- Se pega entero en Supabase → SQL Editor → New query → Run.
-- Se puede correr más de una vez sin romper nada.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. EL MAPA: cómo está armada una unidad
-- ---------------------------------------------------------------------
-- Una "configuración" es un tipo de armado (por ejemplo: 1 eje direccional
-- + 2 ejes traseros duales = 10 cubiertas). Varias unidades comparten la
-- misma configuración, así el mapa se carga una vez sola.

create table if not exists configuraciones (
  id          bigint generated always as identity primary key,
  nombre      text not null unique,
  descripcion text,
  creado      timestamptz not null default now()
);

comment on table configuraciones is
  'Tipos de armado de ejes. Cada unidad apunta a uno.';

-- Las posiciones concretas de ese armado. Una fila por lugar donde entra
-- una cubierta, incluido el auxilio.
create table if not exists configuracion_posiciones (
  id               bigint generated always as identity primary key,
  configuracion_id bigint not null references configuraciones(id) on delete cascade,
  codigo           text   not null,          -- como lo nombra el gomero: 1I, 2IE, 2II, AUX
  eje              int    not null,          -- 1 = el de adelante
  lado             text   not null check (lado in ('I','D','X')),   -- Izquierda, Derecha, X = auxilio
  montaje          text   not null check (montaje in ('unica','interior','exterior')),
  es_auxilio       boolean not null default false,
  orden            int    not null,          -- para dibujar el mapa siempre igual
  unique (configuracion_id, codigo)
);

comment on column configuracion_posiciones.montaje is
  'unica = rueda simple (eje direccional). interior/exterior = rodado dual.';

-- ---------------------------------------------------------------------
-- 2. LAS UNIDADES
-- ---------------------------------------------------------------------
create table if not exists unidades (
  id               bigint generated always as identity primary key,
  patente          text not null unique,     -- normalizada sin espacios: AD247MQ
  interno          text,
  marca            text,
  modelo           text,
  sucursal         text,
  uso              text,
  configuracion_id bigint references configuraciones(id),
  km_actual        numeric,
  activa           boolean not null default true,
  creado           timestamptz not null default now()
);

create index if not exists ix_unidades_sucursal on unidades(sucursal);

-- ---------------------------------------------------------------------
-- 3. LAS CUBIERTAS
-- ---------------------------------------------------------------------
-- Cada cubierta es una ficha con vida propia: se compra, se monta, se
-- rota, se recapa y en algún momento se da de baja. El código es el
-- número de fuego o el que la empresa le ponga.

create table if not exists cubiertas (
  id              bigint generated always as identity primary key,
  codigo          text not null unique,
  marca           text,
  modelo          text,
  medida          text,                       -- 295/80R22.5
  estado          text not null default 'stock'
                  check (estado in ('stock','montada','reparacion','recapado','baja')),
  km_acumulados   numeric not null default 0,
  recapados       int     not null default 0,
  remanente_mm    numeric,                    -- última medición de dibujo
  costo_compra    numeric,
  fecha_alta      date not null default current_date,
  fecha_baja      date,
  motivo_baja     text,
  observaciones   text,
  creado          timestamptz not null default now()
);

create index if not exists ix_cubiertas_estado on cubiertas(estado);
create index if not exists ix_cubiertas_medida on cubiertas(medida);

-- ---------------------------------------------------------------------
-- 4. QUÉ HAY PUESTO AHORA (y qué hubo antes)
-- ---------------------------------------------------------------------
-- Un montaje abierto (hasta is null) es una cubierta que está puesta hoy.
-- Cuando se desmonta se le pone fecha en 'hasta' y la fila queda como
-- historia. Nunca se borra: así se sabe dónde estuvo cada cubierta.

create table if not exists montajes (
  id                   bigint generated always as identity primary key,
  unidad_id            bigint not null references unidades(id),
  posicion_id          bigint not null references configuracion_posiciones(id),
  cubierta_id          bigint not null references cubiertas(id),
  desde                timestamptz not null default now(),
  hasta                timestamptz,
  km_unidad_montaje    numeric,
  km_unidad_desmontaje numeric,
  nota                 text
);

-- Una posición de una unidad no puede tener dos cubiertas al mismo tiempo.
create unique index if not exists ux_montaje_posicion_abierta
  on montajes(unidad_id, posicion_id) where hasta is null;

-- Y una cubierta no puede estar montada en dos lugares a la vez.
create unique index if not exists ux_montaje_cubierta_abierta
  on montajes(cubierta_id) where hasta is null;

create index if not exists ix_montajes_unidad   on montajes(unidad_id);
create index if not exists ix_montajes_cubierta on montajes(cubierta_id);

-- ---------------------------------------------------------------------
-- 5. LOS PARTES: lo que escribe el gomero
-- ---------------------------------------------------------------------
-- El gomero escanea el QR de la unidad, escribe en castellano lo que hizo
-- y eso entra acá como 'pendiente'. Claude lo interpreta y arma una
-- propuesta de movimientos. Recién cuando alguien confirma se aplica.
-- El texto original queda guardado siempre, se confirme o no.

create table if not exists partes (
  id             bigint generated always as identity primary key,
  unidad_id      bigint references unidades(id),
  texto          text not null,
  autor          text,
  origen         text not null default 'qr',
  estado         text not null default 'pendiente'
                 check (estado in ('pendiente','confirmado','descartado','error')),
  interpretacion jsonb,                    -- lo que entendió Claude
  km_unidad      numeric,
  creado         timestamptz not null default now(),
  resuelto       timestamptz,
  resuelto_por   text,
  error          text
);

create index if not exists ix_partes_estado on partes(estado, creado desc);
create index if not exists ix_partes_unidad on partes(unidad_id, creado desc);

-- ---------------------------------------------------------------------
-- 6. LOS MOVIMIENTOS: el libro mayor
-- ---------------------------------------------------------------------
-- Todo lo que le pasó a una cubierta queda acá. Los movimientos que salen
-- de un mismo parte comparten grupo_id: una rotación de cuatro cubiertas
-- son cuatro filas de un mismo grupo.

create table if not exists movimientos (
  id                  bigint generated always as identity primary key,
  grupo_id            uuid   not null default gen_random_uuid(),
  parte_id            bigint references partes(id),
  tipo                text   not null check (tipo in
                        ('alta','montaje','desmontaje','rotacion','recapado',
                         'reparacion','medicion','baja')),
  fecha               timestamptz not null default now(),
  unidad_id           bigint references unidades(id),
  cubierta_id         bigint references cubiertas(id),
  posicion_origen_id  bigint references configuracion_posiciones(id),
  posicion_destino_id bigint references configuracion_posiciones(id),
  km_unidad           numeric,
  remanente_mm        numeric,
  usuario             text,
  nota                text
);

create index if not exists ix_mov_cubierta on movimientos(cubierta_id, fecha desc);
create index if not exists ix_mov_unidad   on movimientos(unidad_id, fecha desc);
create index if not exists ix_mov_grupo    on movimientos(grupo_id);

-- ---------------------------------------------------------------------
-- 7. MEDICIONES DE DIBUJO
-- ---------------------------------------------------------------------
create table if not exists mediciones (
  id           bigint generated always as identity primary key,
  cubierta_id  bigint not null references cubiertas(id) on delete cascade,
  fecha        timestamptz not null default now(),
  remanente_mm numeric not null,
  presion_psi  numeric,
  km_unidad    numeric,
  usuario      text
);

create index if not exists ix_mediciones_cubierta on mediciones(cubierta_id, fecha desc);
