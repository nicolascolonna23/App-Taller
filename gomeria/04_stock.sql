-- =====================================================================
-- STOCK DE CUBIERTAS — vistas para verlo desde la app
-- Se pega en Supabase → SQL Editor → New query → Run, después de los otros.
-- =====================================================================

-- Cada cubierta con dónde está puesta ahora, si lo está. Es la vista que
-- alimenta la pantalla de stock.
create or replace view v_cubiertas as
select
  c.id, c.codigo, c.marca, c.modelo, c.medida, c.estado,
  c.km_acumulados, c.recapados, c.remanente_mm, c.costo_compra,
  c.fecha_alta, c.fecha_baja, c.motivo_baja, c.observaciones,
  u.id       as unidad_id,
  u.patente,
  u.interno,
  u.sucursal,
  p.codigo   as posicion,
  m.desde    as montada_desde,
  -- Un solo campo para mostrar y para buscar: "AD247MQ · 2IE" o "En stock".
  case
    when u.patente is not null then u.patente || ' · ' || p.codigo
    when c.estado = 'stock'      then 'En stock'
    when c.estado = 'reparacion' then 'En reparación'
    when c.estado = 'recapado'   then 'En recapado'
    when c.estado = 'baja'       then 'De baja'
    else c.estado
  end as ubicacion
from cubiertas c
left join montajes m on m.cubierta_id = c.id and m.hasta is null
left join unidades u on u.id = m.unidad_id
left join configuracion_posiciones p on p.id = m.posicion_id;

comment on view v_cubiertas is
  'Todas las cubiertas con su ubicación actual: la unidad y posición si está montada.';

-- Cuántas hay disponibles de cada medida. Es lo primero que se pregunta el
-- gomero antes de salir a comprar.
create or replace view v_stock_por_medida as
select
  coalesce(nullif(trim(medida), ''), 'sin medida') as medida,
  count(*) filter (where estado = 'stock')       as en_stock,
  count(*) filter (where estado = 'montada')     as montadas,
  count(*) filter (where estado = 'reparacion')  as en_reparacion,
  count(*) filter (where estado = 'recapado')    as en_recapado,
  count(*) filter (where estado <> 'baja')       as vivas,
  count(*)                                        as total,
  round(avg(remanente_mm) filter (where estado = 'montada'), 1) as remanente_promedio
from cubiertas
group by 1
order by vivas desc, 1;
