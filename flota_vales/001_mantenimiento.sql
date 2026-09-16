begin;
create table mt_sucursales(id bigint generated always as identity primary key, nombre text not null unique, prefijo text not null unique check(prefijo ~ '^[A-Z]{2,10}$'), secuencia bigint not null default 0, activa boolean not null default true);
create table mt_accesos(usuario_id bigint primary key references usuarios(id), rol text not null check(rol in ('sucursal','mantenimiento','admin')), sucursal_id bigint references mt_sucursales(id), check(rol <> 'sucursal' or sucursal_id is not null));
create table mt_categorias(codigo text primary key, nombre text not null, habilitada boolean not null default false);
insert into mt_categorias values ('larga_distancia','Larga distancia',true),('semirremolque','Semirremolque',true);
alter table unidades add column mantenimiento_sucursal_id bigint references mt_sucursales(id), add column mantenimiento_categoria text references mt_categorias(codigo);
create table mt_config(id boolean primary key default true check(id), datos jsonb not null);
insert into mt_config values(true,'{"umbral_km":null,"lectura_dias":null,"tolerancia_pct":null,"duplicados":"bloquear","max_adjunto_mb":5,"roles_emergencia":["admin"],"roles_diferencia":["admin"],"roles_cierre":["admin"]}');
create table mt_planes(id bigint generated always as identity primary key, nombre text not null, categoria text references mt_categorias(codigo), unidad_id bigint references unidades(id), intervalo numeric not null check(intervalo>0), umbral numeric check(umbral>=0), activo boolean not null default true, check((categoria is null) <> (unidad_id is null)));
create unique index mt_plan_unidad on mt_planes(unidad_id) where activo;
create unique index mt_plan_categoria on mt_planes(categoria) where activo;
create table mt_services(id bigint generated always as identity primary key, unidad_id bigint not null references unidades(id), plan_id bigint references mt_planes(id), fecha date not null, km numeric not null check(km>=0), objetivo numeric not null check(objetivo>km), usuario_id bigint not null references usuarios(id), importado boolean not null default false, cumplido_en_termino boolean, creado timestamptz not null default now());
create table mt_checklists(id bigint generated always as identity primary key, unidad_id bigint not null references unidades(id), sucursal_id bigint not null references mt_sucursales(id), usuario_id bigint not null references usuarios(id), respuestas jsonb not null, resultado text not null check(resultado in ('sin_novedad','novedad')), descripcion text not null default '', creado timestamptz not null default now());
create table mt_solicitudes(id bigint generated always as identity primary key, numero text not null unique, sucursal_id bigint not null references mt_sucursales(id), unidad_id bigint not null references unidades(id), solicitante_id bigint not null references usuarios(id), checklist_id bigint unique references mt_checklists(id), estado text not null default 'BORRADOR' check(estado in ('BORRADOR','PENDIENTE_DE_APROBACION','OBSERVADA','APROBADA','RECHAZADA','EN_REPARACION','PENDIENTE_DE_FACTURA','PENDIENTE_DE_CIERRE','CERRADA','CANCELADA')), descripcion text not null, sintomas text not null default '', urgencia text not null check(urgencia in ('baja','media','alta','critica')), condicion text not null check(condicion in ('operativa','limitada','inmovilizada')), ubicacion text not null, km numeric check(km>=0), proveedor text, tipo_reparacion text, estimado numeric check(estimado>=0), aprobado numeric check(aprobado>=0), presupuesto_id uuid, emergencia boolean not null default false, motivo_emergencia text, aprobacion_id bigint references usuarios(id), aprobacion_fecha timestamptz, primera_respuesta timestamptz, regularizacion_id bigint references usuarios(id), diferencia_id bigint references usuarios(id), diferencia_motivo text, reparacion jsonb not null default '{}', validacion_id bigint references usuarios(id), creado timestamptz not null default now(), actualizado timestamptz not null default now(), cerrado timestamptz, version int not null default 1, check(not emergencia or length(trim(motivo_emergencia))>0));
create index mt_solicitudes_bandeja on mt_solicitudes(sucursal_id,estado,creado);
create table mt_adjuntos(id uuid primary key, solicitud_id bigint not null references mt_solicitudes(id), categoria text not null check(categoria in ('presupuesto','fotografia','factura','diagnostico','otro')), nombre text not null, mime text not null, contenido bytea not null, sha256 text not null, usuario_id bigint not null references usuarios(id), version int not null default 1, reemplaza uuid references mt_adjuntos(id), eliminado boolean not null default false, creado timestamptz not null default now());
alter table mt_solicitudes add foreign key(presupuesto_id) references mt_adjuntos(id);
create table mt_facturas(id bigint generated always as identity primary key, solicitud_id bigint not null unique references mt_solicitudes(id), proveedor text not null, fiscal text not null, tipo text not null, numero text not null, fecha date not null, total numeric not null check(total>0), adjunto_id uuid not null references mt_adjuntos(id), duplicado_motivo text, creado timestamptz not null default now());
create index mt_facturas_duplicados on mt_facturas(fiscal,tipo,numero,total);
create table mt_comentarios(id bigint generated always as identity primary key, solicitud_id bigint not null references mt_solicitudes(id), usuario_id bigint not null references usuarios(id), interno boolean not null default false, texto text not null, creado timestamptz not null default now());
create table mt_auditoria(id bigint generated always as identity primary key, entidad text not null, entidad_id text not null, accion text not null, usuario_id bigint references usuarios(id), anterior jsonb, nuevo jsonb, motivo text, creado timestamptz not null default now());
create index mt_auditoria_entidad on mt_auditoria(entidad,entidad_id,creado);
create table mt_notificaciones(id bigint generated always as identity primary key, solicitud_id bigint references mt_solicitudes(id), sucursal_id bigint references mt_sucursales(id), evento text not null, creado timestamptz not null default now());
create table mt_notificaciones_leidas(notificacion_id bigint references mt_notificaciones(id), usuario_id bigint references usuarios(id), primary key(notificacion_id,usuario_id));
create function mt_numero() returns trigger language plpgsql as $$ declare p text; n bigint; begin
 if TG_OP='UPDATE' then
  if new.numero<>old.numero or new.sucursal_id<>old.sucursal_id or new.unidad_id<>old.unidad_id or new.solicitante_id<>old.solicitante_id then raise exception 'Identidad del vale inmutable'; end if;
  new.actualizado=now(); new.version=old.version+1;
 else
  if new.numero is not null then raise exception 'Número exclusivamente automático'; end if;
  update mt_sucursales set secuencia=secuencia+1 where id=new.sucursal_id and activa returning prefijo,secuencia into p,n;
  if p is null then raise exception 'Sucursal inactiva'; end if;
  new.numero=p||lpad(n::text,greatest(5,length(n::text)),'0');
 end if; return new; end $$;
