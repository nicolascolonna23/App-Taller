-- AE 988 UW deja de formar parte de la flota activa.
-- Se conserva la fila para no destruir su historial de odómetros, órdenes,
-- services, vencimientos y cubiertas. Para el sistema equivale a eliminarla:
-- ya no aparece ni cuenta en ningún módulo operativo.
update unidades
set activa = false, actualizado = now()
where patente = 'AE988UW';
