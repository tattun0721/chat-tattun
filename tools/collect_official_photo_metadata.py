#!/usr/bin/env python3
"""Discover actual hotel website preview photographs; no image copies or Google scraping.
Use property-specific registered website and matching page title. Output image references
with provenance; sites retain copyright and may block third-party display.
"""
import argparse, collections, concurrent.futures, json, re, sys, time, unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser
import requests
from rapidfuzz import fuzz

DATA=Path('site/hotels.json')
OUT=Path('site/website-preview-photos.json')
BAD_DOMAINS={'booking.com','agoda.com','rakuten.co.jp','jalan.net','tripadvisor.jp','tripadvisor.com','instagram.com','facebook.com','twitter.com','x.com','airbnb.jp','airbnb.com','expedia.co.jp','expedia.com','hotels.com','google.com','maps.google.com','japan.travel','youtube.com','hotpepper.jp','navitime.co.jp','map.yahoo.co.jp','itp.ne.jp','hotespa.net.invalid'}
BAD_PATH=re.compile(r'(^|[/_-])(logo|favicon|icon|ogp_default|noimage|no-image|placeholder|blank|default|dummy)([/_.-]|$)',re.I)
GOOD_TYPES={'hotel','resort','inn','lodge','bed_and_breakfast','hostel','ryokan','service_apartment','beach_resort','lodging','guest_house','motel','country_house'}
class OGParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.title=[]; self.in_title=False; self.tags={}; self.meta_title=''
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=='title': self.in_title=True
        if tag=='meta':
            k=(d.get('property') or d.get('name') or '').lower()
            if k in ('og:image','og:image:secure_url','twitter:image','og:title','twitter:title','description','og:site_name','og:type'):
                self.tags.setdefault(k,d.get('content',''))
        if tag=='link' and (d.get('rel') or '').lower()=='image_src':
            self.tags.setdefault('image_src',d.get('href',''))
    def handle_endtag(self,tag):
        if tag=='title':self.in_title=False
    def handle_data(self,data):
        if self.in_title:self.title.append(data)
def norm(t):
    return re.sub(r'[\W_]+','',unicodedata.normalize('NFKC',str(t or '')).lower()).replace('ホテル','hotel').replace('旅館','ryokan')
def domain_bad(host):
    host=(host or '').lower().strip('.')
    return not host or any(host==d or host.endswith('.'+d) for d in BAD_DOMAINS) or host.endswith(('.local','.internal'))
def url_good(u):
    try:
        p=urlparse(u);return p.scheme in ('http','https') and p.hostname and not domain_bad(p.hostname) and not (p.username or p.password) and p.port in (None,80,443)
    except Exception:return False
def image_url(img,base):
    u=urljoin(base,img.strip())
    if not u.startswith('https://'):return None
    p=urlparse(u)
    if not p.hostname or BAD_PATH.search(p.path):return None
    if re.search(r'\.(svg|ico|gif)(?:$|[?])',p.path,re.I):return None
    if len(u)>1500:return None
    return u

def names_match(name,title,url):
    a=norm(name); b=norm(title)
    if len(a)<5 or len(b)<5:return False
    # An exact containment is particularly reliable for property-specific pages.
    if a in b:return True
    if re.search(r'(ホテル|Hotel|旅館)',name,re.I) and len(a)>=9 and fuzz.partial_ratio(a,b)>=94:return True
    # For titles with regional context, fuzzy matching is still strict.
    if len(a)>=12 and fuzz.partial_ratio(a,b)>=91:return True
    return False

