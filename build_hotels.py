#!/usr/bin/env python3
"""Download real Japan lodging records from Overture Places. Never synthesize listings."""
import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

PREFS="北海道 青森県 岩手県 宮城県 秋田県 山形県 福島県 茨城県 栃木県 群馬県 埼玉県 千葉県 東京都 神奈川県 新潟県 富山県 石川県 福井県 山梨県 長野県 岐阜県 静岡県 愛知県 三重県 滋賀県 京都府 大阪府 兵庫県 奈良県 和歌山県 鳥取県 島根県 岡山県 広島県 山口県 徳島県 香川県 愛媛県 高知県 福岡県 佐賀県 長崎県 熊本県 大分県 宮崎県 鹿児島県 沖縄県".split()

def prefecture(region, address):
    t = " ".join(str(x or "") for x in (region,address))
    m = re.search(r"JP[-_](\\d{1,2})",t.upper())
    if m and 1<=int(m.group(1))<=47:return PREFS[int(m.group(1))-1]
    for p in PREFS:
        if p in t:return p
    return ""

def normalize(r):
    rid,name,category,address,city,region,country,websites,lon,lat,status=r
    if not name or lon is None or lat is None:return None
    if country and str(country).upper() not in ("JP","JPN"):return None
    lon,lat=float(lon),float(lat)
    if not(122<=lon<=155 and 20<=lat<=46.7):return None
    if str(status or "").lower()=="permanently_closed":return None
    # Bounding box can contain neighboring countries; require confirmed Japan address.
    address,city,region=str(address or ""),str(city or ""),str(region or "")
    pref=prefecture(region,address)
    if not pref and str(country or "").upper() not in ("JP","JPN"):return None
    name=unicodedata.normalize("NFKC",str(name)).strip()
    if not name:return None
    website=""
    for u in websites or []:
        if isinstance(u,str) and u.startswith(("https://","http://")):
            website=u;break
    return dict(id=str(rid),name=name,pref=pref,city=city,address=address,
                site=website,type=str(category or "lodging"),lat=round(lat,6),lon=round(lon,6),
                source="Overture Maps Places", tags=[])

def latest_release():
    try:
        with urlopen("https://stac.overturemaps.org/catalog.json",timeout=25) as r:
            v=json.load(r)["latest"]
            if re.fullmatch(r"20\\d{2}-\\d{2}-\\d{2}\\.\\d+",v):return v
    except Exception as e:print("STAC fallback:",str(e),flush=True)
    return "2026-10-21.0"

def collect(release):
    import duckdb
    db=duckdb.connect()
    db.execute("INSTALL httpfs; LOAD httpfs;")
    db.execute("SET s3_region='us-west-2'")
    db.execute("SET s3_access_key_id=''")
    db.execute("SET s3_secret_access_key=''")
    db.execute("SET memory_limit='5GB'")
    db.execute("SET threads=4")
    path=f"s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"
    sql=f"""SELECT id,names.primary,taxonomy.primary,
       addresses[1].freeform,addresses[1].locality,addresses[1].region,
       addresses[1].country,websites,bbox.xmin,bbox.ymin,operating_status
       FROM read_parquet('{path}',hive_partitioning=1)
       WHERE bbox.xmin BETWEEN 122 AND 155
         AND bbox.ymin BETWEEN 20 AND 46.7
         AND names.primary IS NOT NULL
         AND list_contains(taxonomy.hierarchy, 'lodging')"""
    print("Fetching from:",path,flush=True)
    cur=db.execute(sql)
    seen={}
    read=0
    while True:
        batch=cur.fetchmany(2500)
        if not batch:break
        for row in batch:
            read+=1
            x=normalize(row)
            if not x:continue
            key=(re.sub(r"\\s+","",x["name"]).casefold(),round(x["lat"],3),round(x["lon"],3))
            if key not in seen or (x["site"] and not seen[key]["site"]):
                seen[key]=x
        if read%10000<2500: print("Scanned",read,"eligible",len(seen),flush=True)
    print("Completed:",read,"scanned,",len(seen),"unique eligible",flush=True)
    return list(seen.values())

def selftest():
    a=normalize(("id","宿A","hotel","奈良県奈良市","奈良市",None,"JP",["https://example.org"],135.8,34.68,"open"))
    assert a["pref"]=="奈良県"
    assert normalize(("x","Korean Hotel","hotel","",None,None,"KR",[],127,37,"open")) is None
    assert normalize(("x","Closed","hotel","奈良県",None,None,"JP",[],135.8,34.7,"permanently_closed")) is None
    print("Self test passed. No mock hotels are published.")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--test",action="store_true")
    p.add_argument("--output",default="site/hotels.json")
    p.add_argument("--release",default="")
    args=p.parse_args()
    if args.test:return selftest()
    release=args.release or latest_release()
    rows=collect(release)
    if not rows:raise RuntimeError("No records fetched; refusing to overwrite existing catalog")
    rows.sort(key=lambda r:(r["pref"],r["city"],r["name"]))
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    info={"source":"Overture Maps Places","release":release,"count":len(rows),
          "prefecture_known":sum(bool(x["pref"]) for x in rows),
          "registered_websites":sum(bool(x["site"]) for x in rows),
          "generated_at_utc":datetime.now(timezone.utc).isoformat(),
          "note":"These are third-party lodging listings, not an official exhaustive register. Facilities, availability, opening status and website authenticity are unverified."}
    (path.parent/"catalog-info.json").write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Saved",len(rows),"actual lodging records to",path,flush=True)

if __name__=="__main__":main()
