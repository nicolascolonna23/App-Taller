-- =====================================================================
-- EL PLAN QUE LE TOCA A CADA PATENTE  (carga masiva desde el Excel)
-- ---------------------------------------------------------------------
-- Sale de «tipo_service_por_patente.xlsx», que está al lado de este
-- archivo: 51 patentes con el tipo de service que les corresponde. Lo
-- mismo que hace la pantalla de Parametrización con «Carga masiva desde
-- Excel», pero de una sola pegada y sin depender de que los cuatro planes
-- ya existan: si falta alguno, lo crea.
--
-- Se pega entero en Supabase → SQL Editor → New query → Run. Va después
-- de 22_planes_mantenimiento.sql y 23_planes_por_unidad.sql.
--
-- Se puede correr las veces que haga falta: no borra ni pisa nada. Suma
-- los planes que dice el Excel a los que cada unidad ya tuviera. Si una
-- patente tiene que dejar de tener un plan, eso se saca a mano desde la
-- ficha de la unidad: un script de carga no adivina una baja.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. LOS CUATRO PLANES        ←←← ACÁ VAN LOS KILÓMETROS ←←←
-- ---------------------------------------------------------------------
-- Reemplazá cada `null` por cada cuántos kilómetros es ese service.
-- Sin ese número el script no sigue: asignar un plan con un intervalo
-- inventado es peor que no asignarlo, porque la unidad avisa cuando no
-- corresponde y nadie se entera de por qué.
--
-- Un plan que YA EXISTE con ese nombre se respeta tal como está: no se le
-- toca el intervalo ni la descripción, y el `null` de acá no le hace nada.
-- ---------------------------------------------------------------------
drop table if exists _plan_excel;
create temp table _plan_excel (nombre text primary key, cada_km numeric, descripcion text);

insert into _plan_excel (nombre, cada_km, descripcion) values
  ('TRACTORES',        null, 'Service de los tractores'),
  ('S-WAY',            null, 'Service de los Iveco S-Way'),
  ('FURGONES',         null, 'Service de los furgones'),
  ('VEHICULOS CHICOS', null, 'Service de los autos y utilitarios chicos');


-- Los que falten y no tengan kilómetros, cortan acá con el nombre puesto.
do $$
declare faltan text;
begin
  select string_agg(e.nombre, ', ' order by e.nombre) into faltan
  from _plan_excel e
  where e.cada_km is null
    and not exists (select 1 from mantenimiento_planes p
                    where upper(btrim(p.nombre)) = e.nombre);
  if faltan is not null then
    raise exception
      'Falta decir cada cuántos km es el service de: %. Escribí los números donde dice null, en el bloque de arriba, y volvé a correr todo el script.', faltan;
  end if;
end $$;


-- El que no existía se crea. El que ya estaba queda como estaba.
insert into mantenimiento_planes (nombre, descripcion, cada_km)
select e.nombre, e.descripcion, e.cada_km
from _plan_excel e
where e.cada_km is not null
  and not exists (select 1 from mantenimiento_planes p
                  where upper(btrim(p.nombre)) = e.nombre);


-- ---------------------------------------------------------------------
-- 2. LO QUE DICE EL EXCEL, PATENTE POR PATENTE
-- ---------------------------------------------------------------------
-- Copiado tal cual de la planilla, con la patente como la escribe el
-- taller. El enganche con `unidades` no se hace por el texto: se le sacan
-- los espacios a las dos puntas, igual que hace la app.
--
-- Las tres filas que el Excel deja abiertas —«VERIFICAR (30.000 km)» y
-- «SIN DATOS»— entran igual a la lista, no enganchan con ningún plan y
-- salen listadas al final. Están a la vista, sin plan, hasta que alguien
-- decida cuál les toca.
-- ---------------------------------------------------------------------
drop table if exists _asignacion_excel;
create temp table _asignacion_excel (patente text, plan text);