def task(row):
    name,pref,city,address,web,kind,lat,lon=(row + ['']*8)[:8] if isinstance(row,list) else (
       row.get('name',''),row.get('pref',''),row.get('city',''),row.get('address',''),
       row.get('site',''),row.get('type',''),row.get('lat'),row.get('lon'))
    if not web or not url_good(web):return None,'skip'
    headers={'User-Agent':'Mozilla/5.0 (compatible; CHAT-TATTUN-MetadataDiscovery/1.0; +https://github.com/tattun0721/chat-tattun)','Accept':'text/html,application/xhtml+xml;q=0.9','Accept-Language':'ja,en;q=0.8'}
    try:
        # Fetch only small metadata-containing portion of public property page.
        with requests.get(web,headers=headers,timeout=(3.5,7.0),allow_redirects=True,stream=True) as r:
            if r.status_code!=200:return None,'http'
            if not url_good(r.url):return None,'redirect'
            if not ('html' in r.headers.get('Content-Type','').lower()):return None,'non-html'
            data=b''
            for chunk in r.iter_content(chunk_size=8192):
                data+=chunk
                if len(data)>=150000:break
            encoding=r.encoding or 'utf-8'
            if encoding.lower()=='iso-8859-1':encoding='utf-8'
            html=data.decode(encoding,errors='replace')
            page=OGParser();page.feed(html)
            title=(page.tags.get('og:title') or page.tags.get('twitter:title') or ''.join(page.title)).strip()
            if not names_match(name,title,r.url):return None,'title-mismatch'
            candidate=page.tags.get('og:image:secure_url') or page.tags.get('og:image') or page.tags.get('twitter:image') or page.tags.get('image_src')
            if not candidate:return None,'no-image-meta'
            photo=image_url(candidate,r.url)
            if not photo:return None,'unsafe-image'
            # A property page may show generic chain images. We only retain page-matched metadata.
            return {'name':name,'pref':pref,'city':city,'url':photo,'source':r.url,
                    'pageTitle':title[:140],'kind':'registered-website-preview',
                    'note':'宿泊施設の登録Webサイトが設定した代表画像。実写・利用許諾・内容は個別未検証'},'ok'
    except Exception as e:return None,'error'

def main():
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=5000)
    p.add_argument('--workers',type=int,default=16);p.add_argument('--offset',type=int,default=0)
    args=p.parse_args()
    rows=json.loads(DATA.read_text(encoding='utf-8'))
    previous=[]
    if OUT.exists():
        try:previous=json.loads(OUT.read_text(encoding='utf-8')).get('photos',[])
        except Exception:previous=[]
    oldkeys={(x.get('name'),x.get('pref')) for x in previous}
    candidates=[r for r in rows if (
       (r[5] in GOOD_TYPES and r[4] and url_good(r[4]) and (r[0],r[1]) not in oldkeys)
       if isinstance(r,list) else (
       r.get('type') in GOOD_TYPES and r.get('site') and url_good(r['site']) and (r.get('name'),r.get('pref')) not in oldkeys))]
    # Prioritize actual hotels/resorts; retain stable names for reproducibility.
    candidates.sort(key=lambda r:(0 if (r[5] if isinstance(r,list) else r.get('type')) in ('hotel','resort','ryokan') else 1,
                            -(len(r[0] if isinstance(r,list) else r.get('name',''))),r[0] if isinstance(r,list) else r.get('name','')))
    candidates=candidates[args.offset:args.offset+args.limit]
    print('Checking',len(candidates),'registered URLs. Prior records:',len(previous),flush=True)
    counts=collections.Counter();found=list(previous)
    t=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i,(photo,status) in enumerate(pool.map(task,candidates),1):
            counts[status]+=1
            if photo:found.append(photo)
            if i%250==0:print('PROGRESS',i,'/',len(candidates),'NEW IMAGES',counts['ok'],'reasons',counts.most_common(6),'elapsed',round(time.monotonic()-t),flush=True)
    dedup={}
    for x in found: dedup[(x['name'],x['pref'])]=x
    found=sorted(dedup.values(),key=lambda x:(x['pref'],x['name']))
    payload={'count':len(found),'new_count':counts['ok'],'checked_count':len(candidates),
             'providers':['Hotel registered website Open Graph metadata'],
             'usage_notice':'Image URLs link to property-registered third-party websites. This does not grant permission to republish images.',
             'photos':found}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print('FINAL',json.dumps({'count':len(found),'new_count':counts['ok'],'checked_count':len(candidates),'outcomes':dict(counts)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
