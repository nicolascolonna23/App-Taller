-- =====================================================================
-- FLUIDOS — lo que se compra por litro y se despacha por unidad
-- ---------------------------------------------------------------------
-- La urea ya estaba resuelta: un tacho propio, tres movimientos y un
-- saldo que nadie edita. El taller maneja otros cinco fluidos con
-- exactamente el mismo problema —aceites, refrigerante, hidráulico,
-- grasa—, así que pasa a ser uno solo: fluidos.
--
-- Lo que cambia respecto de la urea es el envase. Un bin de 1.000 litros
-- y un tambor de 205 no se miran igual, y un balde de grasa se mide en
-- kilos. El fluido dice en qué viene y cuánto entra, y de ahí sale el
-- dibujo: el envase abierto se va vaciando con los despachos, y los que
-- están sin abrir se cuentan al lado.
--
-- Los movimientos son los mismos tres de siempre:
--
--   entrada   llegó el proveedor y se descargó.
--   salida    se despachó a una unidad. Un derrame o un préstamo también
--             salen, y también se anotan: con motivo en vez de patente.
--   ajuste    alguien midió y no da. Se anota la diferencia con su
--             motivo. El saldo NO se corrige a mano: tapar la diferencia
--             editando un número es perder el dato que la explica.
--
-- Se pega entero en Supabase → SQL Editor → Run. Se puede correr las
-- veces que haga falta.
--
-- ANTES tienen que estar corridos 01_esquema.sql y 03_usuarios.sql.
-- Si estaba corrido 28_urea.sql, el tacho y todos sus movimientos se
-- migran acá solos, una sola vez.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. LOS PROVEEDORES
-- ---------------------------------------------------------------------
-- A quién se le compra. Hasta acá el proveedor era un texto que cada uno
-- escribía como quería en cada carga, así que no se podía sumar lo que
-- se le compró a nadie. Se usa en fluidos y en combustible.
create table if not exists proveedores (
  id       bigint generated always as identity primary key,
  nombre   text not null,
  cuit     text,
  contacto text,
  telefono text,
  email    text,
  -- Qué vende. Sirve para ofrecer solo los que corresponden cuando se
  -- carga: al que trae gasoil no tiene sentido ofrecerlo para la grasa.
  rubros   text[] not null default '{}',
  activo   boolean not null default true,
  nota     text,
  creado   timestamptz not null default now()
);

-- "YPF", "ypf" y "Ypf " son el mismo proveedor.
create unique index if not exists ux_proveedores_nombre on proveedores (lower(nombre));

comment on table proveedores is
  'A quién se le compra combustible, urea, aceites o grasa. Se edita en /parametros.';
comment on column proveedores.rubros is
  'combustible, urea, aceites, grasa, repuestos. Vacío es "para todo".';


-- ---------------------------------------------------------------------
-- 2. LOS FLUIDOS
-- ---------------------------------------------------------------------
-- Uno por fluido, no uno por envase comprado: el saldo es del fluido y
-- el envase es cómo se dibuja. `capacidad` es la de UN envase —un bin de
-- 1.000, un tambor de 205, un balde de 20—, así que con 1.700 litros de
-- aceite hay un tambor abierto por la mitad y siete sellados al lado.
create table if not exists fluidos (
  id        bigint generated always as identity primary key,
  nombre    text not null,
  -- Con lo que se lo busca desde el código, sin depender de cómo esté
  -- escrito el nombre. urea, aceite15w40, grasa.
  clave     text not null unique,
  unidad    text not null default 'litros' check (unidad in ('litros', 'kilos')),
  envase    text not null default 'tambor'
            check (envase in ('bin', 'tambor', 'tacho', 'balde', 'tanque')),
  capacidad numeric not null check (capacidad > 0),
  -- Cuándo empieza a avisar. Sin cargarlo se toma el 20% de un envase.
  minimo    numeric check (minimo is null or minimo >= 0),
  sucursal_codigo char(3),
  proveedor_id bigint references proveedores(id),
  activo    boolean not null default true,
  orden     integer not null default 50,
  nota      text,
  creado    timestamptz not null default now(),
  actualizado timestamptz not null default now()
);

create unique index if not exists ux_fluidos_nombre on fluidos (lower(nombre));

