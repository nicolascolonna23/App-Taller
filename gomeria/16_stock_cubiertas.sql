-- =====================================================================
-- EL STOCK DE GOMAS QUE HAY HOY
-- ---------------------------------------------------------------------
-- Alta del stock contado en el taller, de la planilla "Stock Neumáticos".
-- Son 110 cubiertas y quedan todas en estado 'stock', listas para
-- montarse desde Gomería.
--
-- Sobre los códigos: el sistema lleva una ficha por cubierta y el código
-- es el número de fuego. Estas se contaron por montón, así que entran con
-- un código provisorio que dice de qué grupo salieron:
--
--     STK-R###   recapadas      STK-C###   con cámara
--     STK-N###   nuevas         STK-M###   macizas
--
-- Cuando se sepa el número de fuego de una, se le cambia el código a esa
-- ficha y no se pierde nada de lo que haya acumulado:
--
--     update cubiertas set codigo = '4521' where codigo = 'STK-R007';
--
-- Las medidas quedan escritas como venían en la planilla. Las gomas
-- nuevas no traían medida, así que van sin ella: se completa cuando se
-- las mire.
--
-- Se pega entero en Supabase → SQL Editor → Run. Se puede correr las
-- veces que haga falta: los códigos que ya están no se tocan ni se
-- duplican.
-- =====================================================================

insert into cubiertas (codigo, marca, modelo, medida, recapados,
                       observaciones, estado, fecha_alta)
select v.codigo, v.marca, v.modelo, v.medida, v.recapados,
       v.obs || ' · alta de stock del 07/09/2026', 'stock', date '2026-09-07'
