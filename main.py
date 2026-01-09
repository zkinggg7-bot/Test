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
# يتم جلبه من متغيرات البيئة أو استخدام الرابط الافتراضي
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

def extract_background_image(style_str):
    """استخراج الرابط من ستايل background-image"""
    if not style_str: return ''
    match = re.search(r'url\(&quot;(.*?)&quot;\)', style_str)
    if not match:
        match = re.search(r'url\("(.*?)"\)', style_str)
    if not match:
        match = re.search(r'url\((.*?)\)', style_str)
    return match.group(1) if match else ''

def fetch_novel_metadata_html(url):
    """جلب معلومات الرواية من HTML الصفحة مباشرة"""
    try:
        print(f"📡 Fetching metadata from HTML: {url}")
        response = requests.get(url, headers=get_headers(), timeout=15)
        if response.status_code != 200:
            print(f"❌ HTTP Error: {response.status_code}")
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 1. Title
        title_tag = soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"
        
        # 2. Cover
        cover_url = ""
        og_image = soup.find("meta", property="og:image")
        if og_image:
            cover_url = og_image["content"]
        else:
            img_div = soup.find('div', class_='v-image__image--cover')
            if img_div and img_div.has_attr('style'):
                cover_url = extract_background_image(img_div['style'])
            
        # 3. Description
        desc_div = soup.find(class_='text-pre-line') or soup.find('div', class_='v-card__text')
        description = desc_div.get_text(strip=True) if desc_div else ""
        
        # 4. Status & Category
        status = "مستمرة"
        tags = []
        category = "عام"
        
        chips = soup.find_all(class_='v-chip__content')
        for chip in chips:
            text = chip.get_text(strip=True)
            if text in ['مكتملة', 'متوقفة', 'مستمرة']:
                status = text
            elif text not in ['مترجمة', 'رواية']: 
                tags.append(text)
        
        if tags:
            category = tags[0]

        # 5. Total Chapters
        total_chapters = 0
        all_text = soup.get_text()
        chapter_match = re.search(r'الفصول\s*\((\d+)\)', all_text)
        if chapter_match:
            total_chapters = int(chapter_match.group(1))
        else:
            tabs = soup.find_all(class_='v-tab')
            for tab in tabs:
                tab_text = tab.get_text(strip=True)
                if "الفصول" in tab_text:
                    match = re.search(r'\((\d+)\)', tab_text)
                    if match:
                        total_chapters = int(match.group(1))
                        break
        
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
        clean_paragraphs = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20]
        
        if clean_paragraphs:
            text_content = "\n\n".join(clean_paragraphs)
        else:
            content_div = soup.find('div', class_='pre-formatted') or soup.find('div', class_='v-card__text')
            if content_div:
                text_content = content_div.get_text(separator="\n\n", strip=True)
            else:
                return None, None
            
        if len(text_content.strip()) < 50:
            return None, None

        title_tag = soup.find(class_='v-card__subtitle') or soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else f"الفصل {chapter_num}"
        title = re.sub(r'^\d+\s*-\s*', '', title)

        return title, text_content
            
    except Exception as e:
        print(f"Error scraping chapter {chapter_num}: {e}")
        return None, None

def send_data_to_backend(payload):
    """إرسال البيانات إلى الخادم الرئيسي Node.js"""
    try:
        endpoint = f"{NODE_BACKEND_URL}/api/scraper/receive"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': API_SECRET,
            'x-api-secret': API_SECRET
        }
        response = requests.post(endpoint, json=payload, headers=headers, timeout=60)
        
        if response.status_code == 200:
            print("✅ Data sent to backend successfully.")
            return True
        else:
            print(f"❌ Backend Error ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"❌ Failed to send data to backend: {e}")
        return False

def background_worker(url, admin_email, author_name):
    """الوظيفة التي تعمل في الخلفية"""
    print(f"🚀 Starting Scraper for: {url}")
    
    # 1. جلب البيانات الوصفية للرواية
    metadata = fetch_novel_metadata_html(url)
    if not metadata:
        print("❌ Failed to fetch metadata")
        # Send error log to backend
        send_data_to_backend({'adminEmail': admin_email, 'error': 'فشل في جلب بيانات الرواية من المصدر'})
        return

    print(f"📖 Found Novel: {metadata['title']} ({metadata['total_chapters']} Chapters)")

    # 2. إرسال البيانات الوصفية أولاً لإنشاء الرواية ورفع الصورة في الخادم
    # نرسل chapters فارغة لإنشاء الرواية فقط
    init_payload = {
        'adminEmail': admin_email,
        'novelData': metadata,
        'chapters': [] 
    }
    
    if not send_data_to_backend(init_payload):
        print("❌ Stopping execution because initial handshake failed.")
        return

    # 3. حلقة سحب الفصول وإرسالها على دفعات (Batches)
    total = metadata['total_chapters']
    if total == 0:
        total = 50 # Fallback default
        
    batch_size = 5 # إرسال كل 5 فصول دفعة واحدة لتخفيف الحمل وتسريع الاستجابة
    current_batch = []

    for num in range(1, total + 1):
        chap_title, content = scrape_chapter_content_html(url, num)
        
        if content:
            chapter_data = {
                'number': num,
                'title': chap_title,
                'content': content
            }
            current_batch.append(chapter_data)
            print(f"📄 Scraped Chapter {num}")
        else:
            print(f"⚠️ Failed to scrape content for Ch {num}")

        # إذا اكتملت الدفعة أو وصلنا للنهاية
        if len(current_batch) >= batch_size or num == total:
            if current_batch:
                print(f"📤 Sending batch of {len(current_batch)} chapters...")
                payload = {
                    'adminEmail': admin_email,
                    'novelData': metadata, # نرسل الميتاداتا دائماً للتأكيد
                    'chapters': current_batch
                }
                send_data_to_backend(payload)
                current_batch = [] # تصفير الدفعة
                time.sleep(1) # استراحة بسيطة

    print("✨ Scraping Task Completed Successfully!")
    # إرسال إشعار اكتمال (اختياري، الخادم سيعرف من التحديثات)

# ==========================================
# نقاط النهاية (Endpoints)
# ==========================================

@app.route('/', methods=['GET'])
def health_check():
    return "ZEUS Scraper Service (Relay Mode) is Running ⚡", 200

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

    if not url or 'rewayat.club' not in url:
        return jsonify({'message': 'Invalid URL. Must be from rewayat.club'}), 400

    # بدء العمل في الخلفية
    thread = threading.Thread(target=background_worker, args=(url, admin_email, author_name))
    thread.daemon = True 
    thread.start()

    return jsonify({
        'message': 'تم بدء العملية. سيتم إرسال البيانات للخادم الرئيسي تدريجياً.',
        'status': 'started'
    }), 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
