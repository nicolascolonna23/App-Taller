-- =====================================================================
-- VALES DE TALLER
-- ---------------------------------------------------------------------
-- El registro nace antes de la reparación, no después.
--
-- El preventivo ya estaba procedimentado (DM-MAN-001). El correctivo se
-- hacía y se rendía como un gasto más de la sucursal: la plata quedaba
-- anotada, la intervención técnica no. El vale corrige eso: ninguna
-- compra ni trabajo de taller se hace sin un vale aprobado, y ninguna
-- factura se rinde sin el número de vale escrito.
--
-- Tres tablas y un contador:
--
--   sucursales       las siete bocas, con el código de tres letras que
--                    es el prefijo del vale.
--   vales_contador   una fila por sucursal con el último número dado.
--                    El correlativo es por sucursal, no global.
--   vales            el vale: quién pidió, qué unidad, qué falla, en qué
--                    estado está y con qué factura se rindió.
--   vale_eventos     el historial, append-only. Es la evidencia del
--                    circuito: sin esto el vale es una opinión.
--
-- Se pega entero en Supabase → SQL Editor → Run. Se puede correr las
-- veces que haga falta: no borra nada.
--
-- ANTES tienen que estar corridos 01_esquema.sql, 03_usuarios.sql,
-- 15_ordenes.sql y 20_alertas.sql.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. LAS SUCURSALES
-- ---------------------------------------------------------------------
-- El código de tres letras es el mismo que ya usa el maestro de unidades
-- en `unidades.sucursal`: sin eso serían dos listas de sucursales y la
-- ficha de la unidad no cruzaría con el vale.
create table if not exists sucursales (
  codigo  char(3) primary key,
  nombre  text not null,
  activa  boolean not null default true,
  orden   integer not null default 0     -- cómo se listan en la pantalla
);

insert into sucursales (codigo, nombre, orden) values
  ('CAT', 'Catamarca',    1),
  ('TUC', 'Tucumán',      2),
  ('SAL', 'Salta',        3),
  ('LAR', 'La Rioja',     4),
  ('COR', 'Córdoba',      5),
  ('ROS', 'Rosario',      6),
  ('BUE', 'Buenos Aires', 7)
on conflict (codigo) do nothing;

comment on table sucursales is
  'Las bocas de la red. El código de tres letras es el prefijo del vale.';


-- A cada usuario se le puede poner su sucursal: el que carga un vale no
-- elige de dónde sale el número, sale de quién lo pide. Al que no la
-- tenga cargada —administración, mantenimiento— la pantalla se la
-- pregunta.
alter table usuarios
  add column if not exists sucursal_codigo char(3) references sucursales(codigo);

comment on column usuarios.sucursal_codigo is
  'Sucursal del usuario. Define el prefijo de los vales que carga.';


-- ---------------------------------------------------------------------
-- 2. EL CONTADOR
-- ---------------------------------------------------------------------
-- Una fila por sucursal. El número se toma bloqueando esta fila dentro de
-- la misma transacción que inserta el vale: dos sucursales cargando en el
-- mismo segundo no se pisan, y dos usuarios de la misma sucursal esperan
-- uno al otro.
--
-- No se usa max(numero)+1: sin bloqueo, dos cargas simultáneas leen el
-- mismo máximo y escriben el mismo número.
create table if not exists vales_contador (
  sucursal_codigo char(3) primary key references sucursales(codigo),
  ultimo          integer not null default 0 check (ultimo >= 0)
);

insert into vales_contador (sucursal_codigo)
select codigo from sucursales
on conflict (sucursal_codigo) do nothing;

comment on table vales_contador is
  'Último número de vale dado por sucursal. Se bloquea para numerar.';


