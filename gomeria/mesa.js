/* Mesa de montaje. Clic y arrastre producen el mismo movimiento confirmado. */
let shelf=[],dragged=null,chosenStock=null,movePending=null;
const benchMessage=t=>$('#benchStatus').textContent=t;
const editable=()=>!!D.user?.puede_administrar;
const position=id=>(D.map||[]).find(p=>String(p.posicion_id)===String(id));
/* La goma del inspector. No es un ícono: es lo que el gomero está por
   tocar, así que rueda entera. Los tacos corren por la banda, y todo lo
   que está en la cara —el flanco, las ventanas del disco, las tuercas y
   la válvula— gira junto, que es lo que hace ver que la rueda da vueltas:
   un círculo girando no se distingue de uno quieto. El paso de los tacos
   es el mismo que el desplazamiento de la animación, para que el ciclo
   cierre sin salto. Quien pidió menos movimiento en su sistema no ve
   ninguno: está contemplado en el CSS. */
function tireArt(sufijo){
 const id=sufijo||'';
 const tacos=Array.from({length:16},(_,i)=>`<path d="M${76+i%2*3} ${15+i*12}l32 5 23-8" fill="none" stroke="#111820" stroke-width="5"/>`).join('');
 /* Repartidas en la rueda. Van en el grupo achatado, así que un círculo
    se dibuja como la elipse que se ve desde este ángulo. */
 const enRueda=(cuantas,radio,dibujar)=>Array.from({length:cuantas},(_,i)=>{
  const a=i*2*Math.PI/cuantas;
  return dibujar((radio*Math.cos(a)).toFixed(1),(radio*Math.sin(a)).toFixed(1));}).join('');
 const letras=enRueda(16,40,(x,y)=>`<circle cx="${x}" cy="${y}" r="1.5" fill="#6d7a87"/>`);
 const ventanas=enRueda(5,21,(x,y)=>`<circle cx="${x}" cy="${y}" r="5" fill="#0d1217"/>`);
 const tuercas=enRueda(8,12.5,(x,y)=>`<circle cx="${x}" cy="${y}" r="2.6" fill="#9aa8b3"/>`);
 return `<svg class="tire-art" viewBox="0 0 260 200" aria-label="Neumático" role="img">`
  +`<defs><linearGradient id="rubber${id}" x2="1" y2=".6"><stop stop-color="#56616c"/><stop offset=".5" stop-color="#242b33"/><stop offset="1" stop-color="#10161d"/></linearGradient>`
  +`<clipPath id="banda${id}"><path d="M106 18C42 18 37 171 106 179L155 173C211 167 208 20 155 15Z"/></clipPath></defs>`
  +`<ellipse cx="132" cy="185" rx="75" ry="9" fill="#0003"/>`
  +`<path d="M106 18C42 18 37 171 106 179L155 173C211 167 208 20 155 15Z" fill="url(#rubber${id})" stroke="#6c7884" stroke-width="2"/>`
  +`<g class="tacos" clip-path="url(#banda${id})">${tacos}</g>`
  +`<ellipse cx="157" cy="95" rx="48" ry="79" fill="#20272e" stroke="#5b6873" stroke-width="3"/>`
  +`<g transform="translate(157 95) scale(1 1.72)"><g class="llanta">`
  +letras
  +`<circle r="29" fill="#10151b" stroke="#778590" stroke-width="7"/>`
  +`<circle r="26" fill="#2d363f"/>`
  +ventanas+tuercas
  +`<circle r="7.5" fill="#3a444e" stroke="#7d8a95" stroke-width="1.6"/>`
  +`<rect x="-1.7" y="-35.5" width="3.4" height="7" rx="1.6" fill="#c3ccd4"/>`
  +`</g></g></svg>`;
}

/* El logo de la marca, y el nombre si no hay logo cargado. El servidor
   sirve el que se subió desde Parámetros y, si no hay, el que vino con el
   repositorio; cuando no hay ninguno, el onerror deja el texto. */
