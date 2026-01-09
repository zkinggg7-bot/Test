import os
import json
import time
import threading
import requests
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore
from pymongo import MongoClient
import certifi
from datetime import datetime

# ==========================================
# إعدادات التطبيق
# ==========================================
app = Flask(__name__)
CORS(app)

# مفتاح سري لحماية الرابط
API_SECRET = os.environ.get('API_SECRET', 'Zeusndndjddnejdjdjdejekk29393838msmskxcm9239484jdndjdnddjj99292938338zeuslojdnejxxmejj82283849')

# ==========================================
# إعداد قواعد البيانات
# ==========================================

# 1. MongoDB Setup
MONGO_URI = os.environ.get('MONGODB_URI')
novels_collection = None
if MONGO_URI:
    try:
        mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
        mongo_db = mongo_client['zeus'] 
        novels_collection = mongo_db['novels']
        print("✅ Connected to MongoDB")
    except Exception as e:
        print(f"❌ MongoDB Connection Error: {e}")
else:
    print("⚠️ MONGODB_URI not found in env vars")

# 2. Firebase Setup
FIREBASE_KEY = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
firestore_db = None
if FIREBASE_KEY:
    try:
        # تنظيف النص بشكل شامل
        firebase_key_cleaned = FIREBASE_KEY.strip()
        # إزالة أي BOM أو أحرف خفية
        firebase_key_cleaned = firebase_key_cleaned.encode('utf-8').decode('utf-8-sig')
        # تحويل إلى JSON
        cred_dict = json.loads(firebase_key_cleaned)
        
        # إصلاح المفتاح الخاص بشكل دقيق
        if 'private_key' in cred_dict:
            private_key = cred_dict['private_key']
            private_key = private_key.replace('\\n', '\n')
            lines = private_key.split('\n')
            cleaned_lines = []
            for line in lines:
                if '-----BEGIN' in line or '-----END' in line:
                    cleaned_lines.append(line.strip())
                else:
                    cleaned_line = line.strip().replace(' ', '').replace('\t', '')
                    if cleaned_line:
                        cleaned_lines.append(cleaned_line)
            cred_dict['private_key'] = '\n'.join(cleaned_lines)
        
        # تهيئة Firebase
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        firestore_db = firestore.client()
        print("✅ Connected to Firebase Firestore")
        
    except Exception as e:
        print(f"❌ Firebase Connection Error: {e}")
else:
    print("⚠️ FIREBASE_SERVICE_ACCOUNT not found in env vars")

# ==========================================
# أدوات السحب (Scraper Tools) - تم التعديل هنا لضمان السحب
# ==========================================

def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ar,en-US;q=0.7,en;q=0.3'
    }

def get_slug_from_url(url):
    """استخراج المعرف الفريد للرواية من الرابط"""
    try:
        parts = url.rstrip('/').split('/novel/')
        if len(parts) > 1:
            return parts[1].split('/')[0]
    except:
        pass
    return None

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
        
        # 1. Title - البحث في h1 مباشرة كما في الكود الناجح
        title_tag = soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"
        
        # 2. Cover - محاولة جلب الغلاف من تاق og:image لضمان النجاح
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
        
        # البحث عن الكلمات المفتاحية في الصفحة للحالة والتصنيف
        chips = soup.find_all(class_='v-chip__content')
        for chip in chips:
            text = chip.get_text(strip=True)
            if text in ['مكتملة', 'متوقفة', 'مستمرة']:
                status = text
            elif text not in ['مترجمة', 'رواية']: 
                tags.append(text)
        
        if tags:
            category = tags[0]

        # 5. Total Chapters - محاولة جلب الرقم من النص العام إذا فشلت التابات
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
    """سحب نص الفصل باستخدام استهداف الوسوم المباشرة (المنطق الناجح)"""
    url = f"{novel_url.rstrip('/')}/{chapter_num}"
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        if response.status_code != 200:
            return None, None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # الطريقة الناجحة: البحث عن جميع وسوم p التي تحتوي على نص حقيقي
        paragraphs = soup.find_all('p')
        # تنظيف وفلترة النصوص (استبعاد الإعلانات والجمل القصيرة جداً)
        clean_paragraphs = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20]
        
        if clean_paragraphs:
            text_content = "\n\n".join(clean_paragraphs)
        else:
            # محاولة احتياطية: إذا لم يجد p، يبحث في الـ div الرئيسي للمحتوى
            content_div = soup.find('div', class_='pre-formatted') or soup.find('div', class_='v-card__text')
            if content_div:
                text_content = content_div.get_text(separator="\n\n", strip=True)
            else:
                return None, None
            
        # التأكد من وجود نص حقيقي
        if len(text_content.strip()) < 50:
            return None, None

        # استخراج العنوان من v-card__subtitle أو h1
        title_tag = soup.find(class_='v-card__subtitle') or soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else f"الفصل {chapter_num}"
        # إزالة أي أرقام زائدة من بداية العنوان
        title = re.sub(r'^\d+\s*-\s*', '', title)

        return title, text_content
            
    except Exception as e:
        print(f"Error scraping chapter {chapter_num}: {e}")
        return None, None