-- ---------------------------------------------------------------------
-- 3. EL VALE
-- ---------------------------------------------------------------------
-- El id es el número que se escribe en la factura: CAT-00001. Es texto y
-- es la clave: el papel y la base dicen lo mismo, sin traducción.
--
-- El correlativo es inmutable: el número de un vale rechazado o anulado
-- no se reutiliza. Por eso no hay borrado de vales en ningún lado.
create table if not exists vales (
  id              text primary key,        -- 'CAT-00001'
  sucursal_codigo char(3) not null references sucursales(codigo),
  numero          integer not null check (numero > 0),

  -- La unidad. Igual que en las órdenes, la patente se guarda además del
  -- id: un vale viejo tiene que poder leerse aunque la unidad se haya
  -- dado de baja, y puede pedirse por algo que no está en el maestro.
  unidad_id       bigint references unidades(id),
  patente         text not null,
  km              numeric not null check (km >= 0),

  tipo            text not null check (tipo in
                    ('PREVENTIVO', 'CORRECTIVO', 'GOMERIA', 'SINIESTRO')),
  origen          text not null check (origen in
                    ('CHECKLIST', 'RUTA', 'RUTINA_SEMANAL',
                     'PREVENTIVO_KM', 'CONTROL_MENSUAL')),
  urgencia        text not null default 'PUEDE_ESPERAR' check (urgencia in
                    ('PUEDE_ESPERAR', 'OPERA_CON_RIESGO', 'UNIDAD_PARADA')),

  detalle         text not null,
  taller_sugerido text,
  taller          text,                    -- el que asignó el taller al aprobar

  -- Nulo no es cero: nulo quiere decir "a presupuestar".
  monto_estimado   numeric check (monto_estimado is null or monto_estimado >= 0),
  monto_autorizado numeric check (monto_autorizado is null or monto_autorizado >= 0),

  estado          text not null default 'SOLICITADO' check (estado in
                    ('SOLICITADO', 'APROBADO', 'EN_EJECUCION',
                     'CERRADO', 'RECHAZADO')),

  solicitante     text,                    -- el nombre, congelado
  solicitante_id  bigint references usuarios(id),

  -- Cuándo pasó el hecho. En la regularización de ruta es anterior a la
  -- fecha de carga: la falla fue el jueves a las tres de la mañana y el
  -- vale se cargó el viernes.
  fecha_hecho     date not null default current_date,
  creado_en       timestamptz not null default now(),

  nota            text,                    -- motivo del rechazo o condiciones
  factura_numero  text,                    -- se escribe al cerrar
  regularizacion_ruta boolean not null default false,

  -- Un vale rechazado es terminal. Si la sucursal insiste carga uno
  -- nuevo citando el anterior, y así se ve cuántas veces se insistió.
  vale_anterior   text references vales(id),

  aprobado_en     timestamptz,
  aprobado_por    text,
  cerrado_en      timestamptz,
  cerrado_por     text,
  actualizado_en  timestamptz not null default now(),

  unique (sucursal_codigo, numero),

  -- Cerrado sin factura sería otra vez plata sin respaldo.
  check (estado <> 'CERRADO' or factura_numero is not null),
  -- Rechazado sin motivo no le sirve a nadie: la sucursal tiene que
  -- saber qué corregir.
  check (estado <> 'RECHAZADO' or nota is not null)
);

create index if not exists ix_vales_sucursal on vales (sucursal_codigo, numero desc);
create index if not exists ix_vales_estado   on vales (estado, creado_en);
create index if not exists ix_vales_patente  on vales (patente, creado_en desc);
create index if not exists ix_vales_unidad   on vales (unidad_id, creado_en desc);

create or replace function _vale_tocado() returns trigger as $$
begin
  new.actualizado_en := now();
  return new;
end $$ language plpgsql;

drop trigger if exists tg_vale_tocado on vales;
create trigger tg_vale_tocado before update on vales
  for each row execute function _vale_tocado();


-- ---------------------------------------------------------------------
-- 4. EL HISTORIAL
-- ---------------------------------------------------------------------
-- Una fila por cada cosa que le pasó al vale. No se edita ni se borra:
-- el trigger de abajo lo impide en la base, no solo en la aplicación.
-- Sin esto no se puede contestar quién aprobó un gasto, que es la
-- pregunta que aparece cuando el gasto ya se hizo.
create table if not exists vale_eventos (
  id        bigint generated always as identity primary key,
  vale_id   text not null references vales(id),
  estado    text not null,
  usuario   text,
  momento   timestamptz not null default now(),
  comentario text
);

