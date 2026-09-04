-- =====================================================================
-- LOS DATOS DEL MAESTRO
-- ---------------------------------------------------------------------
-- Las 68 unidades de la planilla, para pegar en Supabase -> SQL Editor ->
-- Run. Es lo mismo que hace `importar_unidades.py`, pero sin necesitar la
-- cadena de conexión a mano.
--
-- Se puede correr las veces que haga falta:
--
--   * La unidad que ya está se completa, no se pisa. Un campo vacío acá
--     no borra lo que hay cargado: por eso cada columna va con coalesce.
--   * La que no está se da de alta.
--   * La que está en la base y no acá se deja como está. Sacar una unidad
--     es una decisión, no un efecto de haber importado.
--
-- Para actualizarlo: pegar de nuevo la planilla en
-- gomeria/unidades_maestro.tsv y volver a generarlo.
--
-- ANTES de este archivo tiene que estar corrido 07_unidades.sql, que es
-- el que crea las columnas chasis, chofer, semi y tipo.
-- =====================================================================

create temporary table _maestro (
  patente text primary key, interno text, marca text, modelo text,
  chasis text, chofer text, semi text, sucursal text, uso text, tipo text
);

insert into _maestro values
  ('AA823XJ', '300', 'IVECO', 'IVECO BS-170E28 MLL', '8ATA1RMH0HX101522', 'AGUIRRE ALEJANDRO', null, 'COR', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('AD247MQ', '2', 'SCANIA', 'SCANIA 545-R400 A6X2', '+9BSR6X200++K3932810+', 'PEREIRA NICOLAS', 'AE456MJ', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AD909NU', '200', 'MERCEDES BENZ', 'MERCEDES BENZ ACCELO 815', '8AB979026LA900102', 'LEIVA ANTONIO', null, 'CAT', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('AE116RO', '201', 'IVECO', 'IVECO DAILY 55C17 PASO 3750', '93ZC53C01L8489328', 'ROBLES LEONARDO', null, 'CAT', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('AE423IV', '4', 'IVECO', 'IVECO 460S36TLA14', '8ATM1UPH0MX112222', 'CARDENES JONHATAN', 'AB102VH', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AE423IW', '5', 'SCANIA', 'SCANIA G360 A4X2', '+9BSG4X200++L3975860+', 'MUÑOZ JORGE', 'KUI769', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AE527FA', '450', 'IVECO', 'IVECO 523-DAILY 30-130', '+9BSG4X200++L3975860+', 'ROMERO ESTEBAN', null, 'SAL', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('AE588MW', '6', 'IVECO', 'IVECO CN-600S44TLA15', '8ATM2SSH0MX112807', 'MALUENDEZ MIGUEL', 'AE456MK', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AE988UW', '7', 'IVECO', 'IVECO 490S44T AT', '8ATM1USH0NX115330', 'SAVOY DIEGO', 'PGT703', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AF103BT', '202', 'TOYOTA', 'TOYOTA HIACE L2H2 2.8 TDI 6AT 3A Tipo: 13-FURGON', 'JTFLAHCPXM6008361', 'ROBLES RAMON', null, 'CAT', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('AF218HY', '8', 'IVECO', 'IVECO E-600S44TLA05', '8ATM2SSH0NX116445', 'CASTILLO HERNAN', 'AF455DQ', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AF310TU', '100', 'IVECO', 'IVECO STRALIS HI STREET 26-330 GNC', 'WJME2NN200C422344', 'CITRO DAMIAN', null, 'BUE', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('AF470UT', '9', 'IVECO', 'IVECO BV-490S44T AT', '8ATM1USH0PX119226', 'CEJAS GUSTAVO', 'AF294QU', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AF533SB', '10', 'IVECO', 'IVECO BV-490S44T AT', '8ATM1USH0PX119164', 'CATALAN FERNANDO', 'AA114ZX', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AF577BD', '11', 'IVECO', 'IVECO EN-R7T4B3B8-STRALIS', '8ATS3HUH0PX119351', 'MOYANO SERGIO', 'AD900UK', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AF591UW', '203', 'IVECO', 'IVECO DAILY 55-170', '93ZC053CZP8504717', null, null, 'CAT', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('AF796IX', '12', 'IVECO', 'IVECO CN-600S44TLA15', '8ATM2SSH0PX121035', 'RIOS WALTER', 'AF677RJ', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AG070OR', '204', 'IVECO', 'IVECO -170E28 MLL', '8ATA1RMH0PX122317', 'BARRIONUEVO ALEJANDRO', null, 'CAT', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('AG082ZL', '101', 'IVECO', 'IVECO-DAILY 55-170', '93ZC053CZP8507054', 'SANCHEZ MIGUEL', null, 'BUE', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('AG224IE', '400', 'IVECO', 'IVECO FL-150E21NCMC1A', '8ATA01LF0RX124794', 'SORIA MIGUEL', null, 'LRJ', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('AG286TR', '13', 'IVECO', 'IVECO FD-530S36TLA85A', '8ATS2APH0RX125877', 'BORDATTO FEDERICO', 'AF788NT', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AG708DM', '14', 'IVECO', 'IVECO STRALIS HI ROAD 490S44T 3500 EU. EBS/ESC', '8ATM1USH0RX128067', 'MUÑOZ FABIAN', 'AH048RS', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AG797NJ', '102', 'TOYOTA', 'TOYOTA HIACE', '8AJLAHCW1R3000091', 'FRUTOS JAVIER', null, 'BUE', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('AG865QF', '15', 'IVECO', 'IVECO AS490S44TPA14', '8ATM1WSH0SX129647', 'FERNANDEZ BRUNO', 'MJF254', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AG983HW', '16', 'IVECO', 'IVECO FN-AS600S44TYPA85', '8ATM2SSH0SX130402', 'BANEGAS HECTOR', null, 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AH522SI', '17', 'IVECO', '597-S-WAY 480 6X2', '93ZS62RUZS8607035', 'CABRERA GUILLERMO', 'AC538KW', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AH861UB', '18', 'IVECO', 'S-WAY AS490-480 T 3500 AS-TA', '93ZS62RUZS8605767', 'MARTINS JAVIER', 'AH935PH', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AH938VO', '19', 'IVECO', '597-S-WAY 480 6X2', '93ZS62VUZS8607729', 'HORNOS MARCELO', 'AH797DF', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('AH842GQ', '20', 'IVECO', '597-S-WAY 480 6X2', '93ZS62VUZT8608393', 'ZAULI CRISTIAN', 'AG888WA', 'LAD', 'LARGA DISTANCIA', 'vehiculo'),
  ('CAF865', '500', 'MERCEDES BENZ', 'MERCEDES BENZ L-1620', '9BM695014WB152473', 'OSORES FABIAN', null, 'CAT', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('CDZ499', '401', 'MERCEDES BENZ', 'MERCEDES BENZ 272-710', '9BM688157WB158944', 'SORIA JULIO', null, 'LRJ', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('CYD468', '402', 'MERCEDES BENZ', 'M. BENZ SPRINTER 31OD/F 3000', '8AC690330YA537002', 'NARVAEZ CESAR', null, 'BUE', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('DHS534', '205', 'FORD', 'FORD CARGO', '9BFV2UHGXYDB60392', null, null, 'CAT', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('EWQ717', '250', 'PEUGEOT', 'PEUGEOT BOXER 2.8 TD', '936232JZ251021405', null, null, 'BEL', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('FLG593', '501', 'SCANIA', 'SCANIA P 94DB', '9BSP6X2B063580629', 'RAZOUK ANTONIO', null, 'TUC', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('GWF267', '502', 'IVECO', 'IVECO DAILY 40S14 PASO 3450', '93ZC35A0188400305', null, null, 'TUC', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('HCU499', '251', 'MERCEDES BENZ', 'MERCEDES BENZ L 1318', '9BM6940008B580483', 'MONCHI', null, 'COR', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('HJM284', '207', 'SUSUKI', 'SUSUKI GRAND VITARA JIII 2.0', 'JS3TD54V284107626', 'USO PARTICULAR', null, 'BUE', 'PARTICULAR', 'vehiculo'),
  ('IEX213', '403', 'PEUGEOT', 'PEUGEOT 207 COMPACT XR 1.4 5P', '8AD2MKFWU9G055052', 'FRANCISCO PUNTERI', null, 'TAL', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('ISK266', '404', 'RENAULT', 'RENAULT MASTER PH3 DCI 120 L2H2 PKCNF', '93YADCUH6AJ393126', 'ALVAREZ TOMAS', null, 'BUE', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('JEA499', '405', 'KIA', 'KIA 207-K2500', 'KNCSJX73AB7494487', null, null, 'BUE', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('KOF186', '103', 'IVECO', 'IVECO DAILY 70 C16 PASO4350', '93ZC68B01C8427567', 'PACHECO DIEGO', null, 'BUE', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('KSP007', '104', 'FORD', 'FORD TRANSIT 2.4L 115 T350 TA C/AA', 'WF0XXVTTFBTE04204', 'CHAVEZ MAXIMILIANO', null, 'BUE', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('MDH784', '301', 'HYUNDAI', 'HYUNDAI HD 78', 'KMFGA17PPDC208551', 'QUIÑONES GABRIEL', null, 'COR', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('MJF275', '302', 'FORD', 'FORD CARGO', '9BFXEAFU3DBS33970', null, null, 'CAT', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('NBR784', '105', 'DFM', 'DFM 1063CJ10', '9UTT5ABB5DN320709', null, null, 'BUE', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('PAN639', '208', 'MERCEDES BENZ', 'MERCEDES BENZ SPRINTER 515 CDI-CH 4325', '8AC906155GE109829', 'AVILA NICOLAS', null, 'CAT', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('PDS082', '503', 'IVECO', null, '8ATA1NFHOGX097603', null, null, 'TUC', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('PIQ468', '303', 'MERCEDES BENZ', 'MERCEDES BENZ SPRINTER 515 CDI-CH 4325', '8AC906155GE113839', 'SANCHEZ LEONARDO', null, 'COR', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('RYN309', '406', 'MERCEDES BENZ', 'MERCEDES BENZ 608 D/35', '378.325-12-085918', 'ALVAREZ GASTON', null, 'LRJ', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('VWL688', '107', 'MERCEDES BENZ', 'M. BENZ L1614', '9BM386004NB.950249', 'MANSILLA RUBEN', null, 'BUE', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('VXO389', '108', 'MERCEDES BENZ', 'M. BENZ L1614', '9BM386004NB948545', 'REYES MARTIN', null, 'BUE', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('VYE907', '109', 'MERCEDES BENZ', 'M. BENZ L1614', '9BM386004NB-952483', 'BASTIANI OMAR', null, 'BUE', 'DISTRIBUCION LOCAL', 'vehiculo'),
  ('AUTCAT01', '2000', null, null, null, null, null, null, null, 'equipo'),
  ('TOYCAT01', null, null, null, null, null, null, null, null, 'equipo'),
  ('TOYCAT02', null, null, null, null, null, null, null, null, 'equipo'),
  ('ARTBEL01', null, null, null, null, null, null, null, null, 'equipo'),
  ('HELROD01', null, null, null, null, null, null, null, null, 'equipo'),
  ('ARTCHI01', null, null, null, null, null, null, null, null, 'equipo'),
  ('HELTUC01', null, null, null, null, null, null, null, null, 'equipo'),
  ('HELCOR01', null, null, null, null, null, null, null, null, 'equipo'),
  ('ARTROD01', null, null, null, null, null, null, null, null, 'equipo'),
  ('APIROD01', null, null, null, null, null, null, null, null, 'equipo'),
  ('TOYBUE01', null, null, null, null, null, null, null, null, 'equipo'),
  ('TOYBUE02', null, null, null, null, null, null, null, null, 'equipo'),
  ('ARTBUE01', null, null, null, null, null, null, null, null, 'equipo'),
  ('CATBUE01', null, null, null, null, null, null, null, null, 'equipo'),
  ('PRECAT01', null, null, null, null, null, null, null, null, 'equipo');

-- Las que ya están: se completan campo por campo.
update unidades u set
  interno  = coalesce(m.interno,  u.interno),
  marca    = coalesce(m.marca,    u.marca),
  modelo   = coalesce(m.modelo,   u.modelo),
  chasis   = coalesce(m.chasis,   u.chasis),
  chofer   = coalesce(m.chofer,   u.chofer),
  semi     = coalesce(m.semi,     u.semi),
  sucursal = coalesce(m.sucursal, u.sucursal),
  uso      = coalesce(m.uso,      u.uso),
  tipo     = m.tipo
from _maestro m where m.patente = u.patente;

-- Las que faltan: alta.
insert into unidades (patente, interno, marca, modelo, chasis, chofer,
                      semi, sucursal, uso, tipo)
select m.patente, m.interno, m.marca, m.modelo, m.chasis, m.chofer,
       m.semi, m.sucursal, m.uso, m.tipo
from _maestro m
where not exists (select 1 from unidades u where u.patente = m.patente);

drop table _maestro;

-- El resumen de lo que quedó.
select
  (select count(*) from unidades)                           as unidades,
  (select count(*) from unidades where chasis is not null)  as con_chasis,
  (select count(*) from unidades where chofer is not null)  as con_chofer,
  (select count(*) from unidades where semi   is not null)  as con_semi,
  (select count(*) from unidades where tipo = 'equipo')     as equipos;
