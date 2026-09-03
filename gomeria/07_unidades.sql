-- =====================================================================
-- EL MAESTRO DE UNIDADES
-- ---------------------------------------------------------------------
-- La tabla `unidades` ya existía, pero con la mitad de los datos: le
-- faltaban el chasis, el chofer y el semi asociado, que hasta ahora
-- vivían solo en la planilla. Este archivo se los agrega.
--
-- A partir de acá, la información de una unidad sale de esta tabla y de
-- ningún otro lado. La planilla queda como estaba, pero deja de ser la
-- que manda.
--
-- Se pega entero en Supabase → SQL Editor → Run. Se puede correr las
-- veces que haga falta: no borra nada.
-- =====================================================================

alter table unidades add column if not exists chasis      text;
alter table unidades add column if not exists chofer      text;
alter table unidades add column if not exists semi        text;
alter table unidades add column if not exists tipo        text not null default 'vehiculo';
alter table unidades add column if not exists nota        text;
alter table unidades add column if not exists actualizado timestamptz not null default now();

comment on column unidades.patente is
  'Normalizada, sin espacios ni guiones: AD247MQ. En los equipos sin patente '
  'va el código con el que se los nombra: AUTCAT01.';
comment on column unidades.chasis is 'Número de chasis. Se repite en algunas unidades, así que no es único.';
comment on column unidades.semi   is 'Patente del semi asociado, normalizada. Texto: el semi puede no estar cargado como unidad.';
comment on column unidades.tipo   is 'vehiculo = anda por la calle. equipo = autoelevador, apilador y demás, no tiene patente.';

-- El tipo se limita a dos valores. Se agrega con DO porque Postgres no
-- tiene "add constraint if not exists" y correr el archivo dos veces
-- fallaría.
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'unidades_tipo_valido') then
    alter table unidades add constraint unidades_tipo_valido
      check (tipo in ('vehiculo','equipo'));
  end if;
end $$;

create index if not exists ix_unidades_interno on unidades(interno);
create index if not exists ix_unidades_chofer  on unidades(chofer);
create index if not exists ix_unidades_tipo    on unidades(tipo);

-- Que `actualizado` diga la verdad sin que nadie se acuerde de tocarlo.
create or replace function _unidad_tocada() returns trigger as $$
begin
  new.actualizado := now();
  return new;
end $$ language plpgsql;

drop trigger if exists tg_unidad_tocada on unidades;
create trigger tg_unidad_tocada before update on unidades
  for each row execute function _unidad_tocada();

-- ---------------------------------------------------------------------
-- La vista que lee la pantalla
-- ---------------------------------------------------------------------
-- Junta lo del maestro con lo que el resto del sistema ya sabe de cada
-- unidad: cómo está armada, cuántas cubiertas tiene montadas y cuándo
-- fue la última lectura del satelital. Así la pantalla de unidades no
-- necesita cruzar nada por su cuenta.
drop view if exists v_unidades;
create view v_unidades as
select u.id, u.patente, u.interno, u.tipo, u.marca, u.modelo, u.chasis,
       u.chofer, u.semi, u.sucursal, u.uso, u.nota, u.activa,
       u.km_actual, u.configuracion_id, c.nombre as configuracion,
       (select count(*) from montajes m
         where m.unidad_id = u.id and m.hasta is null) as cubiertas_montadas,
       (select max(o.fecha) from odometros o where o.unidad_id = u.id) as ultima_lectura,
       u.creado, u.actualizado
from unidades u
left join configuraciones c on c.id = u.configuracion_id;

comment on view v_unidades is
  'El maestro con lo que le agrega el resto del sistema. Es lo que lee la pantalla de unidades.';

-- ---------------------------------------------------------------------
-- Lo que no cierra, para mirarlo de vez en cuando
-- ---------------------------------------------------------------------
drop view if exists v_unidades_a_revisar;
create view v_unidades_a_revisar as
-- Un chasis repetido es casi siempre un copiar y pegar en la planilla.
select u.patente, 'chasis repetido' as problema, u.chasis as detalle
  from unidades u
 where u.chasis is not null
   and exists (select 1 from unidades o
                where o.chasis = u.chasis and o.id <> u.id)
union all
select patente, 'sin chofer', null from unidades
 where tipo = 'vehiculo' and activa and coalesce(chofer,'') = ''
union all
select patente, 'sin mapa de cubiertas', null from unidades
 where tipo = 'vehiculo' and activa and configuracion_id is null
union all
-- El satelital manda lecturas de patentes que no están en el maestro:
-- son unidades viejas o equipos que nunca se dieron de alta.
select distinct o.patente, 'reporta al satelital y no está en el maestro', null
  from odometros o where o.unidad_id is null;

comment on view v_unidades_a_revisar is
  'Los datos que no cierran. No es un error: es la lista de lo que falta completar.';
