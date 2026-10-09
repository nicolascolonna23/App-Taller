-- =====================================================================
-- EL COSTO DE LO QUE SE LE PONE A UNA UNIDAD
-- =====================================================================
-- Proveedores en las órdenes, y el costo de cada cubierta y de cada
-- repuesto que sale del depósito para una patente, sumado al gasto de
-- esa unidad.
--
--   * Servicio externo: queda con el proveedor del catálogo (además del
--     nombre escrito, que se conserva).
--   * Cubierta dada de alta con costo: la primera vez que se monta en
--     una unidad se crea un servicio externo por ese costo, con su
--     proveedor, su factura y los km de la unidad.
--   * Repuesto que sale del depósito para una patente sin pasar por una
--     orden: se crea una orden interna cerrada con ese repuesto a su
--     último costo.
--
-- Se pega entero en Supabase -> SQL Editor -> Run. Se puede correr más
-- de una vez.
-- =====================================================================

alter table ordenes_trabajo
  add column if not exists proveedor_id bigint references proveedores(id) on delete set null,
  -- De dónde salió una orden que no cargó una persona: 'cubierta' o 'repuestos'.
  add column if not exists origen text;

alter table cubiertas
  add column if not exists proveedor_id bigint references proveedores(id) on delete set null,
  add column if not exists proveedor text,
  add column if not exists factura text,
  -- true: el costo todavía no se cargó a ninguna unidad. Solo las que
  -- entran desde ahora; las que ya estaban no generan gasto al moverse.
  add column if not exists costo_pendiente boolean not null default false,
  add column if not exists costo_orden_id bigint references ordenes_trabajo(id) on delete set null;

create index if not exists ordenes_trabajo_proveedor on ordenes_trabajo (proveedor_id);