create index if not exists ix_vale_eventos on vale_eventos (vale_id, id);

create or replace function _vale_evento_inmutable() returns trigger as $$
begin
  raise exception 'El historial de un vale no se edita ni se borra.';
end $$ language plpgsql;

drop trigger if exists tg_vale_evento_inmutable on vale_eventos;
create trigger tg_vale_evento_inmutable before update or delete on vale_eventos
  for each row execute function _vale_evento_inmutable();

comment on table vale_eventos is
  'Historial append-only del vale: quién pidió, quién aprobó y cuándo.';


-- ---------------------------------------------------------------------
-- 5. EL ENGANCHE CON LO QUE YA EXISTE
-- ---------------------------------------------------------------------
-- La rendición: la factura del taller entra al sistema como una orden
-- externa, y esa orden lleva el vale escrito. Es el mismo número que va
-- en el papel.
alter table ordenes_trabajo
  add column if not exists vale_id text references vales(id);

create index if not exists ix_ordenes_vale on ordenes_trabajo (vale_id);

comment on column ordenes_trabajo.vale_id is
  'Vale cerrado que respalda esta factura de taller.';

-- Un vale preventivo cerrado es también el último service de la unidad.
alter table services
  add column if not exists vale_id text references vales(id) on delete set null;

create unique index if not exists ux_services_vale on services (vale_id)
  where vale_id is not null;

comment on column services.vale_id is
  'Vale preventivo que originó este registro de service.';


-- ---------------------------------------------------------------------
-- 6. SI EL VALE ES OBLIGATORIO PARA RENDIR
-- ---------------------------------------------------------------------
-- Una sola fila. Nace en `true`, que es la regla: no se rinde una factura
-- de taller sin vale cerrado. Mientras la red se acostumbra se puede
-- aflojar con:
--
--   update vales_ajustes set exigir_vale = false;
--
-- Es a propósito que sea una línea de SQL y no un botón en la pantalla:
-- apagar el circuito tiene que costar más que usarlo.
create table if not exists vales_ajustes (
  unica       boolean primary key default true check (unica),
  exigir_vale boolean not null default true
);

insert into vales_ajustes (unica) values (true) on conflict do nothing;


-- ---------------------------------------------------------------------
-- 7. LA VISTA QUE LEE LA PANTALLA
-- ---------------------------------------------------------------------
-- El vale con lo que sabe el maestro de la unidad, los días que lleva
-- esperando respuesta y el número de la orden con la que se rindió.
create or replace view v_vales as
select
  v.id, v.sucursal_codigo, v.numero, v.unidad_id, v.patente, v.km,
  v.tipo, v.origen, v.urgencia, v.detalle, v.taller_sugerido, v.taller,
  v.monto_estimado, v.monto_autorizado, v.estado, v.solicitante,
  v.fecha_hecho, v.creado_en, v.nota, v.factura_numero,
  v.regularizacion_ruta, v.vale_anterior,
  v.aprobado_en, v.aprobado_por, v.cerrado_en, v.cerrado_por,
  s.nombre as sucursal,
  u.interno, u.marca, u.modelo, u.chofer,
  -- Lo que se gastó de verdad: el autorizado si lo hay, si no el
  -- estimado. Sirve para sumar por unidad sin abrir vale por vale.
  coalesce(v.monto_autorizado, v.monto_estimado) as monto,
  case when v.estado = 'SOLICITADO'
       then (now() - v.creado_en) end as espera,
  o.numero as orden_numero,
  o.id     as orden_id
from vales v
join sucursales s on s.codigo = v.sucursal_codigo
left join unidades u on u.id = v.unidad_id
left join lateral (
  select id, numero from ordenes_trabajo
  where vale_id = v.id and estado <> 'anulada'
  order by numero limit 1) o on true;

comment on view v_vales is
  'Cada vale con su unidad, su espera y la orden con la que se rindió.';
