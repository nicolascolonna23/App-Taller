-- =====================================================================
-- SESIONES GUARDADAS COMO HASH
-- ---------------------------------------------------------------------
-- La app ya guarda las sesiones nuevas como hash del token, y las viejas
-- las pasa a hash la primera vez que se usan. Este script hace lo mismo
-- con todas de una vez, así no queda ningún token en claro en la tabla
-- esperando a que su dueño vuelva. Nadie pierde la sesión.
--
-- Se pega en Supabase → SQL Editor → New query → Run. Se puede correr
-- más de una vez: lo que ya es hash no se toca.
-- =====================================================================

update sesiones
set token = encode(sha256(convert_to(token, 'UTF8')), 'hex')
where token !~ '^[0-9a-f]{64}$';
