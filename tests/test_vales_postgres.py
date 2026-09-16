"""Integración aislada: MT_TEST_DATABASE_URL, nunca DATABASE_URL implícita."""
import os
import sys
import unittest
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'gomeria'))

@unittest.skipUnless(os.environ.get('MT_TEST_DATABASE_URL'),'Requiere PostgreSQL de prueba explícito')
class Integracion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.rows import dict_row
        cls.pg=psycopg; cls.row=dict_row; cls.schema='test_mt_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['MT_TEST_DATABASE_URL'],autocommit=True) as cx:
            cx.execute('create schema '+cls.schema)
        # Se limpia incluso si falla la instalación de la migración en setUpClass.
        cls.addClassCleanup(cls.limpiar_esquema)
        with cls.conectar() as cx:
            cx.execute('create table usuarios(id bigint generated always as identity primary key, usuario text, nombre text, rol text, activo boolean default true)')
            cx.execute('create table unidades(id bigint generated always as identity primary key,patente text,interno text,km_actual numeric,activa boolean default true)')
            cx.execute('create table odometros(id bigint generated always as identity primary key,unidad_id bigint references unidades,patente text,fecha date,km numeric,fuente text,leido timestamptz default now())')
            sql=(Path(__file__).resolve().parents[1]/'flota_vales/001_mantenimiento.sql').read_text().replace('begin;','',1).rsplit('commit;',1)[0]
            cx.execute(sql)
            cx.execute("insert into usuarios(usuario,nombre,rol) values('a','Admin','admin'),('b','Sucursal','operario'),('c','Otra','operario')")
            cx.execute("insert into mt_sucursales(nombre,prefijo) values('Una','AAA'),('Otra','BBB')")
            cx.execute("insert into mt_accesos values(2,'sucursal',1),(3,'sucursal',2)")
            cx.execute("insert into unidades(patente,mantenimiento_sucursal_id,mantenimiento_categoria) values('PRUEBA1',1,'larga_distancia'),('PRUEBA2',2,'semirremolque')")
    @classmethod
    def conectar(cls): return cls.pg.connect(os.environ['MT_TEST_DATABASE_URL'],row_factory=cls.row,options='-c search_path='+cls.schema+',public')
    @classmethod
    def limpiar_esquema(cls):
        with cls.pg.connect(os.environ['MT_TEST_DATABASE_URL'],autocommit=True) as cx: cx.execute('drop schema '+cls.schema+' cascade')
    def crear(self):
        from flota_vales.service import escribir
        with self.conectar() as cx: return escribir(cx,{'id':2,'rol':'operario'},{'op':'crear','unidad_id':1,'descripcion':'Falla','ubicacion':'Sucursal'})
    def test_concurrencia(self):
        with ThreadPoolExecutor(max_workers=8) as pool: numeros=list(pool.map(lambda _:self.crear()['numero'],range(16)))
        valores=sorted(int(n[3:]) for n in numeros)
        self.assertEqual(len(set(numeros)),16);self.assertEqual(valores,list(range(valores[0],valores[0]+16)))
    def test_identidad_y_visibilidad(self):
        from flota_vales.service import escribir,leer
        r=self.crear()
        with self.conectar() as cx:
            with self.assertRaises(self.pg.errors.RaiseException): cx.execute("update mt_solicitudes set numero='XXX' where id=%s",(r['id'],))
        with self.conectar() as cx:
            d=leer(cx,{'id':3,'rol':'operario'},{'op':'detalle','id':r['id']});self.assertNotIn('descripcion',d);self.assertNotIn('aprobado',d)
            with self.assertRaises(PermissionError): escribir(cx,{'id':3,'rol':'operario'},{'op':'crear','unidad_id':1,'descripcion':'Falla','ubicacion':'Ruta'})
    def test_aprobacion_auditada(self):
        from flota_vales.service import escribir
        r=self.crear()
        with self.conectar() as cx:
            with self.assertRaises(PermissionError): escribir(cx,{'id':2,'rol':'operario'},{'op':'transicion','id':r['id'],'estado':'EN_REPARACION','motivo':'Intento'})
            escribir(cx,{'id':1,'rol':'admin'},{'op':'transicion','id':r['id'],'estado':'APROBADA','motivo':'Autorizado','aprobado':100})
            a=cx.execute("select * from mt_auditoria where entidad='mt_solicitudes' and entidad_id=%s order by id desc limit 1",(str(r['id']),)).fetchone();self.assertEqual(a['nuevo']['estado'],'APROBADA');self.assertEqual(a['usuario_id'],1)
    def test_circuito_factura_diferencia_y_reapertura(self):
        import base64
        from flota_vales.service import escribir,leer
        admin={'id':1,'rol':'admin'}; suc={'id':2,'rol':'operario'}; r=self.crear()
        def call(cx,op,**kw): return escribir(cx,admin,{'op':op,'id':r['id'],**kw})
        with self.conectar() as cx:
            call(cx,'config',datos={'tolerancia_pct':5},motivo='Política de prueba')
            archivos=[]
            for nombre in ['uno.pdf','dos.pdf']:
                archivos.append(call(cx,'adjunto',categoria='presupuesto',nombre=nombre,mime='application/pdf',contenido=base64.b64encode(b'%PDF-1.7\n').decode())['id'])
            call(cx,'transicion',estado='APROBADA',motivo='Autorización',aprobado=100,presupuesto_id=archivos[1])
            call(cx,'transicion',estado='EN_REPARACION',motivo='Inicio')
            call(cx,'reparacion',proveedor='Proveedor demo',diagnostico='Fuga',trabajos='Reparación',inicio='2026-01-01',fin='2026-01-02',real=120)
            call(cx,'transicion',estado='PENDIENTE_DE_FACTURA',motivo='Finalizado')
            call(cx,'validar',motivo='Prueba técnica correcta')
            with self.assertRaises(ValueError): call(cx,'transicion',estado='PENDIENTE_DE_CIERRE',motivo='Sin factura')
            archivo=call(cx,'adjunto',categoria='factura',nombre='factura.pdf',mime='application/pdf',contenido=base64.b64encode(b'%PDF-1.7\n').decode())['id']
            call(cx,'factura',proveedor='Proveedor demo',fiscal='30-12345678-9',tipo='A',numero='0001-000001',fecha='2026-01-02',total=120,adjunto_id=archivo)
            with self.assertRaises(ValueError): call(cx,'transicion',estado='PENDIENTE_DE_CIERRE',motivo='Excede tolerancia')
            call(cx,'autorizar_diferencia',motivo='Se agregó un repuesto')
            call(cx,'transicion',estado='PENDIENTE_DE_CIERRE',motivo='Documentación completa')
            call(cx,'transicion',estado='CERRADA',motivo='Cierre administrativo')
            d=leer(cx,suc,{'op':'detalle','id':r['id']});self.assertEqual(d['estado'],'CERRADA');self.assertEqual(d['factura']['total'],120)
            self.assertEqual(str(d['presupuesto_id']),archivos[1]);self.assertGreater(len(d['historial']),4)
            with self.assertRaises(ValueError): call(cx,'comentario',texto='Modificar cerrado')
            call(cx,'reabrir',motivo='Corrección excepcional');d=leer(cx,suc,{'op':'detalle','id':r['id']});self.assertIsNone(d['aprobacion_id'])
    def test_emergencia_y_checklist(self):
        import base64
        from flota_vales.service import escribir
        admin={'id':1,'rol':'admin'}; suc={'id':2,'rol':'operario'}
        with self.conectar() as cx:
            ch=escribir(cx,suc,{'op':'checklist','unidad_id':1,'respuestas':{'frenos':'revisar'},'resultado':'novedad','descripcion':'Falla de frenos'})
            r=escribir(cx,suc,{'op':'crear','unidad_id':1,'checklist_id':ch['id'],'ubicacion':'Ruta','emergencia':True,'motivo_emergencia':'Riesgo vial','condicion':'inmovilizada'})
            d={'op':'transicion','id':r['id'],'estado':'EN_REPARACION','motivo':'Seguridad'}
            with self.assertRaises(ValueError): escribir(cx,suc,d)
            escribir(cx,suc,{'op':'adjunto','id':r['id'],'categoria':'otro','nombre':'evidencia.pdf','mime':'application/pdf','contenido':base64.b64encode(b'%PDF-1.7\n').decode()})
            escribir(cx,suc,d)
            with self.assertRaises(PermissionError): escribir(cx,suc,{'op':'regularizar','id':r['id'],'motivo':'Intento','aprobado':100})
            escribir(cx,admin,{'op':'regularizar','id':r['id'],'motivo':'Se verificó la emergencia','aprobado':100})
            f=cx.execute('select * from mt_solicitudes where id=%s',(r['id'],)).fetchone();self.assertEqual(f['descripcion'],'Falla de frenos');self.assertEqual(f['regularizacion_id'],1)
