-- =====================================================================
-- SOLICITUDES DE TALLER
-- ---------------------------------------------------------------------
-- El registro nace antes de la reparación, no después.
--
-- El preventivo ya estaba procedimentado (DM-MAN-001). El correctivo se
-- hacía y se rendía como un gasto más de la sucursal: la plata quedaba
-- anotada, la intervención técnica no. La solicitud corrige eso: ninguna
-- compra ni trabajo de taller se hace sin una solicitud aprobada, y ninguna
-- factura se rinde sin el número de solicitud escrito.
--
-- Tres tablas y un contador:
--
--   sucursales       las siete bocas, con el código de tres letras que
--                    es el prefijo de la solicitud.
--   solicitudes_contador   una fila por sucursal con el último número dado.
--                    El correlativo es por sucursal, no global.
--   solicitudes            la solicitud: quién pidió, qué unidad, qué falla, en qué
--                    estado está y con qué factura se rindió.
--   solicitud_eventos     el historial, append-only. Es la evidencia del
--                    circuito: sin esto la solicitud es una opinión.
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
-- ficha de la unidad no cruzaría con la solicitud.
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
  'Las bocas de la red. El código de tres letras es el prefijo de la solicitud.';


-- A cada usuario se le puede poner su sucursal: el que carga una solicitud no
-- elige de dónde sale el número, sale de quién lo pide. Al que no la
-- tenga cargada —administración, mantenimiento— la pantalla se la
-- pregunta.
alter table usuarios
  add column if not exists sucursal_codigo char(3);

-- La clave foránea va aparte: si la columna ya existía —la crea también
-- 27_roles.sql, que puede correrse primero— el `add column` no la habría
-- puesto nunca.
do $$
begin
  alter table usuarios
    add constraint usuarios_sucursal_fkey
    foreign key (sucursal_codigo) references sucursales(codigo);
exception
  when duplicate_object then null;
end $$;

comment on column usuarios.sucursal_codigo is
  'Sucursal del usuario. Define el prefijo de las solicitudes que carga.';


-- ---------------------------------------------------------------------
-- 2. EL CONTADOR
-- ---------------------------------------------------------------------
-- Una fila por sucursal. El número se toma bloqueando esta fila dentro de
-- la misma transacción que inserta la solicitud: dos sucursales cargando en el
-- mismo segundo no se pisan, y dos usuarios de la misma sucursal esperan
-- uno al otro.
--
-- No se usa max(numero)+1: sin bloqueo, dos cargas simultáneas leen el
-- mismo máximo y escriben el mismo número.
create table if not exists solicitudes_contador (
  sucursal_codigo char(3) primary key references sucursales(codigo),
  ultimo          integer not null default 0 check (ultimo >= 0)
);

insert into solicitudes_contador (sucursal_codigo)
select codigo from sucursales
on conflict (sucursal_codigo) do nothing;

comment on table solicitudes_contador is
  'Último número de solicitud dado por sucursal. Se bloquea para numerar.';