insert into _asignacion_excel (patente, plan) values
  ('AD 247 MQ', 'TRACTORES'),
  ('AE 423 IV', 'TRACTORES'),
  ('AE 423 IW', 'TRACTORES'),
  ('AE 588 MW', 'TRACTORES'),
  ('AE 988 UW', 'TRACTORES'),
  ('AF 218 HY', 'TRACTORES'),
  ('AF 470 UT', 'TRACTORES'),
  ('AF 533 SB', 'TRACTORES'),
  ('AF 577 BD', 'TRACTORES'),
  ('AF 796 IX', 'TRACTORES'),
  ('AG 286 TR', 'TRACTORES'),
  ('AG 708 DM', 'TRACTORES'),
  ('AG 865 QF', 'TRACTORES'),
  ('AG 983 HW', 'TRACTORES'),
  ('AH 522 SI', 'S-WAY'),
  ('AH 861 UB', 'S-WAY'),
  ('AH 938 VO', 'S-WAY'),
  ('AH 842 GQ', 'S-WAY'),
  ('AF 310 TU', 'VERIFICAR (30.000 KM)'),
  ('AG 082 ZL', 'FURGONES'),
  ('AG 797 NJ', 'VEHICULOS CHICOS'),
  ('KOF 186',   'FURGONES'),
  ('KSP 007',   'FURGONES'),
  ('VWL 688',   'FURGONES'),
  ('VXO 389',   'FURGONES'),
  ('VYE 907',   'FURGONES'),
  ('NBR 784',   'SIN DATOS'),
  ('HCU 499',   'FURGONES'),
  ('AD 909 NU', 'FURGONES'),
  ('AE 116 RO', 'FURGONES'),
  ('AF 103 BT', 'FURGONES'),
  ('AF 591 UW', 'FURGONES'),
  ('AG 070 OR', 'VERIFICAR (30.000 KM)'),
  ('DHS 534',   'FURGONES'),
  ('PAN 639',   'FURGONES'),
  ('CAF 865',   'FURGONES'),
  ('EWQ 717',   'VEHICULOS CHICOS'),
  ('JEA 499',   'FURGONES'),
  ('MJF 275',   'FURGONES'),
  ('MDH 784',   'FURGONES'),
  ('PIQ 468',   'FURGONES'),
  ('AA 823 XJ', 'FURGONES'),
  ('AG 224 IE', 'FURGONES'),
  ('CDZ 499',   'FURGONES'),
  ('CYD 468',   'FURGONES'),
  ('ISK 266',   'FURGONES'),
  ('RYN 309',   'FURGONES'),
  ('PDS 082',   'FURGONES'),
  ('FLG 593',   'FURGONES'),
  ('GWF 267',   'FURGONES'),
  ('AE 527 FA', 'FURGONES');


-- ---------------------------------------------------------------------
-- 3. LA ASIGNACIÓN
-- ---------------------------------------------------------------------
-- `on conflict do nothing` es lo que hace que el script se pueda correr
-- de nuevo sin duplicar nada: la patente que ya tenía ese plan se saltea.
insert into unidad_planes (unidad_id, plan_id, usuario)
select u.id, p.id, 'carga masiva Excel'
from _asignacion_excel a
join unidades u
  on regexp_replace(upper(u.patente), '[^A-Z0-9]', '', 'g')
   = regexp_replace(upper(a.patente), '[^A-Z0-9]', '', 'g')
join mantenimiento_planes p
  on upper(btrim(p.nombre)) = a.plan and p.activo
where u.activa
on conflict (unidad_id, plan_id) do nothing;


-- =====================================================================
-- CÓMO QUEDÓ
-- =====================================================================

-- Cuántas de las 51 filas del Excel quedaron enganchadas.
select count(*) as filas_del_excel_asignadas
from _asignacion_excel a
join unidades u
  on regexp_replace(upper(u.patente), '[^A-Z0-9]', '', 'g')
   = regexp_replace(upper(a.patente), '[^A-Z0-9]', '', 'g')
join mantenimiento_planes p on upper(btrim(p.nombre)) = a.plan and p.activo
join unidad_planes up on up.unidad_id = u.id and up.plan_id = p.id
where u.activa;

-- Cada plan con las unidades que le quedaron.
select p.nombre, p.cada_km, count(up.unidad_id) as unidades
from mantenimiento_planes p
left join unidad_planes up on up.plan_id = p.id
where p.activo
group by p.id, p.nombre, p.cada_km
order by unidades desc, p.nombre;

-- Lo que quedó afuera y por qué. Acá tienen que aparecer las tres filas
-- que el Excel deja abiertas y nada más; cualquier otra cosa en esta
-- lista es una patente que no está en la base o está dada de baja.
select a.patente,
       a.plan,
       case
         when not exists (
           select 1 from unidades u
           where regexp_replace(upper(u.patente), '[^A-Z0-9]', '', 'g')
               = regexp_replace(upper(a.patente), '[^A-Z0-9]', '', 'g')
         ) then 'la patente no está en la base'
         when not exists (
           select 1 from unidades u
           where regexp_replace(upper(u.patente), '[^A-Z0-9]', '', 'g')
               = regexp_replace(upper(a.patente), '[^A-Z0-9]', '', 'g')
             and u.activa
         ) then 'la unidad está dada de baja'
         else 'el Excel no dice qué plan le toca'
       end as motivo
from _asignacion_excel a
where not exists (
  select 1
  from unidades u
  join mantenimiento_planes p on upper(btrim(p.nombre)) = a.plan and p.activo
  join unidad_planes up on up.unidad_id = u.id and up.plan_id = p.id
  where regexp_replace(upper(u.patente), '[^A-Z0-9]', '', 'g')
      = regexp_replace(upper(a.patente), '[^A-Z0-9]', '', 'g')
    and u.activa
)
order by motivo, a.patente;

-- Las unidades activas que siguen sin ningún plan, estén o no en el Excel.
select u.patente, u.interno, u.modelo
from unidades u
where u.activa and u.tipo = 'vehiculo'
  and not exists (select 1 from unidad_planes up where up.unidad_id = u.id)
order by u.patente;
