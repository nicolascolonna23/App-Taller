import unittest
from decimal import Decimal
from flota_vales.service import estado_preventivo, importe, cierre_valido, validar_archivo, propia, TRANSICIONES
import base64

class Reglas(unittest.TestCase):
    def test_objetivo_y_limites(self):
        for km,estado,falta in [(900,'normal',100),(950,'proximo',50),(1000,'vencido',0),(1001,'vencido',-1)]:
            self.assertEqual(estado_preventivo(km,1000,50),(estado,Decimal(falta)))
        self.assertEqual(estado_preventivo(None,1000,50),('sin_datos',None))
    def test_no_inventa_umbral(self):
        self.assertEqual(estado_preventivo(999,1000,None)[0],'normal')
    def test_importes(self):
        for x in ['NaN','Infinity','-1','0.001','abc']:
            with self.assertRaises(ValueError): importe(x)
        self.assertEqual(importe('12.30'),Decimal('12.30'))
    def test_roles_y_finales(self):
        self.assertNotIn('sucursal',TRANSICIONES['PENDIENTE_DE_APROBACION']['APROBADA'])
        self.assertNotIn('EN_REPARACION',TRANSICIONES['BORRADOR'])
        for s in ['CERRADA','CANCELADA','RECHAZADA']: self.assertNotIn(s,TRANSICIONES)
    def test_visibilidad(self):
        self.assertFalse(propia({'rol':'sucursal','sucursal_id':1},{'sucursal_id':2}))
        self.assertTrue(propia({'rol':'mantenimiento','sucursal_id':None},{'sucursal_id':2}))
    def base(self):
        return {'aprobacion_id':1,'validacion_id':1,'emergencia':False,'aprobado':Decimal('100'),'diferencia_id':None,'diferencia_motivo':None}
    def test_cierre(self):
        r=self.base();cfg={'tolerancia_pct':10}
        cierre_valido(r,{'total':110},cfg)
        for f in [None,{'total':111}]:
            with self.assertRaises(ValueError): cierre_valido(r,f,cfg)
        r['diferencia_id']=2;r['diferencia_motivo']='Repuesto adicional';cierre_valido(r,{'total':111},cfg)
        for key in ['aprobacion_id','validacion_id']:
            b={**r,key:None}
            with self.assertRaises(ValueError): cierre_valido(b,{'total':100},cfg)
    def test_emergencia_regularizacion(self):
        r={**self.base(),'emergencia':True,'regularizacion_id':None,'motivo_emergencia':'Seguridad'}
        with self.assertRaises(ValueError): cierre_valido(r,{'total':100},{'tolerancia_pct':0})
        r['regularizacion_id']=1;cierre_valido(r,{'total':100},{'tolerancia_pct':0})
    def test_archivos(self):
        d={'nombre':'factura.pdf','mime':'application/pdf','contenido':base64.b64encode(b'%PDF-1.7\n').decode()}
        self.assertEqual(validar_archivo(d,1)[1],'application/pdf')
        for cambios in [{'mime':'image/png'},{'nombre':'archivo.html'},{'nombre':'../f.pdf'},{'contenido':'!!!'},{'contenido':base64.b64encode(b'<script>').decode()}]:
            with self.assertRaises(ValueError): validar_archivo({**d,**cambios},1)

if __name__=='__main__': unittest.main()
