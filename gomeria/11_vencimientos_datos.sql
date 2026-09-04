-- =====================================================================
-- LOS DATOS DE VENCIMIENTOS
-- ---------------------------------------------------------------------
-- La planilla VENCIMIENTO DE LICENCIAS, para pegar en Supabase -> SQL
-- Editor -> Run. Es lo mismo que hace `importar_vencimientos.py`, pero
-- sin necesitar la cadena de conexión a mano.
--
-- Trae 49 choferes, 144 documentos y 22 unidades que la planilla tenía y
-- el maestro no (casi todas semis).
--
-- Las sucursales vienen con el código corto del maestro: la planilla dice
-- LARGA DISTANCIA y el maestro dice LAD, y sin traducirlas el panel las
-- muestra como dos lugares distintos con la mitad de los datos cada uno.
--
-- Se puede correr las veces que haga falta: una fecha que ya está no se
-- duplica. Una fecha nueva entra como renovación y la vista se queda con
-- la más nueva, que es como funciona el módulo.
--
-- ANTES tiene que estar corrido 06_vencimientos.sql.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Las unidades que faltaban
-- ---------------------------------------------------------------------
-- La planilla de licencias tiene semis y unidades viejas que el maestro
-- no tiene. Se dan de alta con lo poco que se sabe de ellas: son de la
-- flota igual, solo que no llevan mapa de cubiertas.
insert into unidades (patente, sucursal)
select * from (values
  ('AA114ZX', 'LAD'),
  ('AA472IP', 'LAD'),
  ('AB102VH', 'LAD'),
  ('AB102VI', 'LAD'),
  ('AC538KW', 'LAD'),
  ('AD900UK', 'LAD'),
  ('AE456MJ', 'LAD'),
  ('AE456MK', 'LAD'),
  ('AF294QU', 'LAD'),
  ('AF455DQ', 'LAD'),
  ('AF677RJ', 'LAD'),
  ('AF788NT', 'LAD'),
  ('AG979NJ', 'BUE'),
  ('AH048RS', 'LAD'),
  ('AH787DF', 'LAD'),
  ('FMC282', 'LAD'),
  ('KUI769', 'LAD'),
  ('MJF254', 'LAD'),
  ('MJF259', 'LAD'),
  ('OOD560', 'LAD'),
  ('PGT701', 'LAD'),
  ('PGT703', 'LAD')
) as v(patente, sucursal)
where not exists (select 1 from unidades u where u.patente = v.patente);

