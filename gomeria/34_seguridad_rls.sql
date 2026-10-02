-- =====================================================================
-- SEGURIDAD: activar RLS en toda tabla que quede sin protección
-- ---------------------------------------------------------------------
-- Supabase avisa "Table publicly accessible" cuando una tabla no tiene
-- Row-Level Security activado: significa que cualquiera con la URL del
-- proyecto puede leer, editar o borrar esa tabla entera a través de la
-- API pública de Supabase (PostgREST), usando la clave "anon".
--
-- Esta app no usa esa API: todo el acceso real pasa por gomeria/base.py,
-- que se conecta directo a Postgres con SUPABASE_DB_URL (el usuario
-- "postgres", que no está sujeto a RLS). Por eso alcanza con activar RLS
-- y no hace falta crear ninguna política: queda todo bloqueado para la
-- API pública y el backend sigue funcionando exactamente igual.
--
-- Se pega entero en Supabase → SQL Editor → New query → Run. Se puede
-- correr las veces que haga falta.
--
-- ---------------------------------------------------------------------
-- POR QUÉ NO HAY UNA LISTA DE TABLAS
-- ---------------------------------------------------------------------
-- Antes esto era una lista escrita a mano, con un "if la tabla existe"
-- alrededor para que el script se pudiera repetir sin romperse. Esa
-- guarda, que parecía prudencia, fue el agujero.
--
-- Lo que pasó: el módulo de vales se renombró a solicitudes de compra
-- —vales.py a solicitudes.py, 26_vales.sql a 26_solicitudes.sql— y esta
-- lista se actualizó a los nombres nuevos. Pero el 26_solicitudes.sql no
-- se corrió en la base de producción, así que las tablas nuevas no
-- existen y las cuatro viejas —vales, vales_ajustes, vale_eventos y
-- vales_contador— siguen ahí. Resultado: la lista nombraba cuatro tablas
-- que no existen, el "if existe" las salteó en silencio, y las cuatro que
-- sí estaban no las nombraba nadie. El script decía "listo" con cuatro
-- tablas abiertas. Un nombre que no existe no da error: no hace nada.
--
-- Una lista de nombres es una copia de algo que la base ya sabe, y las
-- copias se desincronizan. Así que ahora no se nombra ninguna tabla: se
-- le pregunta a la base cuáles le faltan y se cierran todas. Eso no se
-- puede quedar viejo, cubre las tablas que todavía no existen, y una
-- tabla nueva que alguien se olvide de proteger la agarra la próxima vez
-- que esto corra.
--
-- Fallar cerrado es el lado correcto para equivocarse: si alguna vez hace
-- falta una tabla abierta a PostgREST, se nota al primer pedido que no
-- contesta, y es un minuto. Una tabla abierta sin querer no se nota nunca.
--
-- ---------------------------------------------------------------------
-- CUÁNDO CORRERLO
-- ---------------------------------------------------------------------
-- Este archivo es el 34, así que al armar una base desde cero corre antes
-- que el 35 y los que siguen: no puede cerrar tablas que todavía no
-- existen. Por eso cada migración que crea una tabla cierra la suya, y
-- esto es la red, no el único control.
--
-- La red se tira al final: después de correr la última migración, se pega
-- esto de nuevo y tiene que decir "nada que cerrar". Si dice otra cosa,
-- alguna migración se olvidó de su tabla —y ya está cerrada, pero conviene
-- agregarle el alter al archivo que la crea.
-- =====================================================================

do $$
declare
  t      record;
  cuanto integer := 0;
begin
  for t in
    select c.relname as tabla
      from pg_class c
      join pg_namespace s on s.oid = c.relnamespace
     where s.nspname = 'public'
       and c.relkind in ('r', 'p')      -- tablas, normales y particionadas
       and not c.relrowsecurity
       -- Las que trajo una extensión no son nuestras: no se tocan.
       and not exists (select 1 from pg_depend d
                        where d.objid = c.oid and d.deptype = 'e')
     order by c.relname
  loop
    execute format('alter table public.%I enable row level security', t.tabla);
    raise notice 'RLS activado en %', t.tabla;
    cuanto := cuanto + 1;
  end loop;

  -- Que diga qué hizo. Un script de seguridad que corre y no informa nada
  -- es indistinguible de uno que no hizo nada, y fue así como las cuatro
  -- tablas de vales pasaron inadvertidas.
  if cuanto = 0 then
    raise notice 'Nada que cerrar: todas las tablas de public ya tienen RLS.';
  else
    raise notice 'Listo: % tabla(s) cerradas.', cuanto;
  end if;
end $$;
