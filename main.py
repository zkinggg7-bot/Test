
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
        
        # Title
        title_tag = soup.find(class_='post-title')
        title = title_tag.find('h1').get_text(strip=True) if title_tag else "Unknown"
        title = re.sub(r'\s*~.*$', '', title) # Remove "~ Ar Novel" suffix if present

        # Cover
        img_tag = soup.find(class_='summary_image').find('img')
        cover = img_tag.get('src') if img_tag else ""
        if not cover:
            og_img = soup.find("meta", property="og:image")
            if og_img: cover = og_img["content"]

        # ID for AJAX - IMPROVED EXTRACTION
        novel_id = None
        
        # Method 1: Shortlink (Best for WP)
        shortlink = soup.find("link", rel="shortlink")
        if shortlink:
            # href="https://ar-no.com/?p=269062"
            match = re.search(r'p=(\d+)', shortlink.get('href', ''))
            if match: novel_id = match.group(1)
            
        # Method 2: Hidden Input
        if not novel_id:
            id_input = soup.find('input', class_='rating-post-id')
            if id_input: novel_id = id_input.get('value')
            
        # Method 3: Container Data Attribute
        if not novel_id:
            div_id = soup.find('div', id='manga-chapters-holder')
            if div_id: novel_id = div_id.get('data-id')
            
        # Method 4: Variable in Script
        if not novel_id:
            scripts = soup.find_all('script')
            for s in scripts:
                if s.string and 'manga_id' in s.string:
                    match = re.search(r'"manga_id":"(\d+)"', s.string)
                    if match:
                        novel_id = match.group(1)
                        break
        
        print(f"🔍 Found Novel ID: {novel_id}")

        # Description
        desc_div = soup.find(class_='summary__content') or soup.find(class_='description-summary')
        description = desc_div.get_text(separator="\n", strip=True) if desc_div else ""

        # Tags/Category
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
    """Helper to parse chapters from a BeautifulSoup object containing <li class='wp-manga-chapter'>"""
    chapters = []
    items = soup.find_all('li', class_='wp-manga-chapter')
    
    for item in items:
        a = item.find('a')
        if a:
            link = a.get('href')
            raw_title = a.get_text(strip=True)
            
            # Extract number
            # Titles like: "347 - Name" or "Chapter 10" or "الفصل 10"
            # Try to find the first integer in the string
            num_match = re.search(r'(\d+)', raw_title)
            number = int(num_match.group(1)) if num_match else 0
            
            # Clean title
            clean_title = re.sub(r'^\d+\s*[-–]\s*', '', raw_title).strip()
            
            if number > 0:
                chapters.append({'number': number, 'url': link, 'title': clean_title})
    
    return chapters

def fetch_chapter_list_madara(novel_id, novel_url=None):
    """Get all chapters via AJAX or fallback to scraping the HTML page directly"""
    chapters = []
    
    # 1. Try fetching directly from the novel page (Server Side Rendered)
    if novel_url:
        print(f"📋 Trying to fetch chapters from HTML page: {novel_url}")
        try:
            # Often madara themes show the list on the main page
            res = requests.get(novel_url, headers=get_headers(), timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.content, 'html.parser')
                chapters = parse_madara_chapters_from_html(soup)
                if chapters:
                    print(f"✅ Found {len(chapters)} chapters in HTML.")
                    chapters.sort(key=lambda x: x['number'])
                    return chapters
        except Exception as e:
            print(f"⚠️ Failed HTML fetch: {e}")

    # 2. Try AJAX if HTML failed
    if not chapters and novel_id:
        print(f"📋 Trying AJAX fetch for ID: {novel_id}")
        try:
            ajax_url = "https://ar-no.com/wp-admin/admin-ajax.php"
            data = {'action': 'manga_get_chapters', 'manga': novel_id}
            
            headers = get_headers()
            headers['X-Requested-With'] = 'XMLHttpRequest'
            headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
            
            res = requests.post(ajax_url, data=data, headers=headers)
            if res.status_code == 200: 
                soup = BeautifulSoup(res.content, 'html.parser')
                chapters = parse_madara_chapters_from_html(soup)
                print(f"✅ Found {len(chapters)} chapters via AJAX.")
        except Exception as e:
            print(f"Error fetching chapter list AJAX: {e}")
            
    # Sort by number ascending
    if chapters:
        chapters.sort(key=lambda x: x['number'])
    
    return chapters

