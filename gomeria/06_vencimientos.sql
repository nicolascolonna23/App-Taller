-- =====================================================================
-- VENCIMIENTOS: VTV, licencias, matafuegos y lo que venga después
-- =====================================================================
-- La idea es una sola tabla para todos los vencimientos, no una por
-- tipo. Si mañana hay que seguir el RUTA, la póliza del seguro o el
-- psicofísico, se agrega una fila en tipos_vencimiento y funciona: no
-- hace falta tocar el código ni la base.
--
-- Cada renovación es una fila nueva, nunca un UPDATE sobre la anterior.
-- Así queda el historial: cuándo se hizo cada VTV, en qué taller, qué
-- número tenía. La vista v_vencimientos_hoy se queda con la última de
-- cada cosa, que es lo que se mira todos los días.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. LAS PERSONAS
-- ---------------------------------------------------------------------
-- Los choferes, para las licencias. Separado de usuarios: un chofer no
-- entra a la app, y un usuario de la app no maneja necesariamente.
-- ---------------------------------------------------------------------
create table if not exists personas (
  id        bigint generated always as identity primary key,
  nombre    text not null,
  documento text unique,
  legajo    text,
  sucursal  text,
  telefono  text,
  -- La unidad que maneja hoy. En la planilla el chofer y el dominio van en
  -- la misma fila: la VTV y el matafuego son de la unidad, las licencias
  -- del chofer, pero se miran juntos porque salen juntos a la ruta.
  unidad_id bigint references unidades(id),
  activa    boolean not null default true,
  creado    timestamptz not null default now()
);

create index if not exists ix_personas_activa on personas(activa, nombre);

-- ---------------------------------------------------------------------
-- 2. QUÉ COSAS VENCEN
-- ---------------------------------------------------------------------
-- ambito dice a qué se le cuelga el vencimiento:
--   unidad  -> VTV, matafuego, seguro, RUTA
--   persona -> licencia, LiNTI, psicofísico
--   empresa -> habilitaciones que no son de una unidad ni de alguien
-- aviso_dias es con cuánta anticipación se pone en amarillo.
-- ---------------------------------------------------------------------
create table if not exists tipos_vencimiento (
  id          bigint generated always as identity primary key,
  nombre      text not null unique,
  ambito      text not null check (ambito in ('unidad','persona','empresa')),
  aviso_dias  int  not null default 30 check (aviso_dias >= 0),
  meses       int,                       -- cada cuánto se renueva, si es fijo
  varios      boolean not null default false,  -- ¿puede haber más de uno? (matafuegos)
  orden       int  not null default 100,
  activo      boolean not null default true
);

-- Los cuatro que se controlan hoy, con los nombres de la planilla. Los
-- demás quedan cargados pero apagados: si alguna vez se empiezan a seguir,
-- se prenden con un update y aparecen solos en la pantalla.
insert into tipos_vencimiento (nombre, ambito, aviso_dias, meses, varios, orden, activo) values
  ('VTV',                    'unidad',  30, 12, false, 10, true),
  ('Matafuegos',             'unidad',  30, 12, false, 20, true),
  ('Licencia municipal',     'persona', 30, null, false, 30, true),
  ('Licencia profesional',   'persona', 30, null, false, 40, true),
  ('Seguro',                 'unidad',  30, 12, false, 50, false),
  ('RUTA',                   'unidad',  45, 12, false, 60, false),
  ('LiNTI',                  'persona', 60, 12, false, 70, false),
  ('Psicofísico',            'persona', 45, 12, false, 80, false)
on conflict (nombre) do nothing;

-- ---------------------------------------------------------------------
-- 3. LOS VENCIMIENTOS
-- ---------------------------------------------------------------------
create table if not exists vencimientos (
  id           bigint generated always as identity primary key,
  tipo_id      bigint not null references tipos_vencimiento(id),
  unidad_id    bigint references unidades(id),
  persona_id   bigint references personas(id),
  identificador text,          -- nº de oblea, de licencia, del matafuego
  detalle      text,           -- clase de licencia, kilos del matafuego, aseguradora
  desde        date,
  vence        date not null,
  costo        numeric,
  donde        text,           -- taller, planta de VTV, aseguradora
  observaciones text,
  usuario      text,
  creado       timestamptz not null default now(),

  -- Un vencimiento le pertenece a una unidad o a una persona, según el
  -- ámbito de su tipo, y nunca a las dos. La verificación fina la hace
  -- el disparador de abajo, que es el que puede mirar el tipo.
  constraint ck_vencimiento_sujeto check (
    (unidad_id is not null and persona_id is null) or
    (unidad_id is null and persona_id is not null) or
    (unidad_id is null and persona_id is null)
  )
);

create index if not exists ix_venc_unidad  on vencimientos(unidad_id, tipo_id, vence desc);
create index if not exists ix_venc_persona on vencimientos(persona_id, tipo_id, vence desc);
create index if not exists ix_venc_fecha   on vencimientos(vence);