-- ---------------------------------------------------------------------
-- 3. LA SOLICITUD
-- ---------------------------------------------------------------------
-- El id es el número que se escribe en la factura: CAT-00001. Es texto y
-- es la clave: el papel y la base dicen lo mismo, sin traducción.
--
-- El correlativo es inmutable: el número de una solicitud rechazada o anulado
-- no se reutiliza. Por eso no hay borrado de solicitudes en ningún lado.
create table if not exists solicitudes_compra (
  id              text primary key,        -- 'CAT-00001'
  sucursal_codigo char(3) not null references sucursales(codigo),
  numero          integer not null check (numero > 0),

  -- La unidad. Igual que en las órdenes, la patente se guarda además del
  -- id: una solicitud vieja tiene que poder leerse aunque la unidad se haya
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
  -- solicitud se cargó el viernes.
  fecha_hecho     date not null default current_date,
  creado_en       timestamptz not null default now(),

  nota            text,                    -- motivo del rechazo o condiciones
  factura_numero  text,                    -- se escribe al cerrar
  regularizacion_ruta boolean not null default false,

  -- Una solicitud rechazada es terminal. Si la sucursal insiste carga uno
  -- nuevo citando el anterior, y así se ve cuántas veces se insistió.
  solicitud_anterior   text references solicitudes_compra(id),

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

create index if not exists ix_solicitudes_sucursal on solicitudes_compra (sucursal_codigo, numero desc);
create index if not exists ix_solicitudes_estado   on solicitudes_compra (estado, creado_en);
create index if not exists ix_solicitudes_patente  on solicitudes_compra (patente, creado_en desc);
create index if not exists ix_solicitudes_unidad   on solicitudes_compra (unidad_id, creado_en desc);

create or replace function _solicitud_tocada() returns trigger as $$
begin
  new.actualizado_en := now();
  return new;
end $$ language plpgsql;

drop trigger if exists tg_solicitud_tocada on solicitudes_compra;
create trigger tg_solicitud_tocada before update on solicitudes_compra
  for each row execute function _solicitud_tocada();


-- ---------------------------------------------------------------------
-- 4. EL HISTORIAL
-- ---------------------------------------------------------------------
-- Una fila por cada cosa que le pasó a la solicitud. No se edita ni se borra:
-- el trigger de abajo lo impide en la base, no solo en la aplicación.
-- Sin esto no se puede contestar quién aprobó un gasto, que es la
-- pregunta que aparece cuando el gasto ya se hizo.
create table if not exists solicitud_eventos (
  id        bigint generated always as identity primary key,
  solicitud_id   text not null references solicitudes_compra(id),
  estado    text not null,
  usuario   text,
  momento   timestamptz not null default now(),
  comentario text
);

create index if not exists ix_solicitud_eventos on solicitud_eventos (solicitud_id, id);

create or replace function _solicitud_evento_inmutable() returns trigger as $$
begin
  raise exception 'El historial de una solicitud no se edita ni se borra.';
end $$ language plpgsql;

drop trigger if exists tg_solicitud_evento_inmutable on solicitud_eventos;
create trigger tg_solicitud_evento_inmutable before update or delete on solicitud_eventos
  for each row execute function _solicitud_evento_inmutable();

comment on table solicitud_eventos is
  'Historial append-only de la solicitud: quién pidió, quién aprobó y cuándo.';


-- ---------------------------------------------------------------------
-- 5. EL ENGANCHE CON LO QUE YA EXISTE
-- ---------------------------------------------------------------------
-- Quién gestionó el servicio externo. Es la pregunta que decide si hace
-- falta una solicitud:
--
--   mantenimiento  lo mandó a hacer el área, que ya decide y controla el
--                  gasto. Se carga la factura y listo.
--   sucursal       lo mandó a hacer una boca. Ahí sí va la solicitud: es
--                  el gasto que antes se rendía sin constancia técnica.
--
-- Va en la orden y no en la solicitud porque describe a la factura y no al
-- pedido: una orden vieja, sin gestión anotada, se sigue leyendo igual.
alter table ordenes_trabajo
  add column if not exists gestion text;

alter table ordenes_trabajo
  drop constraint if exists ordenes_trabajo_gestion_check;
alter table ordenes_trabajo
  add constraint ordenes_trabajo_gestion_check
  check (gestion is null or gestion in ('mantenimiento', 'sucursal'));

comment on column ordenes_trabajo.gestion is
  'Quién mandó a hacer el servicio externo: mantenimiento o una sucursal.';

-- La rendición: la factura del taller entra al sistema como una orden
-- externa, y esa orden lleva la solicitud escrita. Es el mismo número que va
-- en el papel.
alter table ordenes_trabajo
  add column if not exists solicitud_id text references solicitudes_compra(id);

create index if not exists ix_ordenes_solicitud on ordenes_trabajo (solicitud_id);

comment on column ordenes_trabajo.solicitud_id is
  'Solicitud cerrada que respalda esta factura de taller.';

-- Una solicitud preventiva cerrada es también el último service de la unidad.
alter table services
  add column if not exists solicitud_id text references solicitudes_compra(id) on delete set null;

create unique index if not exists ux_services_solicitud on services (solicitud_id)
  where solicitud_id is not null;

comment on column services.solicitud_id is
  'Solicitud preventiva que originó este registro de service.';


-- ---------------------------------------------------------------------
-- 6. SI LA SOLICITUD ES OBLIGATORIA PARA RENDIR
-- ---------------------------------------------------------------------
-- Una sola fila. Nace en `true`, que es la regla: una sucursal no rinde
-- una factura de taller sin solicitud cerrada.
--
-- Ojo con el alcance: **solo las de sucursal**. Lo que manda a hacer
-- mantenimiento se carga como siempre, porque el área que decide el gasto
-- es la misma que lo controla. El circuito existe para lo que se resolvía
-- lejos del taller, no para trabarle la carga al taller.
--
-- Si hiciera falta apagarlo del todo mientras la red se acostumbra:
--
--   update solicitudes_ajustes set exigir_solicitud = false;
--
-- Es a propósito que sea una línea de SQL y no un botón en la pantalla:
-- apagar el circuito tiene que costar más que usarlo.
create table if not exists solicitudes_ajustes (
  unica       boolean primary key default true check (unica),
  exigir_solicitud boolean not null default true
);

insert into solicitudes_ajustes (unica) values (true) on conflict do nothing;


-- ---------------------------------------------------------------------
-- 7. LA VISTA QUE LEE LA PANTALLA
-- ---------------------------------------------------------------------
-- La solicitud con lo que sabe el maestro de la unidad, los días que lleva
-- esperando respuesta y el número de la orden con la que se rindió.
create or replace view v_solicitudes as
select
  v.id, v.sucursal_codigo, v.numero, v.unidad_id, v.patente, v.km,
  v.tipo, v.origen, v.urgencia, v.detalle, v.taller_sugerido, v.taller,
  v.monto_estimado, v.monto_autorizado, v.estado, v.solicitante,
  v.fecha_hecho, v.creado_en, v.nota, v.factura_numero,
  v.regularizacion_ruta, v.solicitud_anterior,
  v.aprobado_en, v.aprobado_por, v.cerrado_en, v.cerrado_por,
  s.nombre as sucursal,
  u.interno, u.marca, u.modelo, u.chofer,
  -- Lo que se gastó de verdad: el autorizado si lo hay, si no el
  -- estimado. Sirve para sumar por unidad sin abrir solicitud por solicitud.
  coalesce(v.monto_autorizado, v.monto_estimado) as monto,
  case when v.estado = 'SOLICITADO'
       then (now() - v.creado_en) end as espera,
  o.numero as orden_numero,
  o.id     as orden_id
from solicitudes_compra v
join sucursales s on s.codigo = v.sucursal_codigo
left join unidades u on u.id = v.unidad_id
left join lateral (
  select id, numero from ordenes_trabajo
  where solicitud_id = v.id and estado <> 'anulada'
  order by numero limit 1) o on true;

-- La vista de órdenes suma las dos columnas nuevas al final, para no
-- cambiarle el contrato a lo que ya la lee.
create or replace view v_ordenes as
select
  o.id, o.numero, o.tipo, o.estado, o.unidad_id, o.patente, o.km,
  o.fecha, o.fecha_cierre, o.chofer, o.responsable, o.taller,
  o.solicitado, o.diagnostico, o.observaciones, o.factura, o.monto,
  o.usuario, o.cerrada_por, o.creado_en, o.actualizado_en,
  u.interno, u.marca, u.modelo, u.sucursal, u.chasis,
  coalesce(t.importe, 0)::numeric as total_tareas,
  coalesce(t.cuantas, 0)::integer as cuantas_tareas,
  coalesce(r.importe, 0)::numeric as total_repuestos,
  coalesce(r.cuantos, 0)::integer as cuantos_repuestos,
  case when o.tipo = 'externa' then coalesce(o.monto, 0)
       else coalesce(t.importe, 0) + coalesce(r.importe, 0) end::numeric as total,
  case when o.estado = 'abierta'
       then (current_date - o.fecha)::integer end as dias_abierta,
  o.mantenimiento, o.gestion, o.solicitud_id
from ordenes_trabajo o
left join unidades u on u.id = o.unidad_id
left join lateral (
  select sum(coalesce(importe, 0)) as importe, count(*) as cuantas
  from ordenes_tareas where orden_id = o.id) t on true
left join lateral (
  select sum(coalesce(precio, 0) * cantidad) as importe, count(*) as cuantos
  from ordenes_repuestos where orden_id = o.id) r on true;

comment on view v_solicitudes is
  'Cada solicitud con su unidad, su espera y la orden con la que se rindió.';
