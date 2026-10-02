-- =====================================================================
-- EL CIRCUITO DE RECAPADO
-- =====================================================================
-- Todas las semanas el gomero se lleva un lote de gomas a recapar y trae
-- el de la semana anterior. Hasta ahora eso se cargaba de a una: se le
-- cambiaba el estado a 'recapado' a cada cubierta al salir y se registraba
-- el recapado de cada una al volver. Funcionaba, pero las dos mitades no
-- se hablaban, y por eso no se podía contestar la pregunta que importa:
--
--     si se llevó doce y trajo diez, ¿cuáles son las dos que faltan?
--
-- Eso es plata parada en lo de un tercero y no se notaba. Con el envío
-- como entidad, salida y vuelta quedan emparejadas y lo que no volvió se
-- ve solo.
--
-- La vida de la cubierta NO se cierra al salir: la cierra desgaste.recapar
-- cuando vuelve, junto con abrir la nueva. Acá solo se mueve el estado.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. EL TOPE DE RECAPADOS
-- ---------------------------------------------------------------------
-- Una carcasa aguanta tres recapados. El cuarto es tirar plata en una
-- goma que se va a abrir. Va en parametros y no en el código porque es
-- una decisión de la empresa, no del programa.
alter table parametros
  add column if not exists recapados_maximo integer not null default 3
  check (recapados_maximo between 1 and 10);

comment on column parametros.recapados_maximo is
  'Cuántas veces se puede recapar una carcasa. Al armar el remito, la que '
  'llegó al tope no se puede enviar.';

-- ---------------------------------------------------------------------
-- 2. EL NUMERADOR
-- ---------------------------------------------------------------------
-- Una sola fila que se bloquea para numerar, igual que el contador de
-- solicitudes. No se usa max(numero)+1: sin bloqueo, dos cargas
-- simultáneas leen el mismo máximo y escriben el mismo número.
create table if not exists recapado_contador (
  unica   boolean primary key default true check (unica),
  ultimo  integer not null default 0 check (ultimo >= 0)
);
insert into recapado_contador (unica) values (true) on conflict do nothing;

-- ---------------------------------------------------------------------
-- 3. EL ENVÍO
-- ---------------------------------------------------------------------
-- El id es el número que se escribe en el remito: REC-00001. Es texto y
-- es la clave, así el papel y la base dicen lo mismo sin traducción.
--
-- El correlativo es inmutable: el número de un envío anulado no se
-- reutiliza. Por eso no hay borrado de envíos en ningún lado.
create table if not exists recapado_envios (
  id            text primary key,              -- 'REC-00001'
  numero        integer not null unique check (numero > 0),
  recapador     text not null,
  fecha         date not null default current_date,
  estado        text not null default 'abierto'
                check (estado in ('abierto', 'cerrado', 'anulado')),
  factura       text,                          -- la del recapador, al volver
  fecha_vuelta  date,
  nota          text,
  usuario       text,
  creado        timestamptz not null default now(),
  -- Un envío cerrado tiene fecha de vuelta: es lo que lo cierra.
  check (estado <> 'cerrado' or fecha_vuelta is not null)
);

create index if not exists ix_recapado_abiertos
  on recapado_envios (fecha desc) where estado = 'abierto';

-- ---------------------------------------------------------------------
-- 4. QUÉ SE MANDÓ EN CADA ENVÍO
-- ---------------------------------------------------------------------
-- Una fila por goma. El estado es de la goma dentro de este envío, no del
-- envío: de doce que salieron pueden volver diez, una la rechazan y otra
-- no aparece.
create table if not exists recapado_renglones (
  id                   bigint generated always as identity primary key,
  envio_id             text   not null references recapado_envios(id),
  cubierta_id          bigint not null references cubiertas(id),
  estado               text   not null default 'enviada'
                       check (estado in ('enviada', 'volvio', 'rechazada')),
  -- Con cuánto dibujo se fue. Sirve para discutir con el recapador
  -- cuando dice que la carcasa no servía.
  remanente_salida_mm  numeric,
  recapados_al_salir   integer,
  costo                numeric check (costo >= 0),
  fecha_vuelta         date,
  motivo               text,      -- por qué la rechazaron
  unique (envio_id, cubierta_id)
);

create index if not exists ix_renglon_envio on recapado_renglones (envio_id);
create index if not exists ix_renglon_cubierta on recapado_renglones (cubierta_id);

-- Una goma no puede estar en dos envíos a la vez. Es física: está en un
-- solo lugar. Sin esto, cargar dos veces el mismo remito la duplicaría y
-- después volvería dos veces.
create unique index if not exists ux_renglon_afuera
  on recapado_renglones (cubierta_id) where estado = 'enviada';

-- ---------------------------------------------------------------------
-- 5. QUÉ HAY AFUERA
-- ---------------------------------------------------------------------
-- La pregunta que no se podía contestar. Con los días: una goma que hace
-- un mes que está en lo del recapador es una goma que hay que reclamar.
-- ---------------------------------------------------------------------
drop view if exists v_recapado_afuera;
create view v_recapado_afuera as
select r.id as renglon_id, r.envio_id, e.numero, e.recapador, e.fecha as salio,
       (current_date - e.fecha) as dias_afuera,
       c.id as cubierta_id, c.codigo, c.marca, c.medida,
       c.codigo_provisorio, r.remanente_salida_mm, r.recapados_al_salir
from recapado_renglones r
join recapado_envios e on e.id = r.envio_id
join cubiertas c on c.id = r.cubierta_id
where r.estado = 'enviada' and e.estado = 'abierto'
order by e.fecha, c.codigo;

comment on view v_recapado_afuera is
  'Las gomas que estan en lo del recapador y todavia no volvieron.';

-- ---------------------------------------------------------------------
-- 6. LOS ENVÍOS, CON SU CUENTA
-- ---------------------------------------------------------------------
drop view if exists v_recapado_envios;
create view v_recapado_envios as
select e.*,
       count(r.id)::int                                            as enviadas,
       count(r.id) filter (where r.estado = 'volvio')::int          as volvieron,
       count(r.id) filter (where r.estado = 'rechazada')::int       as rechazadas,
       count(r.id) filter (where r.estado = 'enviada')::int         as pendientes,
       sum(r.costo) filter (where r.estado = 'volvio')              as costo_total
from recapado_envios e
left join recapado_renglones r on r.envio_id = e.id
group by e.id
order by e.numero desc;


-- ---------------------------------------------------------------------
-- 7. SEGURIDAD: igual que el resto, nadie entra con la clave pública.
-- ---------------------------------------------------------------------
-- Sin esto las tres tablas quedan expuestas por PostgREST: cualquiera con
-- la clave anónima lee los envíos y, peor, escribe renglones. La app no
-- entra por ahí, así que activarlo no le cambia nada; lo que cierra es la
-- puerta de al lado.
alter table recapado_contador   enable row level security;
alter table recapado_envios     enable row level security;
alter table recapado_renglones  enable row level security;
