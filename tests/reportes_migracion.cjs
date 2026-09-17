// Ejecutable con PGLITE_MODULE apuntando a @electric-sql/pglite.
const {PGlite}=require(process.env.PGLITE_MODULE||'@electric-sql/pglite');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const db=new PGlite();const root=path.resolve(__dirname,'..');
 try{
 await db.exec(`create table usuarios(id bigint primary key);create table unidades(id bigint primary key,patente text,interno text,sucursal text,activa boolean default true);create table ordenes_trabajo(id bigint primary key);create table roles(codigo text primary key);create table rol_modulos(rol_codigo text references roles,modulo text,primary key(rol_codigo,modulo));insert into roles values('chofer');`);
 await db.exec(fs.readFileSync(path.join(root,'gomeria/06_vencimientos.sql'),'utf8'));
 const sql=fs.readFileSync(path.join(root,'gomeria/30_avisos_y_reportes.sql'),'utf8');await db.exec(sql);await db.exec(sql);
 await db.exec(`insert into usuarios values(1);insert into unidades(id,patente,sucursal) values(1,'TEST001','CAT');insert into vencimientos(tipo_id,unidad_id,vence,aviso_fecha) select id,1,current_date+10,current_date+5 from tipos_vencimiento where nombre='VTV';`);
 assert.equal((await db.query('select estado from v_vencimientos_hoy')).rows[0].estado,'vigente');
 await db.exec('update vencimientos set aviso_fecha=current_date');assert.equal((await db.query('select estado from v_vencimientos_hoy')).rows[0].estado,'por_vencer');
 await assert.rejects(db.exec('update vencimientos set aviso_fecha=vence+1'));
 await db.exec('update vencimientos set aviso_fecha=null');assert.equal((await db.query('select estado from v_vencimientos_hoy')).rows[0].estado,'por_vencer');
 await db.exec("update tipos_vencimiento set aviso_dias=0 where nombre='VTV'");assert.equal((await db.query('select estado from v_vencimientos_hoy')).rows[0].estado,'vigente');
 await db.exec(`insert into reportes_chofer(id,usuario_id,unidad_id,descripcion,urgencia,ocurrido_en) values('00112233-4455-4677-8899-aabbccddeeff',1,1,'Falla','PUEDE_ESPERAR',now())`);
 await assert.rejects(db.exec("update reportes_chofer set estado='ORDEN_CREADA'"));
 await assert.rejects(db.exec("update reportes_chofer set estado='DESESTIMADA',motivo=''"));
 await assert.rejects(db.exec("update reportes_chofer set estado='DESESTIMADA',motivo=null"));
 await db.exec("update reportes_chofer set estado='DESESTIMADA',motivo='Duplicada'");
 assert.equal((await db.query('select count(*)::int n from reportes_chofer')).rows[0].n,1);
 console.log('PASS: PostgreSQL WASM migration twice, explicit/default notices, date and report constraints');
 }finally{await db.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
