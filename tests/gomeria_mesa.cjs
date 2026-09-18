const {chromium}=require('playwright');const fs=require('fs'),path=require('path'),assert=require('assert');const root=path.resolve(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--enable-unsafe-swiftshader']});
 try{
 const page=await browser.newPage({viewport:{width:1600,height:1050}}),errors=[],writes=[];let admin=true;
 page.on('pageerror',e=>errors.push(e.message));
 const stock=[{id:103,codigo:'BRI-103',marca:'BRIDGESTONE',modelo:'R268',medida:'295/80 R22.5',remanente_mm:16,estado:'stock'},{id:101,codigo:'MIC-101',marca:'MICHELIN',modelo:'X Multi',medida:'295/80 R22.5',remanente_mm:14,estado:'stock'},{id:102,codigo:'FAT-102',marca:'FATE',modelo:'DR400',medida:'295/80 R22.5',remanente_mm:11,estado:'stock'}];
 const unit={id:1,patente:'AA472IP',marca:'SEMIRREMOLQUE',sucursal:'CAT',posiciones:13,montadas:0};
 const otra={id:2,patente:'AH787DF',interno:'44',marca:'SCANIA',sucursal:'LAD',posiciones:10,montadas:10};
 const map=[];let id=1;for(let eje=1;eje<=3;eje++)for(const lado of ['I','D'])for(const montaje of ['interior','exterior'])map.push({posicion_id:id++,posicion:`${eje}${lado}${montaje==='interior'?'I':'E'}`,eje,lado,montaje,es_auxilio:false,orden:id,cubierta_id:null});map.push({posicion_id:id,posicion:'AUX',eje:0,lado:'X',es_auxilio:true,orden:id,cubierta_id:null});
 Object.assign(map.find(p=>p.posicion==='2DE'),{cubierta_id:319,cubierta:'319',marca:'FATE'});
 await page.route('**/*',route=>{
 const req=route.request(),u=new URL(req.url()),p=u.pathname;
 if(p==='/api/interpretar')return route.fulfill({json:{parte_id:77,propuesta:{resumen:'Montar cubierta',acciones:[{tipo:'montaje',posicion:'2DE',cubierta:'319'}]}}});
 if(p==='/api/confirmar'){assert.equal(req.postDataJSON().parte_id,77);return route.fulfill({json:{hecho:['Movimiento confirmado']}});}
 if(p==='/api/yo')return route.fulfill({json:{nombre:'Prueba',rol:admin?'admin':'operario',puede_administrar:admin}});
 if(p==='/api/preferencias')return route.fulfill({json:{tema:'claro',paleta:'diemar'}});
 if(p==='/api/tablero')return route.fulfill({json:{unidades:[unit,otra],configuraciones:[],resumen_stock:{stock:stock.filter(t=>t.estado==='stock').length}}});
 if(p==='/api/desgaste')return route.fulfill({json:{instalado:false,aviso:'Sin mediciones',montadas:[]}});
 if(p==='/api/mapa')return route.fulfill({json:{unidad:unit,mapa:map,modelo_3d:'semi',modelo_3d_archivo:'trailer.obj',modelo_3d_por:'mapa',historial:[],movimientos:[]}});
 if(p==='/api/gomeria/stock')return route.fulfill({json:stock.filter(t=>t.estado==='stock')});
 if(p==='/api/marcas')return route.fulfill({json:{marcas:[{id:1,nombre:'Fate',slug:'fate'},{id:2,nombre:'Michelin',slug:'michelin'}],medidas:[{id:1,medida:'295/80R22.5',descripcion:'La de los camiones.'}],puede_gestionar:false}});
 if(p==='/api/inventario-cubiertas')return route.fulfill({json:{cubiertas:stock,resumen:{stock:stock.filter(t=>t.estado==='stock').length}}});
 if(p==='/api/gomeria/posicion'){
 const d=req.postDataJSON();writes.push(d);const pos=map.find(p=>p.posicion_id===Number(d.posicion_id));
 if(d.accion==='montar'){const t=stock.find(t=>t.id===d.cubierta_id);assert(!pos.cubierta_id);Object.assign(pos,{cubierta_id:t.id,cubierta:t.codigo,marca:t.marca,medida:t.medida,remanente_mm:t.remanente_mm});t.estado='montada';}
 else{assert(d.nota.trim());const t=stock.find(t=>t.id===pos.cubierta_id);t.estado=d.destino;pos.cubierta_id=null;pos.cubierta=null;}
 return route.fulfill({json:{mapa:map}});
 }
 const rel=p==='/gomeria'?'gomeria/movil.html':p==='/gomeria-mesa.js'?'gomeria/mesa.js':p.slice(1);const file=path.join(root,rel);
 if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({path:file});return route.fulfill({body:'',status:404});
 });
 await page.goto('http://taller.test/gomeria');await page.waitForFunction(()=>V.ruedas.length>0);await page.locator('[data-stock-id="101"]').waitFor();
 // Elegir unidad es un desplegable: la lista flota y no empuja la mesa.
 assert(await page.locator('#unitList').isHidden(),'la lista arranca cerrada');
 assert.equal(await page.inputValue('#unitSearch'),'AA 472 IP','el campo muestra la unidad elegida');
 const antes=await page.locator('#benchStatus').boundingBox();
 await page.click('#unitSearch');
 await page.locator('#unitList').waitFor();
 assert.equal(await page.locator('#unitList').evaluate(e=>getComputedStyle(e).position),'absolute');
 assert.deepEqual(await page.locator('#benchStatus').boundingBox(),antes,'la lista no puede correr lo de abajo');
 assert.equal(await page.locator('#unitList .unit').count(),2);
 // Se busca por la patente como se ve en pantalla y como se escribe de corrido.
 await page.fill('#unitSearch','ah787');
 assert.equal(await page.locator('#unitList .unit').count(),1);
 await page.fill('#unitSearch','787 df');
 assert.equal(await page.locator('#unitList .unit').count(),1);
 // Con el teclado: baja, Enter, y la lista se cierra con la unidad puesta.
 await page.keyboard.press('ArrowDown');
 assert.equal(await page.locator('#unitList .unit.marcada').count(),1);
 await page.keyboard.press('Enter');
 await page.waitForFunction(()=>document.querySelector('#unitList').hidden);
 assert.equal(await page.inputValue('#unitSearch'),'AH 787 DF · int. 44');
 // Escape cierra sin cambiar de unidad y deja escrita la que está elegida.
 await page.click('#unitSearch');await page.fill('#unitSearch','aa4');
 await page.locator('#unitList .unit').first().waitFor();
 await page.keyboard.press('Escape');
 assert(await page.locator('#unitList').isHidden());
 assert.equal(await page.inputValue('#unitSearch'),'AH 787 DF · int. 44');
 // Y con el mouse: el botón abre, un clic afuera cierra.
 await page.click('#unitToggle');await page.locator('#unitList .unit').first().waitFor();
 await page.click('.stock-shelf h2');
 await page.waitForFunction(()=>document.querySelector('#unitList').hidden);
 await page.click('#unitToggle');await page.locator('[data-pat="AA472IP"]').click();
 await page.waitForFunction(()=>document.querySelector('#unitList').hidden);
 assert.equal(await page.inputValue('#unitSearch'),'AA 472 IP');
 await page.waitForFunction(()=>V.ruedas.length>0);
 // Regression: one mounted tire in a dual must not look empty in 3D.
 assert.equal(await page.locator('.map [data-pos="8"] .code').textContent(),'319');
 assert.equal(await page.locator('.map [data-pos="8"] .mounted-label').textContent(),'MONTADA');
 assert(await page.evaluate(()=>V.ruedas.some(m=>{const e=esquinaDeLaRueda(m);return posicionesDe(e).some(p=>p.cubierta_id===319)&&m.material.color.getHex()===RUEDA.parcial;})));
 await page.locator('[data-ver-pos="8"]').click();await page.waitForFunction(()=>document.querySelector('#tireInspector').textContent.includes('319'));
 // La marca se muestra con su logo, no con el nombre, y la goma rueda.
 await page.locator('#tireInspector .logo-marca img').waitFor();
 assert.equal(new URL(await page.locator('#tireInspector .logo-marca img').getAttribute('src'),'http://taller.test').pathname,'/marcas/fate.png');
 assert(await page.locator('#tireInspector .logo-marca img').evaluate(i=>i.complete&&i.naturalWidth>0),'el logo tiene que llegar: si no, queda el nombre en texto');
 assert(!(await page.locator('#tireInspector .details').innerText()).includes('FATE'),'el nombre tendría que haber quedado reemplazado por el logo');
 for(const clase of ['.tacos','.llanta']){const dur=await page.locator('.tire-art '+clase).evaluate(e=>getComputedStyle(e).animationDuration);assert(parseFloat(dur)>0,'la goma no se mueve: '+clase+' sin animación');}
 // La marca sin logo cargado vuelve a mostrarse en texto.
 await page.evaluate(()=>{document.querySelector('#tireInspector .logo-marca img').dispatchEvent(new Event('error'));});
 assert((await page.locator('#tireInspector .details').innerText()).includes('FATE'),'sin logo tiene que quedar el nombre');
 await page.locator('[data-ver-pos="8"]').click();
 // Icon-only navigation keeps accessible names and hover titles.
 await page.route('**/api/yo',route=>route.fulfill({json:{nombre:'Prueba',administra:true,puede_administrar:admin}}));
 await page.addScriptTag({path:path.join(root,'barra.js')});await page.locator('.barra-admin').waitFor();
 for(const label of ['Usuarios','Parámetros']){const link=page.getByRole('link',{name:label,exact:true});assert.equal(await link.getAttribute('title'),label);assert.equal((await link.textContent()).trim(),'');}
 // Existing Claude workflow remains available: text → preview → confirm.
 await page.click('[data-tab="register"]');await page.selectOption('#workUnit','AA472IP');await page.fill('#workText','Entra Fate 319 en 2DE');await page.click('#interpret');await page.locator('#confirm').waitFor();await page.click('#confirm');await page.waitForFunction(()=>document.querySelector('#workResult').textContent.includes('Guardado.'));await page.click('[data-tab="fleet"]');await page.waitForFunction(()=>V.ruedas.length>0);
 // Click flow with exact position.
 await page.click('[data-stock-id="101"]');await page.locator('.map [data-pos="1"]').click();await page.click('#mountSelected');assert.equal(writes.length,0);await page.click('#movementSave');await page.waitForFunction(()=>document.querySelector('.map [data-pos="1"]')?.dataset.tire==='101');assert.equal(writes.length,1);
 // Native HTML drag back to stock: cancel does not write; reason required.
 await page.locator('.map [data-pos="1"]').dragTo(page.locator('#returnStock'));await page.locator('#movementDialog').waitFor();await page.click('#movementSave');assert.equal(writes.length,1);await page.click('#movementCancel');assert.equal(writes.length,1);
 await page.locator('.map [data-pos="1"]').dragTo(page.locator('#returnStock'));await page.fill('#movementNote','Rotación de cubiertas');await page.click('#movementSave');await page.locator('[data-stock-id="101"]').waitFor();assert.equal(writes.at(-1).destino,'stock');
 // Stock to exact slot by drag.
 await page.locator('[data-stock-id="102"]').dragTo(page.locator('.map [data-pos="2"]'));await page.locator('#movementDialog').waitFor();await page.click('#movementSave');await page.waitForFunction(()=>document.querySelector('.map [data-pos="2"]')?.dataset.tire==='102');
 // Actual 3D hit location, and stock drop onto a dual wheel must ask interior/exterior.
 await page.waitForFunction(()=>V.ruedas.length>0);
 async function hit(){return page.evaluate(()=>{V.tocado=true;const rect=V.render.domElement.getBoundingClientRect();V.escena.updateMatrixWorld(true);V.camara.updateMatrixWorld();for(const wheel of V.ruedas){const p=new THREE.Box3().setFromObject(wheel).getCenter(new THREE.Vector3()).project(V.camara);const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2(p.x,p.y),V.camara);const h=ray.intersectObjects(V.ruedas,false)[0];if(h){const corner=esquinaDelPunto(h.point,h.object),positions=posicionesDe(corner);if(positions.length===2&&positions.every(p=>!p.cubierta_id))return {x:(p.x+1)*rect.width/2,y:(1-p.y)*rect.height/2,positions:positions.map(p=>p.posicion_id)};}}return null;});}
 const spot=await hit();assert(spot,'visible empty dual wheel');
 await page.locator('[data-stock-id="101"]').dragTo(page.locator('#visor canvas'),{targetPosition:{x:spot.x,y:spot.y}});await page.locator('#movementDialog').waitFor();assert.equal(await page.locator('#movementPosition option').count(),2);await page.selectOption('#movementPosition',String(spot.positions[1]));await page.click('#movementSave');await page.waitForFunction(id=>document.querySelector('.map [data-pos="'+id+'"]')?.dataset.tire==='101',spot.positions[1]);
 await page.waitForFunction(()=>V.ruedas.length>0);
 await page.locator('.map [data-pos="'+spot.positions[1]+'"]').click();await page.check('#moveWheels');
 // Find the same mounted corner in the reloaded model.
 const mounted=await page.evaluate(id=>{V.tocado=true;const rect=V.render.domElement.getBoundingClientRect();for(const wheel of V.ruedas){const p=new THREE.Box3().setFromObject(wheel).getCenter(new THREE.Vector3()).project(V.camara);const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2(p.x,p.y),V.camara);const h=ray.intersectObjects(V.ruedas,false)[0];if(h&&posicionesDe(esquinaDelPunto(h.point,h.object)).some(q=>q.posicion_id===id))return {x:(p.x+1)*rect.width/2,y:(1-p.y)*rect.height/2};}return null;},spot.positions[1]);assert(mounted);
 await page.locator('#visor canvas').dragTo(page.locator('#returnStock'),{sourcePosition:mounted});await page.locator('#movementDialog').waitFor();await page.fill('#movementNote','Desgaste irregular');await page.selectOption('#movementDestination','reparacion');await page.click('#movementSave');await page.waitForFunction(id=>!document.querySelector('.map [data-pos="'+id+'"]')?.dataset.tire,spot.positions[1]);assert.equal(writes.at(-1).destino,'reparacion');
 await page.waitForFunction(()=>V.ruedas.length>0);await page.locator('.map [data-pos="2"]').click();await page.screenshot({path:'/tmp/gomeria-mesa-desktop.png',fullPage:true});
 // Un dual tiene dos gomas atrás de una sola rueda del modelo: tocarla de
 // nuevo pasa a la otra, y el mapa marca cuál quedó elegida.
 {
  await page.waitForFunction(()=>V.ruedas.length>0);
  const rueda=await page.evaluate(()=>{V.tocado=true;const r=V.render.domElement.getBoundingClientRect();
   V.escena.updateMatrixWorld(true);V.camara.updateMatrixWorld();
   for(const w of V.ruedas){const p=new THREE.Box3().setFromObject(w).getCenter(new THREE.Vector3()).project(V.camara);
    const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2(p.x,p.y),V.camara);
    const h=ray.intersectObjects(V.ruedas,false)[0];
    if(h&&posicionesDe(esquinaDelPunto(h.point,h.object)).length===2)
     return {x:r.left+(p.x+1)*r.width/2,y:r.top+(1-p.y)*r.height/2};}
   return null;});
  assert(rueda,'no se encontró una rueda dual a la vista');
  await page.mouse.click(rueda.x,rueda.y);
  const primera=await page.evaluate(()=>D.benchPosition);
  assert(primera,'tocar la rueda no eligió ninguna posición');
  assert.equal(await page.locator('.map .tire.chosen').count(),1,'el mapa no marca la elegida');
  assert((await page.locator('#elegida h4').innerText()).match(/interior|exterior/i),
         'no dice cuál de las dos gomas del dual quedó elegida');
  assert((await page.locator('#elegida').innerText()).includes('otra vez'),
         'no cuenta cómo llegar a la otra goma');
  await page.mouse.click(rueda.x,rueda.y);
  const segunda=await page.evaluate(()=>D.benchPosition);
  assert(segunda&&segunda!==primera,'tocar de nuevo no pasó a la otra goma del dual');
  assert.equal(await page.locator('.map [data-pos="'+segunda+'"].chosen').count(),1,
               'el mapa no siguió a la segunda goma');
  // Elegir un casillero del mapa dice cuál: ahí no hay nada que alternar.
  await page.locator('.map [data-pos="'+segunda+'"]').click();
  assert.equal(await page.evaluate(()=>D.benchPosition),segunda,'el clic en el mapa alternó solo');
 }
 // Se puede mirar desde abajo: es la única forma de ver la goma interior
 // de un dual, y el piso se corre solo cuando la cámara baja.
 assert(await page.evaluate(()=>V.control.maxPolarAngle>Math.PI/2),'la cámara no puede bajar del horizonte');
 {
  // Con el 3D en modo mover, el arrastre agarra la goma en vez de girar.
  await page.uncheck('#moveWheels');
  await page.locator('#visor canvas').scrollIntoViewIfNeeded();
  const caja=await page.locator('#visor canvas').boundingBox();
  await page.mouse.move(caja.x+caja.width/2,caja.y+caja.height/2);
  await page.mouse.down();
  // Arrastrar hacia arriba baja la cámara: es el gesto de agacharse.
  for(let i=1;i<=20;i++)await page.mouse.move(caja.x+caja.width/2,caja.y+caja.height/2-i*14);
  await page.mouse.up();
  const visto=await page.evaluate(async()=>{
   await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
   const piso=V.escena.children.find(o=>o.geometry&&o.geometry.type==='CircleGeometry');
   return {y:V.camara.position.y,piso:piso?piso.visible:null};});
  assert(visto.y<0,'la cámara no llegó abajo del piso: y='+visto.y);
  assert.equal(visto.piso,false,'el piso tapa justo lo que se fue a mirar');
  // Y se vuelve a dejar el camión de frente, que después se le saca la foto.
  await page.mouse.move(caja.x+caja.width/2,caja.y+caja.height/2);
  await page.mouse.down();
  for(let i=1;i<=14;i++)await page.mouse.move(caja.x+caja.width/2,caja.y+caja.height/2+i*14);
  await page.mouse.up();
 }
 // Arrastrar del stock lleva una goma con el número de fuego, no la ficha.
 {
  const arrastre=await page.evaluate(()=>{
   const b=document.querySelector('[data-stock-id="103"]');
   b.dispatchEvent(new DragEvent('dragstart',{dataTransfer:new DataTransfer(),bubbles:true}));
   const g=document.querySelector('.goma-arrastre');
   const visto={texto:g?g.textContent.trim():null,goma:!!(g&&g.querySelector('svg.tire-art'))};
   document.dispatchEvent(new DragEvent('dragend',{bubbles:true}));
   return {...visto,limpio:!document.querySelector('.goma-arrastre')};});
  assert.equal(arrastre.texto,'BRI-103','la goma que sigue al mouse no dice cuál es');
  assert(arrastre.goma,'lo que sigue al mouse no es una goma');
  assert(arrastre.limpio,'la goma del arrastre quedó pegada en la página');
 }
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:'/tmp/gomeria-mesa-mobile.png',fullPage:true});
 // El alta de cubierta sugiere las marcas y medidas cargadas en Parámetros.
 await page.click('[data-tab="stock"]');
 assert.deepEqual(await page.locator('#catMarcas option').evaluateAll(o=>o.map(x=>x.value)),['Fate','Michelin']);
 assert.deepEqual(await page.locator('#catMedidas option').evaluateAll(o=>o.map(x=>x.value)),['295/80R22.5']);
 assert.equal(await page.locator('#nBrand').getAttribute('list'),'catMarcas');
 await page.click('[data-tab="fleet"]');await page.waitForFunction(()=>V.ruedas.length>0);
 // Quien pidió menos movimiento en su sistema no ve ninguno.
 await page.emulateMedia({reducedMotion:'reduce'});await page.locator('.map [data-pos="2"]').click();
 assert.equal(await page.locator('.tire-art .tacos').evaluate(e=>getComputedStyle(e).animationName),'none');
 await page.emulateMedia({reducedMotion:'no-preference'});
 admin=false;await page.reload();await page.locator('.map [data-pos="2"]').click();assert.equal(await page.locator('#removeSelected').count(),0);assert.equal(await page.locator('.map [data-pos="2"]').getAttribute('draggable'),'false');assert.deepEqual(errors,[]);
 console.log('PASS: real 3D, click mount, native slot/canvas drag in both directions, dual choice, cancel, reason, repair destination, read-only, responsive, logo de marca, goma que rueda, buscador desplegable, cámara bajo el piso, goma en el arrastre y dual que alterna');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
