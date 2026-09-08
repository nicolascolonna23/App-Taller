-- =====================================================================
-- DESGASTE, COSTO Y RENDIMIENTO DE LAS CUBIERTAS
-- ---------------------------------------------------------------------
-- Se pega entero en Supabase → SQL Editor → New query → Run.
-- Se puede correr las veces que haga falta: no pisa nada de lo que ya
-- esté cargado.
--
-- Hasta acá el sistema sabía dónde está cada goma y cuántos kilómetros
-- lleva. Lo que no sabía es lo único que importa para decidir:
--
--   · cuánto dibujo le queda antes de tener que bajarla
--   · cuánto sale el kilómetro de esa goma
--   · qué marca y qué banda rinden más
--
-- Para eso hacen falta tres cosas que no estaban:
--
--   1. EL DIBUJO DE GOMA NUEVA. Sin saber con cuántos milímetros
--      arrancó, "le quedan 7 mm" no dice si gastó 8 o si gastó 2.
--   2. EL MÍNIMO. A qué altura hay que bajarla. No es el mismo para el
--      direccional que para el arrastre.
--   3. LAS VIDAS. Una cubierta no es una sola cosa: es la goma original,
--      después el primer recapado, después el segundo. Cada vida tiene
--      su costo, su banda y sus kilómetros. Comparar marcas mezclando
--      las vidas de una misma cubierta no compara nada.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. HASTA DÓNDE SE USA UNA GOMA
-- ---------------------------------------------------------------------
-- El mínimo legal en Argentina es 1,6 mm, pero esperar hasta ahí es
-- perder la carcasa: una goma gastada de más ya no se puede recapar, y
-- la carcasa vale más que el dibujo. Por eso el mínimo de la empresa es
-- más alto que el de la ley.
--
-- 'aviso_mm' es el amarillo: a esa altura todavía se puede andar, pero
-- ya hay que ir consiguiendo el reemplazo.
create table if not exists criterios_desgaste (
  funcion   text primary key
            check (funcion in ('direccional','traccion','arrastre','auxilio')),
  minimo_mm numeric not null check (minimo_mm > 0),
  aviso_mm  numeric not null check (aviso_mm > 0),
  nota      text,
  check (aviso_mm >= minimo_mm)
);

insert into criterios_desgaste (funcion, minimo_mm, aviso_mm, nota) values
  ('direccional', 4, 6, 'El eje de adelante se baja antes: es el que dirige y el que revienta peor.'),
  ('traccion',    3, 5, 'Se baja con dibujo suficiente para que la carcasa sirva para recapar.'),
  ('arrastre',    3, 5, 'Ejes del semi y portantes.'),
  ('auxilio',     3, 5, 'El auxilio se controla igual: es el que se usa cuando no hay opción.')
on conflict (funcion) do nothing;


-- ---------------------------------------------------------------------
-- 2. CON CUÁNTO DIBUJO ARRANCA CADA GOMA
-- ---------------------------------------------------------------------
-- Una tabla chica que dice, para cada medida —y si hace falta, para cada
-- marca o cada banda—, con cuántos milímetros sale de fábrica. Se carga
-- una vez y de ahí en más se aplica sola.
--
-- Las filas con 'medida', 'marca' o 'dibujo' en null valen para
-- cualquiera: una fila con solo la medida es "todas las 295". Cuando hay
-- varias que sirven, gana la más específica.
--
-- 'origen' separa lo que se midió de lo que se estimó. Los números que
-- salen de un valor típico se muestran en pantalla con la aclaración: la
-- cuenta se hace igual, pero no se toma una decisión de plata creyendo
-- que es un dato medido.
create table if not exists dibujos_nuevos (
  id     bigint generated always as identity primary key,
  medida text,
  marca  text,
  dibujo text,                     -- modelo de la goma, o banda del recapado
  mm     numeric not null check (mm > 0),
  origen text not null default 'cargado' check (origen in ('cargado','tipico')),
  nota   text
);

create unique index if not exists ux_dibujo_nuevo
  on dibujos_nuevos (coalesce(medida,''), coalesce(marca,''), coalesce(dibujo,''));

