-- =====================================================================
-- UREA — el tacho propio
-- ---------------------------------------------------------------------
-- Combustible es plata que se controla contra un tercero: la estación
-- manda su listado y el sistema cruza remitos. La urea no: el tacho es
-- nuestro, así que no hay nada que cruzar con nadie. Lo que hay que
-- controlar es un stock, y eso en este sistema ya está resuelto en
-- Repuestos: nadie edita el saldo, el saldo es el resultado de los
-- movimientos.
--
-- Tres movimientos y nada más:
--
--   entrada   llegó el proveedor y se descargó en el tacho.
--   salida    se despachó a una unidad. O se derramó, o se prestó: eso
--             también sale del tacho y también se anota.
--   ajuste    alguien midió el tacho y no da. La diferencia se anota con
--             su motivo; el saldo NO se corrige a mano.
--
-- Lo último es la parte que importa. La merma de un tacho de urea es real
-- —evaporación, derrames, lo que se carga y no se anota— y tapar la
-- diferencia editando un número es perder justo el dato que la explica.
--
-- Se pega entero en Supabase → SQL Editor → Run. Se puede correr las
-- veces que haga falta: no borra nada.
--
-- ANTES tienen que estar corridos 01_esquema.sql y 03_usuarios.sql.
-- Con 10_combustible.sql y 05_odometros.sql corridos, además sale el
-- porcentaje de urea sobre gasoil por unidad.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. EL TACHO
-- ---------------------------------------------------------------------
-- Una fila por tacho. Hoy puede ser uno solo; va por sucursal desde el
-- principio para que el día que Tucumán tenga el suyo no haya que tocar
-- nada. `minimo_litros` es cuándo empieza a avisar: si no se carga, se
-- toma el 20% de la capacidad, que para un tacho de 1.000 son los 200
-- litros que dan tiempo a pedir sin quedarse.
create table if not exists urea_tanques (
  id              bigint generated always as identity primary key,
  nombre          text not null,
  sucursal_codigo char(3),
  capacidad_litros numeric not null check (capacidad_litros > 0),
  minimo_litros   numeric check (minimo_litros is null or minimo_litros >= 0),
  activo          boolean not null default true,
  nota            text,
  creado          timestamptz not null default now()
);

comment on table urea_tanques is
  'Los tachos de urea propios. El saldo no se guarda acá: sale de los movimientos.';


-- ---------------------------------------------------------------------
-- 2. LOS MOVIMIENTOS
-- ---------------------------------------------------------------------
-- Append-only en la práctica: se puede borrar el que se cargó por error
-- —y el saldo se corrige solo, porque se calcula— pero no se edita el
-- saldo por ningún lado.
--
-- `litros` va siempre positivo en entrada y salida: el signo lo pone el
-- tipo, no quien carga. En el ajuste sí lleva signo, porque un ajuste es
-- una diferencia: -12 es que faltan doce litros.
create table if not exists urea_movimientos (
  id          bigint generated always as identity primary key,
  tanque_id   bigint not null references urea_tanques(id),
  tipo        text not null check (tipo in ('entrada', 'salida', 'ajuste')),
  fecha       date not null default current_date,
  litros      numeric not null,

  -- Salida: a qué unidad fue. Igual que en las órdenes, la patente se
  -- guarda además del id: una unidad dada de baja tiene que poder leerse.
  unidad_id   bigint references unidades(id),
  patente     text,
  km          numeric check (km is null or km >= 0),

  -- Entrada: de dónde vino y cuánto costó.
  proveedor   text,
  remito      text,
  importe     numeric check (importe is null or importe >= 0),

  -- Salida sin patente (derrame, préstamo, devolución) y motivo del
  -- ajuste. Sin esto, la diferencia de una medición es un número sin
  -- historia.
  motivo      text,
  -- Cuánto marcaba el tacho cuando se midió. Se guarda además de la
  -- diferencia: es el dato que se tomó, y la diferencia es la cuenta.
  medido_litros numeric check (medido_litros is null or medido_litros >= 0),

  usuario_id  bigint references usuarios(id),
  usuario     text,
  creado      timestamptz not null default now(),
  nota        text,

  -- Entrada y salida son cantidades; el ajuste es una diferencia.
  check (case when tipo in ('entrada', 'salida') then litros > 0
              else litros <> 0 end)
);

create index if not exists ix_urea_mov_tanque  on urea_movimientos (tanque_id, fecha desc, id desc);
create index if not exists ix_urea_mov_unidad  on urea_movimientos (unidad_id, fecha desc);
create index if not exists ix_urea_mov_patente on urea_movimientos (patente, fecha desc);
create index if not exists ix_urea_mov_fecha   on urea_movimientos (fecha);

comment on column urea_movimientos.litros is
  'Positivo en entrada y salida: el signo lo pone el tipo. En el ajuste lleva signo.';


-- ---------------------------------------------------------------------
-- 3. EL SALDO
-- ---------------------------------------------------------------------
-- Cada movimiento con su signo ya puesto. De acá sale todo lo demás, así
-- que la regla del signo está escrita una sola vez.
create or replace view v_urea_movimientos as
select m.*,
       case when m.tipo = 'salida' then -m.litros else m.litros end as delta,
       u.interno, u.marca, u.modelo, u.sucursal,
       t.nombre as tanque
from urea_movimientos m
join urea_tanques t on t.id = m.tanque_id
left join unidades u on u.id = m.unidad_id;