def scrape_chapter_madara(url):
    try:
        res = requests.get(url, headers=get_headers(), timeout=15)
        if res.status_code != 200: return None
        soup = BeautifulSoup(res.content, 'html.parser')
        
        # Content is usually in .text-left within .reading-content
        # Based on file provided: <div class="reading-content"> ... <div class="text-left"> ... </div> </div>
        
        container = soup.find(class_='text-left')
        
        if not container:
            # Fallback 1: reading-content
            container = soup.find(class_='reading-content')
        
        if not container:
            # Fallback 2: entry-content
            container = soup.find(class_='entry-content')
            
        if container:
            # Remove ads and junk
            for bad in container.find_all(['div', 'script', 'style', 'input'], class_=['code-block', 'adsbygoogle', 'pf-ad', 'wp-dark-mode-switcher']):
                bad.decompose()
            
            # Remove next/prev links inside content if any
            for nav in container.find_all('div', class_='nav-links'):
                nav.decompose()
            
            # Remove the hidden input for chapter ID
            for inp in container.find_all('input', id='wp-manga-current-chap'):
                inp.decompose()

            text = container.get_text(separator="\n\n", strip=True)
            
            # Cleanup text
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = text.replace('اكمال القراءة', '') # Common artifact
            
            return text
        
        return None
    except: return None

def worker_madara_list(url, admin_email, metadata):
    # 1. Check Backend
    existing_chapters = check_existing_chapters(metadata['title'])
    skip_meta = len(existing_chapters) > 0
    
    if not skip_meta:
        send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': [], 'skipMetadataUpdate': False})

    # 2. Get Full List (Pass URL now for fallback)
    print(f"📋 Fetching full chapter list for ID: {metadata['novel_id']}")
    all_chapters = fetch_chapter_list_madara(metadata['novel_id'], url)
    
    if not all_chapters:
        print(f"⚠️ Failed to get chapters list for {metadata['novel_id']}. Trying to check if URL was a chapter URL...")
        # Emergency check: if the user provided a chapter URL instead of novel URL, we can't scrape list easily.
        return

    print(f"📋 Found {len(all_chapters)} chapters on source.")
    
    batch = []
    
    # 3. Iterate (Skip existing)
    for chap in all_chapters:
        if chap['number'] in existing_chapters:
            continue
            
        print(f"📥 Scraping Ar-Novel Ch {chap['number']}...")
        content = scrape_chapter_madara(chap['url'])
        
        if content:
            batch.append({
                'number': chap['number'],
                'title': chap['title'],
                'content': content
            })
            
            if len(batch) >= 5:
                send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': skip_meta})
                print(f"📤 Sent {len(batch)} chapters.")
                batch = []
                time.sleep(1.0) # Be gentle
        else:
            print(f"⚠️ Failed content for Ch {chap['number']}")
            
    if batch:
        send_data_to_backend({'adminEmail': admin_email, 'novelData': metadata, 'chapters': batch, 'skipMetadataUpdate': skip_meta})
        print(f"📤 Sent final batch.")

# ==========================================
# Main Orchestrator
# ==========================================

@app.route('/', methods=['GET'])
def health_check():
    return "ZEUS Scraper Service (Multi-Site Supported ⚡) is Running", 200

@app.route('/scrape', methods=['POST'])
def trigger_scrape():
    auth_header = request.headers.get('Authorization')
    if auth_header != API_SECRET: return jsonify({'message': 'Unauthorized'}), 401

    data = request.json
    url = data.get('url', '')
    admin_email = data.get('adminEmail')
    
    if not url: return jsonify({'message': 'No URL'}), 400

    # Dispatcher
    if 'rewayat.club' in url:
        meta = fetch_metadata_rewayat(url)
        if not meta: return jsonify({'message': 'Failed metadata', 'error': 'Could not fetch metadata'}), 400
        
        thread = threading.Thread(target=worker_rewayat_probe, args=(url, admin_email, meta))
        thread.daemon = True
        thread.start()
        return jsonify({'message': 'Started Rewayat Probe', 'status': 'started'}), 200
        
    elif 'ar-no.com' in url:
        meta = fetch_metadata_madara(url)
        if not meta: return jsonify({'message': 'Failed metadata', 'error': 'Could not fetch metadata from Ar-Novel'}), 400
        
        # Proceed even if ID is missing, as we might scrape from HTML list
        thread = threading.Thread(target=worker_madara_list, args=(url, admin_email, meta))
        thread.daemon = True
        thread.start()
        return jsonify({'message': 'Started Ar-Novel List Scraper', 'status': 'started'}), 200

    else:
        return jsonify({'message': 'Unsupported Domain'}), 400

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