-- Valores típicos de la industria para las medidas que usa la flota.
-- Están para que las cuentas arranquen el primer día; cuando se mida una
-- goma nueva de verdad, se corrige la fila y se le pone origen 'cargado'.
insert into dibujos_nuevos (medida, marca, dibujo, mm, origen, nota) values
  ('295',     null, null, 15, 'tipico', 'Valor típico de 295/80R22.5. Corregir midiendo una nueva.'),
  ('275',     null, null, 15, 'tipico', 'Valor típico de 275/80R22.5. Corregir midiendo una nueva.'),
  ('1000×20', null, null, 17, 'tipico', 'Valor típico de 1000×20. Corregir midiendo una nueva.')
on conflict do nothing;


-- ---------------------------------------------------------------------
-- 3. LAS VIDAS DE CADA CUBIERTA
-- ---------------------------------------------------------------------
-- Vida 0 es la goma como se compró. Vida 1 es el primer recapado, y así.
-- Cada una tiene su banda, su costo y su dibujo inicial, y contra ella se
-- miden los kilómetros que se hicieron mientras estuvo puesta.
--
-- Es la unidad de comparación: "la banda X rinde 120.000 km" es una
-- afirmación sobre vidas, no sobre cubiertas.
create table if not exists vidas_cubierta (
  id          bigint generated always as identity primary key,
  cubierta_id bigint not null references cubiertas(id) on delete cascade,
  numero      int    not null check (numero >= 0),
  tipo        text   not null check (tipo in ('original','recapado')),
  marca       text,                  -- marca de la goma, o del recapador
  banda       text,                  -- modelo de la goma, o banda que le pusieron
  proveedor   text,                  -- a quién se le compró o quién la recapó
  inicial_mm  numeric check (inicial_mm > 0),   -- si se midió al empezar
  costo       numeric check (costo >= 0),
  desde       date not null default current_date,
  hasta       date,
  motivo_fin  text,
  -- Con cuánto dibujo terminó. Se anota al cerrar la vida y no se deduce
  -- de las mediciones: el mismo día que se cierra una vida se abre la
  -- siguiente, y la medición de la banda nueva no puede contar como el
  -- final de la anterior.
  remanente_fin_mm numeric,
  nota        text,
  creado      timestamptz not null default now(),
  check (hasta is null or hasta >= desde)
);

create unique index if not exists ux_vida_numero
  on vidas_cubierta (cubierta_id, numero);
-- Una cubierta tiene una sola vida corriendo.
create unique index if not exists ux_vida_abierta
  on vidas_cubierta (cubierta_id) where hasta is null;
create index if not exists ix_vida_cubierta on vidas_cubierta (cubierta_id);

-- Por si la tabla ya estaba creada de una corrida anterior.
alter table vidas_cubierta add column if not exists remanente_fin_mm numeric;

comment on table vidas_cubierta is
  'Cada vuelta de una cubierta: la original y cada recapado. Es contra esto que se mide el rendimiento.';


-- ---------------------------------------------------------------------
-- 4. ABRIRLE LA VIDA A LO QUE YA ESTÁ CARGADO
-- ---------------------------------------------------------------------
-- Las cubiertas que ya están en la base no tienen vida abierta. Se les
-- crea una sola, la que están viviendo ahora: si el contador de recapados
-- dice 1, la vida que corre es la 1 y es un recapado.
--
-- De las vidas anteriores no se sabe nada —no quedó registrado— y no se
-- inventan: el rendimiento se empieza a contar desde acá.
insert into vidas_cubierta (cubierta_id, numero, tipo, marca, banda,
                            costo, desde, nota)
select c.id,
       coalesce(c.recapados, 0),
       case when coalesce(c.recapados, 0) > 0 then 'recapado' else 'original' end,
       c.marca,
       case when coalesce(c.recapados, 0) > 0 then null else c.modelo end,
       -- El costo de compra es de la goma original. Si lo que corre es un
       -- recapado, ese costo no es el de esta vida y no se arrastra.
       case when coalesce(c.recapados, 0) = 0 then c.costo_compra end,
       c.fecha_alta,
       'Vida abierta al empezar a medir el desgaste. De las anteriores no hay registro.'
from cubiertas c
where c.estado <> 'baja'
  and not exists (select 1 from vidas_cubierta v where v.cubierta_id = c.id)
on conflict do nothing;


-- =====================================================================
-- LAS VISTAS
-- =====================================================================

