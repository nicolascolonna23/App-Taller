from datetime import date, timedelta
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from gomeria.inicio import _litros, _rellenar, _resumir_km


class LitrosDeLaPortada(unittest.TestCase):
    """Los litros cargados, mirados por día, por mes y por año.

    El corte que se elige arriba no puede cambiar la suma: son tres lupas
    sobre el mismo dato. Y un período sin cargas es un cero, no un hueco:
    saltearlo apretaría el gráfico y haría ver una semana donde hay un mes.
    """

    class Base:
        """Contesta la consulta del total y la de cada corte."""

        def __init__(self, filas=None, rota=False):
            self.filas = filas or {}
            self.rota = rota
            self.consultas = []

        def rollback(self):
            pass

        def execute(self, consulta, valores=()):
            if self.rota:
                raise RuntimeError('relation "combustible_cargas" does not exist')
            sql = " ".join(consulta.split())
            self.consultas.append(sql)
            if "min(fecha)" in sql:
                return Resultado(self.filas.get("total"))
            for unidad in ("day", "month", "year"):
                if f"date_trunc(\'{unidad}\'" in sql:
                    return Resultado(muchas=self.filas.get(unidad, []))
            raise AssertionError(f"Consulta inesperada: {sql}")

    def test_sin_el_modulo_de_combustible_la_portada_sigue(self):
        self.assertIsNone(_litros(self.Base(rota=True)))

    def test_sin_planillas_subidas_no_inventa_un_cero(self):
        cx = self.Base({"total": {"litros": 0, "cargas": 0, "desde": None, "hasta": None}})
        salida = _litros(cx)
        self.assertEqual(salida["cargas"], 0)
        self.assertEqual(salida["cortes"], {})

    def test_los_tres_cortes_salen_del_mismo_dato(self):
        hoy = date.today()
        cx = self.Base({
            "total": {"litros": 1000, "cargas": 4,
                      "desde": date(2026, 1, 2), "hasta": hoy},
            "day": [{"periodo": hoy, "litros": 300, "cargas": 2,
                     "importe": 500, "unidades": 2}],
            "month": [{"periodo": hoy.replace(day=1), "litros": 700, "cargas": 3,
                       "importe": 900, "unidades": 3}],
            "year": [{"periodo": date(hoy.year, 1, 1), "litros": 1000, "cargas": 4,
                      "importe": 1200, "unidades": 4}],
        })
        salida = _litros(cx)
        self.assertEqual(salida["total"], 1000)
        self.assertEqual(salida["cortes"]["dia"]["actual"]["litros"], 300)
        self.assertEqual(salida["cortes"]["mes"]["actual"]["litros"], 700)
        self.assertEqual(salida["cortes"]["anio"]["actual"]["litros"], 1000)
        # El actual es siempre el último de la serie: es el que se muestra.
        for corte in salida["cortes"].values():
            self.assertEqual(corte["actual"], corte["serie"][-1])

    def test_solo_cuenta_la_planilla_y_no_el_listado_de_la_estacion(self):
        """Sumar los dos sería contar dos veces el mismo litro."""
        cx = self.Base({"total": {"litros": 10, "cargas": 1,
                                  "desde": date(2026, 1, 1), "hasta": date(2026, 1, 1)}})
        _litros(cx)
        self.assertTrue(all("origen = \'planilla\'" in c for c in cx.consultas))

    def test_el_periodo_sin_cargas_va_en_cero_y_no_salteado(self):
        hoy = date(2026, 9, 18)
        serie = _rellenar({"2026-09-18": {"litros": 300, "cargas": 2,
                                          "importe": None, "unidades": 1}},
                          "day", hoy, 30)
        self.assertEqual(len(serie), 30)
        self.assertEqual(serie[-1]["litros"], 300)
        self.assertEqual(serie[0]["periodo"], "2026-08-20")
        self.assertEqual({s["litros"] for s in serie[:-1]}, {0.0})

    def test_los_meses_y_los_anios_tambien_se_rellenan(self):
        hoy = date(2026, 2, 10)
        meses = _rellenar({}, "month", hoy, 12)
        self.assertEqual(len(meses), 12)
        # Doce meses para atrás desde febrero de 2026 es marzo de 2025.
        self.assertEqual(meses[0]["periodo"], "2025-03-01")
        self.assertEqual(meses[-1]["periodo"], "2026-02-01")
        anios = _rellenar({}, "year", hoy, 5)
        self.assertEqual([a["periodo"][:4] for a in anios],
                         ["2022", "2023", "2024", "2025", "2026"])