create trigger mt_numero before insert or update on mt_solicitudes for each row execute function mt_numero();
create function mt_inmutable() returns trigger language plpgsql as $$ begin raise exception 'Registro histórico inmutable'; end $$;
create trigger mt_auditoria_inmutable before update or delete on mt_auditoria for each row execute function mt_inmutable();
create trigger mt_solicitud_no_borrar before delete on mt_solicitudes for each row execute function mt_inmutable();
create function mt_auditar() returns trigger language plpgsql as $$ declare a jsonb; n jsonb; begin
 if TG_OP<>'INSERT' then a=to_jsonb(old)-'contenido'; end if;
 if TG_OP<>'DELETE' then n=to_jsonb(new)-'contenido'; end if;
 insert into mt_auditoria(entidad,entidad_id,accion,usuario_id,anterior,nuevo,motivo) values(TG_TABLE_NAME,coalesce(n->>'id',a->>'id',n->>'usuario_id'),TG_OP,nullif(current_setting('mt.usuario',true),'')::bigint,a,n,current_setting('mt.motivo',true)); return coalesce(new,old); end $$;
do $$ declare t text; begin foreach t in array array['mt_sucursales','mt_accesos','mt_config','mt_planes','mt_services','mt_checklists','mt_solicitudes','mt_adjuntos','mt_facturas','mt_comentarios','odometros'] loop
 execute format('create trigger mt_auditar after insert or update or delete on %I for each row execute function mt_auditar()',t);
 end loop;
 foreach t in array array['mt_sucursales','mt_accesos','mt_categorias','mt_config','mt_planes','mt_services','mt_checklists','mt_solicitudes','mt_adjuntos','mt_facturas','mt_comentarios','mt_auditoria','mt_notificaciones','mt_notificaciones_leidas'] loop execute format('alter table %I enable row level security',t); end loop; end $$;
