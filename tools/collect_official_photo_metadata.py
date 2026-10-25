#!/usr/bin/env python3
"""Discover actual hotel website preview photographs; no image copies or Google scraping.
Use property-specific registered website and matching page title. Output image references
with provenance; sites retain copyright and may block third-party display.
"""
import argparse, collections, concurrent.futures, ipaddress, json, re, sys, time, unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser
import requests
from rapidfuzz import fuzz

DATA=Path('site/hotels.json')
OUT=Path('site/website-preview-photos.json')
STATE=Path('site/photo-scan-state.json')
BAD_DOMAINS={'booking.com','agoda.com','rakuten.co.jp','jalan.net','tripadvisor.jp','tripadvisor.com','instagram.com','facebook.com','twitter.com','x.com','airbnb.jp','airbnb.com','expedia.co.jp','expedia.com','hotels.com','google.com','maps.google.com','japan.travel','youtube.com','hotpepper.jp','navitime.co.jp','map.yahoo.co.jp','itp.ne.jp','hotespa.net.invalid'}
BAD_PATH=re.compile(r'(^|[/_-])(logo|favicon|icon|ogp_default|noimage|no-image|placeholder|blank|default|dummy)([/_.-]|$)',re.I)
GOOD_TYPES={'hotel','resort','inn','lodge','bed_and_breakfast','hostel','ryokan','service_apartment','beach_resort','lodging','guest_house','motel','country_house'}
class OGParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.title=[]; self.in_title=False; self.tags={}; self.meta_title=''; self.images=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=='title': self.in_title=True
        if tag=='meta':
            k=(d.get('property') or d.get('name') or '').lower()
            if k in ('og:image','og:image:secure_url','twitter:image','og:title','twitter:title','description','og:site_name','og:type'):
                self.tags.setdefault(k,d.get('content',''))
        if tag=='meta' and (d.get('itemprop') or '').lower()=='image':
            self.tags.setdefault('schema:image',d.get('content',''))
        if tag=='link' and (d.get('rel') or '').lower()=='image_src':
            self.tags.setdefault('image_src',d.get('href',''))
        if tag=='link' and (d.get('rel') or '').lower()=='preload' and (d.get('as') or '').lower()=='image':
            self.tags.setdefault('preload:image',d.get('href','') or d.get('imagesrcset','').split(',')[0].strip().split(' ')[0])
        # Property sites sometimes omit og:image but include visible hero photographs.
        if tag in ('img','source') and len(self.images)<120:
            hint=' '.join(str(d.get(k) or '') for k in ('class','id','alt','data-testid')).lower()
            urls=[d.get(k) for k in ('src','data-src','data-original','data-lazy-src','data-srcset','srcset')]
            for value in filter(None,urls):
                for candidate in str(value).split(',')[:4]:
                    item=candidate.strip().split()[0] if candidate.strip() else ''
                    if item and not item.startswith(('data:','blob:')):
                        self.images.append((item,hint))
                        if len(self.images)>=120:break
    def handle_endtag(self,tag):
        if tag=='title':self.in_title=False
    def handle_data(self,data):
        if self.in_title:self.title.append(data)
def norm(t):
    return re.sub(r'[\W_]+','',unicodedata.normalize('NFKC',str(t or '')).lower()).replace('ホテル','hotel').replace('旅館','ryokan')
def domain_bad(host):
    host=(host or '').lower().strip('.')
    if not host or any(host==d or host.endswith('.'+d) for d in BAD_DOMAINS) or host.endswith(('.local','.internal')):return True
    try:
        ip=ipaddress.ip_address(host)
        return not ip.is_global
    except ValueError:return False
def url_good(u):
    try:
        p=urlparse(u);return p.scheme in ('http','https') and p.hostname and not domain_bad(p.hostname) and not (p.username or p.password) and p.port in (None,80,443)
    except Exception:return False
def image_url(img,base):
    u=urljoin(base,img.strip())
    if not u.startswith('https://'):return None
    p=urlparse(u)
    if not p.hostname or domain_bad(p.hostname) or BAD_PATH.search(p.path):return None
    if re.search(r'\.(svg|ico|gif)(?:$|[?])',p.path,re.I):return None
    if len(u)>1500 or p.username or p.password or p.port not in (None,443):return None
    return u