def background_worker(url, admin_email, author_name):
    """الوظيفة التي تعمل في الخلفية"""
    print(f"🚀 Starting HTML scraper for: {url}")
    
    # 1. جلب البيانات الوصفية
    metadata = fetch_novel_metadata_html(url)
    if not metadata:
        print("❌ Failed to fetch metadata from HTML")
        return

    print(f"📖 Found Novel: {metadata['title']} ({metadata['total_chapters']} Chapters)")

    # 2. إنشاء أو تحديث الرواية في MongoDB
    novel_id = None
    if novels_collection is not None:
        try:
            existing_novel = novels_collection.find_one({'title': metadata['title'], 'authorEmail': admin_email})
            
            novel_doc = {
                'title': metadata['title'],
                'description': metadata['description'],
                'cover': metadata['cover'],
                'author': author_name,
                'authorEmail': admin_email,
                'category': metadata['category'],
                'tags': metadata['tags'],
                'status': metadata['status'],
                'sourceUrl': url,
                'lastChapterUpdate': datetime.now()
            }

            if existing_novel:
                novel_id = existing_novel['_id']
                novels_collection.update_one({'_id': novel_id}, {'$set': novel_doc})
                print(f"🔄 Novel updated in MongoDB: {novel_id}")
            else:
                novel_doc['createdAt'] = datetime.now()
                novel_doc['chapters'] = []
                novel_doc['views'] = 0
                result = novels_collection.insert_one(novel_doc)
                novel_id = result.inserted_id
                print(f"🆕 New novel created in MongoDB: {novel_id}")
        except Exception as e:
            print(f"❌ MongoDB operation error: {e}")
            return
    else:
        print("❌ MongoDB not connected, cannot proceed.")
        return

    # 3. حلقة سحب الفصول
    total = metadata['total_chapters']
    if total == 0:
        print("⚠️ No chapters count found, trying first 100 blind...")
        total = 100

    # جلب قائمة الفصول الموجودة حالياً لتجنب التكرار
    current_novel = novels_collection.find_one({'_id': novel_id})
    existing_numbers = [c['number'] for c in current_novel.get('chapters', [])] if current_novel else []

    for num in range(1, total + 1):
        if num in existing_numbers:
            print(f"⏩ Skipping Ch {num} (Exists)")
            continue

        chap_title, content = scrape_chapter_content_html(url, num)
        
        if content:
            try:
                # أ) الحفظ في Firebase (المحتوى النصي)
                if firestore_db is not None:
                    doc_ref = firestore_db.collection('novels').document(str(novel_id)).collection('chapters').document(str(num))
                    doc_ref.set({
                        'title': chap_title,
                        'content': content,
                        'lastUpdated': firestore.SERVER_TIMESTAMP
                    })

                # ب) التحديث في MongoDB (قائمة الفصول)
                if novels_collection is not None:
                    chapter_meta = {
                        'number': num,
                        'title': chap_title,
                        'createdAt': datetime.now(),
                        'views': 0
                    }
                    novels_collection.update_one(
                        {'_id': novel_id},
                        {'$push': {'chapters': chapter_meta}}
                    )
                
                print(f"✅ Chapter {num} uploaded successfully.")
                time.sleep(1.2) # تأخير بسيط لتجنب الحظر على Railway
                
            except Exception as e:
                print(f"❌ DB Save Error Ch {num}: {e}")
        else:
            print(f"⚠️ Failed to scrape content for Ch {num}")

    print("✨ Scraping Task Completed Successfully!")

# ==========================================
# نقاط النهاية (Endpoints)
# ==========================================

@app.route('/', methods=['GET'])
def health_check():
    return "ZEUS HTML Scraper Service is Running ⚡ v2.2 (Enhanced Logic)", 200

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
        'message': 'تم بدء العملية بنجاح. المحرك يعمل الآن على سحب البيانات وحفظها في قواعد بياناتك.',
        'status': 'started'
    }), 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