-- El sujeto tiene que coincidir con el ámbito del tipo: una VTV sin
-- unidad, o una licencia sin persona, es un dato que después no se
-- puede mostrar en ningún lado.
create or replace function _vencimiento_coherente() returns trigger as $$
declare
  ambito text;
  nombre text;
begin
  select t.ambito, t.nombre into ambito, nombre
    from tipos_vencimiento t where t.id = new.tipo_id;

  if ambito = 'unidad' and new.unidad_id is null then
    raise exception '% es de una unidad: falta la patente.', nombre;
  end if;
  if ambito = 'persona' and new.persona_id is null then
    raise exception '% es de una persona: falta quién.', nombre;
  end if;
  if ambito = 'empresa' and (new.unidad_id is not null or new.persona_id is not null) then
    raise exception '% es de la empresa: no lleva unidad ni persona.', nombre;
  end if;

  if new.desde is not null and new.desde > new.vence then
    raise exception 'La fecha de emisión no puede ser posterior al vencimiento.';
  end if;

  return new;
end $$ language plpgsql;

drop trigger if exists tg_vencimiento_coherente on vencimientos;
create trigger tg_vencimiento_coherente
  before insert or update on vencimientos
  for each row execute function _vencimiento_coherente();

-- ---------------------------------------------------------------------
-- 4. LO QUE SE MIRA TODOS LOS DÍAS
-- ---------------------------------------------------------------------
-- La última renovación de cada cosa, con los días que faltan y el estado.
-- Para los tipos con 'varios' (los matafuegos) la última es por cada
-- identificador, porque un camión lleva más de uno y cada uno vence
-- por su cuenta.
-- ---------------------------------------------------------------------
drop view if exists v_vencimientos_hoy;
create view v_vencimientos_hoy as
select distinct on (v.tipo_id, v.unidad_id, v.persona_id, clave.ident)
       v.id, v.tipo_id, t.nombre as tipo, t.ambito, t.aviso_dias,
       v.unidad_id, u.patente, u.interno, u.sucursal as sucursal_unidad,
       v.persona_id, p.nombre as persona, p.sucursal as sucursal_persona,
       pu.patente as patente_persona,
       v.identificador, v.detalle, v.desde, v.vence, v.donde,
       v.costo, v.observaciones,
       (v.vence - current_date) as dias,
       case
         when v.vence <  current_date then 'vencido'
         when v.vence <= current_date + t.aviso_dias then 'por_vencer'
         else 'vigente'
       end as estado,
       t.orden
from vencimientos v
join tipos_vencimiento t on t.id = v.tipo_id
left join unidades u  on u.id = v.unidad_id
left join personas p  on p.id = v.persona_id
left join unidades pu on pu.id = p.unidad_id
cross join lateral (
  -- Sin 'varios' todas las renovaciones son de la misma cosa, así que la
  -- clave es una sola; con 'varios' cada matafuego va por separado.
  select case when t.varios then coalesce(v.identificador, v.id::text) else '' end as ident
) clave
where t.activo
  and (v.unidad_id is null or u.activa)
  and (v.persona_id is null or p.activa)
order by v.tipo_id, v.unidad_id, v.persona_id, clave.ident, v.vence desc, v.id desc;

-- ---------------------------------------------------------------------
-- LO QUE HAY QUE HACER
-- ---------------------------------------------------------------------
-- Solo lo vencido y lo que está por vencer, lo urgente primero. Es lo
-- que va arriba de la pantalla y lo que sale en el aviso.
-- ---------------------------------------------------------------------
drop view if exists v_vencimientos_pendientes;
create view v_vencimientos_pendientes as
select * from v_vencimientos_hoy
where estado in ('vencido','por_vencer')
order by dias, orden, tipo, patente, persona;

-- ---------------------------------------------------------------------
-- LO QUE FALTA CARGAR
-- ---------------------------------------------------------------------
-- Las unidades activas a las que les falta un vencimiento que debería
-- tener. Un dato que no está no se ve en ninguna lista, y esa es
-- justamente la forma en que se pasan de largo.
-- ---------------------------------------------------------------------
drop view if exists v_vencimientos_faltantes;
create view v_vencimientos_faltantes as
select t.id as tipo_id, t.nombre as tipo, t.ambito,
       u.id as unidad_id, u.patente, u.interno,
       null::bigint as persona_id, null::text as persona,
       u.sucursal
from unidades u
cross join tipos_vencimiento t
where u.activa and t.activo and t.ambito = 'unidad' and not t.varios
  and not exists (select 1 from vencimientos v
                   where v.unidad_id = u.id and v.tipo_id = t.id)
union all
select t.id, t.nombre, t.ambito,
       null::bigint, null::text, null::text,
       p.id, p.nombre,
       p.sucursal
from personas p
cross join tipos_vencimiento t
where p.activa and t.activo and t.ambito = 'persona' and not t.varios
  and not exists (select 1 from vencimientos v
                   where v.persona_id = p.id and v.tipo_id = t.id);

alter table personas          enable row level security;
alter table tipos_vencimiento enable row level security;
alter table vencimientos      enable row level security;
