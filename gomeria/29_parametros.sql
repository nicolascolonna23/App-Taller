-- =====================================================================
-- PARÁMETROS, PLANES, ENGANCHES Y LOS ROLES DEL TALLER
-- ---------------------------------------------------------------------
-- Cuatro cosas que venían atadas con alambre y pasan a estar cargadas:
--
--   1. De dónde salen los kilómetros: del satelital o a mano. Hasta acá
--      era "siempre del satelital", y la sucursal que no tiene equipo
--      quedaba sin kilómetros y sin services.
--   2. Los planes de mantenimiento, con su clase. El preventivo va por
--      kilómetros o por tiempo; el correctivo no tiene intervalo —una
--      rotura no se agenda— así que es un catálogo de trabajos con lo que
--      se espera que lleven de tiempo y de plata.
--   3. El enganche tractor–semi. El semi no tiene satelital: sus
--      kilómetros son los que hizo el tractor mientras lo llevó puesto.
--   4. Los roles con los que se trabaja de verdad: chofer, responsable de
--      sucursal, mecánico y responsable de taller.
--
-- Se pega entero en Supabase → SQL Editor → Run. Se puede correr las
-- veces que haga falta.
--
-- ANTES tienen que estar corridos 01, 03, 05, 20, 22 y 27.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. LOS PARÁMETROS DEL SISTEMA
-- ---------------------------------------------------------------------
-- Una sola fila. Lo que hoy está escrito en el código y mañana alguien
-- va a querer cambiar sin pedirle nada a nadie.
create table if not exists parametros (
  unica        boolean primary key default true check (unica),

  -- De dónde salen los kilómetros:
  --   automatico  los trae el satelital todas las mañanas (hawk.py).
  --   manual      los carga una persona. El job no escribe nada.
  km_origen    text not null default 'automatico'
               check (km_origen in ('automatico', 'manual')),
  km_hora      text not null default '05:00',   -- a qué hora corre el job

  actualizado  timestamptz not null default now(),
  usuario      text
);

insert into parametros (unica) values (true) on conflict do nothing;

comment on table parametros is
  'Una fila. Cómo se comporta el sistema donde antes decidía el código.';


-- ---------------------------------------------------------------------
-- 2. LOS PLANES, CON SU CLASE
-- ---------------------------------------------------------------------
-- El preventivo se agenda: cada tantos kilómetros, o cada tantos días
-- —el aceite se vence aunque el camión no ruede—. El correctivo no se
-- agenda: se define qué trabajo es, cuánto debería llevar y cuánto
-- debería costar, para poder comparar lo que salió contra lo que se
-- esperaba.
alter table mantenimiento_planes
  add column if not exists clase text not null default 'preventivo';

alter table mantenimiento_planes
  drop constraint if exists mantenimiento_planes_clase_check;
alter table mantenimiento_planes
  add constraint mantenimiento_planes_clase_check
  check (clase in ('preventivo', 'correctivo'));

alter table mantenimiento_planes add column if not exists cada_dias integer
  check (cada_dias is null or cada_dias > 0);
alter table mantenimiento_planes add column if not exists tareas text;
alter table mantenimiento_planes add column if not exists horas_estimadas numeric
  check (horas_estimadas is null or horas_estimadas >= 0);
alter table mantenimiento_planes add column if not exists costo_estimado numeric
  check (costo_estimado is null or costo_estimado >= 0);

-- Un plan correctivo no lleva intervalo, así que `cada_km` deja de ser
-- obligatorio. El preventivo lo sigue necesitando y eso se revisa abajo.
alter table mantenimiento_planes alter column cada_km drop not null;

alter table mantenimiento_planes
  drop constraint if exists mantenimiento_planes_cada_km_check;
alter table mantenimiento_planes
  add constraint mantenimiento_planes_cada_km_check
  check (cada_km is null or cada_km > 0);

-- Un preventivo sin cada cuánto no sirve para nada: no puede avisar.
alter table mantenimiento_planes
  drop constraint if exists mantenimiento_planes_preventivo_check;
