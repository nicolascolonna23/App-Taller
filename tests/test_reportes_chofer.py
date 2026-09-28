import base64
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'gomeria'))
import reportes_chofer as r
import vencimientos as v

CHOFER={'id':2,'nombre':'Ana','modulos':['choferes'],'sucursal_codigo':'CAT','gestiona':False}
GESTOR={'id':1,'nombre':'Taller','modulos':['solicitudes','ordenes'],'gestiona':True}
ID='00112233-4455-4677-8899-aabbccddeeff'

class Reportes(unittest.TestCase):
    def test_sin_permiso_no_consulta(self):
        cx=Mock()
        with self.assertRaises(PermissionError):r.contexto(cx,{'id':4,'modulos':[]})
        cx.execute.assert_not_called()
    def test_no_envia_pendiente_de_otra_cuenta(self):
        cx=Mock()
        with self.assertRaises(ValueError):r.recibir(cx,CHOFER,{'usuario_id':1})
        cx.execute.assert_not_called()
    def test_reintento_no_inserta(self):
        cx=Mock();cx.execute.return_value.fetchone.return_value={'usuario_id':2}
        self.assertEqual(r.recibir(cx,CHOFER,{'usuario_id':2,'id':ID})['id'],ID)
        self.assertEqual(cx.execute.call_count,2)
        self.assertNotIn('insert',str(cx.execute.call_args_list))
    def test_no_roba_identificador(self):
        cx=Mock();cx.execute.return_value.fetchone.return_value={'usuario_id':9}
        with self.assertRaises(PermissionError):r.recibir(cx,CHOFER,{'usuario_id':2,'id':ID})
    def test_fotos_rechazan_html_y_exceso(self):
        for fotos in ([{'mime':'image/jpeg','datos':base64.b64encode(b'<html>').decode()}], [{}]*4, [{'mime':'image/png','datos':'?'}]):
            with self.assertRaises(ValueError):r.validar_fotos(fotos)
    def test_chofer_no_resuelve(self):
        with self.assertRaises(PermissionError):r.resolver(Mock(),CHOFER,{'id':ID,'op':'desestimar'})
    def test_ot_reintentada_no_duplica(self):
        with patch.object(r,'obtener',return_value={'estado':'ORDEN_CREADA','orden_id':42}),patch.object(r.ordenes,'abrir') as abrir:
            self.assertEqual(r.resolver(Mock(),GESTOR,{'id':ID,'op':'crear_orden'})['orden_id'],42)
            abrir.assert_not_called()
    def test_desestimar_exige_motivo(self):
        with patch.object(r,'obtener',return_value={'estado':'PENDIENTE'}):
            with self.assertRaises(ValueError):r.resolver(Mock(),GESTOR,{'id':ID,'op':'desestimar','motivo':' '})
    def test_ot_km_invalido(self):
        with patch.object(r,'obtener',return_value={'estado':'PENDIENTE'}):
            for km in ('NaN','Infinity','-1','1.5'):
                with self.assertRaises(ValueError):r.resolver(Mock(),GESTOR,{'id':ID,'op':'crear_orden','km':km})
    def test_fotos_ajenas_no_se_leen(self):
        cx=Mock();cx.execute.return_value.fetchone.return_value={'usuario_id':3,'sucursal':'CAT'}
        with self.assertRaises(PermissionError):r.fotos(cx,CHOFER,ID)
        self.assertEqual(cx.execute.call_count,1)

class Vencimientos(unittest.TestCase):
    def test_fin_de_mes_y_bisiesto(self):
        self.assertEqual(v._sumar_meses(date(2024,1,31),1),date(2024,2,29))
        self.assertEqual(v._sumar_meses(date(2024,2,29),12),date(2025,2,28))
    def test_fecha_fuera_de_rango_no_bloquea(self):
        with self.assertRaises(ValueError):v._sumar_meses(date(9999,12,31),12)
    def test_parametros_invalidos(self):
        for dias,meses in [(-1,12),(1.5,12),(True,12),(30,0),(30,121)]:
            cx=Mock()
            with self.assertRaises(ValueError):v.configurar_tipo(cx,{'tipo_id':1,'aviso_dias':dias,'meses':meses},GESTOR)
            cx.execute.assert_not_called()
    def test_fecha_aviso_no_posterior(self):
        cx=Mock();cx.execute.return_value.fetchone.return_value={'meses':12,'ambito':'unidad'}
        with self.assertRaises(ValueError):v.guardar(cx,{'tipo_id':1,'vence':'2026-10-01','aviso_fecha':'2026-10-02'},GESTOR)
        self.assertEqual(cx.execute.call_count,1)
    def test_solo_gestor_configura(self):
        with self.assertRaises(PermissionError):v.configurar_tipo(Mock(),{},CHOFER)

if __name__=='__main__':unittest.main()