-- ---------------------------------------------------------------------
-- QUÉ FUNCIÓN CUMPLE CADA POSICIÓN
-- ---------------------------------------------------------------------
-- El mínimo depende de dónde va la goma. La función sale del mapa: el
-- primer eje de rueda simple es el direccional, el auxilio es el auxilio,
-- lo que va colgado de un semi es arrastre y el resto es tracción.
create or replace view v_funcion_posicion as
select u.id  as unidad_id,
       p.id  as posicion_id,
       p.codigo as posicion,
       case
         when p.es_auxilio                         then 'auxilio'
         when p.montaje = 'unica' and p.eje = 1    then 'direccional'
         when coalesce(u.uso, '') ilike '%SEMI%'
           or cfg.nombre not like 'S%'             then 'arrastre'
         else 'traccion'
       end as funcion
from unidades u
join configuraciones cfg          on cfg.id = u.configuracion_id
join configuracion_posiciones p   on p.configuracion_id = u.configuracion_id;

comment on view v_funcion_posicion is
  'Direccional, tracción, arrastre o auxilio, deducido del mapa de la unidad.';


-- ---------------------------------------------------------------------
-- KILÓMETROS DE CADA MONTAJE
-- ---------------------------------------------------------------------
-- Los mismos que ya calcula la ficha de la cubierta, pero como vista,
-- para poder sumarlos por vida. Se toma la primera y la última lectura
-- del satelital dentro del montaje. Un salto imposible —más de 1.200 km
-- por día— es un cambio de equipo GPS y no un viaje: se descarta.
create or replace view v_km_montaje as
select m.id                                   as montaje_id,
       m.cubierta_id,
       m.unidad_id,
       m.posicion_id,
       m.desde::date                          as desde,
       coalesce(m.hasta::date, current_date)  as hasta,
       case
         when ini.km is null or fin.km is null           then null
         when fin.km < ini.km                            then null
         when fin.km - ini.km >
              1200 * greatest(fin.fecha - ini.fecha, 1)  then null
         else fin.km - ini.km
       end as km
from montajes m
left join lateral (
  select o.fecha, o.km from odometros o
  where o.unidad_id = m.unidad_id
    and o.fecha >= m.desde::date
    and o.fecha <= coalesce(m.hasta::date, current_date)
  order by o.fecha asc limit 1
) ini on true
left join lateral (
  select o.fecha, o.km from odometros o
  where o.unidad_id = m.unidad_id
    and o.fecha >= m.desde::date
    and o.fecha <= coalesce(m.hasta::date, current_date)
  order by o.fecha desc limit 1
) fin on true;


-- ---------------------------------------------------------------------
-- CADA VIDA CON SUS MILÍMETROS RESUELTOS
-- ---------------------------------------------------------------------
-- El dibujo inicial sale de tres lados, en este orden: el que se midió al
-- abrir la vida, el de la tabla por medida/marca/banda, o nada. El
-- remanente es el de hoy si la vida está abierta, y la última medición
-- antes del cierre si ya terminó.
create or replace view v_vidas as
select r.*,
       coalesce(r.inicial_cargado, d.mm) as inicial_mm,
       case when r.inicial_cargado is not null then 'medido'
            else d.origen end            as inicial_origen,
       case when r.hasta is null then r.remanente_hoy
            else coalesce(r.remanente_cierre, cierre.remanente_mm)
       end as remanente_mm
from (
  select v.id as vida_id, v.cubierta_id, v.numero, v.tipo, v.proveedor,
         v.costo, v.desde, v.hasta, v.motivo_fin, v.nota,
         c.codigo, c.medida, c.estado, c.recapados,
         c.remanente_mm      as remanente_hoy,
         coalesce(v.marca, c.marca)  as marca,
         coalesce(v.banda, c.modelo) as banda,
         v.inicial_mm        as inicial_cargado,
         v.remanente_fin_mm  as remanente_cierre
  from vidas_cubierta v
  join cubiertas c on c.id = v.cubierta_id
) r
left join lateral (
  select dn.mm, dn.origen
  from dibujos_nuevos dn
  where (dn.medida is null or dn.medida = r.medida)
    and (dn.marca  is null or dn.marca  = r.marca)
    and (dn.dibujo is null or dn.dibujo = r.banda)
  -- Gana la fila que más cosas dice: medida pesa más que marca, y marca
  -- más que banda.
  order by (case when dn.medida is null then 0 else 4 end)
         + (case when dn.marca  is null then 0 else 2 end)
         + (case when dn.dibujo is null then 0 else 1 end) desc
  limit 1
) d on true
left join lateral (
  select me.remanente_mm from mediciones me
  where me.cubierta_id = r.cubierta_id
    and me.fecha::date >= r.desde
    and me.fecha::date <= r.hasta
  order by me.fecha desc limit 1
) cierre on true;