comment on table fluidos is
  'Los fluidos del taller. El saldo no se guarda: sale de los movimientos.';
comment on column fluidos.capacidad is
  'La capacidad de UN envase, no la del depósito: es lo que se dibuja lleno.';


-- ---------------------------------------------------------------------
-- 3. LOS MOVIMIENTOS
-- ---------------------------------------------------------------------
-- `cantidad` va siempre positiva en entrada y salida: el signo lo pone el
-- tipo, no quien carga. En el ajuste sí lleva signo, porque un ajuste es
-- una diferencia: -12 es que faltan doce litros.
create table if not exists fluido_movimientos (
  id         bigint generated always as identity primary key,
  fluido_id  bigint not null references fluidos(id),
  tipo       text not null check (tipo in ('entrada', 'salida', 'ajuste')),
  fecha      date not null default current_date,
  cantidad   numeric not null,

  -- Salida: a qué unidad fue. Igual que en las órdenes, la patente se
  -- guarda además del id: una unidad dada de baja tiene que poder leerse.
  unidad_id  bigint references unidades(id),
  patente    text,
  km         numeric check (km is null or km >= 0),

  -- Entrada: de dónde vino y cuánto costó.
  proveedor_id bigint references proveedores(id),
  proveedor  text,
  remito     text,
  importe    numeric check (importe is null or importe >= 0),

  -- Salida sin patente (derrame, préstamo) y motivo del ajuste.
  motivo     text,
  -- Cuánto marcaba cuando se midió. Se guarda además de la diferencia:
  -- es el dato que se tomó, y la diferencia es la cuenta.
  medido     numeric check (medido is null or medido >= 0),

  usuario_id bigint references usuarios(id),
  usuario    text,
  creado     timestamptz not null default now(),
  nota       text,

  -- De qué movimiento de urea salió, para que la migración se pueda
  -- correr las veces que haga falta sin duplicar nada.
  migrado_de bigint unique,

  check (case when tipo in ('entrada', 'salida') then cantidad > 0
              else cantidad <> 0 end)
);

create index if not exists ix_fluido_mov_fluido  on fluido_movimientos (fluido_id, fecha desc, id desc);
create index if not exists ix_fluido_mov_unidad  on fluido_movimientos (unidad_id, fecha desc);
create index if not exists ix_fluido_mov_patente on fluido_movimientos (patente, fecha desc);
create index if not exists ix_fluido_mov_fecha   on fluido_movimientos (fecha);


-- ---------------------------------------------------------------------
-- 4. EL SALDO
-- ---------------------------------------------------------------------
-- Cada movimiento con su signo ya puesto. De acá sale todo lo demás, así
-- que la regla del signo está escrita una sola vez.
create or replace view v_fluido_movimientos as
select m.*,
       case when m.tipo = 'salida' then -m.cantidad else m.cantidad end as delta,
       f.nombre as fluido, f.clave, f.unidad, f.envase,
       u.interno, u.marca, u.modelo, u.sucursal
from fluido_movimientos m
join fluidos f on f.id = m.fluido_id
left join unidades u on u.id = m.unidad_id;


