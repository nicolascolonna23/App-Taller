importScripts('/choferes/cola.js');
const CACHE='choferes-shell-v1';
const FILES=['/choferes/','/choferes/app.js','/choferes/cola.js','/choferes/style.css','/choferes/manifest.webmanifest','/choferes/icon.svg'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(FILES))));
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',e=>{
 const u=new URL(e.request.url);
 if(u.origin===location.origin && e.request.method==='GET' && FILES.includes(u.pathname))
   e.respondWith(caches.open(CACHE).then(async c=>(await c.match(u.pathname))||fetch(e.request)));
});
self.addEventListener('sync',e=>{if(e.tag==='reportes-chofer')e.waitUntil(Cola.sync());});
