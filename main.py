
import os
import json
import time
import threading
import requests
import re
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin

# ==========================================
# إعدادات التطبيق
# ==========================================
app = Flask(__name__)
CORS(app)

# مفتاح سري لحماية الرابط
API_SECRET = os.environ.get('API_SECRET', 'Zeusndndjddnejdjdjdejekk29393838msmskxcm9239484jdndjdnddjj99292938338zeuslojdnejxxmejj82283849')

# رابط الخادم الرئيسي (Node.js)
NODE_BACKEND_URL = os.environ.get('NODE_BACKEND_URL', 'https://c-production-3db6.up.railway.app')

# ==========================================
# 🍪 إعدادات الكوكيز (تجاوز حماية تسجيل الدخول)
# ==========================================
MARKAZ_COOKIES = 'wordpress_logged_in_198f6e9e82ba200a53325105f201ddc5=53a8cc0077488fb5a321840b4e1f18e7%7C1770510651%7CZmUj9XvN1Cem8SZvUhUfgdlhjnaNrDJEG5fx8iqM53y%7C24bb480a43ebe89e75de989f9afd0f4846079186c93e064185de2a015e37df0f'

# ==========================================
# 🔄 GLOBAL SERVER-SIDE SCHEDULER STATE
# ==========================================
SCHEDULER_CONFIG = {
    'active': False,
    'interval_seconds': 86400, # Default 24h
    'next_run': 0,
    'last_run': 0,
    'status': 'idle',
    'admin_email': 'system@auto'
}

# ==========================================
# أدوات السحب المشتركة (Shared Scraper Tools)
# ==========================================

def get_headers(referer=None, use_cookies=False):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ar,en-US;q=0.7,en;q=0.3',
    }
    if referer:
        headers['Referer'] = referer
    
    if use_cookies and MARKAZ_COOKIES and MARKAZ_COOKIES != 'ضع_هنا_الكوكيز_الخاصة_بك_كاملة':
        headers['Cookie'] = MARKAZ_COOKIES
        
    return headers

def fix_image_url(url, base_url='https://api.rewayat.club'):
    if not url: return ""
    if url.startswith('//'):
        return 'https:' + url
    elif url.startswith('/'):
        # Fix for absolute paths without domain
        if 'novelfire.net' in base_url:
            return 'https://novelfire.net' + url
        elif 'wuxiabox.com' in base_url or 'wuxiaspot.com' in base_url:
             parsed = urlparse(base_url)
             domain = f"{parsed.scheme}://{parsed.netloc}"
             return domain + url
        return base_url + url
    elif not url.startswith('http'):
        return base_url + '/' + url
    return url

def parse_relative_date(date_str):
    """تحويل التواريخ النسبية (منذ 5 ساعات) إلى تاريخ حقيقي"""
    try:
        if not date_str: return datetime.now().isoformat()
        
        now = datetime.now()
        text = date_str.lower().strip()
        
        # إزالة كلمات زائدة
        text = text.replace('updated', '').replace('ago', '').strip()
        
        # استخراج الرقم والوحدة
        match = re.search(r'(\d+)\s*(sec|min|hour|day|week|month|year)', text)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)
            
            delta = timedelta(seconds=0)
            if 'sec' in unit: delta = timedelta(seconds=amount)
            elif 'min' in unit: delta = timedelta(minutes=amount)
            elif 'hour' in unit: delta = timedelta(hours=amount)
            elif 'day' in unit: delta = timedelta(days=amount)
            elif 'week' in unit: delta = timedelta(weeks=amount)
            elif 'month' in unit: delta = timedelta(days=amount * 30)
            elif 'year' in unit: delta = timedelta(days=amount * 365)
            
            return (now - delta).isoformat()
            
        # محاولة قراءة تاريخ ثابت (May 20, 2024)
        try:
            # Common formats like "May 20, 2024"
            dt = datetime.strptime(text, '%B %d, %Y')
            return dt.isoformat()
        except:
            pass
            
        return now.isoformat()
    except:
        return datetime.now().isoformat()

def send_data_to_backend(payload):
    """إرسال البيانات إلى الخادم الرئيسي"""
    try:
        endpoint = f"{NODE_BACKEND_URL}/api/scraper/receive"
        headers = { 'Content-Type': 'application/json', 'Authorization': API_SECRET, 'x-api-secret': API_SECRET }
        response = requests.post(endpoint, json=payload, headers=headers, timeout=60)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Failed to send data: {e}")
        return False

