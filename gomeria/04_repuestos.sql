-- Inventario central de repuestos.

create table if not exists repuestos_articulos (
  id              bigint generated always as identity primary key,
  codigo          text not null unique,
  descripcion     text not null,
  rubro           text not null default 'Sin rubro',
  codigo_interno  text,
  stock_minimo    integer not null default 0 check (stock_minimo >= 0),
  activo          boolean not null default true,
  creado_en       timestamptz not null default now(),
  actualizado_en  timestamptz not null default now()
);

create table if not exists repuestos_movimientos (
  id                  bigint generated always as identity primary key,
  articulo_id         bigint not null references repuestos_articulos(id),
  fecha               date not null,
  tipo                text not null check (tipo in ('Entrada', 'Salida', 'Ajuste')),
  cantidad            integer not null check (cantidad <> 0),
  patente             text,
  observaciones       text,
  usuario_id          bigint references usuarios(id),
  clave_importacion   text unique,
  creado_en           timestamptz not null default now(),
  check (tipo = 'Ajuste' or cantidad > 0)
);

create index if not exists idx_repuestos_movimientos_articulo_fecha
  on repuestos_movimientos (articulo_id, fecha desc, id desc);

create or replace view v_repuestos_stock as
select
  a.*,
  coalesce(sum(case when m.tipo = 'Salida' then -abs(m.cantidad)
                    else m.cantidad end), 0)::integer as stock_actual,
  case
    when not a.activo then 'Dado de baja'
    when coalesce(sum(case when m.tipo='Salida' then -abs(m.cantidad) else m.cantidad end),0) < 0 then 'REVISAR'
    when coalesce(sum(case when m.tipo='Salida' then -abs(m.cantidad) else m.cantidad end),0) = 0 then 'SIN STOCK'
    when a.stock_minimo > 0 and coalesce(sum(case when m.tipo='Salida' then -abs(m.cantidad) else m.cantidad end),0) <= a.stock_minimo then 'REPONER'
    else 'OK'
  end as estado
from repuestos_articulos a
left join repuestos_movimientos m on m.articulo_id = a.id
group by a.id;
