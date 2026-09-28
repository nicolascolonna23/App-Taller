/* Shared with the service worker. Never delete a pending report before ACK. */
self.Cola = (() => {
  const db = new Promise((resolve,reject)=>{
    const r=indexedDB.open('taller-choferes',1);
    r.onupgradeneeded=()=>{r.result.createObjectStore('reportes',{keyPath:'id'});r.result.createObjectStore('config');};
    r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);
  });
  async function op(store,method,...args){
    const d=await db;
    return new Promise((resolve,reject)=>{
      const t=d.transaction(store,method.startsWith('get')?'readonly':'readwrite');
      const r=t.objectStore(store)[method](...args);
      t.oncomplete=()=>resolve(r.result);t.onerror=()=>reject(t.error);t.onabort=()=>reject(t.error||new Error('No se pudo guardar.'));
    });
  }
  let active;
  async function send(){
    const r=await fetch('/api/reportes-chofer?op=contexto',{cache:'no-store',redirect:'error'});
    if(!r.ok) throw Error('Iniciá sesión con la cuenta del reporte para enviar.');
    const user=await r.json();
    const pending=await op('reportes','getAll');
    for(const item of pending){
      if(item.usuario_id!==user.usuario_id || item.enviado) continue;
      try {
        const res=await fetch('/api/reportes-chofer',{method:'POST',redirect:'error',headers:{'Content-Type':'application/json'},body:JSON.stringify({...item,op:'recibir'})});
        const ack=await res.json();
        if(!res.ok || ack.id!==item.id || !ack.ok) throw Error(ack.error||'No se confirmó la recepción.');
        await op('reportes','put',{...item,enviado:true,fotos:[],error:null});
      } catch(e){if(e instanceof TypeError)e=new Error('No hay conexión con el servidor.');await op('reportes','put',{...item,error:e.message});throw e;}
    }
  }
  return {op,sync:()=>active||(active=send().finally(()=>active=null))};
})();
