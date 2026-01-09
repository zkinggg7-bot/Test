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
import re

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
            
            # استبدال \\n بسطور حقيقية
            private_key = private_key.replace('\\n', '\n')
            
            # إزالة المسافات والتابات الزائدة من كل سطر
            lines = private_key.split('\n')
            cleaned_lines = []
            for line in lines:
                # الحفاظ على BEGIN/END كما هي
                if '-----BEGIN' in line or '-----END' in line:
                    cleaned_lines.append(line.strip())
                else:
                    # إزالة جميع المسافات من سطور Base64
                    cleaned_line = line.strip().replace(' ', '').replace('\t', '')
                    if cleaned_line:  # تجاهل الأسطر الفارغة
                        cleaned_lines.append(cleaned_line)
            
            # إعادة بناء المفتاح
            cred_dict['private_key'] = '\n'.join(cleaned_lines)
            
            # التحقق من صحة التنسيق
            if not cred_dict['private_key'].startswith('-----BEGIN PRIVATE KEY-----'):
                raise ValueError("Invalid private key format: missing BEGIN header")
            if not cred_dict['private_key'].endswith('-----END PRIVATE KEY-----'):
                raise ValueError("Invalid private key format: missing END footer")
        
        # تهيئة Firebase
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        firestore_db = firestore.client()
        print("✅ Connected to Firebase Firestore")
        
    except json.JSONDecodeError as e:
        print(f"❌ Firebase JSON Parse Error: {e}")
        print(f"First 100 chars of FIREBASE_KEY: {FIREBASE_KEY[:100]}")
    except ValueError as e:
        print(f"❌ Firebase Key Format Error: {e}")
    except Exception as e:
        print(f"❌ Firebase Connection Error: {e}")
        import traceback
        print(traceback.format_exc())
else:
    print("⚠️ FIREBASE_SERVICE_ACCOUNT not found in env vars")

# ==========================================
# منطق السحب (Scraper Logic)
# ==========================================

def get_slug_from_url(url):
    """استخراج المعرف الفريد للرواية من الرابط"""
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
            time.sleep(0.5)
            
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
            
            content_div = soup.find('div', class_='content-area')
            
            if not content_div:
                content_div = soup.find('div', class_=lambda x: x and 'unselectable' in x)
            
            if content_div:
                paragraphs = content_div.find_all('p')
                text_content = "\n\n".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                return text_content
            
            paragraphs = soup.find_all('p')
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

    metadata = fetch_novel_metadata(slug)
    if not metadata:
        print("❌ Failed to fetch metadata")
        return

    print(f"📖 Found Novel: {metadata['title']}")

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

    existing_novel = novels_collection.find_one({'title': metadata['title'], 'authorEmail': admin_email})
    
    if existing_novel:
        novel_id = existing_novel['_id']
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

    chapters_list = fetch_all_chapters_list(slug)
    print(f"📚 Found {len(chapters_list)} chapters.")

    current_novel = novels_collection.find_one({'_id': novel_id})
    existing_numbers = [c['number'] for c in current_novel.get('chapters', [])]

    for chap in chapters_list:
        num = chap['number']
        
        if num in existing_numbers:
            print(f"⏩ Skipping Chapter {num} (Already exists)")
            continue

        print(f"📥 Scraping Chapter {num}...")
        content = scrape_chapter_content(slug, num)
        
        if content:
            try:
                # الحفظ في Firebase (المحتوى)
                doc_ref = firestore_db.collection('novels').document(str(novel_id)).collection('chapters').document(str(num))
                doc_ref.set({
                    'title': chap['title'],
                    'content': content,
                    'lastUpdated': firestore.SERVER_TIMESTAMP
                })

                # التحديث في MongoDB (الميتا داتا)
                chapter_meta = {
                    'number': num,
                    'title': chap['title'],
                    'createdAt': datetime.now(),
                    'views': 0
                }
                
                novels_collection.update_one(
                    {'_id': novel_id},
                    {'$push': {'chapters': chapter_meta}}
                )
                print(f"✅ Saved Chapter {num}")
                
                time.sleep(1) 
            except Exception as e:
                print(f"❌ Firebase/Mongo Error Ch {num}: {e}")
                continue
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
    auth_header = request.headers.get('Authorization')
    if auth_header != API_SECRET:
        return jsonify({'message': 'Unauthorized'}), 401

    data = request.json
    url = data.get('url')
    admin_email = data.get('adminEmail')
    author_name = data.get('authorName', 'ZEUS Bot')

    if not url or 'rewayat.club' not in url:
        return jsonify({'message': 'Invalid URL. Must be from rewayat.club'}), 400

    thread = threading.Thread(target=background_worker, args=(url, admin_email, author_name))
    thread.daemon = True 
    thread.start()

    return jsonify({
        'message': 'تم بدء عملية السحب في الخلفية. ستظهر الفصول تباعاً.',
        'status': 'started'
    }), 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
