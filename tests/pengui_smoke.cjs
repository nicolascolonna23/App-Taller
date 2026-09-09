const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
const dir=path.resolve(__dirname,'..');
const files={'/':'inicio.html','/gomeria':'gomeria/movil.html','/repuestos':'stock_repuestos.html','/flota':'index.html','/control':'control_flota.html','/unidades':'unidades.html','/vencimientos':'vencimientos.html','/alertas':'alertas.html','/ordenes':'ordenes.html','/configuracion':'configuracion.html','/combustible':'combustible.html','/asistente':'asistente.html'};
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.BROWSER_PATH?{executablePath:process.env.BROWSER_PATH}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  page.on('pageerror',e=>console.log('PAGE',page.url(),e.message));
  await page.route('**/*',route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname;
   if(p==='/api/preferencias')return route.fulfill({json:{tema:'claro',paleta:'diemar'}});
   if(p==='/api/yo')return route.fulfill({json:{nombre:'Prueba local',rol:'admin',puede_administrar:true}});
   if(p==='/api/asistente')return route.fulfill({json:req.method()==='POST'?{respuesta:'Soy Pengui, el asistente de IA. Esta es una respuesta de prueba.',fuentes:[]}:{habilitado:true}});
   if(p==='/api/inicio')return route.fulfill({json:{recorrido:{ayer:{km:12345,unidades:50,unidades_completas:50,desde:'2026-09-07',hasta:'2026-09-07'}},combustible:{mes:{mes:'2026-08-01',litros_100km:31.2,litros:10000},previo:{mes:'2026-07-01',litros_100km:32.1}},unidades:87,alertas:{total:2,graves:1}}});
   if(p==='/api/flota')return route.fulfill({json:[{id:7,patente:'AG 797 NJ',interno:'102',marca:'TOYOTA',modelo:'HIACE',chofer:'FRUTOS JAVIER',semi:'',sucursal:'BUE',uso:'DISTRIBUCION'}]});
   if(p==='/api/services')return route.fulfill({json:[{unidad_id:7,patente:'AG797NJ',interno:'102',sucursal:'BUE',ultimo_fecha:'2026-09-01',ultimo_km:41259,cada_km:40000,proximo_km:81259,km_actual:41833,km_restantes:39426,estado:'ok'}]});
   if(p==='/api/alertas')return route.fulfill({json:{instalado:true,resumen:{total:2,grave:1},alertas:[{severidad:'grave',titulo:'VTV vencida',detalle:'AD 247 MQ · venció hace 3 días',enlace:'/alertas'},{severidad:'media',titulo:'Service próximo',detalle:'faltan 2.700 km',enlace:'/control'}]}});
   if(p.startsWith('/api/'))return route.fulfill({status:503,json:{error:'Datos no conectados en esta prueba visual'}});
   if(files[p]){
    let html=fs.readFileSync(path.join(dir,files[p]),'utf8');
    const tema=html.includes('src="/tema.js"')?'':'<script src="/tema.js"></script>';
    const estilos=tema+'<link rel="stylesheet" href="/sistema.css">';
    html=html.includes('</head>')?html.replace('</head>',estilos+'</head>'):html+estilos;
    if(p==='/'){const pos=html.lastIndexOf('</body>');html=pos<0?html+'<script src="/pengui.js"></script>':html.slice(0,pos)+'<script src="/pengui.js"></script>'+html.slice(pos);}
    return route.fulfill({body:html,contentType:'text/html'});
   }
   const assets={'/logo.png':'logo_diemar4.png','/inicio-camion.jpg':'inicio-camion-hero.jpg'};
   const file=path.join(dir,assets[p]||p.slice(1));
   if(file.startsWith(dir+path.sep)&&fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':'image/png'});
   return route.abort();
  });
  for(const url of Object.keys(files).filter(x=>x!=='/asistente')){
    console.log('Checking',url);
    await page.goto('http://taller.test'+url);
    assert.equal(await page.locator('#pengui').count(),url==='/'?1:0);
    if(url==='/gomeria'){
     const visorColor=await page.evaluate(()=>{const d=document.createElement('div');d.className='visor3d';document.body.appendChild(d);return getComputedStyle(d).backgroundColor;});
     assert.equal(visorColor,'rgb(17, 22, 27)');
    }
    if(url==='/repuestos'){
     assert((await page.locator('.brand').evaluate(e=>getComputedStyle(e,'::before').backgroundImage)).includes('/logo.png'));
     const ghostColor=await page.evaluate(()=>{const bar=document.createElement('div'),b=document.createElement('button');bar.className='bar';b.className='btn ghost';bar.appendChild(b);document.body.appendChild(bar);return getComputedStyle(b).color;});
     assert.equal(ghostColor,'rgb(255, 255, 255)');
    }
    if(url==='/control'){
     assert.equal(await page.locator('#tab-general').evaluate(e=>getComputedStyle(e).color),'rgb(17, 17, 17)');
     assert.equal(await page.locator('#btn-refresh').evaluate(e=>getComputedStyle(e).color),'rgb(17, 17, 17)');
     await page.locator('#tab-unidad').click();
     await page.waitForFunction(()=>document.body.innerText.includes('41.259'));
     assert((await page.locator('body').innerText()).includes('01/09/26'));
    }
    if(url==='/combustible')assert(!(await page.locator('body').innerText()).includes('EN PRUEBA'));
    assert.equal(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor),'rgb(245, 245, 242)');
    if(url==='/'){
     assert.equal(await page.locator('.nav a', {hasText:'Asistente IA'}).count(),0);
     assert.equal(await page.locator('.nav a', {hasText:'Alertas'}).count(),0);
     assert.equal(await page.locator('.side-footer').count(),0);
     assert.equal(await page.locator('#sello').count(),0);
     assert.equal(await page.locator('.brand-copy').innerText(),'PENGUIN FLEET\nMANAGEMENT');
     assert((await page.locator('#pengui').boundingBox()).x>=230);
     await page.locator('#alertas-btn').click();
     await page.locator('.alert-item').first().waitFor();
     assert.equal(await page.locator('.alert-item').count(),2);
     await page.locator('#alertas-btn').click();
    }
  }
  await page.goto('http://taller.test/');await page.locator('#pengui .launch').click();
  const chat=page.frameLocator('iframe[title="Conversación con Pengui"]');
  await chat.locator('#send:enabled').waitFor();
  await chat.locator('#question').fill('Hola');await chat.locator('#send').click();
  await chat.locator('.message.assistant').waitFor();
  await page.screenshot({path:'/tmp/pengui-desktop.png'});
  await page.locator('#pengui .close').click();await page.locator('#pengui .launch').click();
  assert.equal(await chat.locator('.message.assistant').count(),1);
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'/tmp/pengui-mobile.png'});
  console.log('Overflow',await page.evaluate(()=>[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right})).slice(0,15)));
  assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth));
  assert(!await chat.locator('body').evaluate(()=>document.documentElement.scrollWidth>innerWidth));
  await chat.locator('#question').press('Escape');await page.waitForFunction(()=>document.querySelector('#pengui').shadowRoot.querySelector('.launch').getAttribute('aria-expanded')==='false');
  console.log('PASS: shared theme on 10 modules; Pengui only on home; alerts dropdown and chat work; desktop and mobile without overflow. Fixtures only.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
