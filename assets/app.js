const $=id=>document.getElementById(id);
const e={
  country:$("country"),region:$("region"),city:$("city"),search:$("search"),bitrate:$("bitrate"),
  download:$("download"),favoritesToggle:$("favorites-toggle"),timeFormat:$("time-format"),
  status:$("status"),stations:$("stations"),visible:$("visible-count"),total:$("total-count"),
  countries:$("country-count"),updated:$("updated"),template:$("station-template"),player:$("player"),
  audio:$("audio"),nowName:$("now-name"),nowLocation:$("now-location"),close:$("close-player"),
  localClock:$("local-clock"),playerLocalTime:$("player-local-time"),playerStationTime:$("player-station-time")
};

const FAVORITES_KEY="landell-wave.favorites.v1";
const TIME_FORMAT_KEY="landell-wave.time-format.v1";
const MAX_FAVORITES=500;
const MAX_RENDERED=1500;
let indexData=null,current=[],visible=[],cache=new Map(),globalSearch=null,favoritesOnly=false,searchTimer=null,currentPlaying=null;
const timeFormatterCache=new Map();

const fmt=n=>new Intl.NumberFormat().format(n);
const uniq=v=>[...new Set(v)].sort((a,b)=>a.localeCompare(b,undefined,{sensitivity:"base",numeric:true}));
const loc=s=>[s.country,s.region,s.city].filter(Boolean).join(" › ");
const stationKey=s=>String(s.id||s.stream||"").slice(0,4096);

