const {chromium}=require('playwright');
const http=require('http'),fs=require('fs'),path=require('path'),assert=require('assert');
const root=path.resolve(__dirname,'..');
let user=1,acks=0,fail=false;const received=new Set();
const server=http.createServer((req,res)=>{
 const u=new URL(req.url,'http://localhost');
 if(u.pathname==='/api/reportes-chofer'){
  res.setHeader('Content-Type','application/json');
  if(req.method==='GET')return res.end(JSON.stringify({usuario_id:user,nombre:'Chofer '+user,unidades:[{id:1,patente:'TEST001'}]}));
  let raw='';req.on('data',c=>raw+=c);req.on('end',()=>{const d=JSON.parse(raw);assert.equal(d.usuario_id,user);if(fail){res.statusCode=503;return res.end(JSON.stringify({error:'Servidor ocupado'}));}received.add(d.id);acks++;res.end(JSON.stringify({ok:true,id:d.id}));});return;
 }
 const rel=u.pathname==='/choferes/'?'choferes/index.html':u.pathname.slice(1);
 const f=path.join(root,rel);if(!fs.existsSync(f)){res.statusCode=404;return res.end();}
 const mime=rel.endsWith('.js')?'text/javascript':rel.endsWith('.css')?'text/css':rel.endsWith('.svg')?'image/svg+xml':'text/html';res.setHeader('Content-Type',mime);res.end(fs.readFileSync(f));
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
 const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:'+server.address().port+'/choferes/');
 await page.waitForFunction(()=>document.querySelector('#save').disabled===false);
 await page.evaluate(()=>navigator.serviceWorker.ready);await page.reload();
 await page.waitForFunction(()=>!!navigator.serviceWorker.controller);
 await context.setOffline(true);await page.reload();await page.waitForFunction(()=>!document.querySelector('#save').disabled);
 await page.selectOption('#unit','1');await page.fill('#description','Falla sin señal');
 await page.setInputFiles('#photos',{name:'foto.png',mimeType:'image/png',buffer:await page.screenshot({clip:{x:0,y:0,width:10,height:10}})});
 await page.waitForFunction(()=>document.querySelectorAll('#preview img').length===1);
 await page.click('#save');await page.waitForFunction(()=>document.querySelector('#pending').textContent.includes('Falla sin señal'));
 await page.reload();await page.waitForFunction(()=>document.querySelector('#pending').textContent.includes('Falla sin señal'));
 let rows=await page.evaluate(()=>Cola.op('reportes','getAll'));assert.equal(rows.length,1);assert.equal(rows[0].fotos.length,1);assert(!rows[0].enviado);
 // A different session must not submit another driver's queue.
 user=2;await context.setOffline(false);await page.evaluate(()=>Cola.sync());assert.equal(received.size,0);
 user=1;fail=true;await page.evaluate(()=>Cola.sync().catch(()=>{}));rows=await page.evaluate(()=>Cola.op('reportes','getAll'));assert(!rows[0].enviado);assert.equal(rows[0].fotos.length,1);
 fail=false;await page.evaluate(()=>Cola.sync());await page.evaluate(()=>Cola.sync());rows=await page.evaluate(()=>Cola.op('reportes','getAll'));assert(rows[0].enviado);assert.equal(received.size,1);assert.equal(acks,1);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 await page.click('#sync');await page.waitForFunction(()=>document.querySelector('#pending').textContent.includes('Enviado al taller'));
 await page.screenshot({path:'/tmp/choferes-mobile.png',fullPage:true});
 console.log('PASS: offline reload + photo persistence + account isolation + failed upload + retry + ACK + mobile layout');
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
