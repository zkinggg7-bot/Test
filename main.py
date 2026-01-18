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
# أدوات السحب (Scraper Tools)
# ==========================================

def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ar,en-US;q=0.7,en;q=0.3'
    }

def extract_from_nuxt(soup):
    """استخراج رابط الصورة من بيانات Nuxt الخام"""
    try:
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and 'window.__NUXT__' in script.string:
                content = script.string
                match = re.search(r'poster_url:"(.*?)"', content)
                if not match:
                    match = re.search(r'poster:"(.*?)"', content)
                
                if match:
                    raw_url = match.group(1)
                    clean_url = raw_url.encode('utf-8').decode('unicode_escape')
                    return clean_url
    except Exception as e:
        print(f"Error extracting from Nuxt: {e}")
    return None

def extract_background_image(style_str):
    if not style_str: return ''
    clean_style = style_str.replace('&quot;', '"').replace("&#39;", "'")
    match = re.search(r'url\s*\((.*?)\)', clean_style, re.IGNORECASE)
    if match:
        url = match.group(1).strip()
        url = url.strip('"\'')
        return url
    return ''

def is_valid_tag(text):
    text = text.strip()
    if not text: return False
    if text in ['مكتملة', 'متوقفة', 'مستمرة', 'مترجمة', 'رواية', 'عمل']: return False
    clean_text = text.replace(',', '').replace('.', '').replace('x', '').strip()
    if clean_text.isdigit(): return False
    if re.search(r'^\d+\s*x$', text, re.IGNORECASE): return False 
    if not re.search(r'[\u0600-\u06FF]', text): return False
    return True

def fix_image_url(url):
    if not url: return ""
    base_api_url = 'https://api.rewayat.club'
    if url.startswith('//'):
        return 'https:' + url
    elif url.startswith('/'):
        return base_api_url + url
    elif not url.startswith('http'):
        return base_api_url + '/' + url
    return url

def fetch_novel_metadata_html(url):
    """جلب معلومات الرواية"""
    try:
        print(f"📡 Fetching metadata from HTML: {url}")
        response = requests.get(url, headers=get_headers(), timeout=15)
        if response.status_code != 200:
            print(f"❌ HTTP Error: {response.status_code}")
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Title
        title_tag = soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"
        
        # Cover
        cover_url = ""
        nuxt_image = extract_from_nuxt(soup)
        if nuxt_image: cover_url = nuxt_image
        
        if not cover_url:
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"): cover_url = og_image["content"]
        
        if not cover_url:
            img_div = soup.find('div', class_='v-image__image--cover')
            if img_div and img_div.has_attr('style'): cover_url = extract_background_image(img_div['style'])
        
        cover_url = fix_image_url(cover_url)

        # Description
        desc_div = soup.find(class_='text-pre-line') or soup.find('div', class_='v-card__text')
        description = desc_div.get_text(strip=True) if desc_div else ""
        
        # Status & Category
        status = "مستمرة"
        tags = []
        category = "عام"
        
        chip_groups = soup.find_all(class_='v-chip-group')
        target_chips = []
        if chip_groups:
            for group in chip_groups[:2]: 
                target_chips.extend(group.find_all(class_='v-chip__content'))
        else:
            target_chips = soup.find_all(class_='v-chip__content')

        for chip in target_chips:
            text = chip.get_text(strip=True)
            if text in ['مكتملة', 'متوقفة', 'مستمرة']:
                status = text
            elif is_valid_tag(text):
                tags.append(text)
        
        tags = list(set(tags))
        if tags: category = tags[0]

        # Total Chapters (تقريبي)
        total_chapters = 0
        all_text = soup.get_text()
        chapter_match = re.search(r'الفصول\s*\((\d+)\)', all_text)
        if chapter_match:
            total_chapters = int(chapter_match.group(1))
        
        if total_chapters == 0:
            tabs = soup.find_all(class_='v-tab')
            for tab in tabs:
                if "الفصول" in tab.get_text():
                    match = re.search(r'(\d+)', tab.get_text())
                    if match: total_chapters = int(match.group(1))

        return {
            'title': title,
            'description': description,
            'cover': cover_url,
            'status': status,
            'tags': tags,
            'category': category,
            'total_chapters': total_chapters
        }

    except Exception as e:
        print(f"❌ Error scraping metadata: {e}")
        return None

def scrape_chapter_content_html(novel_url, chapter_num):
    """سحب نص الفصل"""
    url = f"{novel_url.rstrip('/')}/{chapter_num}"
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        if response.status_code != 200:
            return None, None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        
        paragraphs = soup.find_all('p')
        
        # === تم التعديل هنا: إزالة شرط الطول (> 20) لسحب كل شيء ===
        # الآن نتحقق فقط من أن الفقرة ليست فارغة تماماً
        clean_paragraphs = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
        
        if clean_paragraphs:
            text_content = "\n\n".join(clean_paragraphs)
        else:
            # محاولة بديلة إذا لم تكن هناك وسوم <p>
            content_div = soup.find('div', class_='pre-formatted') or soup.find('div', class_='v-card__text')
            if content_div:
                text_content = content_div.get_text(separator="\n\n", strip=True)
            else:
                return None, None
            
        # === تم التعديل هنا: تخفيف شرط الحد الأدنى لطول الفصل ===
        # كان < 50 سابقاً، جعلناه < 2 ليسمح بالفصول القصيرة جداً أو الملاحظات
        if len(text_content.strip()) < 2:
            return None, None

        title_tag = soup.find(class_='v-card__subtitle') or soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else f"الفصل {chapter_num}"
        title = re.sub(r'^\d+\s*-\s*', '', title)

        return title, text_content
            
    except Exception as e:
        print(f"Error scraping chapter {chapter_num}: {e}")
        return None, None

