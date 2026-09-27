#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, math, re, shutil, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request, zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT="Global-Web-Radio/1.0 (+https://github.com/limapablo/Global-Web-Radio)"
DISCOVERY="https://all.api.radio-browser.info/json/servers"
FALLBACKS=["https://de1.api.radio-browser.info","https://nl1.api.radio-browser.info"]
CITIES_URL="https://download.geonames.org/export/dump/cities1000.zip"
ADMIN1_URL="https://download.geonames.org/export/dump/admin1CodesASCII.txt"
UNKNOWN_REGION="Unknown region"
UNKNOWN_CITY="Unknown city"
MAX_HTTP_BYTES=150 * 1024 * 1024
MAX_GEONAMES_UNCOMPRESSED_BYTES=250 * 1024 * 1024
COUNTRY_CODE_RE=re.compile(r"^[A-Z]{2}$")
RADIO_BROWSER_HOST_RE=re.compile(r"^[a-z0-9.-]+\.api\.radio-browser\.info$", re.I)

@dataclass(frozen=True)
class City:
    name: str
    lat: float
    lon: float
    country_code: str
    admin1_code: str

def get(url, timeout=120, retries=3, max_bytes=MAX_HTTP_BYTES):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!="https" or not parsed.hostname:
        raise ValueError("Build-time downloads require HTTPS")
    req=urllib.request.Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/json,text/plain,*/*"})
    err=None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req,timeout=timeout) as r:
                final=urllib.parse.urlsplit(r.geturl())
                if final.scheme!="https":
                    raise RuntimeError("Refusing HTTPS downgrade redirect")
                length=r.headers.get("Content-Length")
                if length and int(length)>max_bytes:
                    raise RuntimeError("Remote payload exceeds size limit")
                data=r.read(max_bytes+1)
                if len(data)>max_bytes:
                    raise RuntimeError("Remote payload exceeds size limit")
                return data
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, ValueError) as e:
            err=e
            if attempt+1<retries: time.sleep(2*(attempt+1))
    raise RuntimeError(f"Failed to fetch {url}: {err}")

def download(url,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists() or path.stat().st_size==0:
        tmp=path.with_suffix(path.suffix+".part")
        tmp.write_bytes(get(url))
        tmp.replace(path)
    return path

def clean(v,fallback=""):
    s=" ".join(str(v or "").replace("\x00"," ").split()).strip()
    return s or fallback

def slugify(v):
    s=unicodedata.normalize("NFKD",v).encode("ascii","ignore").decode()
    return re.sub(r"[^A-Za-z0-9._-]+","-",s).strip("-._").lower() or "unknown"

def haversine_km(a,b,c,d):
    r=6371.0088
    p1,p2=math.radians(a),math.radians(c)
    dp=math.radians(c-a); dl=math.radians(d-b)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(x))

def load_admin1(path):
    out={}
    for line in path.read_text(encoding="utf-8").splitlines():
        f=line.split("\t")
        if len(f)>=2: out[f[0]]=f[1]
    return out

def load_cities(path):
    buckets=defaultdict(list); by_country=defaultdict(list)
    with zipfile.ZipFile(path) as z:
        candidates=[i for i in z.infolist() if not i.is_dir() and i.filename.endswith(".txt")]
        if len(candidates)!=1:
            raise RuntimeError("Unexpected GeoNames archive layout")
        info=candidates[0]
        if info.file_size>MAX_GEONAMES_UNCOMPRESSED_BYTES:
            raise RuntimeError("GeoNames archive exceeds uncompressed size limit")
        with z.open(info) as fh:
            for raw in fh:
                f=raw.decode("utf-8","replace").rstrip("\n").split("\t")
                if len(f)<11: continue
                try: city=City(f[1],float(f[4]),float(f[5]),f[8].upper(),f[10])
                except Exception: continue
                buckets[(city.country_code,math.floor(city.lat),math.floor(city.lon))].append(city)
                by_country[city.country_code].append(city)
    return buckets,by_country

def nearest_city(lat,lon,cc,buckets,by_country,max_km):
    cand=[]
    for da in range(-2,3):
        for db in range(-2,3):
            cand.extend(buckets.get((cc,math.floor(lat)+da,math.floor(lon)+db),()))
    if not cand and len(by_country.get(cc,()))<=1000: cand=by_country.get(cc,[])
    best=None; dist=10**9
    for c in cand:
        d=haversine_km(lat,lon,c.lat,c.lon)
        if d<dist: best,dist=c,d
    if best is None or dist>max_km: return None,None
    return best,round(dist,1)

def servers():
    out=[]
    try:
        for x in json.loads(get(DISCOVERY,20,2)):
            host=clean(x.get("name")).lower().rstrip(".")
            if host and RADIO_BROWSER_HOST_RE.fullmatch(host):
                out.append("https://"+host)
    except Exception as e:
        print(f"[warn] discovery failed: {e}",file=sys.stderr)
    for x in FALLBACKS:
        if x not in out: out.append(x)
    return out

def fetch_stations(limit):
    q=urllib.parse.urlencode({"hidebroken":"true","order":"country","reverse":"false","limit":str(limit)})
    errors=[]
    for server in servers():
        try:
            data=json.loads(get(f"{server}/json/stations/search?{q}",180,2))
            if isinstance(data,list) and data:
                print(f"[info] fetched {len(data):,} stations from {server}")
                return data
        except Exception as e: errors.append(f"{server}: {e}")
    raise RuntimeError("Radio Browser mirrors failed: "+"; ".join(errors))

def parse_float(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception: return None

def score(s):
    return 1000*int(s.get("lastcheckok") or 0)+min(int(s.get("bitrate") or 0),512)+min(int(s.get("votes") or 0),500)

def safe_web_url(url, allow_http=False):
    try:
        p=urllib.parse.urlsplit(clean(url))
        allowed={"https"} | ({"http"} if allow_http else set())
        return p.scheme.lower() in allowed and bool(p.hostname) and not p.username and not p.password
    except (TypeError, ValueError):
        return False

def valid_stream(url):
    return safe_web_url(url, allow_http=True)

def country_code(value):
    code=clean(value).upper()
    return code if COUNTRY_CODE_RE.fullmatch(code) else "ZZ"

def dedupe(rows):
    chosen={}
    for s in rows:
        if int(s.get("lastcheckok") or 0)!=1: continue
        url=clean(s.get("url_resolved") or s.get("url"))
        if not valid_stream(url): continue
        key=(clean(s.get("stationuuid")) or url)
        s=dict(s); s["_stream"]=url
        if key not in chosen or score(s)>score(chosen[key]): chosen[key]=s
    return list(chosen.values())

def make_record(s,buckets,by_country,admin,max_km):
    cc=country_code(s.get("countrycode"))
    country=clean(s.get("country"),cc)
    region=clean(s.get("state"))
    lat,lon=parse_float(s.get("geo_lat")),parse_float(s.get("geo_long"))
    city=None; city_distance=None
    if lat is not None and lon is not None and cc!="ZZ":
        city,city_distance=nearest_city(lat,lon,cc,buckets,by_country,max_km)
    if city and not region: region=admin.get(f"{cc}.{city.admin1_code}","")
    region=region or clean(s.get("iso_3166_2")) or UNKNOWN_REGION
    tags=[x.strip() for x in clean(s.get("tags")).split(",") if x.strip()]
    langs=[x.strip() for x in clean(s.get("language")).split(",") if x.strip()]
    return {
        "id":clean(s.get("stationuuid")),"name":clean(s.get("name"),"Unnamed station"),
        "country":country,"country_code":cc,"region":region,"city":city.name if city else UNKNOWN_CITY,
        "city_distance_km":city_distance,"stream":s["_stream"],
        "homepage":clean(s.get("homepage")) if safe_web_url(s.get("homepage"), allow_http=False) else "",
        "favicon":clean(s.get("favicon")) if safe_web_url(s.get("favicon"), allow_http=False) else "",
        "tags":tags[:20],"languages":langs[:10],
        "codec":clean(s.get("codec")),"bitrate":int(s.get("bitrate") or 0),
        "votes":int(s.get("votes") or 0),"lat":lat,"lon":lon
    }

def esc(v): return str(v or "").replace('"',"'").replace("\r"," ").replace("\n"," ")

def build_m3u(rows):
    lines=["#EXTM3U"]
    for x in rows:
        group=" | ".join([x["country"],x["region"],x["city"]])
        attrs=[f'tvg-id="{esc(x["id"])}"',f'group-title="{esc(group)}"']
        if x.get("favicon"): attrs.insert(1,f'tvg-logo="{esc(x["favicon"])}"')
        lines += [f'#EXTINF:-1 {" ".join(attrs)},{esc(x["name"])}',x["stream"]]
    return "\n".join(lines)+"\n"

def write_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")

def build(output,cache,limit,max_km):
    cities=download(CITIES_URL,cache/"cities1000.zip")
    adminfile=download(ADMIN1_URL,cache/"admin1CodesASCII.txt")
    buckets,by_country=load_cities(cities); admin=load_admin1(adminfile)
    raw=fetch_stations(limit); stations=dedupe(raw)
    records=[make_record(s,buckets,by_country,admin,max_km) for s in stations]
    records.sort(key=lambda s:(s["country"].casefold(),s["region"].casefold(),s["city"].casefold(),s["name"].casefold()))
    data=output/"data"; playlists=output/"playlists"; countries=data/"countries"; cp=playlists/"countries"
    for d in (data,playlists,countries,cp): d.mkdir(parents=True,exist_ok=True)
    grouped=defaultdict(list)
    for r in records: grouped[r["country_code"]].append(r)
    meta=[]; matched=0
    for code,rows in sorted(grouped.items(),key=lambda kv:kv[1][0]["country"].casefold()):
        matched += sum(x["city"]!=UNKNOWN_CITY for x in rows)
        item={"code":code,"name":rows[0]["country"],"stations":len(rows),
              "regions":len({x["region"] for x in rows}),
              "cities":len({(x["region"],x["city"]) for x in rows if x["city"]!=UNKNOWN_CITY}),
              "file":f"data/countries/{code}.json","playlist":f"playlists/countries/{code}.m3u"}
        meta.append(item)
        write_json(countries/f"{code}.json",{"country":item,"stations":rows})
        (cp/f"{code}.m3u").write_text(build_m3u(rows),encoding="utf-8")
    generated=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    index={"project":"Global-Web-Radio","generated_at":generated,"station_count":len(records),
           "country_count":len(meta),"city_matched_count":matched,
           "city_match_rate":round(matched/len(records),4) if records else 0,
           "max_city_distance_km":max_km,"countries":meta,
           "sources":{"radio_browser":"https://www.radio-browser.info/","geonames":"https://www.geonames.org/"}}
    write_json(data/"index.json",index)
    write_json(data/"sample.json",records[:100])
    (playlists/"world.m3u").write_text(build_m3u(records),encoding="utf-8")
    print(f"[done] {len(records):,} stations / {len(meta)} countries / {matched:,} city matches")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,default=Path("public"))
    p.add_argument("--cache",type=Path,default=Path(".cache"))
    p.add_argument("--station-limit",type=int,default=100000)
    p.add_argument("--max-city-distance-km",type=float,default=80)
    p.add_argument("--clean-generated",action="store_true")
    a=p.parse_args()
    if a.clean_generated:
        for x in (a.output/"data",a.output/"playlists"):
            if x.exists(): shutil.rmtree(x)
    build(a.output,a.cache,a.station_limit,a.max_city_distance_km)

if __name__=="__main__":
    main()
