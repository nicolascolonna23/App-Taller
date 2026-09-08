-- =====================================================================
-- DESHACER UN MOVIMIENTO DE GOMERÍA
-- ---------------------------------------------------------------------
-- Se pega entero en Supabase → SQL Editor → New query → Run. Se puede
-- correr las veces que haga falta.
--
-- El gomero carga un parte, lo confirma, y recién ahí se da cuenta de que
-- puso el número de fuego cambiado. Hasta acá no había vuelta atrás: el
-- movimiento quedaba escrito y el mapa de la unidad, mal.
--
-- Un movimiento deshecho NO se borra. Se marca, se le revierte el efecto
-- —la cubierta vuelve a donde estaba— y desaparece de la lista, pero la
-- fila queda con quién lo deshizo y cuándo. El libro mayor de una flota
-- no puede tener renglones que se evaporan: la diferencia entre "esto no
-- pasó" y "esto se cargó mal y lo corrigió Ramón el martes" es toda la
-- diferencia cuando hay que discutir una goma.
-- =====================================================================

alter table movimientos
  add column if not exists deshecho        timestamptz,
  add column if not exists deshecho_por    text,
  add column if not exists deshecho_motivo text;

comment on column movimientos.deshecho is
  'Cuándo se revirtió. Nulo = el movimiento vale.';

-- Los movimientos que valen. Es por donde entran casi todas las consultas:
-- un movimiento deshecho no tiene que sumar kilómetros ni aparecer en una
-- ficha como si hubiera pasado.
create index if not exists ix_mov_vigentes
  on movimientos (unidad_id, fecha desc) where deshecho is null;

create index if not exists ix_mov_grupo_vigente
  on movimientos (grupo_id) where deshecho is null;

-- ---------------------------------------------------------------------
-- El historial de la unidad, ya agrupado
-- ---------------------------------------------------------------------
-- Un parte es un grupo: una rotación de cuatro cubiertas son cuatro filas
-- de un mismo grupo y en pantalla tienen que ser un solo renglón, con un
-- solo botón de deshacer. Deshacer media rotación no es deshacer nada.
create or replace view v_grupos_movimiento as
select mv.grupo_id,
       mv.unidad_id,
       max(mv.fecha)                                   as fecha,
       min(mv.id)                                      as primer_id,
       max(mv.id)                                      as ultimo_id,
       max(mv.parte_id)                                as parte_id,
       max(mv.usuario)                                 as usuario,
       count(*)::int                                   as renglones,
       array_agg(distinct mv.tipo order by mv.tipo)    as tipos,
       array_remove(array_agg(distinct mv.cubierta_id), null) as cubiertas,
       bool_or(mv.deshecho is not null)                as deshecho_flag,
       max(mv.deshecho)                                as deshecho,
       max(mv.deshecho_por)                            as deshecho_por,
       max(mv.deshecho_motivo)                         as deshecho_motivo
from movimientos mv
group by mv.grupo_id, mv.unidad_id;

comment on view v_grupos_movimiento is
  'Un renglón por parte: lo que en pantalla es un solo movimiento.';

-- ---------------------------------------------------------------------
-- La vida de la cubierta tampoco muestra lo deshecho
-- ---------------------------------------------------------------------
-- Es la misma vista de 02_vistas.sql con una condición más. Si un
-- movimiento se revirtió, en la ficha de la cubierta no puede seguir
-- figurando como algo que le pasó.
create or replace view v_historial_cubierta as
select
  mv.cubierta_id,
  c.codigo         as cubierta,
  mv.fecha,
  mv.tipo,
  u.patente,
  po.codigo        as desde_posicion,
  pd.codigo        as hasta_posicion,
  mv.km_unidad,
  mv.remanente_mm,
  mv.usuario,
  mv.nota,
  pa.texto         as texto_original
from movimientos mv
join cubiertas c on c.id = mv.cubierta_id
left join unidades u  on u.id  = mv.unidad_id
left join configuracion_posiciones po on po.id = mv.posicion_origen_id
left join configuracion_posiciones pd on pd.id = mv.posicion_destino_id
left join partes pa on pa.id = mv.parte_id
where mv.deshecho is null
order by mv.fecha desc;

-- Cómo quedó.
select count(*) filter (where deshecho is null) as movimientos_vigentes,
       count(*) filter (where deshecho is not null) as deshechos
from movimientos;
