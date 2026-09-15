// us-trip Service Worker：讓 app 在完全沒網路時打得開。
// 資料本身靠主頁的 localStorage 快照（us_trip_snap），這裡只負責「網頁與函式庫載得進來」。
// 部署時複製成網站根目錄的 sw.js。
const VERSION='u0915a';
const SHELL='shell-'+VERSION, LIB='lib-'+VERSION, TILES='tiles';
const LIB_URLS=[
  'https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js',
  'https://www.gstatic.com/firebasejs/9.23.0/firebase-database-compat.js',
  'https://www.gstatic.com/firebasejs/9.23.0/firebase-auth-compat.js',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
];
const NAV_TIMEOUT_MS=3000;   // 訊號微弱時請求不會失敗、只會一直轉；超過就改用快取
const TILE_MAX=3000;         // 只存看過的圖磚（OSM 政策禁止批次預抓），超過刪最早存的

self.addEventListener('install',e=>{
  e.waitUntil((async()=>{
    const lib=await caches.open(LIB);
    await lib.addAll(LIB_URLS.map(u=>new Request(u,{mode:'cors'})));
    // 主頁也先存一份，之後第一次離線開啟就有東西可用
    try{
      const r=await fetch('/',{cache:'no-store'});
      if(r.ok)await (await caches.open(SHELL)).put('/',r);
    }catch(_){}
    await self.skipWaiting();
  })());
});

self.addEventListener('activate',e=>{
  e.waitUntil((async()=>{
    const keep=[SHELL,LIB,TILES];
    for(const k of await caches.keys())if(!keep.includes(k))await caches.delete(k);
    await self.clients.claim();
  })());
});

self.addEventListener('fetch',e=>{
  const req=e.request;
  if(req.method!=='GET')return;
  const url=new URL(req.url);
  if(req.mode==='navigate'&&url.origin===self.location.origin){e.respondWith(navFetch(e));return;}
  if(LIB_URLS.includes(req.url)){e.respondWith(cacheFirst(LIB,req));return;}
  if(url.hostname==='fonts.googleapis.com'||url.hostname==='fonts.gstatic.com'){e.respondWith(cacheFirst(LIB,req));return;}
  if(url.hostname==='tile.openstreetmap.org'){e.respondWith(tileFetch(req));return;}
  // 其餘（Firebase 連線與認證、Nominatim、OSRM、Overpass、Open-Meteo、匯率）不攔截：即時資料不該被快取
});

async function navFetch(e){
  const cache=await caches.open(SHELL);
  // 逾時後網路請求仍繼續跑，拿到新版就寫回快取，下次開就是新的
  const net=fetch(e.request).then(r=>{if(r.ok)cache.put('/',r.clone());return r;});
  e.waitUntil(net.catch(()=>{}));
  try{
    return await Promise.race([net,new Promise((_,rej)=>setTimeout(()=>rej(new Error('timeout')),NAV_TIMEOUT_MS))]);
  }catch(_){
    const hit=await cache.match('/');
    return hit||new Response('請先在有網路時開啟一次',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8'}});
  }
}

async function cacheFirst(name,req){
  const c=await caches.open(name);
  const hit=await c.match(req);
  if(hit)return hit;
  const r=await fetch(req);
  if(r.ok||r.type==='opaque')c.put(req,r.clone());
  return r;
}

async function tileFetch(req){
  const c=await caches.open(TILES);
  const hit=await c.match(req);
  if(hit)return hit;
  const r=await fetch(req);
  // 只存 CORS 回應（tileLayer 設了 crossOrigin）；opaque 回應在瀏覽器配額裡會被灌水，3000 張會爆
  if(r.ok){await c.put(req,r.clone());trimTiles(c);}
  return r;
}

let _trimming=false;
async function trimTiles(c){
  if(_trimming)return;
  _trimming=true;
  try{
    const keys=await c.keys();   // 依寫入順序
    for(let i=0;i<keys.length-TILE_MAX;i++)await c.delete(keys[i]);
  }finally{_trimming=false;}
}