-- Defensas de integridad independientes de la interfaz y el endpoint.
create function mt_guardar_integridad() returns trigger language plpgsql as $$
declare f mt_facturas; c jsonb;
begin
 if TG_OP='UPDATE' and old.estado in ('CERRADA','CANCELADA','RECHAZADA') and new.estado=old.estado then
  raise exception 'Reabrir antes de modificar un vale finalizado';
 end if;
 if new.estado='EN_REPARACION' and new.aprobacion_id is null then
  if not new.emergencia or coalesce(trim(new.motivo_emergencia),'')='' or not exists(select 1 from mt_adjuntos where solicitud_id=new.id and not eliminado and categoria in ('fotografia','diagnostico','otro')) then
   raise exception 'Ejecución sin aprobación ni emergencia documentada';
  end if;
 end if;
 if new.estado in ('PENDIENTE_DE_CIERRE','CERRADA') then
  select * into f from mt_facturas where solicitud_id=new.id;
  select datos into c from mt_config where id;
  if new.aprobacion_id is null or new.validacion_id is null or f.id is null or not exists(select 1 from mt_adjuntos where id=f.adjunto_id and solicitud_id=new.id and categoria='factura' and not eliminado) then
   raise exception 'Cierre requiere aprobación, validación técnica y factura válida';
  end if;
  if new.emergencia and new.regularizacion_id is null then raise exception 'Emergencia sin regularización'; end if;
  if new.aprobado is null or c->>'tolerancia_pct' is null then raise exception 'Importe o tolerancia sin configurar'; end if;
  if f.total>new.aprobado*(1+(c->>'tolerancia_pct')::numeric/100) and (new.diferencia_id is null or coalesce(trim(new.diferencia_motivo),'')='') then raise exception 'Diferencia sin autorización'; end if;
 end if;
 return new;
end $$;
create trigger mt_integridad before insert or update on mt_solicitudes for each row execute function mt_guardar_integridad();
create function mt_documento_integridad() returns trigger language plpgsql as $$
begin
 if exists(select 1 from mt_solicitudes where id=new.solicitud_id and estado in ('CERRADA','RECHAZADA','CANCELADA')) then raise exception 'Vale finalizado'; end if;
 if TG_TABLE_NAME='mt_facturas' and not exists(select 1 from mt_adjuntos where id=new.adjunto_id and solicitud_id=new.solicitud_id and categoria='factura' and not eliminado) then raise exception 'Factura sin adjunto válido'; end if;
 return new;
end $$;
create trigger mt_factura_integridad before insert or update on mt_facturas for each row execute function mt_documento_integridad();
-- Guardar historial es obligatorio: ni planes, services, lecturas ni documentos se borran.
do $$ declare t text; begin foreach t in array array['mt_services','mt_checklists','mt_adjuntos','mt_facturas','mt_comentarios','mt_planes'] loop
 execute format('create trigger mt_no_borrar before delete on %I for each row execute function mt_inmutable()',t); end loop; end $$;
create table mt_prefijos(prefijo text primary key,sucursal_id bigint not null references mt_sucursales(id));
insert into mt_prefijos select prefijo,id from mt_sucursales;
alter table mt_prefijos enable row level security;
create function mt_reservar_prefijo() returns trigger language plpgsql as $$ begin
 if exists(select 1 from mt_prefijos where prefijo=new.prefijo and sucursal_id<>new.id) then raise exception 'Prefijo reservado por otra sucursal'; end if;
 insert into mt_prefijos values(new.prefijo,new.id) on conflict do nothing; return new; end $$;
create trigger mt_reservar_prefijo after insert or update on mt_sucursales for each row execute function mt_reservar_prefijo();
alter table odometros add column mantenimiento_usuario_id bigint references usuarios(id), add column km_anterior numeric;
create function mt_lectura_contexto() returns trigger language plpgsql as $$ begin
 new.mantenimiento_usuario_id=nullif(current_setting('mt.usuario',true),'')::bigint;
 select km_actual into new.km_anterior from unidades where id=new.unidad_id;
 return new; end $$;
create trigger mt_lectura_contexto before insert or update on odometros for each row execute function mt_lectura_contexto();
create table mt_migraciones(version int primary key, creado timestamptz not null default now());
alter table mt_migraciones enable row level security;
insert into mt_migraciones(version) values(1);
commit;
