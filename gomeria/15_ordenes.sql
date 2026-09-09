-- =====================================================================
-- ÓRDENES DE TRABAJO
-- ---------------------------------------------------------------------
-- La hoja que se abre cuando una unidad entra al taller y se cierra
-- cuando sale. Adentro va lo que se pidió, lo que se encontró, lo que se
-- le hizo y lo que se le puso.
--
-- Dos clases de orden, la misma tabla:
--
--   interna  el trabajo lo hizo el taller propio. Se abre, se le van
--            cargando trabajos y repuestos, y se cierra.
--   externa  el trabajo lo hizo un tercero y de eso quedó una factura.
--            No hay nada que ir cargando: se anota patente, fecha,
--            número de factura y monto, y nace cerrada.
--
-- Los repuestos que se cargan a una orden salen del stock de verdad: por
-- cada renglón se escribe una Salida en repuestos_movimientos, que es de
-- donde sale el stock de todo el sistema. No hay dos verdades.
--
-- Se pega entero en Supabase → SQL Editor → Run. Se puede correr las
-- veces que haga falta: no borra nada.
-- =====================================================================

-- El número que se ve en la hoja impresa. Va por secuencia y no por el id
-- para que el día que haya que empezar en 1000 sea mover la secuencia y no
-- tocar las filas.
create sequence if not exists ordenes_numero start 1;

create table if not exists ordenes_trabajo (
  id            bigint generated always as identity primary key,
  numero        integer not null unique default nextval('ordenes_numero'),
  tipo          text not null default 'interna'
                check (tipo in ('interna', 'externa')),
  estado        text not null default 'abierta'
                check (estado in ('abierta', 'cerrada', 'anulada')),
  mantenimiento text check (mantenimiento in ('preventivo', 'correctivo')),

  -- La unidad. La patente se guarda además del id porque una orden vieja
  -- tiene que poder leerse aunque la unidad se haya dado de baja, y porque
  -- un trabajo externo puede ser de algo que no está en el maestro.
  unidad_id     bigint references unidades(id),
  patente       text not null,
  km            numeric,

  fecha         date not null default current_date,   -- cuándo entró
  fecha_cierre  date,                                 -- cuándo salió

  chofer        text,
  responsable   text,        -- quién la lleva adelante: el mecánico o el asesor
  taller        text,        -- en las externas, el tercero que hizo el trabajo

  solicitado    text,        -- lo que pidió el que la trajo
  diagnostico   text,        -- lo que se encontró al revisarla
  observaciones text,

  -- Solo en las externas: de eso hay una factura y un monto.
  factura       text,
  monto         numeric check (monto is null or monto >= 0),

  usuario_id    bigint references usuarios(id),
  usuario       text,        -- el nombre, congelado: el usuario puede irse
  cerrada_por   text,
  creado_en     timestamptz not null default now(),
  actualizado_en timestamptz not null default now(),

  -- Una externa sin factura ni monto no es nada: es lo único que aporta.
  check (tipo <> 'externa' or (monto is not null))
);

create index if not exists ix_ordenes_patente on ordenes_trabajo (patente, fecha desc);
create index if not exists ix_ordenes_unidad  on ordenes_trabajo (unidad_id, fecha desc);
create index if not exists ix_ordenes_estado  on ordenes_trabajo (estado);

-- Que `actualizado_en` diga la verdad sin que nadie se acuerde de tocarlo.
create or replace function _orden_tocada() returns trigger as $$
begin
  new.actualizado_en := now();
  return new;
end $$ language plpgsql;

drop trigger if exists tg_orden_tocada on ordenes_trabajo;
create trigger tg_orden_tocada before update on ordenes_trabajo
  for each row execute function _orden_tocada();


-- ---------------------------------------------------------------------
-- Los trabajos: un renglón por cada cosa que se le hizo
-- ---------------------------------------------------------------------
create table if not exists ordenes_tareas (
  id         bigint generated always as identity primary key,
  orden_id   bigint not null references ordenes_trabajo(id) on delete cascade,
  detalle    text not null,
  horas      numeric check (horas is null or horas >= 0),
  importe    numeric check (importe is null or importe >= 0),
  creado_en  timestamptz not null default now()
);

create index if not exists ix_ordenes_tareas on ordenes_tareas (orden_id, id);


-- ---------------------------------------------------------------------
-- Los repuestos: cada renglón es una salida real del depósito
-- ---------------------------------------------------------------------
-- `movimiento_id` es el enganche con el stock. Sacar el renglón borra el
-- movimiento y el repuesto vuelve al estante: es la misma operación vista
-- de los dos lados, no dos anotaciones que se pueden contradecir.
create table if not exists ordenes_repuestos (
  id            bigint generated always as identity primary key,
  orden_id      bigint not null references ordenes_trabajo(id) on delete cascade,
  articulo_id   bigint references repuestos_articulos(id),
  movimiento_id bigint references repuestos_movimientos(id) on delete set null,
  codigo        text,        -- copia al momento de cargarlo
  descripcion   text not null,
  cantidad      integer not null check (cantidad > 0),
  precio        numeric check (precio is null or precio >= 0),
  creado_en     timestamptz not null default now()
);

create index if not exists ix_ordenes_repuestos on ordenes_repuestos (orden_id, id);
create index if not exists ix_ordenes_repuestos_mov on ordenes_repuestos (movimiento_id);


-- ---------------------------------------------------------------------
-- La vista que lee la pantalla
-- ---------------------------------------------------------------------
-- La cabecera con lo que sabe el maestro de la unidad y los totales ya
-- sumados: el listado no tiene que ir a buscar los renglones de cada una.
create or replace view v_ordenes as
select
  o.id, o.numero, o.tipo, o.estado, o.unidad_id, o.patente, o.km,
  o.fecha, o.fecha_cierre, o.chofer, o.responsable, o.taller,
  o.solicitado, o.diagnostico, o.observaciones, o.factura, o.monto,
  o.usuario, o.cerrada_por, o.creado_en, o.actualizado_en,
  u.interno, u.marca, u.modelo, u.sucursal, u.chasis,
  coalesce(t.importe, 0)::numeric  as total_tareas,
  coalesce(t.cuantas, 0)::integer  as cuantas_tareas,
  coalesce(r.importe, 0)::numeric  as total_repuestos,
  coalesce(r.cuantos, 0)::integer  as cuantos_repuestos,
  -- En las internas el total es lo que se cargó renglón por renglón; en
  -- las externas, el monto de la factura.
  case when o.tipo = 'externa' then coalesce(o.monto, 0)
       else coalesce(t.importe, 0) + coalesce(r.importe, 0) end::numeric as total,
  case when o.estado = 'abierta'
       then (current_date - o.fecha)::integer end as dias_abierta,
  o.mantenimiento
from ordenes_trabajo o
left join unidades u on u.id = o.unidad_id
left join lateral (
  select sum(coalesce(importe, 0)) as importe, count(*) as cuantas
  from ordenes_tareas where orden_id = o.id) t on true
left join lateral (
  select sum(coalesce(precio, 0) * cantidad) as importe, count(*) as cuantos
  from ordenes_repuestos where orden_id = o.id) r on true;

comment on view v_ordenes is
  'Cabecera de cada orden con los datos de la unidad y los totales sumados.';