-- El estado de cada tacho: cuánto queda, a qué ritmo se va y para
-- cuántos días alcanza. Las dos formas de quedarse sin urea —el tacho
-- bajo y el consumo alto— miran el mismo número desde distintos lados.
create or replace view v_urea_saldo as
with movimiento as (
  select tanque_id,
         sum(case when tipo = 'salida' then -litros else litros end) as saldo,
         max(fecha) filter (where tipo = 'entrada') as ultima_entrada,
         max(fecha) filter (where tipo = 'salida')  as ultima_salida,
         max(fecha) filter (where tipo = 'ajuste')  as ultima_medicion
  from urea_movimientos group by tanque_id
),
consumo as (
  -- El ritmo de los últimos 30 días. Un tacho recién instalado no tiene
  -- ritmo todavía, y eso es null, no cero: cero diría "no se consume".
  select tanque_id, sum(litros) as litros_30
  from urea_movimientos
  where tipo = 'salida' and fecha >= current_date - 30
  group by tanque_id
)
select t.id as tanque_id, t.nombre, t.sucursal_codigo, t.activo,
       t.capacidad_litros,
       coalesce(t.minimo_litros, round(t.capacidad_litros * 0.20, 2)) as minimo_litros,
       round(coalesce(m.saldo, 0), 2) as saldo,
       round(coalesce(m.saldo, 0) * 100 / t.capacidad_litros, 1) as porcentaje,
       m.ultima_entrada, m.ultima_salida, m.ultima_medicion,
       round(c.litros_30 / 30.0, 2) as consumo_diario,
       case when c.litros_30 > 0
            then floor(coalesce(m.saldo, 0) / (c.litros_30 / 30.0))::int
       end as dias_restantes,
       case
         -- Sin tacho no hay operación: eso no es un aviso, es una parada.
         when coalesce(m.saldo, 0) <= 0 then 'vacio'
         when coalesce(m.saldo, 0) <= coalesce(t.minimo_litros,
                                               t.capacidad_litros * 0.20) / 2
              or (c.litros_30 > 0
                  and coalesce(m.saldo, 0) / (c.litros_30 / 30.0) < 3) then 'critico'
         when coalesce(m.saldo, 0) <= coalesce(t.minimo_litros,
                                               t.capacidad_litros * 0.20)
              or (c.litros_30 > 0
                  and coalesce(m.saldo, 0) / (c.litros_30 / 30.0) < 7) then 'aviso'
         else 'ok'
       end as estado
from urea_tanques t
left join movimiento m on m.tanque_id = t.id
left join consumo c    on c.tanque_id = t.id;

comment on view v_urea_saldo is
  'Cuánto queda en cada tacho, a qué ritmo se va y para cuántos días alcanza.';


-- ---------------------------------------------------------------------
-- 4. LA UREA POR UNIDAD
-- ---------------------------------------------------------------------
-- Teniendo los litros de urea por patente, y ya teniendo los de gasoil y
-- los kilómetros del satelital, salen dos números que hoy no tiene nadie:
--
--   % de urea sobre gasoil   un camión moderno anda entre 3% y 6%. El que
--                            da 1% tiene el sistema anulado —y eso es una
--                            multa esperando—; el que da 12% pierde, o
--                            alguien se está llevando bidones.
--   litros cada 100 km       la misma medida con la que ya se mira el
--                            combustible.
--
-- El combustible y los kilómetros son opcionales: si esos módulos no
-- están corridos, el porcentaje queda en blanco y los litros de urea se
-- ven igual. No se rellena con un número inventado.
create or replace view v_urea_unidad as
with urea as (
  select date_trunc('month', m.fecha)::date as mes,
         m.unidad_id, m.patente,
         count(*)::int as despachos,
         sum(m.litros) as litros_urea,
         min(m.fecha) as primera, max(m.fecha) as ultima
  from urea_movimientos m
  where m.tipo = 'salida' and m.patente is not null
  group by 1, 2, 3
),
gasoil as (
  select date_trunc('month', c.fecha)::date as mes, c.patente,
         sum(c.litros) as litros_gasoil
  from combustible_cargas c
  where c.origen = 'planilla' and c.fecha is not null and c.patente is not null
  group by 1, 2
),
recorrido as (
  select date_trunc('month', k.fecha)::date as mes, k.patente,
         sum(k.recorrido) as km
  from v_km_diarios k
  where k.recorrido is not null
  group by 1, 2
)
select u.mes, u.unidad_id, u.patente,
       un.interno, un.marca, un.modelo, un.sucursal, un.chofer,
       u.despachos,
       round(u.litros_urea, 2) as litros_urea,
       round(g.litros_gasoil, 2) as litros_gasoil,
       r.km,
       case when g.litros_gasoil > 0
            then round(u.litros_urea * 100 / g.litros_gasoil, 1) end as porcentaje_gasoil,
       case when r.km > 0
            then round(u.litros_urea * 100 / r.km, 2) end as litros_100km,
       u.primera, u.ultima
from urea u
left join unidades un on un.id = u.unidad_id
left join gasoil g    on g.mes = u.mes and g.patente = u.patente
left join recorrido r on r.mes = u.mes and r.patente = u.patente;

comment on view v_urea_unidad is
  'Urea despachada por unidad y por mes, con el porcentaje sobre el gasoil.';


-- ---------------------------------------------------------------------
-- 5. EL PRIMER TACHO
-- ---------------------------------------------------------------------
-- Uno, para que la pantalla no arranque vacía. Los litros y el mínimo se
-- corrigen desde la pantalla; el nombre también.
insert into urea_tanques (nombre, capacidad_litros, nota)
select 'Tacho de urea', 1000,
       'Creado por 28_urea.sql. Corregir capacidad y mínimo desde la pantalla.'
where not exists (select 1 from urea_tanques);