def check_existing_chapters(title):
    """التحقق من الفصول الموجودة في الباك إند"""
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

# ==========================================
# دالة الخلفية (تم تعديلها لتعمل بوضع Probe Mode)
# ==========================================
def background_worker(url, admin_email, author_name, start_from=1, update_info=True):
    print(f"🚀 Starting Scraper for: {url}")
    
    # 1. الميتاداتا
    metadata = fetch_novel_metadata_html(url)
    if not metadata:
        send_data_to_backend({'adminEmail': admin_email, 'error': 'فشل في جلب بيانات الرواية'})
        return

    print(f"📖 Found Novel: {metadata['title']} (Site says approx: {metadata['total_chapters']} Chaps)")

    # 2. المصافحة الذكية
    existing_chapters = check_existing_chapters(metadata['title'])
    skip_metadata_update = False
    
    max_existing = 0
    if len(existing_chapters) > 0:
        max_existing = max(existing_chapters)
        print(f"ℹ️ Novel exists locally with {len(existing_chapters)} chapters. Max ID: {max_existing}")
        skip_metadata_update = True
    else:
        # إرسال البيانات الأولية إذا كانت جديدة كلياً
        if not send_data_to_backend({
            'adminEmail': admin_email, 'novelData': metadata, 'chapters': [], 'skipMetadataUpdate': False
        }): return

    # 3. حلقة السحب الذكية (While Loop for Probing)
    # لا نعتمد على range ثابت، بل نستمر حتى نصل لحد الأخطاء المتتالية
    
    current_chapter = start_from
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 15 # سيتوقف بعد 15 محاولة فاشلة متتالية (للتأكد من عدم وجود فصول جديدة)
    
    # حد أقصى للأمان لمنع الحلقات اللانهائية في حال تعطل الموقع
    SAFETY_LIMIT = 5000 
    
    batch_size = 5 
    current_batch = []
    
    print(f"🕵️‍♂️ Starting PROBE MODE from chapter {current_chapter}...")

    while current_chapter < SAFETY_LIMIT:
        
        # أ) إذا كان الفصل موجوداً مسبقاً
        if current_chapter in existing_chapters:
            # نتخطى الفصل، لكن نصفر عداد الأخطاء لأن التسلسل صحيح وموجود
            consecutive_errors = 0
            if current_chapter % 50 == 0:
                print(f"⏩ Skipped existing chapter {current_chapter}...")
            current_chapter += 1
            continue
        
        # ب) الفصل غير موجود، نحاول سحبه
        chap_title, content = scrape_chapter_content_html(url, current_chapter)
        
        if content:
            # نجاح!
            consecutive_errors = 0 # تصفير العداد
            
            chapter_data = {'number': current_chapter, 'title': chap_title, 'content': content}
            current_batch.append(chapter_data)
            print(f"📄 Scraped NEW Chapter {current_chapter}")
            
            # إرسال الدفعة
            if len(current_batch) >= batch_size:
                print(f"📤 Sending batch of {len(current_batch)}...")
                send_data_to_backend({
                    'adminEmail': admin_email, 'novelData': metadata, 'chapters': current_batch, 'skipMetadataUpdate': skip_metadata_update
                })
                current_batch = [] 
                time.sleep(1) 
        else:
            # فشل (404 أو محتوى فارغ)
            consecutive_errors += 1
            print(f"⚠️ Failed/Empty Ch {current_chapter} (Error {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS})")
            
            # شرط التوقف الحاسم
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f"🛑 Reached {MAX_CONSECUTIVE_ERRORS} consecutive errors at chapter {current_chapter}. Stopping probe.")
                break
        
        current_chapter += 1

    # إرسال ما تبقى في الدفعة الأخيرة
    if len(current_batch) > 0:
        send_data_to_backend({
            'adminEmail': admin_email, 'novelData': metadata, 'chapters': current_batch, 'skipMetadataUpdate': skip_metadata_update
        })

    print(f"✨ Scraping Task Completed! Scanned up to {current_chapter}")

# ==========================================
# نقاط النهاية (Endpoints)
# ==========================================

@app.route('/', methods=['GET'])
def health_check():
    return "ZEUS Scraper Service (Probe Mode Active 🕵️‍♂️) is Running ⚡", 200

@app.route('/scrape', methods=['POST'])
def trigger_scrape():
    auth_header = request.headers.get('Authorization')
    if auth_header != API_SECRET:
        return jsonify({'message': 'Unauthorized'}), 401

    data = request.json
    if not data:
        return jsonify({'message': 'No data provided'}), 400
        
    url = data.get('url')
    admin_email = data.get('adminEmail')
    author_name = data.get('authorName', 'ZEUS Bot')
    start_from = int(data.get('startFrom', 1))

    if not url or 'rewayat.club' not in url:
        return jsonify({'message': 'Invalid URL'}), 400

    thread = threading.Thread(target=background_worker, args=(url, admin_email, author_name, start_from))
    thread.daemon = True 
    thread.start()

    return jsonify({'message': 'Started', 'status': 'started'}), 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
