#!/usr/bin/env python3
"""Fetch actual, freely licensed hotel photos from Commons into a ZIP artifact.
Never substitutes another hotel's image or AI imagery."""
import concurrent.futures, hashlib, io, json, re, time
from pathlib import Path
from urllib.parse import quote
import requests
from PIL import Image

NAMES = [
"JW MARRIOTT Hotel Nara.jpg",
"Nara Hotel 2014 (3b).jpg",
"Osaka Marriott Miyako Hotel 19F Bar Plus 20150210-001.jpg",
"Conrad Osaka Japan01-r.jpg",
"Kobe Port Tower and Hotel Okura Kobe.jpg",
"Cerulean Tower Tokyu Hotel.jpg",
"Entrance of Nagoya Marriott Associa Hotel (Nagoya Station side).jpg",
"Prince Park Tower Tokyo1.jpg",
"The Prince Gallery Tokyo Kioicho Lobby 2018.jpg",
"Gorakadan Onsen Rotenburo 2.jpg",
"20250102 InterContinental Yokohama Grand, InterContinental Yokohama Pier 8, Marine & Walk Yokohama 203215.jpg",
"Hyatt Regency Kyoto.JPG",
"Hotel New Otani Tokyo (9518404550).jpg",
"Imperial Hotel Tokyo.JPG",
"The Peninsula Tokyo.jpg",
"The-Tokyo-Station-Hotel Entrance.jpg",
"Grand Hyatt Tokyo.JPG",
"ParkHyattTokyo.JPG",
"The Ritz-Carton Kyoto.jpg",
"Ritz-Carlton Osaka 20091223-001.jpg",
"Hotel Nikko Kansai Airport Front Entrance.JPG",
"Hotel Granvia Kyoto 20111007-001.jpg",
"Hotel Granvia Osaka.JPG",
"Hotel Granvia Okayama Lobby 2025.jpg",
"Hotel-Granvia-Hiroshima-1.jpg",
"Hotel Hankyu International 1F North Entrance 20110602-001.jpg",
"Hotel Monterey Kyoto 1F concierge desk 20130201-001.jpg",
"Hotel Monterey La Soeur Osaka 2F entrance 20101218-001.jpg",
"Waldorf Astoria Osaka Entrance.jpg",
"ST.REGIS HOTEL OSAKA ENTRANCE.JPG",
"Hilton Osaka 20120429-001.jpg",
"Hilton Tokyo 2019b.jpg",
"Hilton Tokyo Bay.JPG",
"Hilton Fukuoka Sea Hawk Hotel and Fukuoka Dome.jpg",
"ホテル日航奈良.JPG",
"Sheraton Grande Tokyo Bay Hotel.jpg",
"Tokyo DisneyLand Hotel.jpg",
"2018 Keio Plaza Hotel.jpg",
"Keio Plaza Hotel Sapporo.JPG",
"Hotel Wing International Ikebukuro 20221216 01.jpg",
"Hotel EMION 2020.jpg",
"名古屋プリンスホテル スカイタワー (50523581076).jpg",
"定山渓ビューホテル - panoramio.jpg",
"Hotel TIAD at night - 1.jpg",
"InterContinental Hotel Yokohama.jpg",
"ホテル グランセレッソ鹿児島 (42068725404).jpg",
"Hotel Clad in Gotemba (3) Apr 3, 2021.jpg"
]
API='https://commons.wikimedia.org/w/api.php'
HEAD={'User-Agent':'ChatTattunHotelPhotos/1.0 (https://github.com/tattun0721/chat-tattun; photo credits in website)'}
out=Path("photo-assets");out.mkdir(exist_ok=True)
def check(name):
    title="File:"+name
    try:
        r=requests.get(API,params={'action':'query','format':'json','formatversion':'2',
            'prop':'imageinfo','titles':title,'iiprop':'url|extmetadata',
            'iiurlwidth':800},headers=HEAD,timeout=25);r.raise_for_status()
        pages=r.json().get('query',{}).get('pages',[])
        if not pages or not pages[0].get('imageinfo'):return name,None,"missing Commons file"
        inf=pages[0]['imageinfo'][0]
        md=inf.get('extmetadata') or {}
        license=(md.get('LicenseShortName') or {}).get('value','')
        if not re.search(r'CC(?:[- ]?BY|0)|Public domain|PD-',license,re.I):return name,None,"license not approved: "+license
        url=inf.get('thumburl') or inf.get('url')
        if not url:return name,None,"missing file URL"
        imr=requests.get(url,headers=HEAD,timeout=35);imr.raise_for_status()
        image=Image.open(io.BytesIO(imr.content)).convert('RGB')
        image.thumbnail((1000,750),Image.Resampling.LANCZOS)
        digest=hashlib.sha256(name.encode()).hexdigest()[:16]
        fname=f'{digest}.jpg';image.save(out/fname,'JPEG',quality=77,optimize=True)
        author=re.sub('<[^>]+>','',str((md.get('Artist') or {}).get('value','')))[:180]
        return name,{'file':'photo-assets/'+fname,'source':inf.get('descriptionurl',f'https://commons.wikimedia.org/wiki/File:{quote(name)}'),'author':author,'license':license},None
    except Exception as e:
        return name,None,str(e)[:240]
manifest={};fail=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    for title,entry,err in executor.map(check,NAMES):
        if entry:manifest[title]=entry
        else:fail.append([title,err])
        print("PHOTO",title,'OK' if entry else err,flush=True)
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'failed.json').write_text(json.dumps(fail,ensure_ascii=False,indent=2),encoding='utf-8')
print('REAL LICENSED HOTEL PHOTOS',len(manifest),'OF',len(NAMES),flush=True)
