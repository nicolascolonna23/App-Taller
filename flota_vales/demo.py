"""Demo únicamente en una base explícita con nombre de prueba/demo/desarrollo."""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'gomeria'))
import psycopg
from psycopg.rows import dict_row
import auth
from flota_vales.service import escribir

def main():
    url=os.environ.get('MT_DEMO_DATABASE_URL','')
    name=urlparse(url).path.lower()
    if not url or not any(x in name for x in ('test','demo','dev')):
        raise SystemExit('Usá MT_DEMO_DATABASE_URL con una base de demostración (test/demo/dev).')
    clave=os.environ.get('MT_DEMO_PASSWORD')
    if not clave: raise SystemExit('Definí MT_DEMO_PASSWORD; no se distribuyen contraseñas fijas.')
    with psycopg.connect(url,row_factory=dict_row) as cx:
        if cx.execute("select 1 from usuarios where usuario='demo.flota'").fetchone(): raise SystemExit('La demo ya existe.')
        id=auth.crear_usuario(cx,'demo.flota','Administrador demo',clave,'admin'); u={'id':id,'rol':'admin'}
        escribir(cx,u,{'op':'sucursal','nombre':'Sucursal demostración','prefijo':'DEMO','motivo':'Datos aislados de prueba'})
        b=cx.execute("select id from mt_sucursales where prefijo='DEMO'").fetchone()['id']
        v=cx.execute("insert into unidades(patente,mantenimiento_sucursal_id,mantenimiento_categoria,km_actual) values('DEMO001',%s,'larga_distancia',10000) returning id",(b,)).fetchone()['id']
        escribir(cx,u,{'op':'crear','unidad_id':v,'descripcion':'Ejemplo: pérdida de aire','ubicacion':'Base de demostración','urgencia':'alta','condicion':'inmovilizada'})
    print('Demo creada; ingresá como demo.flota con la contraseña suministrada.')

if __name__=='__main__': main()
