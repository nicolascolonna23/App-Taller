-- =====================================================================
-- COMBUSTIBLE DE LA FLOTA
-- ---------------------------------------------------------------------
-- Hasta acá el módulo era solo un control de facturación: se subían los
-- dos papeles, se cruzaban y listo. Los litros de la flota seguían
-- viviendo en la planilla de Google, y por eso el consumo de la portada
-- se leía de ahí y no de la base.
--
-- Esto no agrega ninguna carga nueva ni pide subir nada de nuevo: son
-- vistas sobre lo que ya se importa como "nuestra planilla". El mismo
-- archivo que sirve para cruzar contra la estación pasa a ser, además, el
-- registro de combustible de la flota.
--
-- El consumo sale de cruzar dos cosas que ya están en la base:
--
--     los litros   de combustible_cargas (origen = 'planilla')
--     los km       de v_km_diarios, la serie del satelital
--
-- Y es la primera vez que el consumo se puede calcular por unidad y por
-- mes sin que nadie copie un número a mano.
--
-- Se pega entero en Supabase → SQL Editor → Run. Se puede correr las
-- veces que haga falta: son vistas, no toca ni un dato.
-- =====================================================================

drop view if exists v_combustible_mes;
drop view if exists v_combustible_flota;

-- ---------------------------------------------------------------------
-- Cada unidad, cada mes: cuánto cargó, cuánto costó y cuánto consume
-- ---------------------------------------------------------------------
create view v_combustible_flota as
with cargas as (
  -- Solo nuestra planilla. El listado de la estación es el papel del
  -- proveedor y sirve para controlar la factura, no para decir cuánto
  -- gastó la flota: contarlo también sería contar cada litro dos veces.
  select c.unidad_id,
         c.patente,
         date_trunc('month', c.fecha)::date as mes,
         count(*)::int  as cargas,
         sum(c.litros)  as litros,
         sum(c.importe) as importe,
         min(c.fecha)   as primera,
         max(c.fecha)   as ultima
  from combustible_cargas c
  where c.origen = 'planilla' and c.fecha is not null
  -- La patente entra en el agrupado además del id: las cargas de una
  -- patente que todavía no engancha con ninguna unidad tienen unidad_id
  -- en null, y sin esto caerían todas juntas en un mismo renglón.
  group by 1, 2, 3
),
recorrido as (
  -- v_km_diarios ya descarta lo que no es un viaje: los retrocesos, que
  -- son cambios de módulo GPS, y los saltos imposibles. Sumar de ahí es
  -- sumar kilómetros creíbles.
  select k.unidad_id,
         date_trunc('month', k.fecha)::date as mes,
         sum(k.recorrido) as km,
         count(*)::int    as dias
  from v_km_diarios k
  where k.recorrido is not null
  group by 1, 2
)
select c.mes,
       c.unidad_id,
       c.patente,
       u.interno, u.marca, u.modelo, u.sucursal, u.chofer,
       c.cargas,
       round(c.litros, 2)  as litros,
       round(c.importe, 2) as importe,
       c.primera, c.ultima,
       case when c.litros > 0
            then round(c.importe / c.litros, 2) end as precio_litro,
       r.km,
       r.dias as dias_con_lectura,
       -- El consumo, como se mide en camiones: litros cada 100 km.
       case when r.km > 0 and c.litros > 0
            then round(c.litros * 100 / r.km, 2) end as litros_100km,
       case when r.km > 0 and c.importe > 0
            then round(c.importe / r.km, 2) end as pesos_km,
       -- Por qué a esta unidad no se le puede calcular el consumo. Es
       -- media respuesta, pero es mucho mejor que una celda vacía que no
       -- se sabe si es un cero o un dato que falta.
       case
         when c.unidad_id is null then 'la patente no está en el maestro'
         when r.km is null        then 'sin lecturas del satelital ese mes'
         when r.km = 0            then 'el satelital no le contó kilómetros'
       end as sin_consumo
from cargas c
left join unidades u  on u.id = c.unidad_id
left join recorrido r on r.unidad_id = c.unidad_id and r.mes = c.mes;

comment on view v_combustible_flota is
  'Combustible de la flota por unidad y por mes: litros, importe, precio por '
  'litro y consumo en L/100 km cruzando con la serie del satelital. Sale de '
  'lo que se importa como "nuestra planilla".';


-- ---------------------------------------------------------------------
-- El total de la flota, mes por mes
-- ---------------------------------------------------------------------
create view v_combustible_mes as
select mes,
       count(*)::int          as unidades,
       sum(cargas)::int       as cargas,
       round(sum(litros), 2)  as litros,
       round(sum(importe), 2) as importe,
       case when sum(litros) > 0
            then round(sum(importe) / sum(litros), 2) end as precio_litro,
       sum(km) as km,
       -- El consumo de la flota se calcula sobre los totales y no
       -- promediando el de cada unidad: un utilitario que hizo 200 km no
       -- puede pesar lo mismo que un tractor que hizo 12.000.
       --
       -- Y entran solo los litros de las unidades a las que se les
       -- conocen los kilómetros. Sumar arriba los litros de una patente
       -- sin lecturas, cuyos km no están abajo, da un consumo inventado:
       -- más alto cuanto más combustible haya cargado esa unidad. Los
       -- litros que quedan afuera se cuentan aparte, en `sin_consumo`,
       -- para que no desaparezcan sin que nadie se entere.
       case when sum(km) > 0 and sum(litros) filter (where km > 0) > 0
            then round(sum(litros) filter (where km > 0) * 100 / sum(km), 2)
       end as litros_100km,
       case when sum(km) > 0 and sum(importe) filter (where km > 0) > 0
            then round(sum(importe) filter (where km > 0) / sum(km), 2)
       end as pesos_km,
       count(*) filter (where sin_consumo is not null)::int as sin_consumo,
       round(sum(litros) filter (where sin_consumo is not null), 2) as litros_sin_consumo
from v_combustible_flota
group by mes;

comment on view v_combustible_mes is
  'El total de combustible de la flota mes por mes. El consumo se calcula '
  'sobre los totales, no promediando unidades.';
