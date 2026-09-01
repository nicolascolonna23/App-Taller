-- =====================================================================
-- GOMERÍA — vistas y seguridad
-- Se corre después de 01_esquema.sql, en el mismo SQL Editor.
-- =====================================================================

-- ---------------------------------------------------------------------
-- CÓMO ESTÁ ARMADA CADA UNIDAD HOY
-- ---------------------------------------------------------------------
-- Una fila por posición de cada unidad, con la cubierta que tiene puesta
-- (o vacía si esa posición está sin cubierta). Es la vista que dibuja el
-- mapa en pantalla.
create or replace view v_mapa_unidad as
select
  u.id                as unidad_id,
  u.patente,
  u.interno,
  u.sucursal,
  p.id                as posicion_id,
  p.codigo            as posicion,
  p.eje,
  p.lado,
  p.montaje,
  p.es_auxilio,
  p.orden,
  c.id                as cubierta_id,
  c.codigo            as cubierta,
  c.marca,
  c.medida,
  c.remanente_mm,
  c.recapados,
  m.desde             as montada_desde,
  m.km_unidad_montaje,
  case when c.id is null then 'vacía' else 'ocupada' end as estado_posicion
from unidades u
join configuracion_posiciones p on p.configuracion_id = u.configuracion_id
left join montajes  m on m.unidad_id = u.id and m.posicion_id = p.id and m.hasta is null
left join cubiertas c on c.id = m.cubierta_id;

comment on view v_mapa_unidad is
  'El mapa de cada unidad con lo que tiene puesto ahora. Una fila por posición.';

-- ---------------------------------------------------------------------
-- LA VIDA DE CADA CUBIERTA
-- ---------------------------------------------------------------------
create or replace view v_historial_cubierta as
select
  mv.cubierta_id,
  c.codigo         as cubierta,
  mv.fecha,
  mv.tipo,
  u.patente,
  po.codigo        as desde_posicion,
  pd.codigo        as hasta_posicion,
  mv.km_unidad,
  mv.remanente_mm,
  mv.usuario,
  mv.nota,
  pa.texto         as texto_original
from movimientos mv
join cubiertas c on c.id = mv.cubierta_id
left join unidades u  on u.id  = mv.unidad_id
left join configuracion_posiciones po on po.id = mv.posicion_origen_id
left join configuracion_posiciones pd on pd.id = mv.posicion_destino_id
left join partes pa on pa.id = mv.parte_id
order by mv.fecha desc;

-- ---------------------------------------------------------------------
-- CUBIERTAS DISPONIBLES PARA MONTAR
-- ---------------------------------------------------------------------
create or replace view v_stock as
select c.*
from cubiertas c
where c.estado = 'stock'
  and not exists (select 1 from montajes m where m.cubierta_id = c.id and m.hasta is null);

-- ---------------------------------------------------------------------
-- POSICIONES VACÍAS (lo que falta montar)
-- ---------------------------------------------------------------------
create or replace view v_posiciones_vacias as
select unidad_id, patente, posicion, eje, lado, montaje, es_auxilio
from v_mapa_unidad
where cubierta_id is null;

-- =====================================================================
-- SEGURIDAD
-- ---------------------------------------------------------------------
-- Supabase expone las tablas por internet a través de su API. Con RLS
-- prendido y sin políticas, nadie que tenga la clave pública (anon) puede
-- leer ni escribir nada. El servidor de la app usa la clave service_role,
-- que pasa por encima de RLS: por eso esa clave nunca sale del servidor.
-- =====================================================================
alter table configuraciones            enable row level security;
alter table configuracion_posiciones   enable row level security;
alter table unidades                   enable row level security;
alter table cubiertas                  enable row level security;
alter table montajes                   enable row level security;
alter table partes                     enable row level security;
alter table movimientos                enable row level security;
alter table mediciones                 enable row level security;
