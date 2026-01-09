import os
import json
import time
import threading
import requests
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

# مفتاح سري لحماية الرابط (يجب أن يطابق الموجود في تطبيق React Native)
API_SECRET = os.environ.get('API_SECRET', 'Zeusndndjddnejdjdjdejekk29393838msmskxcm9239484jdndjdnddjj99292938338zeuslojdnejxxmejj82283849')

# ==========================================
# إعداد قواعد البيانات
# ==========================================

# 1. MongoDB Setup
MONGO_URI = os.environ.get('MONGODB_URI')
if MONGO_URI:
    try:
        mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
        mongo_db = mongo_client.get_database() # يستخدم قاعدة البيانات الافتراضية في الرابط
        novels_collection = mongo_db['novels']
        print("✅ Connected to MongoDB")
    except Exception as e:
        print(f"❌ MongoDB Connection Error: {e}")
else:
    print("⚠️ MONGO_URI not found in env vars")

# 2. Firebase Setup
FIREBASE_KEY = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
if FIREBASE_KEY:
    try:
        # إذا كان المفتاح نص JSON (كما في Railway Variables)
        cred_dict = json.loads(FIREBASE_KEY)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        firestore_db = firestore.client()
        print("✅ Connected to Firebase Firestore")
    except Exception as e:
        print(f"❌ Firebase Connection Error: {e}")
else:
    print("⚠️ FIREBASE_KEY not found in env vars")

# ==========================================
# منطق السحب (Scraper Logic)
# ==========================================

def get_slug_from_url(url):
    """استخراج المعرف الفريد للرواية من الرابط"""
    # Example: https://rewayat.club/novel/the-beginning-after-the-end/
    # Slug: the-beginning-after-the-end
    parts = url.split('/novel/')
    if len(parts) > 1:
        return parts[1].strip('/').split('/')[0]
    return None

def fetch_novel_metadata(slug):
    """جلب معلومات الرواية من API الموقع"""
    api_url = f"https://api.rewayat.club/api/novel/{slug}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                'title': data.get('arabic', data.get('english', 'Unknown')),
                'description': data.get('about', ''),
                'cover': f"https://api.rewayat.club{data.get('poster_url', '')}" if data.get('poster_url') else '',
                'status': 'مكتملة' if data.get('get_novel_status') == 'مكتملة' else 'مستمرة',
                'tags': [g['arabic'] for g in data.get('genre', [])],
                'slug': slug
            }
    except Exception as e:
        print(f"Error fetching metadata: {e}")
    return None

def fetch_all_chapters_list(slug):
    """جلب قائمة جميع الفصول باستخدام الترقيم"""
    chapters = []
    page = 1
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    while True:
        # API الموقع يدعم الترقيم
        url = f"https://api.rewayat.club/api/chapters/{slug}/?ordering=number&page={page}"
        try:
            print(f"Fetching chapters list page {page}...")
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                break
            
            data = response.json()
            results = data.get('results', [])
            
            if not results:
                break
                
            for item in results:
                chapters.append({
                    'number': item.get('number'),
                    'title': item.get('title'),
                    'id': item.get('id')
                })
            
            if not data.get('next'):
                break
                
            page += 1
            time.sleep(0.5) # مهلة بسيطة
            
        except Exception as e:
            print(f"Error fetching chapters list: {e}")
            break
            
    return chapters

def scrape_chapter_content(slug, chapter_num):
    """سحب نص الفصل من صفحة HTML"""
    url = f"https://rewayat.club/novel/{slug}/{chapter_num}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # محاولة إيجاد النص في العناصر الشائعة
            # بناءً على بنية الموقع: <div class="content-area"> أو <div class="v-card__text">
            content_div = soup.find('div', class_='content-area')
            
            if not content_div:
                # محاولة بديلة: البحث عن أي div يحتوي على نصوص p كثيرة
                content_div = soup.find('div', class_=lambda x: x and 'unselectable' in x)
            
            if content_div:
                paragraphs = content_div.find_all('p')
                text_content = "\n\n".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                return text_content
            
            # محاولة أخيرة: سحب كل النصوص p
            paragraphs = soup.find_all('p')
            # تصفية النصوص القصيرة جداً (مثل القوائم)
            clean_text = "\n\n".join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20])
            return clean_text
            
    except Exception as e:
        print(f"Error scraping chapter {chapter_num}: {e}")
    
    return None