-- ---------------------------------------------------------------------
-- KILÓMETROS DE CADA VIDA
-- ---------------------------------------------------------------------
-- Un montaje no cruza el borde de una vida: para recapar hay que
-- desmontar. Así que cada montaje cae entero adentro de una sola vida, la
-- que estaba abierta el día que se montó.
-- El día que se cierra una vida se abre la siguiente, así que comparar
-- contra 'desde' y 'hasta' pondría los montajes de ese día en las dos. Por
-- eso cada montaje elige su vida: la última que ya había empezado el día
-- que se montó.
create or replace view v_km_vida as
select v.id                       as vida_id,
       sum(k.km)                  as km,
       count(k.montaje_id)::int   as montajes,
       count(k.km)::int           as montajes_con_km
from vidas_cubierta v
left join v_km_montaje k
       on k.cubierta_id = v.cubierta_id
      and v.id = (
        select vv.id from vidas_cubierta vv
        where vv.cubierta_id = k.cubierta_id
        order by (vv.desde <= k.desde) desc,
                 case when vv.desde <= k.desde then vv.numero end desc nulls last,
                 vv.numero asc
        limit 1)
group by v.id;


-- ---------------------------------------------------------------------
-- EL RENDIMIENTO DE CADA VIDA
-- ---------------------------------------------------------------------
-- Acá están los números que se pidieron, uno por vida:
--
--   km_por_mm   cuántos kilómetros aguanta cada milímetro de dibujo.
--               Es el número que compara gomas sin que el precio moleste.
--   pesos_km    lo que sale el kilómetro de esa goma.
--   pesos_mm    lo que sale cada milímetro gastado.
--   km_proyectados  lo que va a durar la vida entera si sigue gastando
--               al mismo ritmo, desde el dibujo nuevo hasta el mínimo.
--
-- 'confiable' es la bandera honesta: dice si la cuenta se apoya en datos
-- suficientes. Una goma con dos días de uso da un km_por_mm cualquiera.
create or replace view v_rendimiento_cubiertas as
select b.*,
       case when b.mm_gastados > 0 then round(b.km / b.mm_gastados) end          as km_por_mm,
       case when b.km > 0          then round(b.costo / b.km, 2) end             as pesos_km,
       case when b.mm_gastados > 0 then round(b.costo / b.mm_gastados, 2) end    as pesos_mm,
       case when b.mm_gastados > 0 and b.mm_utiles is not null
            then round(b.km / b.mm_gastados * b.mm_utiles) end                   as km_proyectados,
       coalesce(b.km >= 5000 and b.mm_gastados >= 1, false)                     as confiable
from (
  select v.vida_id, v.cubierta_id, v.codigo, v.numero, v.tipo, v.marca, v.banda,
         v.proveedor, v.medida, v.estado, v.desde, v.hasta, v.motivo_fin,
         v.inicial_mm, v.inicial_origen, v.remanente_mm,
         nullif(v.costo, 0)                                as costo,
         k.km, k.montajes, k.montajes_con_km,
         case when v.inicial_mm is not null and v.remanente_mm is not null
               and v.inicial_mm > v.remanente_mm
              then round(v.inicial_mm - v.remanente_mm, 1) end as mm_gastados,
         -- Los milímetros que se pueden usar de verdad: del dibujo nuevo
         -- hasta el mínimo con el que hay que bajarla.
         case when v.inicial_mm is not null
              then v.inicial_mm - (select minimo_mm from criterios_desgaste
                                    where funcion = 'traccion') end as mm_utiles
  from v_vidas v
  left join v_km_vida k on k.vida_id = v.vida_id
) b;