-- Cuánto queda de cada fluido, en cuántos envases está y para cuántos
-- días alcanza. Las dos formas de quedarse sin —el saldo bajo y el
-- consumo alto— miran el mismo número desde distintos lados.
create or replace view v_fluidos_saldo as
with movimiento as (
  select fluido_id,
         sum(case when tipo = 'salida' then -cantidad else cantidad end) as saldo,
         max(fecha) filter (where tipo = 'entrada') as ultima_entrada,
         max(fecha) filter (where tipo = 'salida')  as ultima_salida,
         max(fecha) filter (where tipo = 'ajuste')  as ultima_medicion
  from fluido_movimientos group by fluido_id
),
consumo as (
  -- El ritmo de los últimos 30 días. Un fluido recién cargado no tiene
  -- ritmo todavía, y eso es null, no cero: cero diría "no se consume".
  select fluido_id, sum(cantidad) as salido_30
  from fluido_movimientos
  where tipo = 'salida' and fecha >= current_date - 30
  group by fluido_id
),
base as (
  select f.id as fluido_id, f.nombre, f.clave, f.unidad, f.envase, f.capacidad,
         f.sucursal_codigo, f.proveedor_id, f.activo, f.orden, f.nota,
         coalesce(f.minimo, round(f.capacidad * 0.20, 2)) as minimo,
         round(coalesce(m.saldo, 0), 2) as saldo,
         m.ultima_entrada, m.ultima_salida, m.ultima_medicion,
         round(c.salido_30 / 30.0, 2) as consumo_diario,
         c.salido_30
  from fluidos f
  left join movimiento m on m.fluido_id = f.id
  left join consumo c    on c.fluido_id = f.id
)
select b.*,
       p.nombre as proveedor,
       -- Cuántos envases hay contando el abierto, cuánto tiene el abierto
       -- y cuántos quedan sin tocar. Es lo que se dibuja.
       greatest(ceil(b.saldo / b.capacidad), 0)::int as envases,
       case when b.saldo <= 0 then 0
            else round(b.saldo - (ceil(b.saldo / b.capacidad) - 1) * b.capacidad, 2)
       end as abierto,
       greatest(ceil(b.saldo / b.capacidad)::int - 1, 0) as sellados,
       case when b.saldo <= 0 then 0
            else round((b.saldo - (ceil(b.saldo / b.capacidad) - 1) * b.capacidad)
                       * 100 / b.capacidad, 1)
       end as porcentaje,
       case when b.salido_30 > 0
            then floor(b.saldo / (b.salido_30 / 30.0))::int
       end as dias_restantes,
       case
         -- Un fluido que todavía nadie cargó no está vacío: está sin
         -- estrenar. Si fueran lo mismo, el día que se corre este script
         -- saltarían cinco alarmas de algo que nunca se compró.
         when coalesce(b.ultima_entrada, b.ultima_salida, b.ultima_medicion) is null
              then 'sin_cargar'
         -- Sin fluido no hay operación: eso no es un aviso, es una parada.
         when b.saldo <= 0 then 'vacio'
         when b.saldo <= b.minimo / 2
              or (b.salido_30 > 0 and b.saldo / (b.salido_30 / 30.0) < 3) then 'critico'
         when b.saldo <= b.minimo
              or (b.salido_30 > 0 and b.saldo / (b.salido_30 / 30.0) < 7) then 'aviso'
         else 'ok'
       end as estado,
       coalesce(b.ultima_entrada, b.ultima_salida, b.ultima_medicion) is not null as usado
from base b
left join proveedores p on p.id = b.proveedor_id;

comment on view v_fluidos_saldo is
  'Cuánto queda de cada fluido, en cuántos envases, y para cuántos días alcanza.';


