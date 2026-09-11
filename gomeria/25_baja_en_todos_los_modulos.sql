-- =====================================================================
-- QUE LA BAJA LLEGUE A TODOS LOS MÓDULOS
-- ---------------------------------------------------------------------
-- Dar de baja una unidad es una sola columna: `unidades.activa`. De ahí
-- salía para el maestro, para los services y para los vencimientos, que
-- ya la miraban. Pero las alertas de gomería y las de combustible no la
-- miraban, así que un camión vendido seguía pidiendo cambio de cubierta
-- todas las mañanas.
--
-- Se pega entero en Supabase → SQL Editor → New query → Run. Son vistas:
-- se puede correr las veces que haga falta y no toca un solo dato.
--
-- ---------------------------------------------------------------------
-- LO QUE OLVIDA Y LO QUE RECUERDA
-- ---------------------------------------------------------------------
-- La regla es una sola: LO OPERATIVO SE OLVIDA DE LA UNIDAD, LA HISTORIA
-- LA RECUERDA.
--
-- Se olvidan las listas que piden hacer algo hoy —alertas, tableros,
-- selectores—: una unidad que no está en la calle no puede reclamar
-- trabajo.
--
-- La recuerdan el combustible que cargó, las órdenes que tuvo y las
-- gomas que usó. Eso ya pasó. Si el consumo filtrara por `activa`, dar
-- de baja un camión en septiembre cambiaría el consumo de la flota de
-- junio, que es un número que alguien ya miró y ya usó. Un tablero que
-- cambia el pasado no se puede auditar.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. LAS GOMAS
-- ---------------------------------------------------------------------
-- La unidad de baja deja de avisar, pero las gomas que tiene puestas
-- siguen figurando montadas en el mapa de gomería: están arriba de ese
-- camión de verdad, y si la vista las diera por desaparecidas nadie se
-- acordaría de bajarlas. Por eso se toca la vista de ALERTAS y no la del
-- mapa ni la del historial.
create or replace view v_alertas_cubiertas as
select a.*,
       case
         when a.remanente_mm is null                then 'sin_medir'
         when a.remanente_mm <= a.minimo_mm         then 'al_limite'
         when a.remanente_mm <= a.aviso_mm          then 'cerca'
         else 'ok'
       end as alerta,
       case when a.km_por_mm is not null and a.remanente_mm is not null
                 and a.remanente_mm > a.minimo_mm
            then round((a.remanente_mm - a.minimo_mm) * a.km_por_mm) end as km_restantes,
       case when a.km_por_mm is not null and a.remanente_mm is not null
                 and a.remanente_mm > a.minimo_mm and a.km_dia > 0
            then round((a.remanente_mm - a.minimo_mm) * a.km_por_mm / a.km_dia) end as dias_restantes
from (
  select c.id            as cubierta_id,
         c.codigo, c.medida, c.estado,
         u.id            as unidad_id,
         u.patente, u.interno,
         fp.posicion, fp.funcion,
         cr.minimo_mm, cr.aviso_mm,
         c.remanente_mm,
         r.vida_id, r.numero as vida, r.tipo, r.marca, r.banda,
         r.inicial_mm, r.inicial_origen, r.km, r.costo,
         r.pesos_km, r.pesos_mm, r.mm_gastados,
         coalesce(r.km_por_mm, g.km_por_mm) as km_por_mm,
         (r.km_por_mm is null and g.km_por_mm is not null) as ritmo_estimado,
         d.km_dia,
         m.desde as montada_desde
  from montajes m
  join cubiertas c            on c.id = m.cubierta_id
  join unidades u             on u.id = m.unidad_id
  join v_funcion_posicion fp  on fp.posicion_id = m.posicion_id and fp.unidad_id = u.id
  join criterios_desgaste cr  on cr.funcion = fp.funcion
  left join v_rendimiento_cubiertas r
         on r.cubierta_id = c.id and r.hasta is null
  left join v_rendimiento_marcas g
         on g.tipo = r.tipo
        and g.marca = coalesce(r.marca, '(sin marca)')
        and g.banda is not distinct from r.banda
  left join v_km_dia_unidad d on d.unidad_id = u.id
  where m.hasta is null
    and u.activa                 -- ← lo único que cambia
) a;

comment on view v_alertas_cubiertas is
  'Las gomas puestas en unidades activas, con el mínimo que les toca y '
  'cuánto les falta para llegar. Las de una unidad de baja siguen '
  'montadas en el mapa, pero no reclaman.';


-- ---------------------------------------------------------------------
-- 2. EL COMBUSTIBLE
-- ---------------------------------------------------------------------
-- Una carga más grande de lo normal es una alerta para ir a preguntar
-- hoy. En una unidad que ya no está en la flota no hay a quién
-- preguntarle, y el renglón queda para siempre arriba de la lista.
--
-- Las cargas NO se borran ni se sacan del consumo: siguen en
-- `combustible_cargas` y en `v_combustible_flota`. Lo que deja de pasar
-- es que griten.
create or replace view v_cargas_grandes as
select c.id as carga_id, c.remito, c.remito_bruto, c.fecha,
       c.patente, c.unidad_id, u.interno,
       c.litros, c.importe, c.estacion, c.chofer,
       r.litros_maximos,
       round(c.litros - r.litros_maximos, 2) as litros_de_mas
from combustible_cargas c
cross join alertas_reglas r
left join unidades u on u.id = c.unidad_id
where c.origen = 'planilla'
  and c.litros is not null
  and c.litros > r.litros_maximos
  and (c.fecha is null or c.fecha >= current_date - r.combustible_dias)
  -- La patente que no engancha con ninguna unidad avisa igual: no se sabe
  -- de quién es esa carga, y eso es justamente lo que hay que mirar.
  and (u.id is null or u.activa);   -- ← lo único que cambia

comment on view v_cargas_grandes is
  'Cargas de combustible más grandes de lo normal, de unidades activas o '
  'de patentes que no están en el maestro.';


-- =====================================================================
-- CÓMO QUEDÓ
-- =====================================================================
select count(*) filter (where activa)     as activas,
       count(*) filter (where not activa) as de_baja
from unidades;

-- Lo que dejó de reclamar al dar de baja. Si acá hay algo, es una unidad
-- de baja que tiene gomas puestas: siguen arriba del camión y alguien las
-- tiene que bajar.
select u.patente, count(*) as cubiertas_montadas
from montajes m
join unidades u on u.id = m.unidad_id
where m.hasta is null and not u.activa
group by u.patente
order by u.patente;

-- Órdenes de trabajo abiertas de unidades de baja. No se cierran solas.
select o.numero, o.patente, o.fecha, o.estado
from ordenes_trabajo o
join unidades u on u.id = o.unidad_id
where o.estado = 'abierta' and not u.activa
order by o.fecha;
