-- =====================================================================
-- USUARIOS, ROLES Y MÓDULOS
-- ---------------------------------------------------------------------
-- Hasta acá los roles eran tres y estaban escritos en el código:
-- operario, encargado y admin. Alcanzaba cuando el sistema era gomería.
-- Con flota, combustible, órdenes y solicitudes de orden de compra ya no:
-- el responsable de una sucursal no es un operario de taller, y no tiene
-- por qué ver —ni que le pregunten por— el stock del depósito.
--
-- Desde acá el rol es una fila que se edita desde la pantalla:
--
--   roles         quién es, qué puede hacer y qué módulos abre.
--   rol_modulos   un renglón por módulo habilitado. Es la lista blanca:
--                 lo que no está, no se abre.
--
-- Dos permisos que no son módulos sino nivel, porque atraviesan todo:
--
--   gestiona    aprueba, cierra y corrige: el taller y mantenimiento.
--   administra  usuarios, roles, borrar y reabrir. El dueño del sistema.
--
-- Y uno que ata el rol a la red:
--
--   pide_sucursal  el usuario de ese rol tiene que tener sucursal. Es lo
--                  que hace que un responsable de boca pueda pedir: la
--                  solicitud se numera según quién la pide.
--
-- Se pega entero en Supabase → SQL Editor → Run. Se puede correr las
-- veces que haga falta: no borra nada y no toca los roles que ya se
-- hayan editado a mano.
--
-- ANTES tiene que estar corrido 03_usuarios.sql. Si además está corrido
-- 26_solicitudes.sql, el rol de sucursal nace con su módulo.
-- =====================================================================

create table if not exists roles (
  codigo        text primary key,          -- 'admin', 'sucursal', 'gomeria'…
  nombre        text not null,             -- como se lee en la pantalla
  descripcion   text,
  gestiona      boolean not null default false,
  administra    boolean not null default false,
  pide_sucursal boolean not null default false,
  de_sistema    boolean not null default false,  -- no se puede borrar
  activo        boolean not null default true,
  orden         integer not null default 0,
  creado_en     timestamptz not null default now()
);

comment on table roles is
  'Los roles del sistema. Los de sistema no se borran: dejarían gente afuera.';


-- Un renglón por módulo habilitado. Lista blanca: lo que no está, no se
-- abre, y el servidor lo revisa en cada pedido —no alcanza con esconder
-- el botón en la pantalla.
create table if not exists rol_modulos (
  rol_codigo text not null references roles(codigo) on delete cascade,
  modulo     text not null,
  primary key (rol_codigo, modulo)
);

create index if not exists ix_rol_modulos on rol_modulos (rol_codigo);


-- ---------------------------------------------------------------------
-- LOS CUATRO ROLES CON LOS QUE ARRANCA
-- ---------------------------------------------------------------------
-- Los tres de siempre, más el de sucursal, que es el que faltaba.
-- Se pueden editar desde la pantalla y se les pueden agregar otros; estos
-- cuatro no se borran porque hay gente colgando de ellos.
insert into roles (codigo, nombre, descripcion, gestiona, administra,
                   pide_sucursal, de_sistema, orden) values
  ('admin',     'Administrador',
   'Todo el sistema, más usuarios y roles.', true,  true,  false, true, 1),
  ('encargado', 'Encargado de taller',
   'Aprueba, cierra y corrige. No administra usuarios.', true, false, false, true, 2),
  ('operario',  'Operario',
   'Carga lo que hace: partes, repuestos y órdenes.', false, false, false, true, 3),
  ('sucursal',  'Responsable de sucursal',
   'Pide, sigue y rinde las solicitudes de su boca.', false, false, true, true, 4)
on conflict (codigo) do nothing;


-- Los módulos de cada uno. `on conflict do nothing` respeta lo que se
-- haya cambiado desde la pantalla: volver a correr el script no le
-- devuelve a un rol un módulo que alguien le sacó a propósito… salvo que
-- ese renglón no exista, que es la primera vez.
insert into rol_modulos (rol_codigo, modulo)
select 'admin', m from unnest(array[
  'flota','unidades','gomeria','repuestos','ordenes','solicitudes',
  'combustible','alertas','vencimientos','asistente','usuarios']) as m
on conflict do nothing;

insert into rol_modulos (rol_codigo, modulo)
select 'encargado', m from unnest(array[
  'flota','unidades','gomeria','repuestos','ordenes','solicitudes',
  'combustible','alertas','vencimientos','asistente']) as m
on conflict do nothing;

-- El operario queda con lo que ya usaba: nadie pierde de un día para el
-- otro una pantalla que venía abriendo. Lo que no tiene es lo que nunca
-- fue suyo: la bandeja de solicitudes y la administración de usuarios.
insert into rol_modulos (rol_codigo, modulo)
select 'operario', m from unnest(array[
  'flota','unidades','gomeria','repuestos','ordenes',
  'combustible','alertas','vencimientos','asistente']) as m
on conflict do nothing;

-- La sucursal ve lo suyo: pedir, seguir la unidad y mirar lo que vence.
-- No el depósito ni el tablero del taller.
insert into rol_modulos (rol_codigo, modulo)
select 'sucursal', m from unnest(array[
  'solicitudes','unidades','alertas','vencimientos']) as m
on conflict do nothing;


-- ---------------------------------------------------------------------
-- EL USUARIO PASA A APUNTAR AL ROL
-- ---------------------------------------------------------------------
-- Antes el rol era un texto con tres valores permitidos. Ahora es una
-- fila de `roles`: por eso se saca el check y se pone la clave foránea.
-- Los usuarios que ya estaban no se tocan: sus tres roles son los tres
-- que acaban de crearse con el mismo código.
alter table usuarios drop constraint if exists usuarios_rol_check;

alter table usuarios drop constraint if exists usuarios_rol_fkey;
alter table usuarios
  add constraint usuarios_rol_fkey foreign key (rol) references roles(codigo);

-- La sucursal del usuario la agregó 26_solicitudes.sql. Si esta base
-- todavía no lo corrió, la columna se crea igual: el rol de sucursal la
-- necesita para saber quién pide, y sin ella la pantalla de usuarios no
-- podría asignarla.
alter table usuarios
  add column if not exists sucursal_codigo char(3);

comment on column usuarios.rol is
  'Código del rol. La tabla roles dice qué puede hacer y qué módulos abre.';
