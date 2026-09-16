#!/usr/bin/env python3
"""Ejecuta las cinco pruebas PostgreSQL en una base explícita o Docker temporal."""
import importlib.util
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TESTS = [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
         '-p', 'test_vales_postgres.py', '-v']


def main():
    if importlib.util.find_spec('psycopg') is None:
        print('Falta psycopg. Instalá las dependencias con:', file=sys.stderr)
        print(f'{sys.executable} -m pip install -r requirements.txt', file=sys.stderr)
        return 1
    env = os.environ.copy()
    if env.get('MT_TEST_DATABASE_URL'):
        print('Ejecutando las cinco pruebas en la base de prueba indicada.', flush=True)
        return subprocess.run(TESTS, cwd=ROOT, env=env).returncode

    docker = shutil.which('docker')
    if not docker:
        mac = Path('/Applications/Docker.app/Contents/Resources/bin/docker')
        if mac.exists():
            docker = str(mac)
    if not docker:
        print('Abrí Docker Desktop o definí MT_TEST_DATABASE_URL con una base de prueba.', file=sys.stderr)
        return 1
    estado = subprocess.run([docker, 'info'], capture_output=True, text=True)
    if estado.returncode:
        print('Docker no está disponible. Abrí Docker Desktop y esperá a que indique que está iniciado.', file=sys.stderr)
        print('Luego repetí: python3 scripts/probar_mantenimiento.py', file=sys.stderr)
        return 1

    name = 'mantenimiento-test-' + secrets.token_hex(6)
    password = secrets.token_urlsafe(24)
    docker_env = {**env, 'POSTGRES_PASSWORD': password}
    print('Preparando PostgreSQL 17 temporal (puede descargar la imagen)…', flush=True)
    creado = False
    try:
        run = subprocess.run([docker, 'run', '--rm', '-d', '--name', name,
                              '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_DB=flota_test',
                              '-p', '127.0.0.1::5432', 'postgres:17-alpine'],
                             env=docker_env, stdout=subprocess.PIPE, text=True)
        if run.returncode:
            return run.returncode
        creado = True
        puerto = subprocess.check_output([docker, 'port', name, '5432/tcp'], text=True).strip().rsplit(':', 1)[1]
        for _ in range(45):
            ready = subprocess.run([docker, 'exec', name, 'pg_isready', '-U', 'postgres', '-d', 'flota_test'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            print('PostgreSQL no inició a tiempo.', file=sys.stderr)
            return 1
        env['MT_TEST_DATABASE_URL'] = f'postgresql://postgres:{password}@127.0.0.1:{puerto}/flota_test'
        print('Ejecutando cinco pruebas de integración en la base temporal…', flush=True)
        return subprocess.run(TESTS, cwd=ROOT, env=env).returncode
    finally:
        if creado:
            print('Deteniendo y eliminando el contenedor de esta prueba…', flush=True)
            subprocess.run([docker, 'stop', name], stdout=subprocess.DEVNULL, check=False)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except subprocess.SubprocessError as error:
        print(f'No se pudo completar la prueba: {error}', file=sys.stderr)
        sys.exit(1)