from (values
  ('STK-R001', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R002', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R003', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R004', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R005', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R006', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R007', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R008', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R009', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R010', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R011', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R012', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R013', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R014', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R015', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R016', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R017', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R018', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R019', 'FATE', null, '295', 1, 'Recapada'),
  ('STK-R020', 'MICHELIN', null, '295', 1, 'Recapada'),
  ('STK-R021', 'MICHELIN', null, '295', 1, 'Recapada'),
  ('STK-R022', 'MICHELIN', null, '295', 1, 'Recapada'),
  ('STK-R023', 'MICHELIN', null, '295', 1, 'Recapada'),
  ('STK-R024', 'MICHELIN', null, '295', 1, 'Recapada'),
  ('STK-R025', 'MICHELIN', null, '295', 1, 'Recapada'),
  ('STK-R026', 'MICHELIN', null, '295', 1, 'Recapada'),
  ('STK-R027', 'MICHELIN', null, '295', 1, 'Recapada'),
  ('STK-R028', 'MICHELIN', null, '295', 1, 'Recapada'),
  ('STK-R029', 'BF GOODRICH', null, '295', 1, 'Recapada'),
  ('STK-R030', 'BF GOODRICH', null, '295', 1, 'Recapada'),
  ('STK-R031', 'BF GOODRICH', null, '295', 1, 'Recapada'),
  ('STK-R032', 'BF GOODRICH', null, '295', 1, 'Recapada'),
  ('STK-R033', 'FATE', null, '1000×20', 1, 'Recapada sin usar'),
  ('STK-R034', 'FATE', null, '1000×20', 1, 'Recapada sin usar'),
  ('STK-R035', 'FATE', null, '1000×20', 1, 'Recapada sin usar'),
  ('STK-R036', 'FATE', null, '1000×20', 1, 'Recapada sin usar'),
  ('STK-R037', 'FATE', null, '1000×20', 1, 'Recapada sin usar'),
  ('STK-R038', 'FATE', null, '1000×20', 1, 'Recapada usada'),
  ('STK-R039', 'FATE', null, '1000×20', 1, 'Recapada usada'),
  ('STK-R040', 'FATE', null, '1000×20', 1, 'Recapada usada'),
  ('STK-R041', 'FATE', null, '1000×20', 1, 'Recapada usada'),
  ('STK-R042', 'FATE', null, '1000×20', 1, 'Recapada usada'),
  ('STK-R043', 'FATE', null, '1000×20', 1, 'Recapada usada'),
  ('STK-R044', 'FATE', null, '275', 1, 'Recapada'),
  ('STK-R045', 'FATE', null, '275', 1, 'Recapada'),
  ('STK-R046', 'FATE', null, '275', 1, 'Recapada'),
  ('STK-R047', 'FATE', null, '275', 1, 'Recapada'),
  ('STK-R048', 'FATE', null, '275', 1, 'Recapada'),
  ('STK-R049', 'MICHELIN', null, '275', 1, 'Recapada'),
  ('STK-R050', 'MICHELIN', null, '275', 1, 'Recapada'),
  ('STK-R051', 'MICHELIN', null, '275', 1, 'Recapada'),
  ('STK-R052', 'MICHELIN', null, '275', 1, 'Recapada'),
  ('STK-R053', 'PIRELLI', null, '275', 1, 'Recapada'),
  ('STK-R054', 'PIRELLI', null, '275', 1, 'Recapada'),
  ('STK-R055', 'PIRELLI', null, '275', 1, 'Recapada'),
  ('STK-N001', 'BF GOODRICH', 'Lineal', null, 0, 'Nueva'),
  ('STK-N002', 'BF GOODRICH', 'Lineal', null, 0, 'Nueva'),
  ('STK-N003', 'BF GOODRICH', 'Lineal', null, 0, 'Nueva'),
  ('STK-N004', 'BF GOODRICH', 'Lineal', null, 0, 'Nueva'),
  ('STK-N005', 'BF GOODRICH', 'Lineal', null, 0, 'Nueva'),
  ('STK-N006', 'BF GOODRICH', 'Lineal', null, 0, 'Nueva'),
  ('STK-N007', 'BF GOODRICH', 'Lineal', null, 0, 'Nueva'),
  ('STK-N008', 'BF GOODRICH', 'Lineal', null, 0, 'Nueva'),
  ('STK-N009', 'BRIDGESTONE', 'Taco', null, 0, 'Nueva'),
  ('STK-N010', 'BRIDGESTONE', 'Taco', null, 0, 'Nueva'),
  ('STK-N011', 'BRIDGESTONE', 'Taco', null, 0, 'Nueva'),
  ('STK-N012', 'BRIDGESTONE', 'Taco', null, 0, 'Nueva'),
  ('STK-N013', 'BRIDGESTONE', 'Taco', null, 0, 'Nueva'),
  ('STK-N014', 'BRIDGESTONE', 'Taco', null, 0, 'Nueva'),
  ('STK-N015', 'BRIDGESTONE', 'Taco', null, 0, 'Nueva'),
  ('STK-N016', 'BRIDGESTONE', 'Taco', null, 0, 'Nueva'),
  ('STK-N017', null, 'Lineal', null, 0, 'Nueva'),
  ('STK-N018', null, 'Lineal', null, 0, 'Nueva'),
  ('STK-N019', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N020', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N021', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N022', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N023', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N024', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N025', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N026', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N027', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N028', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N029', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N030', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N031', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N032', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N033', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N034', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N035', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N036', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N037', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N038', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N039', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N040', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N041', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N042', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N043', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N044', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N045', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N046', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N047', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-N048', 'COMPSAL', null, null, 0, 'Nueva'),
  ('STK-C001', null, null, '700×12', 0, 'Con cámara'),
  ('STK-C002', null, null, '700×12', 0, 'Con cámara'),
  ('STK-C003', null, null, '900×9', 0, 'Con cámara'),
  ('STK-M001', null, null, '700×12', 0, 'Maciza'),
  ('STK-M002', null, null, '700×12', 0, 'Maciza'),
  ('STK-M003', null, null, '600×9', 0, 'Maciza'),
  ('STK-M004', null, null, '600×9', 0, 'Maciza')
) as v(codigo, marca, modelo, medida, recapados, obs)
on conflict (codigo) do nothing;

-- Qué quedó cargado. Tiene que dar 110, igual que la planilla.
select coalesce(observaciones, '') as que_son,
       coalesce(medida, '(sin medida)') as medida,
       coalesce(marca, '(sin marca)')   as marca,
       count(*) as cuantas
from cubiertas
where codigo like 'STK-%'
group by 1, 2, 3
order by 1, 2, 3;

select count(*) as total_de_gomas_dadas_de_alta
from cubiertas where codigo like 'STK-%';