function isObviouslyLocalHost(host){
  const h=(host||"").toLowerCase().replace(/\.$/,"");
  if(!h||h==="localhost"||h.endsWith(".localhost")||h.endsWith(".local")||h.endsWith(".internal")||h.endsWith(".lan")||h.endsWith(".home.arpa"))return true;
  if(/^127\./.test(h)||/^10\./.test(h)||/^192\.168\./.test(h)||/^169\.254\./.test(h))return true;
  const m=h.match(/^172\.(\d+)\./);if(m&&Number(m[1])>=16&&Number(m[1])<=31)return true;
  if(h==="::1"||h.startsWith("fe80:")||h.startsWith("fc")||h.startsWith("fd"))return true;
  return false;
}
function safeExternalUrl(value,{allowHttp=false}={}){
  try{
    const u=new URL(value);
    if(!["https:",...(allowHttp?["http:"]:[])].includes(u.protocol)||u.username||u.password||isObviouslyLocalHost(u.hostname))return "";
    return u.href;
  }catch{return ""}
}
function options(select,values,label){
  const old=select.value;
  select.replaceChildren(new Option(label,""));
  for(const v of values)select.add(new Option(v,v));
  if([...select.options].some(o=>o.value===old))select.value=old;
}
function syncUrl(){
  const p=new URLSearchParams();
  if(e.country.value)p.set("country",e.country.value);
  if(e.region.value)p.set("region",e.region.value);
  if(e.city.value)p.set("city",e.city.value);
  if(e.search.value.trim())p.set("q",e.search.value.trim());
  if(favoritesOnly)p.set("favorites","1");
  history.replaceState(null,"",location.pathname+(p.size?"?"+p:""));
}
function getTimeFormat(){
  try{return localStorage.getItem(TIME_FORMAT_KEY)==="12"?"12":"24"}catch{return "24"}
}
function setTimeFormat(value){
  const normalized=value==="12"?"12":"24";
  try{localStorage.setItem(TIME_FORMAT_KEY,normalized)}catch{}
  e.timeFormat.value=normalized;
  timeFormatterCache.clear();
  updateClocks();
}
function timeFormatter(timeZone=""){
  const mode=getTimeFormat(),key=`${mode}|${timeZone||"local"}`;
  if(timeFormatterCache.has(key))return timeFormatterCache.get(key);
  const options={hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:mode==="12"};
  if(timeZone)options.timeZone=timeZone;
  try{
    const formatter=new Intl.DateTimeFormat(undefined,options);
    timeFormatterCache.set(key,formatter);
    return formatter;
  }catch{return null}
}
function formatTime(timeZone=""){
  const formatter=timeFormatter(timeZone);
  if(!formatter)return "";
  try{return formatter.format(new Date())}catch{return ""}
}
function stationTimeText(station){
  const tz=String(station?.timezone||"").trim();
  const value=tz?formatTime(tz):"";
  return value?`Station time: ${value}`:"Station time: unavailable";
}
function updateClocks(){
  const local=formatTime();
  e.localClock.textContent=local?`Local time: ${local}`:"Local time: unavailable";
  e.playerLocalTime.textContent=local?`Your time: ${local}`:"Your time: unavailable";
  e.playerStationTime.textContent=currentPlaying?stationTimeText(currentPlaying):"Station time: unavailable";
  for(const node of e.stations.querySelectorAll(".station-time[data-timezone]")){
    const tz=node.dataset.timezone||"";
    const value=tz?formatTime(tz):"";
    node.textContent=value?`Station time: ${value}`:"Station time: unavailable";
  }
}
function readFavorites(){
  try{
    const parsed=JSON.parse(localStorage.getItem(FAVORITES_KEY)||"[]");
    return Array.isArray(parsed)?parsed.slice(0,MAX_FAVORITES):[];
  }catch{return []}
}
function writeFavorites(items){
  try{
    localStorage.setItem(FAVORITES_KEY,JSON.stringify(items.slice(0,MAX_FAVORITES)));
    return true;
  }catch{
    e.status.textContent="Favorites could not be saved on this device.";
    return false;
  }
}
function favoriteMap(){return new Map(readFavorites().map(s=>[stationKey(s),s]))}
function isFavorite(s){return favoriteMap().has(stationKey(s))}
function toggleFavorite(s){
  const items=readFavorites(),key=stationKey(s),i=items.findIndex(x=>stationKey(x)===key);
  if(i>=0)items.splice(i,1);
  else{
    if(items.length>=MAX_FAVORITES){e.status.textContent=`Favorite limit reached (${MAX_FAVORITES}).`;return}
    items.unshift({
      id:s.id||"",name:s.name||"Unnamed station",country:s.country||"",country_code:s.country_code||"",
      region:s.region||"",city:s.city||"",timezone:s.timezone||"",stream:s.stream||"",homepage:s.homepage||"",
      tags:Array.isArray(s.tags)?s.tags.slice(0,20):[],languages:Array.isArray(s.languages)?s.languages.slice(0,10):[],
      codec:s.codec||"",bitrate:Number(s.bitrate||0)
    });
  }
  if(writeFavorites(items))renderCurrent().catch(showError);
}
async function loadGlobalSearch(){
  if(globalSearch)return globalSearch;
  e.status.textContent="Loading worldwide search index…";
  const r=await fetch("data/search.json",{cache:"no-store"});
  if(!r.ok)throw Error("Worldwide search index unavailable");
  const payload=await r.json();
  if(!payload||!Array.isArray(payload.stations))throw Error("Worldwide search index invalid");
  globalSearch=payload.stations;
  return globalSearch;
}
function matchesQuery(s,q){
  if(!q)return true;
  return [s.name,s.country,s.region,s.city,...(s.tags||[]),...(s.languages||[])].join(" ").toLocaleLowerCase().includes(q);
}
function applyFilters(source){
  const r=e.region.value,c=e.city.value,q=e.search.value.trim().toLocaleLowerCase(),min=Number(e.bitrate.value||0);
  return source.filter(s=>{
    if(r&&s.region!==r)return false;
    if(c&&s.city!==c)return false;
    if(min&&Number(s.bitrate||0)<min)return false;
    return matchesQuery(s,q);
  });
}
async function init(){
  e.timeFormat.value=getTimeFormat();
  updateClocks();
  setInterval(updateClocks,30000);
  const r=await fetch("data/index.json",{cache:"no-store"});
  if(!r.ok)throw Error("Catalog index unavailable");
  indexData=await r.json();
  e.total.textContent=fmt(indexData.station_count);
  e.countries.textContent=fmt(indexData.country_count);
  e.updated.textContent=new Date(indexData.generated_at).toLocaleDateString();
  e.country.replaceChildren(new Option("All countries / global search",""));
  for(const c of indexData.countries)e.country.add(new Option(`${c.name} (${fmt(c.stations)})`,c.code));
  const p=new URLSearchParams(location.search),c=p.get("country");
  favoritesOnly=p.get("favorites")==="1";
  e.favoritesToggle.setAttribute("aria-pressed",String(favoritesOnly));
  if(p.get("q"))e.search.value=p.get("q");
  if(c&&indexData.countries.some(x=>x.code===c)){e.country.value=c;await loadCountry(c,p)}
  else await renderCurrent();
}
async function loadCountry(code,params=null){
  favoritesOnly=false;e.favoritesToggle.setAttribute("aria-pressed","false");
  if(!code){
    current=[];e.region.disabled=e.city.disabled=true;
    options(e.region,[],"All regions");options(e.city,[],"All cities");
    await renderCurrent();return;
  }
  e.status.textContent="Loading stations…";
  let payload=cache.get(code);
  if(!payload){
    const r=await fetch(`data/countries/${encodeURIComponent(code)}.json`,{cache:"no-store"});
    if(!r.ok)throw Error("Country catalog unavailable");
    payload=await r.json();cache.set(code,payload);
  }
  current=payload.stations;
  options(e.region,uniq(current.map(s=>s.region)),"All regions");e.region.disabled=false;
  if(params?.get("region"))e.region.value=params.get("region");
  rebuildCities();
  if(params?.get("city"))e.city.value=params.get("city");
  await renderCurrent();
}
function rebuildCities(){
  const r=e.region.value,subset=r?current.filter(s=>s.region===r):current;
  options(e.city,uniq(subset.map(s=>s.city)),"All cities");
  e.city.disabled=!e.country.value;
}
async function renderCurrent(){
  const q=e.search.value.trim();
  let source=[],scope="";
  if(favoritesOnly){
    source=readFavorites();scope="favorites";
    e.region.disabled=e.city.disabled=true;
  }else if(e.country.value){
    source=current;scope="country";
    e.region.disabled=false;e.city.disabled=false;
  }else if(q.length>=2){
    source=await loadGlobalSearch();scope="global";
    e.region.disabled=e.city.disabled=true;
  }else{
    visible=[];e.stations.replaceChildren();e.visible.textContent="0";e.download.disabled=true;
    e.status.textContent="Choose a country, search at least 2 characters worldwide, or open Favorites.";
    syncUrl();return;
  }
  visible=applyFilters(source);
  e.visible.textContent=fmt(visible.length);
  e.download.disabled=visible.length===0;
  e.stations.replaceChildren();
  const frag=document.createDocumentFragment();
  for(const s of visible.slice(0,MAX_RENDERED))frag.append(card(s));
  e.stations.append(frag);
  updateClocks();
  if(!visible.length)e.status.textContent=scope==="favorites"?"No favorite stations match the current filters.":"No stations match the current filters.";
  else if(visible.length>MAX_RENDERED)e.status.textContent=`Showing the first ${fmt(MAX_RENDERED)} of ${fmt(visible.length)} matches. Narrow the search to render fewer rows.`;
  else if(scope==="global")e.status.textContent=`Worldwide search: ${fmt(visible.length)} station(s) found.`;
  else if(scope==="favorites")e.status.textContent=`Favorites: ${fmt(visible.length)} station(s).`;
  else e.status.textContent=`${fmt(visible.length)} station(s) shown.`;
  syncUrl();
}
function card(s){
  const n=e.template.content.firstElementChild.cloneNode(true);
  n.querySelector(".station-name").textContent=s.name;
  n.querySelector(".location").textContent=loc(s);
  n.querySelector(".meta").textContent=[s.codec,s.bitrate?`${s.bitrate} kbps`:"",...(s.languages||[]).slice(0,2),...(s.tags||[]).slice(0,3)].filter(Boolean).join(" · ");
  const clock=n.querySelector(".station-time");
  clock.dataset.timezone=String(s.timezone||"");
  clock.textContent=stationTimeText(s);
  const fav=n.querySelector(".favorite");
  const active=isFavorite(s);
  fav.textContent=active?"★":"☆";fav.classList.toggle("is-favorite",active);
  fav.setAttribute("aria-label",active?"Remove from favorites":"Add to favorites");
  fav.title=active?"Remove from favorites":"Add to favorites";
  fav.addEventListener("click",()=>toggleFavorite(s));
  n.querySelector(".play").addEventListener("click",()=>play(s));
  const w=n.querySelector(".website"),homepage=safeExternalUrl(s.homepage);
  if(homepage)w.href=homepage;else{w.hidden=true;w.removeAttribute("href")}
  n.querySelector(".copy").addEventListener("click",async ev=>{
    try{await navigator.clipboard.writeText(s.stream);const b=ev.currentTarget,o=b.textContent;b.textContent="Copied";setTimeout(()=>b.textContent=o,1200)}
    catch{e.status.textContent="Could not copy the stream URL."}
  });
  return n;
}
function play(s){
  const stream=safeExternalUrl(s.stream,{allowHttp:true});
  if(!stream){e.status.textContent="Blocked an unsafe or invalid stream URL.";return}
  currentPlaying=s;
  e.player.hidden=false;e.nowName.textContent=s.name;e.nowLocation.textContent=loc(s);
  updateClocks();
  if(e.audio.src!==stream)e.audio.src=stream;
  e.audio.play().catch(()=>{e.status.textContent="The browser could not play this stream."});
}
function download(){
  const lines=["#EXTM3U"];
  for(const s of visible){
    const g=[s.country,s.region,s.city].join(" | ").replaceAll('"',"'"),name=(s.name||"").replace(/[\r\n]/g," ");
    lines.push(`#EXTINF:-1 tvg-id="${String(s.id||"").replaceAll('"',"'")}" group-title="${g}",${name}`,s.stream);
  }
  const blob=new Blob([lines.join("\n")+"\n"],{type:"audio/x-mpegurl;charset=utf-8"}),url=URL.createObjectURL(blob),a=document.createElement("a");
  a.href=url;a.download=favoritesOnly?"landell-wave-favorites.m3u":[e.country.value,e.region.value,e.city.value].filter(Boolean).join("-").replace(/[^\p{L}\p{N}._-]+/gu,"-")||"landell-wave-search.m3u";
  a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function scheduleSearch(){
  clearTimeout(searchTimer);
  searchTimer=setTimeout(()=>renderCurrent().catch(showError),180);
}
e.country.addEventListener("change",()=>loadCountry(e.country.value).catch(showError));
e.region.addEventListener("change",()=>{rebuildCities();renderCurrent().catch(showError)});
e.city.addEventListener("change",()=>renderCurrent().catch(showError));
e.bitrate.addEventListener("change",()=>renderCurrent().catch(showError));
e.search.addEventListener("input",scheduleSearch);
e.timeFormat.addEventListener("change",()=>setTimeFormat(e.timeFormat.value));
e.favoritesToggle.addEventListener("click",()=>{
  favoritesOnly=!favoritesOnly;
  e.favoritesToggle.setAttribute("aria-pressed",String(favoritesOnly));
  renderCurrent().catch(showError);
});
e.download.addEventListener("click",download);
e.close.addEventListener("click",()=>{e.audio.pause();currentPlaying=null;e.player.hidden=true;updateClocks()});
function showError(err){console.error(err);e.status.textContent="Error: "+err.message}
init().catch(showError);
