-- Ejecutar después de 06, 15, 21, 26 y 27. No borra registros.
BEGIN;
alter table vencimientos add column if not exists aviso_fecha date;
do $$ begin
 alter table vencimientos add constraint aviso_antes_vencimiento check (aviso_fecha is null or aviso_fecha <= vence);
exception when duplicate_object then null; end $$;
drop view if exists v_vencimientos_faltantes;
drop view if exists v_vencimientos_pendientes;
drop view if exists v_vencimientos_hoy;

create view v_vencimientos_hoy as
select distinct on (v.tipo_id, v.unidad_id, v.persona_id, clave.ident)
       v.id, v.tipo_id, t.nombre as tipo, t.ambito, t.aviso_dias,
       v.unidad_id, u.patente, u.interno, u.sucursal as sucursal_unidad,
       v.persona_id, p.nombre as persona, p.sucursal as sucursal_persona,
       pu.patente as patente_persona,
       v.identificador, v.detalle, v.desde, v.vence, v.donde,
       v.costo, v.observaciones, v.aviso_fecha,
       (v.vence - current_date) as dias,
       case
         when v.vence <  current_date then 'vencido'
         when current_date >= coalesce(v.aviso_fecha, v.vence - t.aviso_dias) then 'por_vencer'
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


create table if not exists reportes_chofer (
 id uuid primary key,
 usuario_id bigint not null references usuarios(id),
 unidad_id bigint not null references unidades(id),
 descripcion text not null check(length(descripcion) between 1 and 2000),
 urgencia text not null check(urgencia in ('PUEDE_ESPERAR','OPERA_CON_RIESGO','UNIDAD_PARADA')),
 ocurrido_en timestamptz not null,
 recibido_en timestamptz not null default now(),
 estado text not null default 'PENDIENTE' check(estado in ('PENDIENTE','DESESTIMADA','ORDEN_CREADA')),
 motivo text,
 orden_id bigint unique references ordenes_trabajo(id),
 resuelto_por bigint references usuarios(id),
 resuelto_en timestamptz,
 check(estado <> 'DESESTIMADA' or (motivo is not null and length(trim(motivo)) > 0)),
 check((estado = 'ORDEN_CREADA') = (orden_id is not null))
);
create table if not exists reporte_fotos (
 reporte_id uuid not null references reportes_chofer(id),
 posicion integer not null check(posicion between 0 and 2),
 mime text not null check(mime in ('image/jpeg','image/png','image/webp')),
 contenido bytea not null check(octet_length(contenido) <= 2097152),
 primary key(reporte_id,posicion)
);
alter table reportes_chofer enable row level security;
alter table reporte_fotos enable row level security;
create index if not exists reportes_chofer_estado on reportes_chofer(estado, recibido_en);
insert into rol_modulos(rol_codigo, modulo)
select codigo, 'choferes' from roles where codigo='chofer'
on conflict do nothing;
COMMIT;