def check_existing_chapters(title):
    """التحقق من الفصول الموجودة في الباك إند لمنع التكرار"""
    try:
        endpoint = f"{NODE_BACKEND_URL}/api/scraper/check-chapters"
        headers = { 'Content-Type': 'application/json', 'Authorization': API_SECRET, 'x-api-secret': API_SECRET }
        response = requests.post(endpoint, json={'title': title}, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('exists'):
                return data['chapters']
            else:
                return []
        return []
    except Exception as e:
        print(f"❌ Error checking existence: {e}")
        return []

# ==========================================
# 🟣 1. Rewayat Club (Nuxt) Logic
# ==========================================

def extract_from_nuxt(soup):
    try:
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and 'window.__NUXT__' in script.string:
                content = script.string
                match = re.search(r'poster_url:"(.*?)"', content)
                if not match: match = re.search(r'poster:"(.*?)"', content)
                if match:
                    raw_url = match.group(1)
                    return raw_url.encode('utf-8').decode('unicode_escape')
    except: pass
    return None

def fetch_metadata_rewayat(url):
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title_tag = soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"
        
        cover_url = extract_from_nuxt(soup) or ""
        if not cover_url:
            og_image = soup.find("meta", property="og:image")
            if og_image: cover_url = og_image["content"]
        cover_url = fix_image_url(cover_url)

        desc_div = soup.find(class_='text-pre-line') or soup.find('div', class_='v-card__text')
        description = desc_div.get_text(separator="\n\n", strip=True) if desc_div else ""
        
        # 🔥🔥 STATUS CHECK - REWAYAT CLUB SPECIFIC 🔥🔥
        status = "مستمرة"
        # 1. Check for specific status badges in Vuetify chips
        chips = soup.find_all(class_='v-chip__content')
        for chip in chips:
            txt = chip.get_text(strip=True)
            if "مكتملة" in txt or "Completed" in txt:
                status = "مكتملة"
                break
        
        # 2. Fallback: Search in full text if not found
        if status == "مستمرة":
            if "مكتملة" in soup.get_text():
                status = "مكتملة"

        return {
            'title': title, 'description': description, 'cover': cover_url,
            'status': status, 'category': "عام", 'tags': [], 'sourceUrl': url,
            'lastUpdate': datetime.now().isoformat() # Fallback for rewayat
        }
    except Exception as e:
        print(f"Error rewayat metadata: {e}")
        return None

def scrape_chapter_rewayat(novel_url, chapter_num):
    url = f"{novel_url.rstrip('/')}/{chapter_num}"
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        if response.status_code != 200: return None, None
        soup = BeautifulSoup(response.content, 'html.parser')
        paragraphs = soup.find_all('p')
        clean_paragraphs = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
        if clean_paragraphs:
            text = "\n\n".join(clean_paragraphs)
        else:
            div = soup.find('div', class_='pre-formatted') or soup.find('div', class_='v-card__text')
            text = div.get_text(separator="\n\n", strip=True) if div else ""
        
        if len(text.strip()) < 2: return None, None
        
        title_tag = soup.find(class_='v-card__subtitle') or soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else f"الفصل {chapter_num}"
        title = re.sub(r'^\d+\s*-\s*', '', title)
        return title, text
    except: return None, None

def worker_rewayat_probe(url, admin_email, metadata):
    existing_chapters = check_existing_chapters(metadata['title'])
    # If novel exists, we set skipMetadataUpdate = True, BUT we still send the detected status
    skip_meta = len(existing_chapters) > 0
    
    # Send initial meta update (always send sourceUrl and status)
    send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': [], 'skipMetadataUpdate': skip_meta})

    current_chapter = 1
    errors = 0
    batch = []
    
    while current_chapter < 5000 and errors < 15:
        if current_chapter in existing_chapters:
            current_chapter += 1
            errors = 0
            continue
            
        chap_title, content = scrape_chapter_rewayat(url, current_chapter)
        if content:
            errors = 0
            batch.append({'number': current_chapter, 'title': chap_title, 'content': content})
            print(f"Fetched Ch {current_chapter}")
            if len(batch) >= 5:
                send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': True})
                batch = []
                time.sleep(1)
        else:
            errors += 1
            print(f"Failed Ch {current_chapter} ({errors}/15)")
        current_chapter += 1
        
    if batch:
        send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': True})

# ==========================================
# 🟢 2. Madara Themes (Ar-Novel & Markaz Riwayat)
# ==========================================

def get_base_url(url):
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"

def fetch_metadata_madara(url):
    try:
        use_cookies = 'markazriwayat.com' in url
        response = requests.get(url, headers=get_headers(use_cookies=use_cookies), timeout=15)
        
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title_tag = soup.find(class_='post-title')
        title = title_tag.find('h1').get_text(strip=True) if title_tag else "Unknown"
        title = re.sub(r'\s*~.*$', '', title) 

        cover = ""
        og_img = soup.find("meta", property="og:image")
        if og_img: 
            cover = og_img["content"]
        
        if not cover:
            img_container = soup.find(class_='summary_image')
            if img_container:
                img_tag = img_container.find('img')
                if img_tag:
                    cover = img_tag.get('data-src') or img_tag.get('src') or img_tag.get('srcset', '').split(' ')[0]

        cover = fix_image_url(cover)

        novel_id = None
        shortlink = soup.find("link", rel="shortlink")
        if shortlink:
            match = re.search(r'p=(\d+)', shortlink.get('href', ''))
            if match: novel_id = match.group(1)
            
        if not novel_id:
            id_input = soup.find('input', class_='rating-post-id')
            if id_input: novel_id = id_input.get('value')
            
        if not novel_id:
            body_tag = soup.find('body')
            if body_tag and body_tag.has_attr('class'):
                body_class = body_tag.get('class', [])
                for c in body_class:
                    if c.startswith('manga-id-'):
                        novel_id = c.replace('manga-id-', '')

        print(f"Found Novel ID: {novel_id}")

        desc_div = soup.find(class_='summary__content') or soup.find(class_='description-summary')
        if desc_div:
            description = desc_div.get_text(separator="\n\n", strip=True)
            description = re.sub(r'\n{3,}', '\n\n', description)
        else:
            description = ""

        genres_content = soup.find(class_='genres-content')
        category = "عام"
        tags = []
        if genres_content:
            links = genres_content.find_all('a')
            tags = [a.get_text(strip=True) for a in links]
            if tags: category = tags[0]

        # Check Status in Madara
        status = "مستمرة"
        status_terms = soup.find_all('div', class_='post-status')
        if status_terms:
            for st in status_terms:
                txt = st.get_text(strip=True).lower()
                if 'completed' in txt or 'مكتملة' in txt:
                    status = "مكتملة"
                    break
        
        # 🔥 Extract Last Update Time (Madara specific)
        last_update = datetime.now().isoformat()
        # Usually in .post-on or .post-date
        update_node = soup.select_one('.post-on span') or soup.select_one('.post-on')
        if update_node:
            last_update = parse_relative_date(update_node.get_text(strip=True))

        return {
            'title': title, 'description': description, 'cover': cover,
            'status': status, 'category': category, 'tags': tags,
            'novel_id': novel_id, 'sourceUrl': url,
            'lastUpdate': last_update
        }
    except Exception as e:
        print(f"Error Madara Meta: {e}")
        return None

def fetch_metadata_markaz(url):
    return fetch_metadata_madara(url)

def parse_madara_chapters_from_html(soup):
    chapters = []
    items = soup.find_all('li', class_='wp-manga-chapter')
    
    for item in items:
        a = item.find('a')
        if a:
            link = a.get('href')
            raw_title = a.get_text(strip=True)
            num_match = re.search(r'(\d+)', raw_title)
            number = int(num_match.group(1)) if num_match else 0
            clean_title = re.sub(r'^\d+\s*[-–]\s*', '', raw_title).strip()
            
            if number > 0:
                chapters.append({'number': number, 'url': link, 'title': clean_title})
    
    return chapters

def fetch_chapter_list_madara(novel_id, novel_url):
    chapters = []
    base_url = get_base_url(novel_url)
    use_cookies = 'markazriwayat.com' in novel_url
    
    if novel_url:
        ajax_endpoint = f"{novel_url.rstrip('/')}/ajax/chapters/"
        try:
            headers = get_headers(use_cookies=use_cookies)
            headers['X-Requested-With'] = 'XMLHttpRequest'
            res = requests.post(ajax_endpoint, headers=headers, timeout=20)
            if res.status_code == 200:
                soup = BeautifulSoup(res.content, 'html.parser')
                chapters = parse_madara_chapters_from_html(soup)
                print(f"✅ Chapters fetched via /ajax/chapters/ ({len(chapters)})")
        except Exception as e:
            print(f"AJAX endpoint failed: {e}")

    if not chapters and novel_id:
        try:
            admin_ajax_url = f"{base_url}/wp-admin/admin-ajax.php"
            data = {'action': 'manga_get_chapters', 'manga': novel_id}
            res = requests.post(admin_ajax_url, data=data, headers=get_headers(novel_url, use_cookies=use_cookies), timeout=20)
            if res.status_code == 200:
                soup = BeautifulSoup(res.content, 'html.parser')
                chapters = parse_madara_chapters_from_html(soup)
                print(f"✅ Chapters fetched via admin-ajax ({len(chapters)})")
        except Exception as e:
            print(f"admin-ajax failed: {e}")
            
    if chapters:
        chapters.sort(key=lambda x: x['number'])
    
    return chapters

def scrape_chapter_madara(url):
    try:
        use_cookies = 'markazriwayat.com' in url
        res = requests.get(url, headers=get_headers(use_cookies=use_cookies), timeout=15)
        if res.status_code != 200: return None
        soup = BeautifulSoup(res.content, 'html.parser')
        
        container = soup.find(class_='reader-target') or \
                    soup.find(class_='reading-content') or \
                    soup.find(class_='text-left') or \
                    soup.find(class_='text-right') or \
                    soup.find(class_='entry-content')
            
        if container:
            for bad in container.find_all(['div', 'script', 'style', 'input', 'ins', 'iframe', 'button']):
                if bad.get('class') and any(c in ['nav-links', 'code-block', 'adsbygoogle', 'pf-ad', 'wpmcr-under-title-row'] for c in bad.get('class')):
                    bad.decompose()
                if bad.get('id') == 'reader-btn':
                    bad.decompose()
            
            for nav in container.find_all('div', class_='nav-links'):
                nav.decompose()

            text = container.get_text(separator="\n\n", strip=True)
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = text.replace('اكمال القراءة', '')
            text = text.replace('إعدادات القراءة', '') 
            
            if len(text) < 200 and 'سجل' in text:
                print("⚠️ Warning: Chapter content seems blocked by login wall.")
                
            return text
        return None
    except: return None

def worker_madara_list(url, admin_email, metadata):
    existing_chapters = check_existing_chapters(metadata['title'])
    skip_meta = len(existing_chapters) > 0
    
    # Always update meta to sync status and URL
    send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': [], 'skipMetadataUpdate': skip_meta})

    all_chapters = fetch_chapter_list_madara(metadata.get('novel_id'), url)
    
    if not all_chapters:
        print(f"No chapters found for {metadata['title']}")
        return

    print(f"Processing {len(all_chapters)} chapters.")
    
    batch = []
    for chap in all_chapters:
        if chap['number'] in existing_chapters:
            continue
            
        print(f"Scraping {metadata['title']} - Ch {chap['number']}...")
        content = scrape_chapter_madara(chap['url'])
        
        if content:
            batch.append({
                'number': chap['number'],
                'title': chap['title'],
                'content': content
            })
            
            if len(batch) >= 5:
                send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': True})
                batch = []
                time.sleep(1.5)
        
    if batch:
        send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': True})

# ==========================================
# 🟠 3. Novel Fire (novelfire.net) Logic
# ==========================================

def fetch_metadata_novelfire(url):
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Update: Use dedicated classes if possible based on new HTML
        title_tag = soup.select_one('h1.novel-title')
        if not title_tag:
            # Fallback to OG
            meta_title = soup.find("meta", property="og:title")
            title = meta_title["content"] if meta_title else "Unknown Title"
        else:
            title = title_tag.get_text(strip=True)
            
        title = title.replace(' - Novel Fire', '').strip()

        # Cover (Updated selector)
        cover = ""
        img_tag = soup.select_one('figure.cover img')
        if img_tag:
            cover = img_tag.get('src')
        
        if not cover:
            og_img = soup.find("meta", property="og:image")
            if og_img: cover = og_img["content"]
            
        cover = fix_image_url(cover, base_url='https://novelfire.net')

        # Description (Updated selector for .summary .content)
        desc_div = soup.select_one('.summary .content')
        if not desc_div:
            desc_div = soup.find('div', class_='description') or soup.find('div', id='novel-summary')
            
        description = desc_div.get_text(separator="\n\n", strip=True) if desc_div else ""

        tags = []
        # Updated genre selector
        genre_links = soup.select('.categories ul li a')
        if not genre_links:
            genre_links = soup.select('.novel-genres a')
            
        for link in genre_links:
            tags.append(link.get_text(strip=True))
        category = tags[0] if tags else "عام"

        # 🔥🔥 STATUS CHECK - NOVEL FIRE SPECIFIC 🔥🔥
        status = "مستمرة"
        completed_tag = soup.find('strong', class_='completed')
        if completed_tag and 'Completed' in completed_tag.get_text(strip=True):
            status = "مكتملة"

        # 🔥 Extract Last Update Time
        last_update = datetime.now().isoformat()
        update_node = soup.select_one('.chapter-latest-container .update')
        if update_node:
            last_update = parse_relative_date(update_node.get_text(strip=True))

        return {
            'title': title, 'description': description, 'cover': cover,
            'status': status, 'category': category, 'tags': tags, 'sourceUrl': url,
            'lastUpdate': last_update
        }
    except Exception as e:
        print(f"Error NovelFire Meta: {e}")
        return None

def fetch_chapter_list_novelfire(novel_url):
    """سحب جميع الفصول من NovelFire مع دعم التنقل بين الصفحات (Pagination)"""
    chapters = []
    # التأكد من الذهاب لصفحة الفصول
    if not novel_url.rstrip('/').endswith('/chapters'):
        list_url = novel_url.rstrip('/') + '/chapters'
    else:
        list_url = novel_url

    try:
        # البدء من الصفحة الأولى
        current_page = 1
        
        while True:
            # تكوين رابط الصفحة الحالية
            page_url = f"{list_url}?page={current_page}"
            print(f"🔍 Fetching chapters from NovelFire Page: {current_page}")
            
            res = requests.get(page_url, headers=get_headers(), timeout=15)
            if res.status_code != 200: break
            
            soup = BeautifulSoup(res.content, 'html.parser')
            
            # استخراج الفصول من الصفحة الحالية
            items = soup.select('ul.chapter-list li')
            if not items:
                break # لا توجد فصول، توقف
                
            for item in items:
                a = item.find('a')
                if a:
                    href = a.get('href', '')
                    link = 'https://novelfire.net' + href if href.startswith('/') else href
                    raw_title = a.get_text(strip=True)
                    
                    # استخراج رقم الفصل من الرابط أو العنوان
                    num_match = re.search(r'chapter-(\d+)', link)
                    if not num_match: num_match = re.search(r'(\d+)', raw_title)
                    
                    number = int(num_match.group(1)) if num_match else 0
                    if number > 0:
                        chapters.append({'number': number, 'url': link, 'title': raw_title})
            
            # التحقق مما إذا كانت هناك صفحة تالية (Next)
            # نبحث عن زر Next في Pagination
            next_btn = soup.select_one('li.page-item a[rel="next"]')
            if next_btn:
                current_page += 1
                time.sleep(0.5) # تأخير بسيط لتجنب الضغط على السيرفر
            else:
                break # لا توجد صفحة تالية، انتهينا

        # ترتيب جميع الفصول المجمعة من كل الصفحات
        chapters.sort(key=lambda x: x['number'])
        print(f"✅ Total chapters found across all pages: {len(chapters)}")
        return chapters
    except Exception as e:
        print(f"Error list NovelFire with pagination: {e}")
        return []

def scrape_chapter_novelfire(url):
    try:
        res = requests.get(url, headers=get_headers(), timeout=15)
        if res.status_code != 200: return None
        soup = BeautifulSoup(res.content, 'html.parser')
        
        container = soup.find('div', id='content') or soup.find('div', class_='chapter-content')
        if container:
            for bad in container.find_all(['div', 'script', 'style', 'ins', 'button']):
                if bad.get('class') and ('ads' in str(bad.get('class'))):
                    bad.decompose()

            text = container.get_text(separator="\n\n", strip=True)
            text = re.sub(r'Read.*online.*now!', '', text)
            text = re.sub(r'\n{3,}', '\n\n', text)
            return text
        return None
    except: return None

def worker_novelfire_list(url, admin_email, metadata):
    existing_chapters = check_existing_chapters(metadata['title'])
    skip_meta = len(existing_chapters) > 0
    
    # Always update metadata to sync status (Completed), sourceUrl AND lastUpdate
    send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': [], 'skipMetadataUpdate': skip_meta})

    all_chapters = fetch_chapter_list_novelfire(url)
    if not all_chapters:
        print(f"No chapters found for {metadata['title']}")
        return

    batch = []
    for chap in all_chapters:
        if chap['number'] in existing_chapters:
            continue
            
        print(f"Scraping NovelFire: Ch {chap['number']}...")
        content = scrape_chapter_novelfire(chap['url'])
        if content:
            batch.append({'number': chap['number'], 'title': chap['title'], 'content': content})
            if len(batch) >= 5:
                send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': True})
                batch = []
                time.sleep(1)
        
    if batch:
        send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': True})

# ==========================================
# 🔵 4. WuxiaBox / WuxiaSpot Logic
# ==========================================

def fetch_metadata_wuxiabox(url):
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Title
        title_tag = soup.select_one('h1.novel-title')
        title = title_tag.get_text(strip=True) if title_tag else "Unknown"
        
        # Cover
        cover = ""
        img_tag = soup.select_one('figure.cover img')
        if img_tag:
            cover = img_tag.get('data-src') or img_tag.get('src')
        
        # Domain parsing for base url
        parsed_uri = urlparse(url)
        base_url = '{uri.scheme}://{uri.netloc}'.format(uri=parsed_uri)
        cover = fix_image_url(cover, base_url=base_url)

        # Description
        desc_div = soup.select_one('.summary .content') or soup.select_one('.description')
        description = desc_div.get_text(separator="\n\n", strip=True) if desc_div else ""

        # Tags & Category
        tags = []
        tags_container = soup.select('.tags a.tag')
        for t in tags_container:
            tags.append(t.get_text(strip=True))
        
        category = "عام"
        cat_tag = soup.select_one('.categories a')
        if cat_tag:
            category = cat_tag.get_text(strip=True)

        status_tag = soup.select_one('.header-stats strong')
        status = "مستمرة"
        if status_tag:
            txt = status_tag.get_text(strip=True).lower()
            if 'completed' in txt: status = "مكتملة"

        return {
            'title': title, 'description': description, 'cover': cover,
            'status': status, 'category': category, 'tags': tags,
            'base_url': base_url, 'sourceUrl': url,
            'lastUpdate': datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Error WuxiaBox Meta: {e}")
        return None

def fetch_chapter_list_wuxiabox(url, metadata):
    chapters = []
    base_url = metadata.get('base_url', 'https://wuxiabox.com')
    
    try:
        current_url = url
        
        while True:
            print(f"🔍 Fetching chapters from WuxiaBox: {current_url}")
            response = requests.get(current_url, headers=get_headers(), timeout=15)
            if response.status_code != 200: break
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract chapters
            chapter_list = soup.select('ul.chapter-list li a')
            if not chapter_list:
                # Sometimes list is dynamic, but usually on these sites it's paginated
                break
                
            for a in chapter_list:
                href = a.get('href')
                full_link = urljoin(base_url, href)
                title = a.get('title') or a.get_text(strip=True)
                
                # Extract number
                # Often format is "Chapter 123 title" or just "Chapter 123"
                # Using regex to find the first integer in the text
                num_match = re.search(r'Chapter\s+(\d+)', title, re.IGNORECASE)
                if not num_match:
                    num_match = re.search(r'(\d+)', title)
                
                if num_match:
                    number = int(num_match.group(1))
                    chapters.append({'number': number, 'url': full_link, 'title': title})
            
            # Find Next Page
            # The pagination is usually in ul.pagination
            next_btn = None
            pagination_links = soup.select('ul.pagination li a')
            for link in pagination_links:
                if '>' in link.get_text() or 'Next' in link.get_text():
                    next_btn = link
                    break
                # Sometimes it is just the last link if not numbered
                
            if next_btn:
                next_href = next_btn.get('href')
                current_url = urljoin(base_url, next_href)
                time.sleep(0.5)
            else:
                break
        
        # Remove duplicates based on number
        unique_chapters = {c['number']: c for c in chapters}.values()
        chapters = list(unique_chapters)
        chapters.sort(key=lambda x: x['number'])
        
        return chapters

    except Exception as e:
        print(f"Error WuxiaBox List: {e}")
        return []

def scrape_chapter_wuxiabox(url):
    try:
        res = requests.get(url, headers=get_headers(), timeout=15)
        if res.status_code != 200: return None
        soup = BeautifulSoup(res.content, 'html.parser')
        
        content_div = soup.select_one('.chapter-content')
        if not content_div: return None
        
        # Clean ads
        for script in content_div.find_all('script'):
            script.decompose()
        for div in content_div.find_all('div'):
            # Usually ads are in divs inside content
            div.decompose()
        for style in content_div.find_all('style'):
            style.decompose()
            
        text = content_div.get_text(separator="\n\n", strip=True)
        # Cleanup
        text = re.sub(r'\(End of this chapter\)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text
    except: return None

def worker_wuxiabox_list(url, admin_email, metadata):
    existing_chapters = check_existing_chapters(metadata['title'])
    skip_meta = len(existing_chapters) > 0
    
    send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': [], 'skipMetadataUpdate': skip_meta})

    all_chapters = fetch_chapter_list_wuxiabox(url, metadata)
    if not all_chapters:
        print("No chapters found")
        return

    batch = []
    for chap in all_chapters:
        if chap['number'] in existing_chapters:
            continue
            
        print(f"Scraping WuxiaBox: Ch {chap['number']}...")
        content = scrape_chapter_wuxiabox(chap['url'])
        
        if content:
            batch.append({'number': chap['number'], 'title': chap['title'], 'content': content})
            if len(batch) >= 5:
                send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': True})
                batch = []
                time.sleep(1)
                
    if batch:
        send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': True})

# ==========================================
# 🔴 5. FreeWebNovel Logic
# ==========================================

def fetch_metadata_freewebnovel(url):
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Title
        title_tag = soup.find("meta", property="og:title")
        title = title_tag["content"] if title_tag else soup.select_one('h1.tit').get_text(strip=True)
        # Remove site suffix
        title = title.split(' - ')[0].strip()

        # Cover
        cover_tag = soup.find("meta", property="og:image")
        cover = cover_tag["content"] if cover_tag else ""
        
        # Description
        desc_div = soup.select_one('.m-desc .txt .inner')
        if desc_div:
            description = desc_div.get_text(separator="\n\n", strip=True)
        else:
            desc_meta = soup.find("meta", property="og:description")
            description = desc_meta["content"] if desc_meta else ""

        # Status
        status = "مستمرة"
        status_node = soup.select_one('.m-imgtxt .item span.s3 a')
        if status_node and 'Completed' in status_node.get_text():
            status = "مكتملة"

        # Categories
        tags = []
        genre_links = soup.select('.m-imgtxt .item a[href*="genre"]')
        for link in genre_links:
            tags.append(link.get_text(strip=True))
        category = tags[0] if tags else "عام"

        return {
            'title': title, 'description': description, 'cover': cover,
            'status': status, 'category': category, 'tags': tags, 'sourceUrl': url,
            'lastUpdate': datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Error Freewebnovel Meta: {e}")
        return None

def fetch_chapter_list_freewebnovel(url):
    chapters = []
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        if response.status_code != 200: return []
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # List items
        items = soup.select('ul#idData li a')
        for a in items:
            href = a.get('href')
            full_link = urljoin('https://freewebnovel.com', href)
            title = a.get('title') or a.get_text(strip=True)
            
            # Extract number
            match = re.search(r'Chapter\s+(\d+)', title, re.IGNORECASE)
            if match:
                num = int(match.group(1))
                chapters.append({'number': num, 'url': full_link, 'title': title})
        
        # Deduplicate and sort
        unique = {c['number']: c for c in chapters}.values()
        chapters = list(unique)
        chapters.sort(key=lambda x: x['number'])
        return chapters
    except Exception as e:
        print(f"Error Freewebnovel List: {e}")
        return []

def scrape_chapter_freewebnovel(url):
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.content, 'html.parser')
        
        content_div = soup.select_one('.m-read .txt')
        if not content_div: return None
        
        # Clean specific trash found in file
        for bad in content_div.find_all(['script', 'style', 'subtxt', 'div', 'center']):
            bad.decompose()
            
        # Clean text
        text = content_div.get_text(separator="\n\n", strip=True)
        # Remove common ads in text if any remain
        text = re.sub(r'Find.*novels.*at.*freewebnovel.*', '', text, flags=re.IGNORECASE)
        return text
    except: return None

def worker_freewebnovel_list(url, admin_email, metadata):
    existing_chapters = check_existing_chapters(metadata['title'])
    skip_meta = len(existing_chapters) > 0
    
    send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': [], 'skipMetadataUpdate': skip_meta})

    all_chapters = fetch_chapter_list_freewebnovel(url)
    
    batch = []
    for chap in all_chapters:
        if chap['number'] in existing_chapters: continue
        
        print(f"Scraping Freewebnovel: Ch {chap['number']}...")
        content = scrape_chapter_freewebnovel(chap['url'])
        
        if content:
            batch.append({'number': chap['number'], 'title': chap['title'], 'content': content})
            if len(batch) >= 5:
                send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': True})
                batch = []
                time.sleep(1)
                
    if batch:
        send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': True})

# ==========================================
# 🔄 MAIN AUTOMATIC SCHEDULER LOGIC
# ==========================================

def perform_single_scrape(url, admin_email):
    """Executes scraping for a single URL without creating new threads (synchronous for scheduler)"""
    try:
        if not url: return
        print(f"⏰ Scheduler Checking: {url}")
        
        if 'rewayat.club' in url:
            meta = fetch_metadata_rewayat(url)
            if meta: worker_rewayat_probe(url, admin_email, meta)
        elif 'ar-no.com' in url:
            meta = fetch_metadata_madara(url)
            if meta: worker_madara_list(url, admin_email, meta)
        elif 'markazriwayat.com' in url:
            meta = fetch_metadata_madara(url)
            if meta: worker_madara_list(url, admin_email, meta)
        elif 'novelfire.net' in url:
            meta = fetch_metadata_novelfire(url)
            if meta: worker_novelfire_list(url, admin_email, meta)
        elif 'wuxiabox.com' in url or 'wuxiaspot.com' in url:
            meta = fetch_metadata_wuxiabox(url)
            if meta: worker_wuxiabox_list(url, admin_email, meta)
        elif 'freewebnovel.com' in url:
            meta = fetch_metadata_freewebnovel(url)
            if meta: worker_freewebnovel_list(url, admin_email, meta)
    except Exception as e:
        print(f"⚠️ Scheduler Error for {url}: {e}")

def scheduler_loop():
    """Background thread that runs forever"""
    while True:
        try:
            now = time.time()
            if SCHEDULER_CONFIG['active'] and now >= SCHEDULER_CONFIG['next_run']:
                SCHEDULER_CONFIG['status'] = 'running'
                print("🚀 [Scheduler] Starting Auto Update Job...")
                
                # 1. Fetch Watchlist from Node.js using API Key
                try:
                    headers = {'x-api-secret': API_SECRET}
                    res = requests.get(f"{NODE_BACKEND_URL}/api/admin/watchlist", headers=headers, timeout=30)
                    if res.status_code == 200:
                        watchlist = res.json()
                        print(f"📋 [Scheduler] Found {len(watchlist)} novels.")
                        
                        for item in watchlist:
                            if item.get('sourceUrl') and item.get('status') == 'ongoing':
                                perform_single_scrape(item['sourceUrl'], SCHEDULER_CONFIG['admin_email'])
                                time.sleep(2) # Politeness delay
                        
                        print("✅ [Scheduler] Job Completed.")
                    else:
                        print(f"❌ [Scheduler] Failed to fetch watchlist: HTTP {res.status_code}")
                except Exception as req_err:
                    print(f"❌ [Scheduler] Connection Error: {req_err}")

                # Update next run time
                SCHEDULER_CONFIG['last_run'] = now
                SCHEDULER_CONFIG['next_run'] = now + SCHEDULER_CONFIG['interval_seconds']
                SCHEDULER_CONFIG['status'] = 'idle'
            
            time.sleep(5) # Check every 5 seconds
        except Exception as e:
            print(f"🔥 [Scheduler] Critical Loop Error: {e}")
            time.sleep(60)

# Start Scheduler Thread immediately
scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
scheduler_thread.start()

# ==========================================
# Main Routes
# ==========================================

@app.route('/', methods=['GET'])
def health_check():
    return "ZEUS Scraper Service is Running (Scheduler Active)", 200

@app.route('/scheduler/config', methods=['POST'])
def configure_scheduler():
    auth_header = request.headers.get('Authorization')
    if auth_header != API_SECRET: return jsonify({'message': 'Unauthorized'}), 401
    
    data = request.json
    SCHEDULER_CONFIG['active'] = data.get('active', False)
    SCHEDULER_CONFIG['interval_seconds'] = int(data.get('interval', 86400))
    SCHEDULER_CONFIG['admin_email'] = data.get('adminEmail', 'system@auto')
    
    # If activating, set next run immediately if not set
    if SCHEDULER_CONFIG['active'] and SCHEDULER_CONFIG['next_run'] < time.time():
        SCHEDULER_CONFIG['next_run'] = time.time() + 5 # Run in 5 seconds
        
    return jsonify({
        'message': 'Scheduler Updated',
        'config': SCHEDULER_CONFIG
    })

@app.route('/scheduler/status', methods=['GET'])
def get_scheduler_status():
    return jsonify(SCHEDULER_CONFIG)

@app.route('/scrape', methods=['POST'])
def trigger_scrape():
    auth_header = request.headers.get('Authorization')
    if auth_header != API_SECRET: return jsonify({'message': 'Unauthorized'}), 401

    try:
        data = request.json
        url = data.get('url', '').strip()
        admin_email = data.get('adminEmail')
        
        if not url: return jsonify({'message': 'No URL provided'}), 400

        # Run logic in thread
        if 'rewayat.club' in url:
            meta = fetch_metadata_rewayat(url)
            if meta: 
                threading.Thread(target=worker_rewayat_probe, args=(url, admin_email, meta)).start()
                return jsonify({'message': 'Started Rewayat Club'}), 200
        elif 'ar-no.com' in url:
            meta = fetch_metadata_madara(url)
            if meta:
                threading.Thread(target=worker_madara_list, args=(url, admin_email, meta)).start()
                return jsonify({'message': 'Started Ar-Novel'}), 200
        elif 'markazriwayat.com' in url:
            meta = fetch_metadata_markaz(url)
            if meta:
                threading.Thread(target=worker_madara_list, args=(url, admin_email, meta)).start()
                return jsonify({'message': 'Started Markaz'}), 200
        elif 'novelfire.net' in url:
            meta = fetch_metadata_novelfire(url)
            if meta:
                threading.Thread(target=worker_novelfire_list, args=(url, admin_email, meta)).start()
                return jsonify({'message': 'Started Novel Fire'}), 200
        elif 'wuxiabox.com' in url or 'wuxiaspot.com' in url:
            meta = fetch_metadata_wuxiabox(url)
            if meta:
                threading.Thread(target=worker_wuxiabox_list, args=(url, admin_email, meta)).start()
                return jsonify({'message': 'Started WuxiaBox'}), 200
        elif 'freewebnovel.com' in url:
            meta = fetch_metadata_freewebnovel(url)
            if meta:
                threading.Thread(target=worker_freewebnovel_list, args=(url, admin_email, meta)).start()
                return jsonify({'message': 'Started FreeWebNovel'}), 200
        
        return jsonify({'message': 'Unsupported or Failed'}), 400
            
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Server Error: {error_trace}")
        return jsonify({'message': 'Internal Server Error', 'details': str(e), 'trace': error_trace}), 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, threaded=True)
