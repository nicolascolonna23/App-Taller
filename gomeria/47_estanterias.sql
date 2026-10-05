-- =====================================================================
-- ESTANTERÍAS DEL DEPÓSITO Y DÓNDE ESTÁ CADA REPUESTO
-- =====================================================================
-- El depósito se arma como un plano visto desde arriba: cada estantería
-- es un rectángulo con su posición en centímetros, su largo, su
-- profundidad y el lado que da al pasillo (el frente). Por dentro tiene
-- pisos (de abajo hacia arriba) y módulos (de izquierda a derecha,
-- mirándola de frente). Cada cruce piso × módulo es un casillero.
--
-- Un repuesto tiene una sola ubicación: moverlo es cambiarla, no sumar
-- otra. Así la pregunta "¿dónde está?" tiene una respuesta.
--
-- Se pega entero en Supabase -> SQL Editor -> Run. Se puede correr más
-- de una vez.
-- =====================================================================

create table if not exists repuestos_estanterias (
  id              bigint generated always as identity primary key,
  nombre          text not null unique,
  pasillo         text not null default '',
  x_cm            integer not null default 0 check (x_cm >= 0),
  y_cm            integer not null default 0 check (y_cm >= 0),
  largo_cm        integer not null default 200 check (largo_cm between 25 and 2000),
  profundidad_cm  integer not null default 50 check (profundidad_cm between 20 and 300),
  alto_cm         integer not null default 200 check (alto_cm between 30 and 1000),
  pisos           integer not null default 4 check (pisos between 1 and 15),
  modulos         integer not null default 3 check (modulos between 1 and 20),
  -- Hacia dónde mira, en el plano: el lado del pasillo.
  frente          text not null default 'sur'
                  check (frente in ('norte', 'sur', 'este', 'oeste')),
  creado_en       timestamptz not null default now(),
  actualizado_en  timestamptz not null default now()
);

create table if not exists repuestos_ubicaciones (
  articulo_id     bigint primary key references repuestos_articulos(id) on delete cascade,
  estanteria_id   bigint not null references repuestos_estanterias(id) on delete cascade,
  piso            integer not null check (piso >= 1),
  modulo          integer not null check (modulo >= 1),
  usuario_id      bigint references usuarios(id),
  actualizado_en  timestamptz not null default now()
);

create index if not exists idx_repuestos_ubicaciones_estanteria
  on repuestos_ubicaciones (estanteria_id, piso, modulo);

-- Las tablas nuevas quedan cerradas a la API pública de Supabase, igual
-- que el resto (ver 34_seguridad_rls.sql): solo entra el servidor.
alter table repuestos_estanterias enable row level security;
alter table repuestos_ubicaciones enable row level security;
