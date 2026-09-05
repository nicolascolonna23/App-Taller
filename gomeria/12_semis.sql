-- =====================================================================
-- LOS SEMIRREMOLQUES — armado y mapa de cubiertas
-- ---------------------------------------------------------------------
-- Se pega entero en Supabase → SQL Editor → New query → Run.
-- Se puede correr más de una vez sin romper nada: no pisa ningún mapa
-- que ya esté cargado.
--
-- Los semis estaban en el maestro pero sin armado, así que no tenían
-- dónde anotar una cubierta: la gomería del semi quedaba afuera del
-- sistema. Acá se cargan los dos armados que usa la flota y se le pone a
-- cada semi el que corresponde.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. LOS ARMADOS
-- ---------------------------------------------------------------------
-- La nomenclatura es la misma que ya se usa en los tractores: una letra
-- por eje, de adelante hacia atrás. S = rueda simple, D = rodado dual.
-- Un semi no tiene eje direccional, así que son todos duales.
insert into configuraciones (nombre, descripcion) values
  ('D-D-D', 'Semirremolque de tres ejes, todos duales. 12 cubiertas.'),
  ('D-D',   'Semirremolque de dos ejes, los dos duales. 8 cubiertas.')
on conflict (nombre) do nothing;

-- Las posiciones de cada armado. El código es el que canta el gomero:
-- el número de eje, el lado, y si es la interior o la exterior del dual.
--   3IE = tercer eje, izquierda, exterior
insert into configuracion_posiciones
       (configuracion_id, codigo, eje, lado, montaje, orden)
select c.id, v.codigo, v.eje, v.lado, v.montaje, v.orden
from configuraciones c
join (values
  -- D-D-D: doce cubiertas, cuatro por eje.
  ('D-D-D', '1IE', 1, 'I', 'exterior',  1),
  ('D-D-D', '1II', 1, 'I', 'interior',  2),
  ('D-D-D', '1DI', 1, 'D', 'interior',  3),
  ('D-D-D', '1DE', 1, 'D', 'exterior',  4),
  ('D-D-D', '2IE', 2, 'I', 'exterior',  5),
  ('D-D-D', '2II', 2, 'I', 'interior',  6),
  ('D-D-D', '2DI', 2, 'D', 'interior',  7),
  ('D-D-D', '2DE', 2, 'D', 'exterior',  8),
  ('D-D-D', '3IE', 3, 'I', 'exterior',  9),
  ('D-D-D', '3II', 3, 'I', 'interior', 10),
  ('D-D-D', '3DI', 3, 'D', 'interior', 11),
  ('D-D-D', '3DE', 3, 'D', 'exterior', 12),
  -- D-D: ocho.
  ('D-D',   '1IE', 1, 'I', 'exterior',  1),
  ('D-D',   '1II', 1, 'I', 'interior',  2),
  ('D-D',   '1DI', 1, 'D', 'interior',  3),
  ('D-D',   '1DE', 1, 'D', 'exterior',  4),
  ('D-D',   '2IE', 2, 'I', 'exterior',  5),
  ('D-D',   '2II', 2, 'I', 'interior',  6),
  ('D-D',   '2DI', 2, 'D', 'interior',  7),
  ('D-D',   '2DE', 2, 'D', 'exterior',  8)
) as v(armado, codigo, eje, lado, montaje, orden) on v.armado = c.nombre
on conflict (configuracion_id, codigo) do nothing;

-- ---------------------------------------------------------------------
-- 2. EL ARMADO DE CADA SEMI
-- ---------------------------------------------------------------------
-- Tres ejes es lo que lleva el semi de larga distancia, que es lo que
-- tiene la flota. Se le pone a los que todavía no tienen armado; al que
-- ya tenga uno cargado no se lo toca.
--
-- Si alguno resulta ser de dos ejes, se cambia desde la ficha de la
-- unidad en Flota: el selector de armado ya está y muestra los dos.
update unidades
   set configuracion_id = (select id from configuraciones where nombre = 'D-D-D'),
       actualizado = now()
 where configuracion_id is null
   and upper(replace(coalesce(uso, ''), ' ', '')) like 'SEMI%';

-- ---------------------------------------------------------------------
-- 3. CÓMO QUEDÓ
-- ---------------------------------------------------------------------
-- Para mirar de una que ninguno quedó sin mapa.
select coalesce(c.nombre, 'SIN ARMADO') as armado,
       count(*) as semis,
       (select count(*) from configuracion_posiciones p
         where p.configuracion_id = u.configuracion_id
           and not p.es_auxilio) as gomas
  from unidades u
  left join configuraciones c on c.id = u.configuracion_id
 where upper(replace(coalesce(u.uso, ''), ' ', '')) like 'SEMI%'
 group by c.nombre, u.configuracion_id
 order by 1;
