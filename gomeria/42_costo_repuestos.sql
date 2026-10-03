-- =====================================================================
-- CUÁNTO SALE CADA REPUESTO
-- =====================================================================
-- El inventario de repuestos llevaba cantidades y nada más: cuántos
-- filtros entraron, cuántos salieron y a qué unidad. Con eso se sabe si
-- falta algo, pero no cuánto vale lo que hay en el estante ni cuánto
-- costó lo que se le puso a un camión.
--
-- El costo va en el movimiento y no en el artículo, porque es del
-- movimiento: el mismo filtro no cuesta lo mismo en marzo que en
-- septiembre, y guardarlo en la ficha del artículo sería pisar el precio
-- viejo cada vez que se compra. Así queda la serie completa y se puede
-- ver cómo se movió.
--
-- Solo lleva costo lo que entra. Una salida es el repuesto que ya se
-- compró saliendo del estante: su costo es el que tenía cuando entró, no
-- uno nuevo.
-- =====================================================================

alter table repuestos_movimientos
  add column if not exists costo_unitario numeric check (costo_unitario >= 0);

comment on column repuestos_movimientos.costo_unitario is
  'Lo que salió cada unidad en esta compra, sin IVA. Solo en los '
  'movimientos que suman stock: una salida no tiene costo propio.';

-- ---------------------------------------------------------------------
-- EL STOCK, CON LO QUE VALE
-- ---------------------------------------------------------------------
-- Se valoriza al último costo conocido y no a un promedio. Dos razones:
-- se puede explicar de una sola frase —"tantos por lo que salió el
-- último"— y no se ensucia con las entradas viejas, que son casi todas y
-- no tienen costo cargado. El promedio ponderado de esas daría un número
-- que parece preciso y no lo es.
--
-- Por eso también va `entradas_con_costo`: dice de cuánta información
-- sale el número. Cero entradas con costo es "todavía no se sabe", que es
-- distinto de "vale cero".
--
-- Se borra y se vuelve a crear en vez de reemplazarla: la vista usa a.*,
-- y si a repuestos_articulos se le agregó una columna después de crearla
-- (creado_en, por ejemplo), PostgreSQL no deja reemplazarla con las
-- columnas en otro orden ("cannot change name of view column"). La vista
-- no guarda datos: borrarla no borra nada.
-- ---------------------------------------------------------------------
drop view if exists v_repuestos_stock;
create view v_repuestos_stock as
select
  a.*,
  coalesce(sum(case when m.tipo = 'Salida' then -abs(m.cantidad)
                    else m.cantidad end), 0)::integer as stock_actual,
  case
    when not a.activo then 'Dado de baja'
    when coalesce(sum(case when m.tipo='Salida' then -abs(m.cantidad) else m.cantidad end),0) < 0 then 'REVISAR'
    when coalesce(sum(case when m.tipo='Salida' then -abs(m.cantidad) else m.cantidad end),0) = 0 then 'SIN STOCK'
    when a.stock_minimo > 0 and coalesce(sum(case when m.tipo='Salida' then -abs(m.cantidad) else m.cantidad end),0) <= a.stock_minimo then 'REPONER'
    else 'OK'
  end as estado,
  u.costo_unitario as ultimo_costo,
  u.fecha          as ultimo_costo_fecha,
  count(m.id) filter (where m.costo_unitario is not null)::integer
    as entradas_con_costo,
  -- Lo que vale lo que hay hoy. Sin costo conocido queda en null y no en
  -- cero: no saber cuánto vale no es que no valga nada.
  case when u.costo_unitario is not null
       then round(u.costo_unitario * coalesce(sum(
              case when m.tipo = 'Salida' then -abs(m.cantidad)
                   else m.cantidad end), 0), 2)
  end as valorizado
from repuestos_articulos a
left join repuestos_movimientos m on m.articulo_id = a.id
left join lateral (
  select costo_unitario, fecha from repuestos_movimientos
  where articulo_id = a.id and costo_unitario is not null
  order by fecha desc, id desc limit 1
) u on true
group by a.id, u.costo_unitario, u.fecha;
