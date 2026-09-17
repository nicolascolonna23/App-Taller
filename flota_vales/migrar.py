"""Aplicación explícita, transaccional y versionada. No se ejecuta al iniciar la app."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'gomeria'))
import base

def main():
    with base.conectar() as cx:
        cx.execute("select pg_advisory_xact_lock(hashtextextended('migracion_mantenimiento',0))")
        existe=cx.execute("select to_regclass('mt_migraciones') as t").fetchone()['t']
        if existe and cx.execute('select 1 from mt_migraciones where version=1').fetchone():
            print('Mantenimiento ya está actualizado.'); return
        # La transacción de conexión abarca todo el script.
        sql=Path(__file__).with_name('001_mantenimiento.sql').read_text()
        cx.execute(sql.replace('begin;','',1).rsplit('commit;',1)[0])
    print('Migración 1 aplicada. Configurá sucursales, permisos y unidades antes de operar.')

if __name__=='__main__': main()
