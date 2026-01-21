import os
import json
import time
import threading
import requests
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
from datetime import datetime

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
# أدوات السحب المشتركة (Shared Scraper Tools)
# ==========================================

def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ar,en-US;q=0.7,en;q=0.3',
        'Referer': 'https://ar-no.com/'
    }

def fix_image_url(url, base_url='https://api.rewayat.club'):
    if not url: return ""
    if url.startswith('//'):
        return 'https:' + url
    elif url.startswith('/'):
        return base_url + url
    elif not url.startswith('http'):
        return base_url + '/' + url
    return url

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
                return data['chapters'] # يعيد مصفوفة بالأرقام
            else:
                return []
        return []
    except Exception as e:
        print(f"❌ Error checking existence: {e}")
        return []

# ==========================================
# 🟣 1. Rewayat Club (Nuxt) Logic - Probe Mode
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
        description = desc_div.get_text(strip=True) if desc_div else ""
        
        return {
            'title': title, 'description': description, 'cover': cover_url,
            'status': "مستمرة", 'category': "عام", 'tags': []
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
    skip_meta = len(existing_chapters) > 0
    
    if not skip_meta:
        send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': [], 'skipMetadataUpdate': False})

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
                send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': skip_meta})
                batch = []
                time.sleep(1)
        else:
            errors += 1
            print(f"Failed Ch {current_chapter} ({errors}/15)")
        current_chapter += 1
        
    if batch:
        send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': skip_meta})

# ==========================================
# 🟢 2. Ar Novel (Madara) Logic - List Mode
# ==========================================

def fetch_metadata_madara(url):
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # استخراج العنوان
        title_tag = soup.find(class_='post-title')
        title = title_tag.find('h1').get_text(strip=True) if title_tag else "Unknown"
        title = re.sub(r'\s*~.*$', '', title) 

        # استخراج الغلاف
        cover = ""
        img_container = soup.find(class_='summary_image')
        if img_container:
            img_tag = img_container.find('img')
            if img_tag:
                cover = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('srcset', '').split(' ')[0]
        
        if not cover:
            og_img = soup.find("meta", property="og:image")
            if og_img: cover = og_img["content"]

        # استخراج ID الرواية (هام لطلب AJAX)
        novel_id = None
        shortlink = soup.find("link", rel="shortlink")
        if shortlink:
            match = re.search(r'p=(\d+)', shortlink.get('href', ''))
            if match: novel_id = match.group(1)
            
        if not novel_id:
            id_input = soup.find('input', class_='rating-post-id')
            if id_input: novel_id = id_input.get('value')
            
        if not novel_id:
            body_class = soup.find('body').get('class', [])
            for c in body_class:
                if c.startswith('manga-id-'):
                    novel_id = c.replace('manga-id-', '')

        print(f"Found Novel ID: {novel_id}")

        # الوصف
        desc_div = soup.find(class_='summary__content') or soup.find(class_='description-summary')
        description = desc_div.get_text(separator="\n", strip=True) if desc_div else ""

        # التصنيفات
        genres_content = soup.find(class_='genres-content')
        category = "عام"
        tags = []
        if genres_content:
            links = genres_content.find_all('a')
            tags = [a.get_text(strip=True) for a in links]
            if tags: category = tags[0]

        return {
            'title': title, 'description': description, 'cover': cover,
            'status': 'مستمرة', 'category': category, 'tags': tags,
            'novel_id': novel_id
        }
    except Exception as e:
        print(f"Error Madara Meta: {e}")
        return None

def parse_madara_chapters_from_html(soup):
    """تحليل الفصول من كود HTML"""
    chapters = []
    items = soup.find_all('li', class_='wp-manga-chapter')
    
    for item in items:
        a = item.find('a')
        if a:
            link = a.get('href')
            raw_title = a.get_text(strip=True)
            
            # استخراج الرقم
            num_match = re.search(r'(\d+)', raw_title)
            number = int(num_match.group(1)) if num_match else 0
            
            # تنظيف العنوان
            clean_title = re.sub(r'^\d+\s*[-–]\s*', '', raw_title).strip()
            
            if number > 0:
                chapters.append({'number': number, 'url': link, 'title': clean_title})
    
    return chapters

def fetch_chapter_list_madara(novel_id, novel_url=None):
    """جلب قائمة الفصول بالكامل مع الترتيب التصاعدي"""
    chapters = []
    
    # محاولة 1: AJAX
    if novel_url:
        ajax_endpoint = f"{novel_url.rstrip('/')}/ajax/chapters/"
        try:
            headers = get_headers()
            headers['X-Requested-With'] = 'XMLHttpRequest'
            res = requests.post(ajax_endpoint, headers=headers, timeout=20)
            if res.status_code == 200:
                soup = BeautifulSoup(res.content, 'html.parser')
                chapters = parse_madara_chapters_from_html(soup)
        except Exception as e:
            print(f"AJAX endpoint failed: {e}")

    # محاولة 2: admin-ajax
    if not chapters and novel_id:
        try:
            ajax_url = "https://ar-no.com/wp-admin/admin-ajax.php"
            data = {'action': 'manga_get_chapters', 'manga': novel_id}
            res = requests.post(ajax_url, data=data, headers=get_headers(), timeout=20)
            if res.status_code == 200:
                soup = BeautifulSoup(res.content, 'html.parser')
                chapters = parse_madara_chapters_from_html(soup)
        except: pass
            
    # التعديل الجوهري: ترتيب الفصول من 1 فما فوق لضمان البدء من البداية
    if chapters:
        chapters.sort(key=lambda x: x['number'])
    
    return chapters

def scrape_chapter_madara(url):
    try:
        res = requests.get(url, headers=get_headers(), timeout=15)
        if res.status_code != 200: return None
        soup = BeautifulSoup(res.content, 'html.parser')
        
        container = soup.find(class_='text-left') or soup.find(class_='reading-content') or soup.find(class_='entry-content')
            
        if container:
            for bad in container.find_all(['div', 'script', 'style', 'input', 'ins', 'iframe']):
                if bad.get('class') and any(c in ['code-block', 'adsbygoogle', 'pf-ad'] for c in bad.get('class')):
                    bad.decompose()
            
            for nav in container.find_all('div', class_='nav-links'):
                nav.decompose()

            text = container.get_text(separator="\n\n", strip=True)
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = text.replace('اكمال القراءة', '')
            return text
        return None
    except: return None

def worker_madara_list(url, admin_email, metadata):
    existing_chapters = check_existing_chapters(metadata['title'])
    skip_meta = len(existing_chapters) > 0
    
    if not skip_meta:
        send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': [], 'skipMetadataUpdate': False})

    all_chapters = fetch_chapter_list_madara(metadata.get('novel_id'), url)
    
    if not all_chapters:
        print(f"No chapters found for {metadata['title']}")
        return

    # الترتيب تم بالفعل في الدالة السابقة
    print(f"Processing {len(all_chapters)} chapters (Sorted Ascending).")
    
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
                send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': skip_meta})
                batch = []
                time.sleep(1.2)
        
    if batch:
        send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': skip_meta})

# ==========================================
# Main Orchestrator
# ==========================================

@app.route('/', methods=['GET'])
def health_check():
    return "ZEUS Scraper Service is Running", 200

@app.route('/scrape', methods=['POST'])
def trigger_scrape():
    auth_header = request.headers.get('Authorization')
    if auth_header != API_SECRET: return jsonify({'message': 'Unauthorized'}), 401

    data = request.json
    url = data.get('url', '')
    admin_email = data.get('adminEmail')
    
    if not url: return jsonify({'message': 'No URL'}), 400

    # تم استخدام daemon=False لضمان عدم قتل الخيط فور انتهاء الطلب الرئيسي
    # ملاحظة: في بيئات الاستضافة السحابية، يفضل استخدام Celery أو Redis للمهام الطويلة
    if 'rewayat.club' in url:
        meta = fetch_metadata_rewayat(url)
        if not meta: return jsonify({'message': 'Failed metadata'}), 400
        thread = threading.Thread(target=worker_rewayat_probe, args=(url, admin_email, meta))
        thread.daemon = False 
        thread.start()
        return jsonify({'message': 'Scraping started in background. You can close the app.'}), 200
        
    elif 'ar-no.com' in url:
        meta = fetch_metadata_madara(url)
        if not meta: return jsonify({'message': 'Failed metadata'}), 400
        thread = threading.Thread(target=worker_madara_list, args=(url, admin_email, meta))
        thread.daemon = False
        thread.start()
        return jsonify({'message': 'Scraping started in background. You can close the app.'}), 200

    else:
        return jsonify({'message': 'Unsupported Domain'}), 400

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    # استخدام threaded=True لضمان التعامل مع عدة طلبات في نفس الوقت
    app.run(host='0.0.0.0', port=port, threaded=True)