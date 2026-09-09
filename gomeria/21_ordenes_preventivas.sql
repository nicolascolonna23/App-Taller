-- =====================================================================
-- MANTENIMIENTO PREVENTIVO EN ÓRDENES
-- ---------------------------------------------------------------------
-- Ejecutar una vez después de 15_ordenes.sql y 20_alertas.sql.
-- Es idempotente: se puede volver a correr sin borrar información.
-- =====================================================================

alter table ordenes_trabajo
  add column if not exists mantenimiento text;

alter table ordenes_trabajo
  drop constraint if exists ordenes_trabajo_mantenimiento_check;
alter table ordenes_trabajo
  add constraint ordenes_trabajo_mantenimiento_check
  check (mantenimiento is null or mantenimiento in ('preventivo', 'correctivo'));

-- La relación evita duplicar el service al reintentar un cierre y permite
-- retirarlo si la orden se reabre, se anula o se borra.
alter table services
  add column if not exists orden_id bigint
  references ordenes_trabajo(id) on delete cascade;

create unique index if not exists ux_services_orden on services (orden_id)
  where orden_id is not null;

-- Se agrega la nueva columna al final para conservar el contrato de la vista.
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
  o.mantenimiento
from ordenes_trabajo o
left join unidades u on u.id = o.unidad_id
left join lateral (
  select sum(coalesce(importe, 0)) as importe, count(*) as cuantas
  from ordenes_tareas where orden_id = o.id) t on true
left join lateral (
  select sum(coalesce(precio, 0) * cantidad) as importe, count(*) as cuantos
  from ordenes_repuestos where orden_id = o.id) r on true;

comment on column ordenes_trabajo.mantenimiento is
  'Clasificación obligatoria para nuevas órdenes: preventivo o correctivo.';
comment on column services.orden_id is
  'Orden preventiva que originó este registro de service.';