-- ---------------------------------------------------------------------
-- 2. Los choferes
-- ---------------------------------------------------------------------
create temporary table _personas (nombre text, sucursal text, patente text);
insert into _personas values
  ('Aguirre Alejandro', 'CAT', 'MJF275'),
  ('Aguirre Jose Luis', 'BEL', 'EWQ717'),
  ('Ahumada Carlo Alberto', 'TUC', 'GWF267'),
  ('Alvarez Matias Gaston', 'LRJ', 'RYN309'),
  ('Alvarez Tomas Agustin', 'LRJ', 'ISK266'),
  ('Avila Ramon Nicolas', 'CAT', 'PAN639'),
  ('Bastiani Omar', 'BUE', 'VYE907'),
  ('Bruno Fernández', 'LAD', 'AG865QF'),
  ('Castillo Hernan', 'LAD', 'AF218HY'),
  ('Catalán Raúl Fernando', 'LAD', 'AF533SB'),
  ('Chavez Maximiliano', 'BUE', 'KSP007'),
  ('Citro Damian', 'BUE', 'AF310TU'),
  ('Claudio Fabian Muñoz', 'LAD', 'AG708DM'),
  ('Cordoba Ramon Alberto', 'BEL', 'EWQ717'),
  ('Cordoba Ramon Ariel', 'BEL', 'HCU499'),
  ('Cristian Zauli', 'LAD', 'AH842GQ'),
  ('Delfini Renzo', 'COR', 'HCU499'),
  ('Diego Savoy', 'LAD', null),
  ('Federico Bordatto', 'LAD', 'AG286TR'),
  ('Frutos Javier', 'BUE', 'AG979NJ'),
  ('Guillermo Daniel Cabrera Barreto', 'LAD', 'AH522SI'),
  ('Gustavo Alejandro Cejas', 'LAD', 'AF470UT'),
  ('Hector Banegas', 'LAD', 'AG983HW'),
  ('Javier Martins', 'LAD', 'AH861UB'),
  ('Jonathan Cardenes', 'LAD', 'AE423IV'),
  ('Jorge Ramón Muñoz', 'LAD', 'AE423IW'),
  ('Leiva Segundo Antonio', 'CAT', 'AD909NU'),
  ('Maluendez Miguel', 'LAD', 'AE588MW'),
  ('Mansilla Ruben', 'BUE', 'VWL688'),
  ('Marcelo Enrique Hornos', 'LAD', 'AH938VO'),
  ('Marcelo Petri', 'LAD', 'AD247MQ'),
  ('Moyano Sergio', 'LAD', 'AF577BD'),
  ('Narvaez Cesar Ovidio', 'LRJ', 'CYD468'),
  ('Osores Fabian Alejandro', 'TUC', 'PDS082'),
  ('Pacheco Diego', 'BUE', 'KOF186'),
  ('Pereira Nicolas', 'LAD', 'KUI769'),
  ('Quiñones Gabriel', 'COR', 'AA823XJ'),
  ('Razouk Antonio Enrique', 'TUC', 'FLG593'),
  ('Reyes Martin', 'BUE', 'VXO389'),
  ('Robles Avila Pedro', 'CAT', 'AE116RO'),
  ('Robles Ramon Eduardo', 'CAT', 'AF103BT'),
  ('Romero Esteban', 'CAT', 'AF591UW'),
  ('Sanchez Leonardo', 'COR', 'PIQ468'),
  ('Sanchez Miguel', 'BUE', 'AG082ZL'),
  ('Segura Marcelo Exequiel', 'CAT', 'DHS534'),
  ('Soria Julio Martin', 'LRJ', 'CDZ499'),
  ('Soria Miguel Osvaldo', 'LRJ', 'AG224IE'),
  ('Walter Ariel Rios', 'LAD', 'AF796IX'),
  ('Zazzetta Julian', 'CAT', 'AG070OR');

insert into personas (nombre, sucursal, unidad_id)
select p.nombre, p.sucursal, u.id
from _personas p left join unidades u on u.patente = p.patente
where not exists (select 1 from personas x where x.nombre = p.nombre);

-- Al que ya estaba se le completa la sucursal y la unidad, sin pisarlas
-- si ya tenía algo.
update personas x set
  sucursal  = coalesce(x.sucursal, p.sucursal),
  unidad_id = coalesce(x.unidad_id, u.id)
from _personas p left join unidades u on u.patente = p.patente
where x.nombre = p.nombre;

drop table _personas;

