const {chromium}=require('playwright');const fs=require('fs'),path=require('path'),assert=require('assert');const root=path.resolve(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--enable-unsafe-swiftshader']});
 try{
 const page=await browser.newPage({viewport:{width:1600,height:1050}}),errors=[],writes=[];let admin=true;
 page.on('pageerror',e=>errors.push(e.message));
 const stock=[{id:103,codigo:'BRI-103',marca:'BRIDGESTONE',modelo:'R268',medida:'295/80 R22.5',remanente_mm:16,estado:'stock'},{id:101,codigo:'MIC-101',marca:'MICHELIN',modelo:'X Multi',medida:'295/80 R22.5',remanente_mm:14,estado:'stock'},{id:102,codigo:'FAT-102',marca:'FATE',modelo:'DR400',medida:'295/80 R22.5',remanente_mm:11,estado:'stock'}];
 const unit={id:1,patente:'AA472IP',marca:'SEMIRREMOLQUE',sucursal:'CAT',posiciones:13,montadas:0};
 const map=[];let id=1;for(let eje=1;eje<=3;eje++)for(const lado of ['I','D'])for(const montaje of ['interior','exterior'])map.push({posicion_id:id++,posicion:`${eje}${lado}${montaje==='interior'?'I':'E'}`,eje,lado,montaje,es_auxilio:false,orden:id,cubierta_id:null});map.push({posicion_id:id,posicion:'AUX',eje:0,lado:'X',es_auxilio:true,orden:id,cubierta_id:null});
 await page.route('**/*',route=>{
 const req=route.request(),u=new URL(req.url()),p=u.pathname;
 if(p==='/api/yo')return route.fulfill({json:{nombre:'Prueba',rol:admin?'admin':'operario',puede_administrar:admin}});
 if(p==='/api/preferencias')return route.fulfill({json:{tema:'claro',paleta:'diemar'}});
 if(p==='/api/tablero')return route.fulfill({json:{unidades:[unit],configuraciones:[],resumen_stock:{stock:stock.filter(t=>t.estado==='stock').length}}});
 if(p==='/api/desgaste')return route.fulfill({json:{instalado:false,aviso:'Sin mediciones',montadas:[]}});
 if(p==='/api/mapa')return route.fulfill({json:{unidad:unit,mapa:map,modelo_3d:'semi',modelo_3d_archivo:'trailer.obj',modelo_3d_por:'mapa',historial:[],movimientos:[]}});
 if(p==='/api/gomeria/stock')return route.fulfill({json:stock.filter(t=>t.estado==='stock')});
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
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:'/tmp/gomeria-mesa-mobile.png',fullPage:true});
 admin=false;await page.reload();await page.locator('.map [data-pos="2"]').click();assert.equal(await page.locator('#removeSelected').count(),0);assert.equal(await page.locator('.map [data-pos="2"]').getAttribute('draggable'),'false');assert.deepEqual(errors,[]);
 console.log('PASS: real 3D, click mount, native slot/canvas drag in both directions, dual choice, cancel, reason, repair destination, read-only, responsive');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