function logoMarca(nombre){
 const m=String(nombre||'').trim();if(!m)return '—';
 const slug=m.toLowerCase().replace(/[^a-z0-9]/g,'');
 if(!slug)return esc(m);
 return `<span class="logo-marca" title="${esc(m)}"><img src="/marcas/${esc(slug)}.png" alt="${esc(m)}" onerror="this.closest('.logo-marca').replaceWith(document.createTextNode(${esc(JSON.stringify(m))}))"></span>`;
}
let shelfRequest=0;
async function cargarEstante(){
 const request=++shelfRequest;
 try{const rows=await api('/api/gomeria/stock?buscar='+encodeURIComponent($('#shelfSearch').value));if(request!==shelfRequest)return;shelf=rows;pintarEstante();}
 catch(e){shelf=[];$('#shelfList').textContent=e.message;}
}
function pintarEstante(){
 const q=$('#shelfSearch').value.toLowerCase().trim(),rows=shelf.filter(t=>[t.codigo,t.marca,t.modelo,t.medida].join(' ').toLowerCase().includes(q));
 $('#shelfList').innerHTML=rows.map(t=>`<button class="shelf-item ${String(chosenStock)===String(t.id)?'on':''}" data-stock-id="${t.id}" draggable="${editable()}"><i class="rubber-mini" aria-hidden="true"></i><span><b>${esc(t.codigo)}</b><small>${esc([t.marca,t.modelo].filter(Boolean).join(' · '))}</small><small>${esc(t.medida||'Sin medida')} · ${t.remanente_mm==null?'Sin medir':esc(t.remanente_mm)+' mm'}</small></span></button>`).join('')||'<p class="workbench-help">No hay cubiertas disponibles con este filtro.</p>';
 for(const b of $$('#shelfList [data-stock-id]')){
   b.onclick=()=>{chosenStock=Number(b.dataset.stockId);pintarEstante();pintarInspector();benchMessage('Cubierta seleccionada. Elegí un casillero vacío para montarla.');};
   b.ondragstart=e=>{if(!editable())return e.preventDefault();dragged={tipo:'stock',id:Number(b.dataset.stockId)};e.dataTransfer.setData('application/x-taller-cubierta',JSON.stringify(dragged));e.dataTransfer.effectAllowed='move';gomaDeArrastre(e,shelf.find(x=>String(x.id)===String(b.dataset.stockId))?.codigo);};
   b.ondragend=limpiarArrastre;
 }
}
/* Lo que sigue al mouse mientras se arrastra: una goma con su número de
   fuego, no la ficha entera del listado. El navegador le saca la foto en
   el momento del dragstart, así que el nodo tiene que estar puesto en la
   página —fuera de la pantalla— y se limpia al soltar. */
