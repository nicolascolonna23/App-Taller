import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app  # noqa: F401  (agrega gomeria/ al camino)
import asistente as a
import ensenanzas as e
import permisos

ADMIN = {'id': 1, 'rol': 'admin', 'administra': True}
OPERARIO = {'id': 2, 'rol': 'operario', 'administra': False}


def cx_con(activas=0, devuelve=None):
    """Una conexión de mentira: cuenta activas e inserta."""
    cx = MagicMock()

    def ejecutar(sql, params=()):
        r = MagicMock()
        if 'count(*)' in sql:
            r.fetchone.return_value = {'n': activas}
        else:
            r.fetchone.return_value = devuelve or {'id': 7, 'estado': 'activa'}
            r.rowcount = 1
        return r
    cx.execute.side_effect = ejecutar
    return cx


def respuesta():
    return dict(status='completed', output=[dict(type='message', content=[dict(type='output_text', text='Hay 70.')])])


class Ensenanzas(unittest.TestCase):
    def test_solo_admin_carga_edita_y_borra(self):
        for op in ({'op': 'crear', 'texto': 'abc def'}, {'op': 'editar', 'id': 1, 'texto': 'abc def'},
                   {'op': 'estado', 'id': 1, 'estado': 'activa'}, {'op': 'borrar', 'id': 1}):
            with self.assertRaises(PermissionError):
                e.aplicar(cx_con(), op, OPERARIO)

    def test_propuesta_de_operario_queda_pendiente(self):
        cx = cx_con(devuelve={'id': 3, 'estado': 'pendiente'})
        salida = e.aplicar(cx, {'op': 'proponer', 'texto': 'Goma grande es la 295/80.',
                                'pregunta': 'p', 'respuesta': 'r'}, OPERARIO)
        self.assertEqual(salida['estado'], 'pendiente')
        sql, params = cx.execute.call_args[0]
        self.assertIn("'chat'", sql)
        self.assertEqual(params[2], 'pendiente')
        self.assertIsNone(params[-1])

    def test_propuesta_de_admin_queda_activa(self):
        cx = cx_con()
        e.aplicar(cx, {'op': 'proponer', 'texto': 'Goma grande es la 295/80.'}, ADMIN)
        self.assertEqual(cx.execute.call_args[0][1][2], 'activa')

    def test_tope_de_activas(self):
        with self.assertRaises(ValueError):
            e.aplicar(cx_con(activas=e.ACTIVAS_MAXIMAS), {'op': 'crear', 'texto': 'abc def'}, ADMIN)

    def test_largo_y_vacio(self):
        with self.assertRaises(ValueError):
            e.aplicar(cx_con(), {'op': 'crear', 'texto': '  '}, ADMIN)
        with self.assertRaises(ValueError):
            e.aplicar(cx_con(), {'op': 'crear', 'texto': 'x' * (e.LARGO_MAXIMO + 1)}, ADMIN)

    def test_texto_para_el_modelo(self):
        self.assertEqual(e.texto_para_el_modelo([]), '')
        t = e.texto_para_el_modelo([{'tema': 'Repuestos', 'texto': 'Filtro grande es el de aire.'}])
        self.assertIn('- [Repuestos] Filtro grande es el de aire.', t)
        self.assertIn('prevalece la regla', t)

    def test_titan_recibe_las_ensenanzas(self):
        modelo = MagicMock(side_effect=[
            dict(status='completed', output=[dict(type='function_call', name='consultar_sistema',
                 arguments=json.dumps(dict(dominio='cubiertas', buscar='', estado='', desde='', hasta='')),
                 call_id='c1')]),
            respuesta()])
        fuente = lambda p: dict(fuente='x', url='/gomeria', consultado='2026-10-08', filtros=p,
                                resumen={'cantidad': 1}, registros=[], truncado=False)
        a._responder([{'role': 'user', 'content': 'stock'}], modelo, fuente, '\nENSEÑANZA-PRUEBA')
        self.assertIn('ENSEÑANZA-PRUEBA', modelo.call_args_list[0][0][0]['instructions'])

    def test_sin_base_titan_responde_igual(self):
        with patch.object(a.base, 'conectar', side_effect=SystemExit('sin base')):
            self.assertEqual(a.leer_ensenanzas(), '')

    def test_rutas_protegidas_por_el_modulo_asistente(self):
        self.assertEqual(permisos.modulo_de('/asistente/conocimiento'), 'asistente')
        self.assertEqual(permisos.modulo_de('/api/asistente/ensenanzas'), 'asistente')


if __name__ == '__main__':
    unittest.main()
