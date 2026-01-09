import requests
from bs4 import BeautifulSoup
import os
import time

# --- الإعدادات ---
BASE_URL = "https://rewayat.club/novel/you-are-running-30000-simulations-a-day-trying-to-stay-healthy-or-what/"
TOTAL_CHAPTERS = 5  # لغرض التجربة على Railway سنكتفي بـ 5 فصول
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
}

def fetch_chapter(chapter_num):
    url = f"{BASE_URL}{chapter_num}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # استخراج العنوان
            title_tag = soup.find('div', class_='v-card__subtitle')
            chapter_title = title_tag.get_text(strip=True) if title_tag else f"Chapter {chapter_num}"
            
            # استخراج المحتوى
            paragraphs = soup.find_all('p')
            clean_paragraphs = [p.get_text(strip=True) for p in paragraphs if len(p.get_text()) > 30]
            content = "\n\n".join(clean_paragraphs)
            
            # عرض النتيجة في الـ Logs لكي تراها في Railway
            print(f"✅ تم سحب الفصل {chapter_num}: {chapter_title}")
            print(f"📝 بداية النص: {content[:100]}...") # نطبع أول 100 حرف للتأكد
            print("-" * 20)
            
        else:
            print(f"❌ فشل تحميل الفصل {chapter_num} - رمز الخطأ: {response.status_code}")
            
    except Exception as e:
        print(f"⚠️ خطأ في الفصل {chapter_num}: {str(e)}")

if __name__ == "__main__":
    print("🚀 بدء تشغيل السكريبت على Railway...")
    for i in range(1, TOTAL_CHAPTERS + 1):
        fetch_chapter(i)
        time.sleep(2)
    print("✨ انتهت التجربة بنجاح!")