def background_worker(url, admin_email, author_name):
    """الوظيفة التي تعمل في الخلفية"""
    print(f"🚀 Starting scraper for: {url}")
    
    slug = get_slug_from_url(url)
    if not slug:
        print("❌ Invalid URL")
        return

    # 1. جلب البيانات الوصفية
    metadata = fetch_novel_metadata(slug)
    if not metadata:
        print("❌ Failed to fetch metadata")
        return

    print(f"📖 Found Novel: {metadata['title']}")

    # 2. إنشاء/تحديث الرواية في MongoDB
    novel_doc = {
        'title': metadata['title'],
        'description': metadata['description'],
        'cover': metadata['cover'],
        'author': author_name,
        'authorEmail': admin_email,
        'category': metadata['tags'][0] if metadata['tags'] else 'عام',
        'tags': metadata['tags'],
        'status': metadata['status'],
        'sourceUrl': url,
        'lastChapterUpdate': datetime.now(),
        'createdAt': datetime.now()
    }

    # البحث إذا كانت موجودة لتحديثها
    existing_novel = novels_collection.find_one({'title': metadata['title'], 'authorEmail': admin_email})
    
    if existing_novel:
        novel_id = existing_novel['_id']
        # تحديث الحقول فقط
        novels_collection.update_one({'_id': novel_id}, {'$set': {
            'cover': metadata['cover'],
            'status': metadata['status'],
            'lastChapterUpdate': datetime.now()
        }})
        print(f"🔄 Updated existing novel ID: {novel_id}")
    else:
        result = novels_collection.insert_one({**novel_doc, 'chapters': [], 'views': 0})
        novel_id = result.inserted_id
        print(f"🆕 Created new novel ID: {novel_id}")

    # 3. جلب قائمة الفصول
    chapters_list = fetch_all_chapters_list(slug)
    print(f"📚 Found {len(chapters_list)} chapters.")

    # 4. سحب الفصول وحفظها
    new_chapters_meta = [] # لتحديث MongoDB
    
    # نحضر الفصول الموجودة حالياً لتجنب التكرار
    current_novel = novels_collection.find_one({'_id': novel_id})
    existing_numbers = [c['number'] for c in current_novel.get('chapters', [])]

    for chap in chapters_list:
        num = chap['number']
        
        # إذا الفصل موجود، تخطاه (يمكنك إزالة هذا الشرط إذا أردت تحديث المحتوى)
        if num in existing_numbers:
            print(f"⏩ Skipping Chapter {num} (Already exists)")
            continue

        print(f"📥 Scraping Chapter {num}...")
        content = scrape_chapter_content(slug, num)
        
        if content:
            # A. الحفظ في Firebase (المحتوى النصي)
            try:
                doc_ref = firestore_db.collection('novels').document(str(novel_id)).collection('chapters').document(str(num))
                doc_ref.set({
                    'title': chap['title'],
                    'content': content,
                    'lastUpdated': firestore.SERVER_TIMESTAMP
                })
            except Exception as e:
                print(f"❌ Firebase Error Ch {num}: {e}")
                continue

            # B. التجهيز لـ MongoDB (الميتا داتا)
            chapter_meta = {
                'number': num,
                'title': chap['title'],
                'createdAt': datetime.now(),
                'views': 0
            }
            
            # إضافة لـ Mongo مباشرة لتحديث القائمة فوراً
            novels_collection.update_one(
                {'_id': novel_id},
                {'$push': {'chapters': chapter_meta}}
            )
            print(f"✅ Saved Chapter {num}")
            
            time.sleep(1) # احترام الموقع وتجنب الحظر
        else:
            print(f"⚠️ Empty content for Chapter {num}")

    print("✨ Scraping Task Completed!")

# ==========================================
# نقاط النهاية (Endpoints)
# ==========================================

@app.route('/', methods=['GET'])
def health_check():
    return "ZEUS Scraper Service is Running ⚡", 200

@app.route('/scrape', methods=['POST'])
def trigger_scrape():
    # 1. التحقق من المفتاح السري
    auth_header = request.headers.get('Authorization')
    if auth_header != API_SECRET:
        return jsonify({'message': 'Unauthorized'}), 401

    data = request.json
    url = data.get('url')
    admin_email = data.get('adminEmail')
    author_name = data.get('authorName', 'ZEUS Bot')

    if not url or 'rewayat.club' not in url:
        return jsonify({'message': 'Invalid URL. Must be from rewayat.club'}), 400

    # 2. تشغيل السحب في عملية منفصلة (Thread)
    thread = threading.Thread(target=background_worker, args=(url, admin_email, author_name))
    thread.daemon = True # لتعمل في الخلفية
    thread.start()

    return jsonify({
        'message': 'تم بدء عملية السحب في الخلفية. ستظهر الفصول تباعاً.',
        'status': 'started'
    }), 200

if __name__ == "__main__":
    from datetime import datetime
    # تشغيل السيرفر
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