alter table mantenimiento_planes
  add constraint mantenimiento_planes_preventivo_check
  check (clase <> 'preventivo' or cada_km is not null or cada_dias is not null);

comment on column mantenimiento_planes.clase is
  'preventivo: se agenda por km o por días. correctivo: catálogo de trabajos.';


-- ---------------------------------------------------------------------
-- 3. EL ENGANCHE TRACTOR–SEMI
-- ---------------------------------------------------------------------
-- El semi no tiene satelital. Sus kilómetros son los del tractor que lo
-- llevó, mientras lo llevó: por eso el enganche tiene fechas y no es una
-- columna de texto en la unidad, que solo sabe decir el de hoy y borra
-- el de ayer.
create table if not exists enganches (
  id         bigint generated always as identity primary key,
  tractor_id bigint not null references unidades(id),
  semi_id    bigint not null references unidades(id),
  desde      date not null default current_date,
  hasta      date,                       -- null: sigue enganchado
  usuario    text,
  nota       text,
  creado     timestamptz not null default now(),
  check (tractor_id <> semi_id),
  check (hasta is null or hasta >= desde)
);

-- Un semi va atrás de un tractor y un tractor lleva un semi: los dos, de
-- a uno por vez. Lo que está abierto es lo que no se puede repetir.
create unique index if not exists ux_enganche_semi_abierto
  on enganches (semi_id) where hasta is null;
create unique index if not exists ux_enganche_tractor_abierto
  on enganches (tractor_id) where hasta is null;

create index if not exists ix_enganches_semi    on enganches (semi_id, desde desc);
create index if not exists ix_enganches_tractor on enganches (tractor_id, desde desc);

-- Qué unidades son semis. Se marca solo la primera vez que se engancha
-- una, y se siembra con lo que ya decía el maestro en `unidades.semi`.
alter table unidades add column if not exists es_semi boolean not null default false;

update unidades u set es_semi = true
where not u.es_semi
  and exists (select 1 from unidades t
              where t.semi is not null and t.semi = u.patente);

comment on table enganches is
  'Qué semi llevó cada tractor y desde cuándo. De acá salen los km del semi.';


-- Los kilómetros que le corresponden al semi, día por día: los que hizo
-- el tractor mientras lo llevaba puesto.
--
-- El recorrido de una fecha es el tramo entre la lectura anterior y esa
-- fecha, así que el día del enganche no cuenta: ese tramo lo hizo el
-- tractor solo o con otro semi atrás.
create or replace view v_km_semi_diario as
select e.semi_id,
       e.tractor_id,
       k.fecha,
       k.recorrido
from enganches e
join v_km_diarios k
  on k.unidad_id = e.tractor_id
 and k.fecha > e.desde
 and (e.hasta is null or k.fecha <= e.hasta)
where k.recorrido is not null;


-- La pantalla del submódulo: cada semi con el tractor que lleva hoy y lo
-- que rodó desde que se registran enganches.
create or replace view v_semis as
select s.id as semi_id, s.patente, s.interno, s.marca, s.modelo, s.sucursal,
       s.km_actual, s.activa,
       e.id as enganche_id, e.tractor_id, e.desde,
       t.patente as tractor, t.interno as tractor_interno,
       round(coalesce(k.km, 0), 0) as km_enganchado,
       k.ultima as ultimo_dia,
       coalesce(c.cuantos, 0)::int as enganches
from unidades s
left join lateral (
  select * from enganches e2 where e2.semi_id = s.id and e2.hasta is null limit 1
) e on true
left join unidades t on t.id = e.tractor_id
left join lateral (
  select sum(recorrido) as km, max(fecha) as ultima
  from v_km_semi_diario d where d.semi_id = s.id
) k on true
left join lateral (
  select count(*) as cuantos from enganches e3 where e3.semi_id = s.id
) c on true
where s.es_semi;

comment on view v_semis is
  'Cada semi con su tractor de hoy y los kilómetros que le corresponden.';


