const CACHE = "kavalheiro-v3";
const ASSETS = ["/","/static/styles.css","/static/app.js","/static/manifest.json"];
self.addEventListener("install",(e)=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)))});
self.addEventListener("activate",(e)=>{e.waitUntil(caches.keys().then(keys=>Promise.all(keys.map(k=>k!==CACHE?caches.delete(k):null))))});
self.addEventListener("fetch",(e)=>{
  const req=e.request;
  if(req.url.includes("/api/")){e.respondWith(fetch(req));return;}
  e.respondWith(caches.match(req).then(res=>res||fetch(req).then(net=>{const copy=net.clone();caches.open(CACHE).then(c=>c.put(req,copy));return net;}).catch(()=>caches.match("/"))));
});