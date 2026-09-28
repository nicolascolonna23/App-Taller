import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'gomeria'))
import unidades
import base

ADMIN={'rol':'admin','nombre':'Taller'}
class Conexion:
    def __init__(self,estado='stock'):
        self.estado=estado
        self.sql=[]
    def execute(self,sql,params=()):
        self.sql.append(sql)
        if 'select * from unidades' in sql:r={'id':1,'activa':True,'configuracion_id':1,'patente':'AA472IP'}
        elif 'select 1 from configuracion_posiciones' in sql:r={'existe':1}
        elif 'select * from cubiertas' in sql:r={'id':10,'estado':self.estado,'codigo':'C10','medida':'295/80 R22.5'}
        else:r=None
        cur=Mock();cur.fetchone.return_value=r;return cur

class MesaCubiertas(unittest.TestCase):
    def test_retiro_exige_motivo_antes_de_mutar(self):
        cx=Conexion()
        with patch.object(base,'montaje_abierto',return_value={'cubierta_id':10}),patch.object(base,'sacar_de_servicio') as sacar:
            with self.assertRaisesRegex(ValueError,'motivo'):unidades.mover_cubierta(cx,{'accion':'desmontar','unidad_id':1,'posicion_id':2,'nota':' '},ADMIN)
            sacar.assert_not_called()
    def test_posicion_modificada_rechaza_operacion(self):
        for accion,esperada in [('desmontar',9),('montar',None)]:
            with self.subTest(accion=accion),patch.object(base,'montaje_abierto',return_value={'cubierta_id':10}),patch.object(base,'montar') as montar,patch.object(base,'sacar_de_servicio') as sacar:
                with self.assertRaisesRegex(ValueError,'posición cambió'):unidades.mover_cubierta(Conexion(),{'accion':accion,'unidad_id':1,'posicion_id':2,'cubierta_esperada':esperada,'nota':'Cambio'},ADMIN)
                montar.assert_not_called();sacar.assert_not_called()
    def test_retiro_conserva_motivo_y_destino(self):
        cx=Conexion()
        with patch.object(base,'montaje_abierto',return_value={'cubierta_id':10}),patch.object(base,'sacar_de_servicio') as sacar,patch.object(unidades,'posiciones',return_value=[]):
            unidades.mover_cubierta(cx,{'accion':'desmontar','unidad_id':1,'posicion_id':2,'cubierta_esperada':10,'nota':'Pinchadura','destino':'reparacion'},ADMIN)
            self.assertEqual(sacar.call_args.kwargs['nota'],'Pinchadura');self.assertEqual(sacar.call_args.kwargs['destino'],'reparacion')
            self.assertIn('for update',cx.sql[0])
    def test_no_monta_cubierta_dada_de_baja(self):
        with patch.object(base,'montaje_abierto',return_value=None),patch.object(base,'montar') as montar:
            with self.assertRaisesRegex(ValueError,'no está disponible'):unidades.mover_cubierta(Conexion('baja'),{'accion':'montar','unidad_id':1,'posicion_id':2,'cubierta_id':10},ADMIN)
            montar.assert_not_called()
    def test_no_reemplaza_silenciosamente(self):
        with patch.object(base,'montaje_abierto',return_value={'cubierta_id':10}),patch.object(base,'montar') as montar:
            with self.assertRaisesRegex(ValueError,'ocupada'):unidades.mover_cubierta(Conexion(),{'accion':'montar','unidad_id':1,'posicion_id':2,'cubierta_id':11,'solo_vacia':True},ADMIN)
            montar.assert_not_called()
    def test_consulta_no_puede_mover(self):
        with self.assertRaises(PermissionError):unidades.mover_cubierta(Conexion(),{}, {'rol':'operario'})
if __name__=='__main__':unittest.main()