class Resultado:
    def __init__(self, una=None, muchas=None):
        self.una, self.muchas = una, muchas or []

    def fetchone(self):
        return self.una

    def fetchall(self):
        return self.muchas


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

    def test_daily_series_preserves_gaps_zero_and_total(self):
        rows = [dict(unidad_id=1, fecha=date(2026,9,d), km=km)
                for d, km in [(1,100),(2,180),(3,180),(5,250),(6,310)]]
        result = _resumir_km(rows, date(2026,9,8))['semana']
        self.assertEqual(len(result['serie']), 7)
        self.assertEqual([p['km'] for p in result['serie']], [None,80,0,None,None,60,None])
        self.assertEqual(sum(p['km'] or 0 for p in result['serie']), result['km'])
        self.assertEqual(result['serie'][1]['unidades'], 1)
        self.assertEqual(result['serie'][3]['unidades'], 0)

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

    def test_pengui_only_on_authenticated_home(self):
        handler=object.__new__(app.App)
        handler.usuario={'id':1}
        handler.path='/'
        with patch.object(app.gom.Handler, '_responder') as send:
            handler._responder(b'<html><head></head><body></body></html>', 'text/html')
            self.assertIn('/pengui.js',send.call_args.args[0])
            self.assertIn('/sistema.css',send.call_args.args[0])
        handler.path='/ordenes'
        with patch.object(app.gom.Handler, '_responder') as send:
            handler._responder(b'<html><head></head><body></body></html>', 'text/html')
            self.assertNotIn('/pengui.js',send.call_args.args[0])
            self.assertIn('/sistema.css',send.call_args.args[0])
        handler.usuario=None
        with patch.object(app.gom.Handler, '_responder') as send:
            handler._responder('login', 'text/html')
            self.assertEqual(send.call_args.args[0],'login')

    def test_pengui_not_on_gomeria_despite_the_rewritten_path(self):
        """/gomeria le cambia self.path a "/" para que el manejador de
        Gomería sirva su pantalla. Mirar self.path hacía aparecer al muñeco
        justo encima del mapa de cubiertas."""
        handler=object.__new__(app.App)
        handler.usuario={'id':1}
        handler.ruta_original='/gomeria'
        handler.path='/'                      # como queda después de reescribirla
        with patch.object(app.gom.Handler, '_responder') as send:
            handler._responder(b'<html><head></head><body></body></html>', 'text/html')
            self.assertNotIn('/pengui.js',send.call_args.args[0])

    def test_company_logo_in_every_browser_tab(self):
        """Gomería y Configuración no declaraban el icono y en la solapa se
        veía el globo gris del navegador. Se inyecta como el resto de lo
        compartido, así la pantalla que se agregue mañana no se lo olvida."""
        handler=object.__new__(app.App)
        handler.usuario={'id':1}
        handler.path='/gomeria'
        with patch.object(app.gom.Handler, '_responder') as send:
            handler._responder(b'<html><head></head><body></body></html>', 'text/html')
            self.assertIn('rel="icon" href="/favicon.png"',send.call_args.args[0])

    def test_the_screen_that_already_declares_it_keeps_only_one(self):
        handler=object.__new__(app.App)
        handler.usuario={'id':1}
        handler.path='/alertas'
        propio='<html><head><link rel="icon" href="/favicon.png"></head><body></body></html>'
        with patch.object(app.gom.Handler, '_responder') as send:
            handler._responder(propio.encode(), 'text/html')
            self.assertEqual(send.call_args.args[0].count('rel="icon"'), 1)

if __name__=='__main__':
    unittest.main()