-- ---------------------------------------------------------------------
-- EL RANKING: QUÉ MARCA Y QUÉ BANDA RINDEN MÁS
-- ---------------------------------------------------------------------
-- Una fila por marca y banda. Los kilómetros y los milímetros se suman
-- antes de dividir: así una goma con pocos kilómetros no pesa igual que
-- una que hizo cien mil. Solo entran las vidas confiables.
create or replace view v_rendimiento_marcas as
select r.tipo,
       coalesce(r.marca, '(sin marca)') as marca,
       r.banda,
       count(*)::int                    as vidas,
       sum(r.km)                        as km,
       sum(r.mm_gastados)               as mm_gastados,
       round(sum(r.km) / nullif(sum(r.mm_gastados), 0))         as km_por_mm,
       round(avg(r.inicial_mm), 1)                              as inicial_mm,
       count(r.costo)::int                                      as vidas_con_costo,
       sum(r.costo)                                             as costo,
       round(sum(r.costo) / nullif(sum(r.km) filter (where r.costo is not null), 0), 2) as pesos_km,
       round(sum(r.costo) / nullif(sum(r.mm_gastados) filter (where r.costo is not null), 0), 2) as pesos_mm,
       -- Lo que va a durar una goma de esta marca y esta banda, de nueva
       -- hasta el mínimo. Es el número con el que se elige proveedor.
       round(sum(r.km) / nullif(sum(r.mm_gastados), 0)
             * (avg(r.inicial_mm) - (select minimo_mm from criterios_desgaste
                                      where funcion = 'traccion'))) as km_proyectados
from v_rendimiento_cubiertas r
where r.confiable
group by r.tipo, coalesce(r.marca, '(sin marca)'), r.banda;


-- ---------------------------------------------------------------------
-- CUÁNTO ANDA POR DÍA CADA UNIDAD
-- ---------------------------------------------------------------------
-- Para poder decir "llega al mínimo en tres semanas" y no solo "en
-- 12.000 km". Se miran los últimos 60 días.
create or replace view v_km_dia_unidad as
select o.unidad_id,
       round((max(o.km) - min(o.km)) / nullif(max(o.fecha) - min(o.fecha), 0)) as km_dia
from odometros o
where o.unidad_id is not null
  and o.fecha >= current_date - 60
group by o.unidad_id
having max(o.fecha) > min(o.fecha)
   and max(o.km) >= min(o.km);


-- ---------------------------------------------------------------------
-- LA ALERTA
-- ---------------------------------------------------------------------
-- Una fila por cubierta montada, con el mínimo que le corresponde por
-- dónde está puesta y cuánto le falta para llegar.
--
-- No espera a que llegue: con el desgaste de esa misma goma calcula
-- cuántos kilómetros y cuántos días le quedan. Un aviso que llega cuando
-- la goma ya está en el mínimo no sirve para comprar nada.
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
         -- El desgaste propio si ya se midió; si no, el promedio de las
         -- gomas de la misma marca y banda, que es mejor que nada.
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
) a;

comment on view v_alertas_cubiertas is
  'Las gomas puestas, con el mínimo que les toca y cuánto les falta para llegar.';


-- ---------------------------------------------------------------------
-- LO QUE HAY EN EL DEPÓSITO Y NO SIRVE PARA MONTAR
-- ---------------------------------------------------------------------
-- Una goma en stock por debajo del mínimo más bajo no se puede poner en
-- ningún lado. Mejor saberlo en el estante que arriba del camión.
create or replace view v_stock_gastado as
select c.id as cubierta_id, c.codigo, c.marca, c.modelo, c.medida,
       c.remanente_mm, c.recapados,
       (select min(minimo_mm) from criterios_desgaste) as minimo_mm
from cubiertas c
where c.estado = 'stock'
  and c.remanente_mm is not null
  and c.remanente_mm <= (select min(minimo_mm) from criterios_desgaste);


-- =====================================================================
-- SEGURIDAD
-- ---------------------------------------------------------------------
-- Igual que el resto: nadie entra con la clave pública. El servidor usa
-- la de servicio, que no sale de la nube.
-- =====================================================================
alter table criterios_desgaste enable row level security;
alter table dibujos_nuevos     enable row level security;
alter table vidas_cubierta     enable row level security;


-- =====================================================================
-- CÓMO QUEDÓ
-- =====================================================================
select funcion, minimo_mm as "mínimo", aviso_mm as "aviso" from criterios_desgaste
order by funcion;

select count(*) as vidas_abiertas from vidas_cubierta where hasta is null;

-- Las que ya se pueden medir y las que están esperando un dato.
select case
         when inicial_mm is null then 'falta el dibujo de goma nueva'
         when remanente_mm is null then 'falta medir el remanente'
         when km is null then 'falta que Hawk reporte kilómetros'
         else 'se puede calcular'
       end as estado_del_dato,
       count(*) as cubiertas
from v_rendimiento_cubiertas
group by 1 order by 2 desc;

select alerta, count(*) as cubiertas from v_alertas_cubiertas group by 1 order by 1;
