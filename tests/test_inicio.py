from datetime import date, timedelta
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from gomeria.inicio import _resumir_km


class Inicio(unittest.TestCase):
    def test_pengui_introduction_without_inventing_data(self):
        respuesta=app.asistente.responder({'mensajes':[{'role':'user','content':'¿Quién sos?'}]}, {'id':1,'rol':'admin'})
        self.assertIn('Pengui, el asistente de IA',respuesta['respuesta'])
        self.assertEqual(respuesta['fuentes'],[])

    def test_stationary_is_zero_not_missing(self):
        hoy = date(2026, 9, 8)
        rows = [dict(unidad_id=1, fecha=hoy-timedelta(days=d), km=100) for d in (2, 1)]
        self.assertEqual(_resumir_km(rows, hoy)['ayer']['km'], 0)
        self.assertIsNone(_resumir_km([], hoy)['ayer']['km'])

    def test_reset_gap_and_impossible_jump_are_excluded(self):
        rows = [dict(unidad_id=1, fecha=date(2026,9,d), km=km)
                for d, km in [(1,1000),(2,1100),(3,10),(4,60),(6,200),(7,8000)]]
        result = _resumir_km(rows, date(2026,9,8))
        self.assertEqual(result['semana']['km'], 150)
        self.assertEqual(result['semana']['unidades_completas'], 0)
        self.assertFalse(result['semana']['comparar'])

    def test_compare_requires_same_fleet_and_full_coverage(self):
        hoy=date(2026,9,8)
        rows=[dict(unidad_id=1,fecha=hoy-timedelta(days=d),km=10000-d*100)
              for d in range(16)]
        self.assertTrue(_resumir_km(rows,hoy)['semana']['comparar'])
        rows.append(dict(unidad_id=2,fecha=hoy-timedelta(days=2),km=100))
        rows.append(dict(unidad_id=2,fecha=hoy-timedelta(days=1),km=150))
        self.assertFalse(_resumir_km(rows,hoy)['semana']['comparar'])

    def test_shared_assets_only_on_authenticated_html(self):
        handler=object.__new__(app.App)
        handler.usuario={'id':1}
        with patch.object(app.gom.Handler, '_responder') as send:
            handler._responder(b'<html><head></head><body></body></html>', 'text/html')
            self.assertIn('/pengui.js',send.call_args.args[0])
            self.assertIn('/sistema.css',send.call_args.args[0])
        handler.usuario=None
        with patch.object(app.gom.Handler, '_responder') as send:
            handler._responder('login', 'text/html')
            self.assertEqual(send.call_args.args[0],'login')

if __name__=='__main__':
    unittest.main()
