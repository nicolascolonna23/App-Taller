'use strict';
const $=s=>document.querySelector(s);
let account=null, photos=[], recording=null, busy=false;
const status=m=>$('#status').textContent=m;
async function render(){
 const rows=(await Cola.op('reportes','getAll')).filter(r=>r.usuario_id===account?.usuario_id).reverse();
 $('#pending').replaceChildren();
 for(const r of rows){
   const a=document.createElement('article'),h=document.createElement('strong'),p=document.createElement('p');
   h.textContent=r.enviado?'Enviado al taller':'Pendiente de envío';p.textContent=r.descripcion;
   a.append(h,p);const small=document.createElement('small');small.textContent=new Date(r.ocurrido_en).toLocaleString()+(r.error?' · '+r.error:'');a.append(small);$('#pending').append(a);
 }
}
async function context(){
 try{
   const r=await fetch('/api/reportes-chofer?op=contexto',{cache:'no-store',redirect:'error'});
   if(!r.ok){const e=new Error('Iniciá sesión con una cuenta habilitada para choferes.');e.auth=true;throw e;}
   account=await r.json();await Cola.op('config','put',account,'cuenta');
 }catch(e){
   if(e.auth){account=null;status(e.message);return;}
   account=await Cola.op('config','get','cuenta');
   if(!account){status('Conectate e iniciá sesión una vez antes de usar la app sin señal.');return;}
   status('Sin conexión verificada. Los reportes quedarán pendientes para '+account.nombre+'.');
 }
 $('#session').textContent='Cuenta: '+account.nombre;
 $('#unit').replaceChildren(new Option('Elegí una unidad',''));
 for(const u of account.unidades)$('#unit').add(new Option(u.patente+(u.interno?' · '+u.interno:''),u.id));
 $('#save').disabled=false;await render();
}
async function sync(){
 if(busy||!navigator.onLine)return;
 busy=true;$('#sync').disabled=true;
 try{await Cola.sync();status('Envíos verificados. Los reportes confirmados figuran como enviados.');}
 catch(e){status((e instanceof TypeError?'No hay conexión con el servidor.':e.message)+' Los pendientes se conservan en este teléfono.');}
 finally{busy=false;$('#sync').disabled=false;await render();}
}
async function photo(file){
 if(file.size>25*1024*1024)throw Error('La foto supera los 25 MB.');
 const bitmap=await createImageBitmap(file),scale=Math.min(1,1600/Math.max(bitmap.width,bitmap.height));
 const c=document.createElement('canvas');c.width=Math.round(bitmap.width*scale);c.height=Math.round(bitmap.height*scale);
 c.getContext('2d').drawImage(bitmap,0,0,c.width,c.height);bitmap.close();
 const url=c.toDataURL('image/jpeg',.8),datos=url.split(',')[1];
 if(datos.length>2796200)throw Error('La foto sigue siendo demasiado grande. Elegí una más pequeña.');
 return {mime:'image/jpeg',datos};
}
function previews(){
 $('#preview').replaceChildren();photos.forEach((p,i)=>{
   const box=document.createElement('div'),img=document.createElement('img'),b=document.createElement('button');
   img.src='data:'+p.mime+';base64,'+p.datos;img.alt='Foto adjunta '+(i+1);b.type='button';b.className='secondary';b.textContent='Quitar foto';b.onclick=()=>{photos.splice(i,1);previews();};box.append(img,b);$('#preview').append(box);
 });
}
let processing=false;
async function addPhotos(e){
 if(processing)return;processing=true;$('#save').disabled=true;
 try{
 const files=[...e.target.files];if(photos.length+files.length>3)throw Error('Podés adjuntar hasta 3 fotos.');
 const converted=[];for(const f of files)converted.push(await photo(f));photos.push(...converted);previews();
 }catch(e){status(e.message);}finally{processing=false;e.target.value='';$('#save').disabled=!account;}
}
$('#photos').onchange=addPhotos;$('#camera').onchange=addPhotos;
$('#report').onsubmit=async e=>{
 e.preventDefault();if(!account||processing)return;$('#save').disabled=true;
 try{
 const item={id:crypto.randomUUID(),usuario_id:account.usuario_id,unidad_id:Number($('#unit').value),descripcion:$('#description').value.trim(),urgencia:$('#urgency').value,ocurrido_en:new Date().toISOString(),fotos:photos};
 if(!item.descripcion)throw Error('Describí la falla.');
 await Cola.op('reportes','put',item);
 $('#report').reset();photos=[];previews();status('Reporte guardado en el teléfono. Pendiente de confirmación del taller.');await render();
 if('serviceWorker' in navigator){const reg=await navigator.serviceWorker.getRegistration('/choferes/');if(reg?.sync)await reg.sync.register('reportes-chofer').catch(()=>{});}
 await sync();
 }catch(e){status('No se pudo completar: '+e.message);}finally{$('#save').disabled=false;}
};
$('#dictate').onclick=()=>{
 const Speech=window.SpeechRecognition||window.webkitSpeechRecognition;
 if(!Speech){status('Usá el micrófono del teclado para dictar en este teléfono.');$('#description').focus();return;}
 if(recording){recording.stop();return;}
 recording=new Speech();recording.lang='es-AR';recording.interimResults=false;
 recording.onresult=e=>{$('#description').value=($('#description').value+' '+e.results[0][0].transcript).trim().slice(0,2000);};
 recording.onerror=()=>status('No se pudo dictar. Revisá el permiso del micrófono y la conexión, o usá el teclado.');
 recording.onend=()=>{recording=null;$('#dictate').textContent='Dictar por voz';};
 try{recording.start();$('#dictate').textContent='Detener dictado';}catch(e){recording=null;status(e.message);}
};
$('#sync').onclick=sync;window.addEventListener('online',sync);window.addEventListener('offline',()=>status('Sin conexión. Podés guardar la falla y sus fotos.'));
document.addEventListener('visibilitychange',()=>{if(!document.hidden)sync();});
setInterval(()=>{if(!document.hidden)sync();},30000);
(async()=>{
 $('#save').disabled=true;
 if('serviceWorker' in navigator)await navigator.serviceWorker.register('/choferes/sw.js').catch(()=>status('No se pudo preparar el uso sin conexión. Revisá la conexión y volvé a abrir.'));
 await context();
 if(account&&navigator.onLine)await sync();
})().catch(e=>status('No se pudo abrir el almacenamiento del teléfono: '+e.message));