-- ---------------------------------------------------------------------
-- 5. LO QUE LLEVÓ CADA UNIDAD
-- ---------------------------------------------------------------------
-- Teniendo lo despachado por patente, y ya teniendo el gasoil y los
-- kilómetros del satelital, salen dos números que hoy no tiene nadie:
--
--   % sobre gasoil     para la urea, un camión moderno anda entre 3% y 6%.
--                      El que da 1% tiene el sistema anulado —y eso es una
--                      multa esperando—; el que da 12% pierde, o alguien
--                      se está llevando bidones.
--   cada 100 km        la misma medida con la que ya se mira el gasoil.
--                      Un motor que toma aceite se ve acá antes que en la
--                      varilla.
--
-- El combustible y los kilómetros son opcionales: si esos módulos no
-- están corridos queda en blanco, no se rellena con un número inventado.
create or replace view v_fluidos_unidad as
with salidas as (
  select date_trunc('month', m.fecha)::date as mes,
         m.fluido_id, m.unidad_id, m.patente,
         count(*)::int as despachos,
         sum(m.cantidad) as cantidad,
         min(m.fecha) as primera, max(m.fecha) as ultima
  from fluido_movimientos m
  where m.tipo = 'salida' and m.patente is not null
  group by 1, 2, 3, 4
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
select s.mes, s.fluido_id, f.nombre as fluido, f.clave, f.unidad,
       s.unidad_id, s.patente,
       un.interno, un.marca, un.modelo, un.sucursal, un.chofer,
       s.despachos,
       round(s.cantidad, 2) as cantidad,
       round(g.litros_gasoil, 2) as litros_gasoil,
       r.km,
       case when g.litros_gasoil > 0
            then round(s.cantidad * 100 / g.litros_gasoil, 1) end as porcentaje_gasoil,
       case when r.km > 0
            then round(s.cantidad * 100 / r.km, 2) end as cada_100km,
       s.primera, s.ultima
from salidas s
join fluidos f        on f.id = s.fluido_id
left join unidades un on un.id = s.unidad_id
left join gasoil g    on g.mes = s.mes and g.patente = s.patente
left join recorrido r on r.mes = s.mes and r.patente = s.patente;

comment on view v_fluidos_unidad is
  'Lo que llevó cada unidad de cada fluido, por mes, con el % sobre el gasoil.';


-- ---------------------------------------------------------------------
-- 6. LOS FLUIDOS CON LOS QUE SE ARRANCA
-- ---------------------------------------------------------------------
-- Los seis que maneja el taller. La capacidad es la del envase con el que
-- se compra cada uno; se corrige desde /parametros, igual que el mínimo.
insert into fluidos (nombre, clave, unidad, envase, capacidad, orden) values
  ('Urea',                       'urea',        'litros', 'bin',    1000, 1),
  ('Aceite 15W40',               'aceite15w40', 'litros', 'tambor',  205, 10),
  ('Aceite 20W50',               'aceite20w50', 'litros', 'tambor',  205, 11),
  ('Refrigerante concentrado',   'refrigerante','litros', 'tambor',  205, 20),
  ('Líquido hidráulico',         'hidraulico',  'litros', 'tambor',  205, 21),
  ('Grasa',                      'grasa',       'kilos',  'balde',    20, 30)
on conflict (clave) do nothing;


-- ---------------------------------------------------------------------
-- 7. LO QUE YA ESTABA CARGADO EN UREA
-- ---------------------------------------------------------------------
-- El tacho de urea con sus movimientos pasa acá tal cual. Se puede
-- correr de nuevo: cada movimiento migrado deja anotado de cuál salió, y
-- los que ya están no vuelven a entrar. Las tablas viejas no se tocan:
-- si algo salió mal, el dato original sigue donde estaba.
do $$
declare
  destino bigint;
  tacho   record;
begin
  if to_regclass('public.urea_tanques') is null then
    return;
  end if;

  select id into destino from fluidos where clave = 'urea';
  if destino is null then
    return;
  end if;

  -- La capacidad y el mínimo del tacho que ya estaba mandan sobre los del
  -- alta: alguien los cargó mirando el tacho de verdad.
  select * into tacho from urea_tanques order by id limit 1;
  if found then
    update fluidos
       set capacidad = tacho.capacidad_litros,
           minimo = coalesce(tacho.minimo_litros, minimo),
           sucursal_codigo = coalesce(tacho.sucursal_codigo, sucursal_codigo),
           envase = case when tacho.capacidad_litros >= 900 then 'bin'
                         when tacho.capacidad_litros >= 150 then 'tambor'
                         else 'tacho' end,
           actualizado = now()
     where id = destino
       and not exists (select 1 from fluido_movimientos where fluido_id = destino);
  end if;

  insert into fluido_movimientos
    (fluido_id, tipo, fecha, cantidad, unidad_id, patente, km,
     proveedor, remito, importe, motivo, medido, usuario_id, usuario, creado, nota,
     migrado_de)
  select destino, m.tipo, m.fecha, m.litros, m.unidad_id, m.patente, m.km,
         m.proveedor, m.remito, m.importe, m.motivo, m.medido_litros,
         m.usuario_id, m.usuario, m.creado, m.nota, m.id
  from urea_movimientos m
  where not exists (select 1 from fluido_movimientos v where v.migrado_de = m.id);

  -- Y los proveedores que aparezcan escritos en esas cargas, para que la
  -- lista no arranque vacía.
  insert into proveedores (nombre, rubros)
  select distinct btrim(m.proveedor), array['urea']
  from urea_movimientos m
  where coalesce(btrim(m.proveedor), '') <> ''
    and not exists (select 1 from proveedores p
                    where lower(p.nombre) = lower(btrim(m.proveedor)))
  on conflict do nothing;
end $$;
