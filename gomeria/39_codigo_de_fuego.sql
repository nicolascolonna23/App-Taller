-- =====================================================================
-- EL NÚMERO DE FUEGO
-- =====================================================================
-- El código de una cubierta es su número de fuego: el que le graba el
-- gomero y el único que la identifica físicamente. Pero hay dos momentos
-- en que una cubierta entra al sistema sin él:
--
--   · el alta de stock del 07/09, que se contó por montón y entró con
--     códigos STK-R###, STK-N###, STK-C### y STK-M### (ver
--     16_stock_cubiertas.sql);
--   · el alta por factura, donde la factura trae medida, marca y costo
--     pero el fuego todavía no está grabado.
--
-- Hasta ahora eso se resolvía a mano, con un update. El problema no era
-- cambiar el código: era saber a cuáles les faltaba. Una cubierta con un
-- código provisorio se ve igual que cualquier otra en el listado, así que
-- nadie se entera de que ese STK-R035 es una goma sin identificar hasta
-- que la busca por el fuego y no aparece.
--
-- Esta columna lo dice. Y la vista de abajo las junta, para poder ir
-- completándolas.
-- =====================================================================

alter table cubiertas
  add column if not exists codigo_provisorio boolean not null default false;

comment on column cubiertas.codigo_provisorio is
  'true = el código no es el número de fuego, es uno puesto para poder '
  'cargarla. Se apaga solo cuando se le graba el fuego de verdad.';

-- Las que ya están: las del alta por montón. Se marca una sola vez —el
-- "and not codigo_provisorio" hace que volver a correr esto no pise una
-- que ya se completó y después se volvió a llamar STK- por lo que sea.
update cubiertas
   set codigo_provisorio = true
 where codigo ~ '^(STK|FC)-'
   and not codigo_provisorio
   and estado <> 'baja';

-- ---------------------------------------------------------------------
-- LAS QUE ESPERAN SU NÚMERO
-- ---------------------------------------------------------------------
-- Con lo que hace falta para salir a buscarlas: dónde está cada una, y
-- desde cuándo espera. Una cubierta montada sin fuego es la más urgente:
-- está rodando y no se la puede identificar si hay que sacarla.
-- ---------------------------------------------------------------------
drop view if exists v_cubiertas_sin_fuego;
create view v_cubiertas_sin_fuego as
select c.id, c.codigo, c.marca, c.modelo, c.medida, c.estado,
       c.recapados, c.remanente_mm, c.fecha_alta,
       (current_date - c.fecha_alta) as dias_esperando,
       u.patente, p.codigo as posicion
from cubiertas c
left join montajes m on m.cubierta_id = c.id and m.hasta is null
left join unidades u on u.id = m.unidad_id
left join configuracion_posiciones p on p.id = m.posicion_id
where c.codigo_provisorio and c.estado <> 'baja'
order by (m.id is not null) desc, c.fecha_alta, c.codigo;

comment on view v_cubiertas_sin_fuego is
  'Cubiertas cargadas con un código provisorio, esperando el número de '
  'fuego. Las montadas primero: son las que no se pueden identificar si '
  'hay que sacarlas.';
