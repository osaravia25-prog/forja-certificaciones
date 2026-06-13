const CACHE='forja-pro-v1';
const ASSETS=['/','/styles.css','/script.js','/verificar-certificado.html','/portal-alumnos.html'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).catch(()=>{}));});
self.addEventListener('fetch',e=>{e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));});
