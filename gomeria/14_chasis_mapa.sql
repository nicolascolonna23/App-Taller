-- =====================================================================
-- EL MAPA DE LOS CAMIONES DE REPARTO
-- ---------------------------------------------------------------------
-- Se pega entero en Supabase → SQL Editor → New query → Run.
-- Se puede correr más de una vez sin romper nada: no pisa ningún mapa que
-- ya esté cargado.
--
-- El chasis con caja lleva seis gomas: un eje simple adelante, que es el
-- que dobla, y uno dual atrás, que es el que carga. Es el mismo armado que
-- un tractor 4x2 aunque el camión sea otra cosa.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. EL ARMADO
-- ---------------------------------------------------------------------
-- La nomenclatura es la de siempre: una letra por eje, de adelante hacia
-- atrás. S = rueda simple, D = rodado dual.
insert into configuraciones (nombre, descripcion) values
  ('S-D', 'Camión de dos ejes: simple adelante y dual atrás. 6 cubiertas.')
on conflict (nombre) do nothing;

insert into configuracion_posiciones
       (configuracion_id, codigo, eje, lado, montaje, orden)
select c.id, v.codigo, v.eje, v.lado, v.montaje, v.orden
from configuraciones c
join (values
  ('1I',  1, 'I', 'unica',    1),
  ('1D',  1, 'D', 'unica',    2),
  ('2IE', 2, 'I', 'exterior', 3),
  ('2II', 2, 'I', 'interior', 4),
  ('2DI', 2, 'D', 'interior', 5),
  ('2DE', 2, 'D', 'exterior', 6)
) as v(codigo, eje, lado, montaje, orden) on true
where c.nombre = 'S-D'
on conflict (configuracion_id, codigo) do nothing;

-- ---------------------------------------------------------------------
-- 2. LAS UNIDADES
-- ---------------------------------------------------------------------
-- Las cinco que faltaban. Se les pone solo si todavía no tienen armado.
update unidades
   set configuracion_id = (select id from configuraciones where nombre = 'S-D'),
       actualizado = now()
 where configuracion_id is null
   and replace(replace(upper(patente), ' ', ''), '-', '') in
       ('AA823XJ', 'AG070OR', 'AG224IE', 'KOF186', 'JEA499');

-- ---------------------------------------------------------------------
-- 3. LAS OTRAS TRECE, SI CORRESPONDE
-- ---------------------------------------------------------------------
-- Son el mismo camión: cabina adelante, caja atrás, dual atrás. Las tres
-- L1614, la L1620, la L1318, la 608 D, la 272-710, la Accelo, los dos
-- Cargo, la P 94DB, la HD 78 y la DFM.
--
-- No se les pone solo porque nadie lo pidió. Para ponérselo, sacale los
-- dos guiones a la línea de abajo y volvé a correr todo.
--
-- update unidades
--    set configuracion_id = (select id from configuraciones where nombre = 'S-D'),
--        actualizado = now()
--  where configuracion_id is null and tipo = 'vehiculo'
--    and upper(coalesce(marca,'') || ' ' || coalesce(modelo,'')) ~
--        'L1614|L-1620|L 1318|608 D|272-710|ACCELO|CARGO|P 94|HD 78|1063';

-- ---------------------------------------------------------------------
-- 4. CÓMO QUEDÓ
-- ---------------------------------------------------------------------
select u.patente, u.marca, u.modelo,
       coalesce(c.nombre, 'SIN ARMADO') as armado,
       (select count(*) from configuracion_posiciones p
         where p.configuracion_id = u.configuracion_id
           and not p.es_auxilio) as gomas
  from unidades u
  left join configuraciones c on c.id = u.configuracion_id
 where replace(replace(upper(u.patente), ' ', ''), '-', '') in
       ('AA823XJ', 'AG070OR', 'AG224IE', 'KOF186', 'JEA499')
 order by u.patente;