def choose_photo(page,base):
    # Respect the source page's representative image first, then inspect its
    # main visual images. Never substitute a photograph of another property.
    for key in ('og:image:secure_url','og:image','twitter:image','schema:image','image_src','preload:image'):
        candidate=page.tags.get(key)
        if candidate:
            result=image_url(candidate,base)
            if result:return result,'open-graph'
    ranked=[]
    for i,(url,hint) in enumerate(page.images):
        result=image_url(url,base)
        if not result:continue
        path=urlparse(result).path.lower()
        score=0
        if re.search(r'hero|mainvisual|main-visual|main_view|slide|slider|keyvisual|mv[-_/]|topimage|top-img',hint+' '+path):score+=9
        if re.search(r'room|hotel|stay|facility|exterior|photo|gallery|旅館|ホテル|外観|客室|景色|風景',hint+' '+path):score+=3
        if re.search(r'btn|banner|button|thumbnail|avatar|qr|sns|facebook|instagram|menu|nav|badge|spacer|payment|icon|logo',hint+' '+path):score-=15
        if re.search(r'\b(?:[1-9]\d?|1\d\d)[xX](?:[1-9]\d?|1\d\d)\b',path):score-=10
        if score>=3:ranked.append((score,-i,result))
    if ranked:
        ranked.sort(reverse=True)
        return ranked[0][2],'page-photo'
    return None,None

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
    record_id=row.get('id') if isinstance(row,dict) else None
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
                if len(data)>=260000:break
            encoding=r.encoding or 'utf-8'
            if encoding.lower()=='iso-8859-1':encoding='utf-8'
            html=data.decode(encoding,errors='replace')
            page=OGParser();page.feed(html)
            title=(page.tags.get('og:title') or page.tags.get('twitter:title') or ''.join(page.title)).strip()
            if not names_match(name,title,r.url):return None,'title-mismatch'
            photo,method=choose_photo(page,r.url)
            if not photo:return None,'no-page-photo'
            # A property page may show generic chain images. We only retain page-matched metadata.
            return {'id':record_id,'name':name,'pref':pref,'city':city,'url':photo,'source':r.url,
                    'pageTitle':title[:140],'method':method,'kind':'registered-website-preview',
                    'note':'登録Webサイトの掲載画像URL。実写・公式サイト・利用許諾・内容は個別未検証'},'ok'
    except Exception as e:return None,'error'

def main():
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=0,help='0 means every remaining registered website')
    p.add_argument('--workers',type=int,default=16);p.add_argument('--offset',type=int,default=0)
    p.add_argument('--retry-days',type=int,default=60,help='Revisit failed sites after this many days')
    args=p.parse_args()
    rows=json.loads(DATA.read_text(encoding='utf-8'))
    previous=[]
    if OUT.exists():
        try:previous=json.loads(OUT.read_text(encoding='utf-8')).get('photos',[])
        except Exception:previous=[]
    oldkeys={(x.get('name'),x.get('pref'),x.get('city')) for x in previous}
    state={}
    if STATE.exists():
        try:state=json.loads(STATE.read_text(encoding='utf-8')).get('attempts',{})
        except Exception:state={}
    today=int(time.time()//86400)
    def row_key(r):
        if isinstance(r,list):return '|'.join(str(x) for x in (r[0],r[1],r[2],r[4]))
        return r.get('id') or '|'.join(str(r.get(k,'')) for k in ('name','pref','city','site'))
    def due(r):
        attempt=state.get(row_key(r))
        return not attempt or today-int(attempt.get('day',0))>=args.retry_days
    # Attempt every lodging record that has a registered property website.
    candidates=[r for r in rows if (
       (r[4] and url_good(r[4]) and (r[0],r[1],r[2]) not in oldkeys and due(r))
       if isinstance(r,list) else (
       r.get('site') and url_good(r['site']) and (r.get('name'),r.get('pref'),r.get('city')) not in oldkeys and due(r)))]
    # Prioritize actual hotels/resorts; retain stable names for reproducibility.
    candidates.sort(key=lambda r:(0 if (r[5] if isinstance(r,list) else r.get('type')) in ('hotel','resort','ryokan') else 1,
                            -(len(r[0] if isinstance(r,list) else r.get('name',''))),r[0] if isinstance(r,list) else r.get('name','')))
    candidates=candidates[args.offset:args.offset+args.limit] if args.limit>0 else candidates[args.offset:]
    print('Checking',len(candidates),'registered URLs. Prior records:',len(previous),flush=True)
    counts=collections.Counter();found=list(previous)
    t=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i,(row,(photo,status)) in enumerate(zip(candidates,pool.map(task,candidates)),1):
            counts[status]+=1
            state[row_key(row)]={'day':today,'status':status}
            if photo:found.append(photo)
            if i%250==0:print('PROGRESS',i,'/',len(candidates),'NEW IMAGES',counts['ok'],'reasons',counts.most_common(6),'elapsed',round(time.monotonic()-t),flush=True)
    dedup={}
    for x in found: dedup[(x['name'],x['pref'],x.get('city'))]=x
    found=sorted(dedup.values(),key=lambda x:(x['pref'],x['name']))
    payload={'count':len(found),'new_count':counts['ok'],'checked_count':len(candidates),
             'providers':['Hotel registered website Open Graph metadata'],
             'usage_notice':'Image URLs link to property-registered third-party websites. This does not grant permission to republish images.',
             'photos':found}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    STATE.write_text(json.dumps({'last_scan_day':today,'attempts':state},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print('FINAL',json.dumps({'count':len(found),'new_count':counts['ok'],'checked_count':len(candidates),'outcomes':dict(counts)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