-- ---------------------------------------------------------------------
-- 4. LOS ROLES CON LOS QUE SE TRABAJA
-- ---------------------------------------------------------------------
-- Dos permisos más, porque los dos niveles que había no alcanzaban:
--
--   repara            carga trabajos y repuestos en una orden abierta. Es
--                     el mecánico: hace, pero no aprueba ni cierra.
--   solo_su_sucursal  ve lo de su boca y nada más. Es el responsable de
--                     sucursal y el chofer: la red entera no les sirve y
--                     les muestra plata que no es suya.
alter table roles add column if not exists repara boolean not null default false;
alter table roles add column if not exists solo_su_sucursal boolean not null default false;

-- El encargado y el administrador reparan por definición: el que cierra
-- una orden también puede cargarle un renglón.
update roles set repara = true where gestiona and not repara;

insert into roles (codigo, nombre, descripcion, gestiona, administra, repara,
                   pide_sucursal, solo_su_sucursal, de_sistema, orden) values
  ('taller',   'Responsable de taller',
   'Aprueba solicitudes, abre y cierra órdenes, carga services.',
   true,  false, true,  false, false, true, 5),
  ('mecanico', 'Mecánico',
   'Carga en la orden lo que hizo y los repuestos que puso. No aprueba ni cierra.',
   false, false, true,  false, false, true, 6),
  ('chofer',   'Chofer',
   'Ve su unidad: lo que vence, lo que le toca y lo que se le hizo.',
   false, false, false, true,  true,  true, 7)
on conflict (codigo) do nothing;

-- El responsable de sucursal ve lo suyo: pide órdenes de trabajo y mira
-- los services de su boca. La red entera no le sirve.
update roles set solo_su_sucursal = true, pide_sucursal = true
where codigo = 'sucursal';

insert into rol_modulos (rol_codigo, modulo)
select 'taller', m from unnest(array[
  'flota','unidades','gomeria','repuestos','ordenes','solicitudes',
  'alertas','vencimientos','combustible','parametros']) as m
on conflict do nothing;

insert into rol_modulos (rol_codigo, modulo)
select 'mecanico', m from unnest(array[
  'flota','unidades','gomeria','repuestos','ordenes','alertas']) as m
on conflict do nothing;

insert into rol_modulos (rol_codigo, modulo)
select 'chofer', m from unnest(array[
  'flota','alertas','vencimientos']) as m
on conflict do nothing;

-- Al responsable de sucursal: services de su boca y solicitudes. Nada del
-- depósito ni del tablero del taller.
insert into rol_modulos (rol_codigo, modulo)
select 'sucursal', m from unnest(array[
  'solicitudes','flota','unidades','alertas','vencimientos']) as m
on conflict do nothing;

-- La parametrización es de quien administra, y del responsable de taller
-- para los planes.
insert into rol_modulos (rol_codigo, modulo) values
  ('admin', 'parametros'), ('encargado', 'parametros')
on conflict do nothing;


-- ---------------------------------------------------------------------
-- 5. EL USUARIO MAESTRO
-- ---------------------------------------------------------------------
-- Uno, el dueño del sistema. No se le puede dar de baja ni cambiarle el
-- rol desde la pantalla —ni él mismo—, y administra siempre, aunque
-- alguien le toque los permisos al rol. Es el seguro contra quedarse
-- afuera del propio sistema.
alter table usuarios add column if not exists es_maestro boolean not null default false;

create unique index if not exists ux_usuario_maestro
  on usuarios (es_maestro) where es_maestro;

-- El primero que administra y todavía nadie marcó. Si hay que cambiarlo:
--   update usuarios set es_maestro = false;
--   update usuarios set es_maestro = true where usuario = 'elquesea';
update usuarios set es_maestro = true
where id = (select u.id from usuarios u join roles r on r.codigo = u.rol
            where r.administra and u.activo order by u.id limit 1)
  and not exists (select 1 from usuarios where es_maestro);

comment on column usuarios.es_maestro is
  'El dueño del sistema: no se le da de baja ni se le cambia el rol desde la pantalla.';