let fantasma=null;
function gomaDeArrastre(e,codigo){
 fantasma?.remove();
 fantasma=document.createElement('div');
 fantasma.className='goma-arrastre';
 fantasma.innerHTML=tireArt('-arrastre')+`<b>${esc(codigo||'')}</b>`;
 document.body.append(fantasma);
 try{e.dataTransfer.setDragImage(fantasma,48,46);}catch(_){/* el navegador que no la acepta usa la suya */}
}
function limpiarArrastre(){dragged=null;fantasma?.remove();fantasma=null;$$('.drop-ready').forEach(e=>e.classList.remove('drop-ready'));}
function elegirPosicion(id){
 D.benchPosition=id;const p=position(id);if(!p)return;
 if(V.render&&!p.es_auxilio){const eje=V.ejes.findIndex((_,i)=>ejeDelMapa(i+1)===p.eje)+1;if(eje)elegirEsquina(esquina(eje,p.lado));}
 $$('.tire[data-pos]').forEach(b=>b.classList.toggle('chosen',String(b.dataset.pos)===String(id)));
 if(p.cubierta_id)chosenStock=null;
 pintarEstante();pintarInspector();
}
function pintarInspector(){
 const p=position(D.benchPosition),t=shelf.find(t=>String(t.id)===String(chosenStock));
 const mounted=p?.cubierta_id&&!t;
 const code=t?.codigo||(mounted?p.cubierta:null);
 $('#tireInspector').innerHTML=`<h3>${code?'Cubierta '+esc(code):'Neumático seleccionado'}</h3>${tireArt()}<p class="workbench-help">${t?'En stock · lista para montar':p?esc(fmtPat(D.selected)+' · '+p.posicion)+(mounted?' · Montada':' · Posición vacía'):'Elegí una cubierta del stock o una posición del vehículo.'}</p>${(t||mounted)?`<div class="details"><div class="detail"><span>Marca</span><b>${logoMarca((t||p).marca)}</b></div><div class="detail"><span>Medida</span><b>${esc((t||p).medida||'—')}</b></div><div class="detail"><span>Remanente</span><b>${(t||p).remanente_mm==null?'—':esc((t||p).remanente_mm)+' mm'}</b></div><div class="detail"><span>Posición</span><b>${p?esc(p.posicion):'Elegir'}</b></div></div>`:''}${editable()&&t?'<button class="btn" id="mountSelected">Montar en posición elegida</button>':''}${editable()&&mounted?'<button class="btn" id="removeSelected">Retirar cubierta</button>':''}${code?'<button class="btn alt" id="inspectTire">Ver historial y mediciones</button>':''}<p class="workbench-help">${editable()?'También podés arrastrar entre el stock y los casilleros.':'Consulta: tu rol no permite cambiar cubiertas.'}</p>`;
 if($('#mountSelected'))$('#mountSelected').onclick=()=>{if(!p)return benchMessage('Primero elegí un casillero vacío debajo del modelo.');proponerMontaje(t.id,p);};
 if($('#removeSelected'))$('#removeSelected').onclick=()=>proponerRetiro(p);
 if($('#inspectTire'))$('#inspectTire').onclick=()=>openTire(t?.id||p.cubierta_id);
}
function engancharMesa(){
 for(const b of $$('[data-ver-pos]'))b.onclick=()=>{elegirPosicion(b.dataset.verPos);$('#visor')?.scrollIntoView({behavior:'smooth',block:'center'});};
 for(const b of $$('.tire[data-pos]')){
   const p=position(b.dataset.pos);b.onclick=()=>elegirPosicion(b.dataset.pos);
   b.draggable=!!(editable()&&p?.cubierta_id);
   b.ondragstart=e=>{if(!p?.cubierta_id||!editable())return e.preventDefault();dragged={tipo:'montada',posicion_id:p.posicion_id,cubierta_id:p.cubierta_id,unidad_id:D.unidadId};e.dataTransfer.setData('application/x-taller-cubierta',JSON.stringify(dragged));e.dataTransfer.effectAllowed='move';gomaDeArrastre(e,p.cubierta);};
   b.ondragend=limpiarArrastre;
   b.ondragover=e=>{if(editable()&&dragged?.tipo==='stock'&&!p?.cubierta_id){e.preventDefault();b.classList.add('drop-ready');}};
   b.ondragleave=()=>b.classList.remove('drop-ready');
   b.ondrop=e=>{e.preventDefault();b.classList.remove('drop-ready');if(dragged?.tipo==='stock')proponerMontaje(dragged.id,p);limpiarArrastre();};
 }
}
function arrastrarRueda3d(e,esq){
 if(!editable())return false;
 const positions=posicionesDe(esq),selected=position(D.benchPosition),p=positions.length===1?positions[0]:positions.find(p=>p===selected);
 elegirEsquina(esq);
 if(!p){benchMessage('Eje dual: elegí primero el casillero interior o exterior y después arrastrá la rueda.');return false;}
 if(!p.cubierta_id){benchMessage('Esa posición está vacía.');return false;}
 elegirPosicion(p.posicion_id);dragged={tipo:'montada',posicion_id:p.posicion_id,cubierta_id:p.cubierta_id,unidad_id:D.unidadId};e.dataTransfer.setData('application/x-taller-cubierta',JSON.stringify(dragged));e.dataTransfer.effectAllowed='move';gomaDeArrastre(e,p.cubierta);return true;
}
function soltarEnRueda3d(e,esq){
 if(!editable()||dragged?.tipo!=='stock')return;
 elegirEsquina(esq);const available=posicionesDe(esq).filter(p=>!p.cubierta_id),id=dragged.id;limpiarArrastre();
 if(!available.length)return benchMessage('Esa rueda no tiene posiciones vacías. Retirá primero la cubierta con su motivo.');
 proponerMontaje(id,available[0],available);
}
function proponerMontaje(id,p,opciones){
 if(!editable()||!p)return;
 if(p.cubierta_id)return benchMessage('La posición está ocupada. Retirá primero la cubierta indicando el motivo.');
 const t=shelf.find(t=>String(t.id)===String(id));if(!t)return benchMessage('La cubierta ya no figura disponible. Actualizá el stock.');
 abrirMovimiento({accion:'montar',unidad_id:D.unidadId,posicion_id:p.posicion_id,cubierta_id:t.id,cubierta_esperada:null,solo_vacia:true},`Montar ${t.codigo}`,`En ${fmtPat(D.selected)} · ${p.posicion}`,opciones||[p]);
}
function proponerRetiro(p){
 if(!editable()||!p?.cubierta_id)return;
 abrirMovimiento({accion:'desmontar',unidad_id:D.unidadId,posicion_id:p.posicion_id,cubierta_esperada:p.cubierta_id},`Retirar ${p.cubierta}`,`De ${fmtPat(D.selected)} · ${p.posicion}`);
}
function abrirMovimiento(data,title,subtitle,options){
 movePending=data;
 $('#movementTitle').textContent=title;$('#movementSubtitle').textContent=subtitle;
 $('#movementFields').innerHTML=options?`<label for="movementPosition">Posición exacta</label><select id="movementPosition">${options.map(p=>`<option value="${p.posicion_id}">${esc(p.posicion)} · vacía</option>`).join('')}</select><label for="movementNote">Observación (opcional)</label><textarea id="movementNote" maxlength="300"></textarea>`:`<label for="movementDestination">Destino de la cubierta</label><select id="movementDestination"><option value="stock">Stock · disponible para usar</option><option value="reparacion">Reparación</option><option value="recapado">Recapado</option><option value="baja">Baja definitiva</option></select><label for="movementNote">Motivo del retiro (obligatorio)</label><textarea id="movementNote" required maxlength="300" placeholder="Ej.: cambio por desgaste, pinchadura, rotación…"></textarea>`;
 $('#movementError').textContent='';$('#movementSave').disabled=false;$('#movementDialog').showModal();
}
const dlg=document.createElement('dialog');dlg.id='movementDialog';dlg.className='modal move-dialog';dlg.innerHTML='<form id="movementForm"><h2 id="movementTitle"></h2><p id="movementSubtitle" class="sub"></p><div id="movementFields"></div><p id="movementError" class="error" role="alert"></p><div class="actions"><button class="btn alt" type="button" id="movementCancel">Cancelar</button><button class="btn" id="movementSave">Confirmar movimiento</button></div></form>';document.body.append(dlg);
$('#movementCancel').onclick=()=>dlg.close();
dlg.oncancel=e=>{if($('#movementSave').disabled)e.preventDefault();};
$('#movementForm').onsubmit=async e=>{
 e.preventDefault();if(!movePending)return;const note=$('#movementNote').value.trim();
 if(movePending.accion==='desmontar'&&!note){$('#movementError').textContent='Indicá el motivo del retiro.';return;}
 const data={...movePending,nota:note};if($('#movementDestination'))data.destino=$('#movementDestination').value;if($('#movementPosition'))data.posicion_id=Number($('#movementPosition').value);
 $('#movementSave').disabled=true;$('#movementCancel').disabled=true;
 try{await api('/api/gomeria/posicion',data);dlg.close();chosenStock=null;await dashboard();await loadStock();benchMessage('Movimiento guardado. Se actualizaron el mapa, el stock y el historial.');}
 catch(e){$('#movementError').textContent=e.message;}
 finally{$('#movementSave').disabled=false;$('#movementCancel').disabled=false;}
};
let shelfTimer;
$('#shelfSearch').oninput=()=>{clearTimeout(shelfTimer);shelfTimer=setTimeout(cargarEstante,200);};
$('#returnStock').ondragover=e=>{if(editable()&&dragged?.tipo==='montada'){e.preventDefault();$('#returnStock').classList.add('drop-ready');}};
$('#returnStock').ondragleave=()=>$('#returnStock').classList.remove('drop-ready');
$('#returnStock').ondrop=e=>{e.preventDefault();if(dragged?.tipo==='montada'&&dragged.unidad_id===D.unidadId){const p=position(dragged.posicion_id);if(p?.cubierta_id===dragged.cubierta_id)proponerRetiro(p);}limpiarArrastre();};
document.addEventListener('dragend',limpiarArrastre);