-- ---------------------------------------------------------------------
-- 3. Los documentos
-- ---------------------------------------------------------------------
create temporary table _vencs (
  tipo text, patente text, persona text, desde date, vence date,
  identificador text, detalle text, donde text, observaciones text
);
insert into _vencs values
  ('Licencia municipal', null, 'Aguirre Alejandro', '2025-12-18', '2030-10-30', null, null, null, null),
  ('Licencia municipal', null, 'Aguirre Jose Luis', '2025-02-24', '2030-02-24', null, null, null, null),
  ('Licencia municipal', null, 'Alvarez Matias Gaston', '2024-01-10', '2029-01-10', null, null, null, null),
  ('Licencia municipal', null, 'Alvarez Tomas Agustin', '2026-01-02', '2031-01-02', null, null, null, null),
  ('Licencia municipal', null, 'Avila Ramon Nicolas', '2025-01-08', '2031-02-08', null, null, null, null),
  ('Licencia municipal', null, 'Bastiani Omar', '2026-03-04', '2027-03-04', null, null, null, null),
  ('Licencia municipal', null, 'Bruno Fernández', null, '2026-10-25', null, null, null, '2026-12-06 00:00:00'),
  ('Licencia municipal', null, 'Castillo Hernan', null, '2027-07-01', null, null, null, null),
  ('Licencia municipal', null, 'Catalán Raúl Fernando', null, '2031-02-10', null, null, null, null),
  ('Licencia municipal', null, 'Chavez Maximiliano', '2024-11-25', '2026-11-25', null, null, null, 'CAMIONETA ROTA ESTA UTILIZANDO ISK266'),
  ('Licencia municipal', null, 'Citro Damian', '2025-03-21', '2027-03-21', null, null, null, null),
  ('Licencia municipal', null, 'Claudio Fabian Muñoz', null, '2026-12-09', null, null, null, null),
  ('Licencia municipal', null, 'Cordoba Ramon Alberto', '2024-10-22', '2029-10-22', null, null, null, null),
  ('Licencia municipal', null, 'Cordoba Ramon Ariel', '2025-07-22', '2030-07-08', null, null, null, null),
  ('Licencia municipal', null, 'Cristian Zauli', null, '2026-04-01', null, null, null, null),
  ('Licencia municipal', null, 'Delfini Renzo', '2026-01-05', '2028-01-05', null, null, null, null),
  ('Licencia municipal', null, 'Federico Bordatto', null, '2027-04-09', null, null, null, null),
  ('Licencia municipal', null, 'Frutos Javier', '2025-03-31', '2027-03-31', null, null, null, null),
  ('Licencia municipal', null, 'Guillermo Daniel Cabrera Barreto', null, '2027-06-17', null, null, null, null),
  ('Licencia municipal', null, 'Gustavo Alejandro Cejas', null, '2027-05-18', null, null, null, null),
  ('Licencia municipal', null, 'Hector Banegas', null, '2027-06-13', null, null, null, null),
  ('Licencia municipal', null, 'Javier Martins', null, '2026-11-03', null, null, null, 'CARGAS PELIGROSAS'),
  ('Licencia municipal', null, 'Jonathan Cardenes', null, '2030-08-04', null, null, null, null),
  ('Licencia municipal', null, 'Jorge Ramón Muñoz', null, '2026-08-18', null, null, null, null),
  ('Licencia municipal', null, 'Leiva Segundo Antonio', '2023-04-25', '2026-04-24', null, null, null, null),
  ('Licencia municipal', null, 'Maluendez Miguel', null, '2027-02-19', null, null, null, null),
  ('Licencia municipal', null, 'Mansilla Ruben', '2026-03-13', '2027-03-13', null, null, null, null),
  ('Licencia municipal', null, 'Marcelo Enrique Hornos', null, '2026-12-26', null, null, null, null),
  ('Licencia municipal', null, 'Marcelo Petri', null, '2027-01-26', null, null, null, null),
  ('Licencia municipal', null, 'Moyano Sergio', null, '2026-10-14', null, null, null, null),
  ('Licencia municipal', null, 'Narvaez Cesar Ovidio', '2022-07-14', '2027-07-14', null, null, null, null),
  ('Licencia municipal', null, 'Osores Fabian Alejandro', '2024-06-13', '2026-06-16', null, null, null, null),
  ('Licencia municipal', null, 'Pacheco Diego', '2025-02-04', '2027-02-04', null, null, null, null),
  ('Licencia municipal', null, 'Quiñones Gabriel', '2024-01-10', '2028-01-10', null, null, null, null),
  ('Licencia municipal', null, 'Reyes Martin', '2025-05-08', '2027-05-08', null, null, null, null),
  ('Licencia municipal', null, 'Robles Avila Pedro', '2025-12-23', '2027-12-22', null, null, null, null),
  ('Licencia municipal', null, 'Robles Ramon Eduardo', '2023-10-13', '2026-10-12', null, null, null, null),
  ('Licencia municipal', null, 'Romero Esteban', '2023-03-27', '2026-03-26', null, null, null, null),
  ('Licencia municipal', null, 'Sanchez Leonardo', '2021-11-26', '2026-11-26', null, null, null, null),
  ('Licencia municipal', null, 'Sanchez Miguel', '2026-02-20', '2027-02-20', null, null, null, null),
  ('Licencia municipal', null, 'Soria Julio Martin', '2025-11-18', '2030-11-18', null, null, null, null),
  ('Licencia municipal', null, 'Soria Miguel Osvaldo', '2025-05-14', '2027-05-14', null, null, null, null),
  ('Licencia municipal', null, 'Walter Ariel Rios', null, '2026-12-20', null, null, null, null),
  ('Licencia municipal', null, 'Zazzetta Julian', '2025-08-29', '2030-08-28', null, null, null, null),
  ('Licencia profesional', null, 'Aguirre Alejandro', '2025-12-18', '2030-10-30', null, null, null, null),
  ('Licencia profesional', null, 'Ahumada Carlo Alberto', '2025-10-18', '2030-10-14', null, null, null, null),
  ('Licencia profesional', null, 'Alvarez Matias Gaston', '2024-01-10', '2029-01-10', null, null, null, null),
  ('Licencia profesional', null, 'Alvarez Tomas Agustin', '2026-01-02', '2031-01-02', null, null, null, null),
  ('Licencia profesional', null, 'Bruno Fernández', null, '2026-10-25', null, null, null, '2026-12-06 00:00:00'),
  ('Licencia profesional', null, 'Castillo Hernan', null, '2027-07-01', null, null, null, null),
  ('Licencia profesional', null, 'Catalán Raúl Fernando', null, '2031-02-10', null, null, null, null),
  ('Licencia profesional', null, 'Claudio Fabian Muñoz', null, '2026-12-09', null, null, null, null),
  ('Licencia profesional', null, 'Cordoba Ramon Ariel', '2025-07-22', '2030-07-08', null, null, null, null),
  ('Licencia profesional', null, 'Cristian Zauli', null, '2026-04-01', null, null, null, null),
  ('Licencia profesional', null, 'Delfini Renzo', '2026-01-05', '2028-01-05', null, null, null, null),
  ('Licencia profesional', null, 'Federico Bordatto', null, '2027-04-09', null, null, null, null),
  ('Licencia profesional', null, 'Guillermo Daniel Cabrera Barreto', null, '2027-06-17', null, null, null, null),
  ('Licencia profesional', null, 'Gustavo Alejandro Cejas', null, '2027-05-18', null, null, null, null),
  ('Licencia profesional', null, 'Hector Banegas', null, '2027-06-13', null, null, null, null),
  ('Licencia profesional', null, 'Javier Martins', null, '2026-12-06', null, null, null, 'CARGAS PELIGROSAS'),
  ('Licencia profesional', null, 'Jonathan Cardenes', null, '2030-08-04', null, null, null, null),
  ('Licencia profesional', null, 'Jorge Ramón Muñoz', null, '2026-08-18', null, null, null, null),
  ('Licencia profesional', null, 'Maluendez Miguel', null, '2027-02-19', null, null, null, null),
  ('Licencia profesional', null, 'Marcelo Enrique Hornos', null, '2026-12-26', null, null, null, null),
  ('Licencia profesional', null, 'Marcelo Petri', null, '2027-01-26', null, null, null, null),
  ('Licencia profesional', null, 'Moyano Sergio', null, '2026-10-14', null, null, null, null),
  ('Licencia profesional', null, 'Narvaez Cesar Ovidio', '2022-07-14', '2027-07-14', null, null, null, null),
  ('Licencia profesional', null, 'Quiñones Gabriel', '2024-01-10', '2028-01-10', null, null, null, null),
  ('Licencia profesional', null, 'Razouk Antonio Enrique', '2025-10-29', '2030-10-28', null, null, null, null),
  ('Licencia profesional', null, 'Sanchez Leonardo', '2021-11-26', '2026-10-26', null, null, null, null),
  ('Licencia profesional', null, 'Soria Julio Martin', '2025-11-18', '2030-11-18', null, null, null, null),
  ('Licencia profesional', null, 'Soria Miguel Osvaldo', '2025-05-14', '2027-05-14', null, null, null, null),
  ('Licencia profesional', null, 'Walter Ariel Rios', null, '2026-12-20', null, null, null, null),
  ('Licencia profesional', null, 'Zazzetta Julian', '2021-01-23', '2026-01-22', null, null, null, null),
  ('Matafuegos', 'AE423IV', null, '2025-11-01', '2026-11-01', null, null, null, null),
  ('Matafuegos', 'AE423IW', null, '2025-08-01', '2026-08-01', null, null, null, null),
  ('Matafuegos', 'AE588MW', null, '2026-04-01', '2027-04-01', null, null, null, null),
  ('Matafuegos', 'AF470UT', null, '2025-11-01', '2026-11-01', null, null, null, null),
  ('Matafuegos', 'AF533SB', null, '2025-08-01', '2026-08-01', null, null, null, null),
  ('Matafuegos', 'AF577BD', null, '2026-06-01', '2027-06-01', null, null, null, null),
  ('Matafuegos', 'AF796IX', null, '2025-11-28', '2026-11-28', null, null, null, null),
  ('Matafuegos', 'AG286TR', null, '2026-04-01', '2027-04-01', null, null, null, null),
  ('Matafuegos', 'AG708DM', null, '2025-02-01', '2026-02-01', null, null, null, null),
  ('Matafuegos', 'AG983HW', null, '2026-06-01', '2027-06-01', null, null, null, null),
  ('Matafuegos', 'AH522SI', null, '2026-04-01', '2027-04-01', null, null, null, null),
  ('VTV', 'AA114ZX', null, null, '2027-04-09', null, null, null, null),
  ('VTV', 'AA472IP', null, null, '2026-09-17', null, null, null, null),
  ('VTV', 'AA823XJ', null, '2026-01-01', '2027-01-01', null, null, null, null),
  ('VTV', 'AB102VH', null, null, '2027-07-06', null, null, null, null),
  ('VTV', 'AB102VI', null, null, '2027-02-13', null, null, null, null),
  ('VTV', 'AC538KW', null, null, '2027-04-14', null, null, null, null),
  ('VTV', 'AD247MQ', null, null, '2027-06-08', null, null, null, null),
  ('VTV', 'AD900UK', null, null, '2026-09-25', null, null, null, null),
  ('VTV', 'AD909NU', null, '2026-01-27', '2027-01-27', null, null, null, null),
  ('VTV', 'AE116RO', null, '2025-12-27', '2026-12-26', null, null, null, null),
  ('VTV', 'AE423IV', null, null, '2027-02-13', null, null, null, null),
  ('VTV', 'AE423IW', null, null, '2026-09-01', null, null, null, null),
  ('VTV', 'AE456MJ', null, null, '2027-06-08', null, null, null, null),
  ('VTV', 'AE456MK', null, null, '2027-06-02', null, null, null, null),
  ('VTV', 'AE588MW', null, null, '2027-06-02', null, null, null, null),
  ('VTV', 'AF103BT', null, '2025-11-27', '2026-12-26', null, null, null, null),
  ('VTV', 'AF218HY', null, null, '2027-03-03', null, null, null, null),
  ('VTV', 'AF294QU', null, null, '2027-07-02', null, null, null, null),
  ('VTV', 'AF310TU', null, '2026-03-31', '2027-03-31', null, null, null, null),
  ('VTV', 'AF455DQ', null, null, '2027-07-02', null, null, null, null),
  ('VTV', 'AF470UT', null, null, '2027-07-02', null, null, null, null),
  ('VTV', 'AF533SB', null, null, '2027-07-29', null, null, null, null),
  ('VTV', 'AF577BD', null, null, '2026-09-25', null, null, null, null),
  ('VTV', 'AF591UW', null, '2025-12-09', '2026-12-09', null, null, null, null),
  ('VTV', 'AF677RJ', null, null, '2027-03-04', null, null, null, null),
  ('VTV', 'AF788NT', null, null, '2027-03-18', null, null, null, null),
  ('VTV', 'AF796IX', null, null, '2027-03-05', null, null, null, null),
  ('VTV', 'AG070OR', null, '2025-06-27', '2026-06-26', null, null, null, null),
  ('VTV', 'AG082ZL', null, '2026-01-16', '2027-01-16', null, null, null, null),
  ('VTV', 'AG224IE', null, '2025-11-17', '2026-11-17', null, null, null, null),
  ('VTV', 'AG286TR', null, null, '2026-11-04', null, null, null, null),
  ('VTV', 'AG708DM', null, null, '2027-01-23', null, null, null, null),
  ('VTV', 'AG865QF', null, null, '2026-11-28', null, null, null, '2026-12-06 00:00:00'),
  ('VTV', 'AG979NJ', null, null, '2027-08-30', null, null, null, null),
  ('VTV', 'AG983HW', null, null, '2027-01-23', null, null, null, null),
  ('VTV', 'AH048RS', null, null, '2027-05-06', null, null, null, null),
  ('VTV', 'AH522SI', null, null, '2026-10-13', null, null, null, null),
  ('VTV', 'AH787DF', null, null, '2027-05-07', null, null, null, null),
  ('VTV', 'AH861UB', null, null, '2026-12-17', null, null, null, 'CARGAS PELIGROSAS'),
  ('VTV', 'AH938VO', null, null, '2026-10-22', null, null, null, null),
  ('VTV', 'FLG593', null, '2025-09-04', '2026-09-04', null, null, null, null),
  ('VTV', 'FMC282', null, null, '2026-12-12', null, null, null, null),
  ('VTV', 'GWF267', null, '2025-05-28', '2026-05-28', null, null, null, null),
  ('VTV', 'HCU499', null, '2025-11-14', '2026-11-14', null, null, null, null),
  ('VTV', 'KOF186', null, '2026-03-31', '2027-03-31', null, null, null, null),
  ('VTV', 'KSP007', null, '2026-06-12', '2027-06-12', null, null, null, 'CAMIONETA ROTA ESTA UTILIZANDO ISK266'),
  ('VTV', 'KUI769', null, null, '2026-09-01', null, null, null, null),
  ('VTV', 'MJF254', null, null, '2026-11-27', null, null, null, null),
  ('VTV', 'MJF259', null, null, '2027-01-29', null, null, null, null),
  ('VTV', 'MJF275', null, '2025-03-14', '2026-03-14', null, null, null, null),
  ('VTV', 'OOD560', null, null, '2027-08-25', null, null, null, null),
  ('VTV', 'PAN639', null, '2025-12-02', '2026-12-02', null, null, null, null),
  ('VTV', 'PDS082', null, '2025-03-12', '2026-03-12', null, null, null, null),
  ('VTV', 'PGT701', null, null, '2026-10-13', null, null, null, null),
  ('VTV', 'PGT703', null, null, '2026-11-10', null, null, null, null),
  ('VTV', 'PIQ468', null, '2026-06-26', '2027-06-26', null, null, null, null),
  ('VTV', 'VWL688', null, '2026-05-19', '2026-11-19', null, null, null, null),
  ('VTV', 'VXO389', null, '2026-05-19', '2026-11-19', null, null, null, null),
  ('VTV', 'VYE907', null, '2026-06-18', '2026-12-18', null, null, null, null);

insert into vencimientos (tipo_id, unidad_id, persona_id, desde, vence,
                          identificador, detalle, donde, observaciones)
select t.id, u.id, p.id, v.desde, v.vence,
       v.identificador, v.detalle, v.donde, v.observaciones
from _vencs v
join tipos_vencimiento t on t.nombre = v.tipo
left join unidades u on u.patente = v.patente
left join personas p on p.nombre = v.persona
where (v.patente is null or u.id is not null)
  and (v.persona is null or p.id is not null)
  -- Una fecha ya cargada no se duplica. Una distinta entra como
  -- renovación y la vista se queda con la más nueva.
  and not exists (
    select 1 from vencimientos y
    where y.tipo_id = t.id
      and y.unidad_id is not distinct from u.id
      and y.persona_id is not distinct from p.id
      and y.vence = v.vence
      and coalesce(y.identificador,'') = coalesce(v.identificador,''));

drop table _vencs;

-- El resumen de lo que quedó.
select estado, count(*)::int as documentos
from v_vencimientos_hoy group by estado order by documentos desc;
