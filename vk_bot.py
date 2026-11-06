import os
import re
import time
import random
import requests
import feedparser
from datetime import datetime
from bs4 import BeautifulSoup
import vk_api
import subprocess

# ================= НАСТРОЙКИ =================
VK_ACCESS_TOKEN = os.environ.get("VK_ACCESS_TOKEN", "")
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "-183445484")

NEWS_SOURCES = [
    "https://androidinsider.ru/feed/",
    "https://www.iphone.ru/feed",
    "https://appleinsider.ru/feed/",
    "https://habr.com/ru/rss/hub/android/",
    "https://habr.com/ru/rss/hub/ios/",
]

ANDROID_KEYWORDS = ["android", "андроид", "google pixel", "samsung", "xiaomi", "oneplus", "redmi", "poco", "realme", "смартфон", "galaxy", "pixel"]
IPHONE_KEYWORDS = ["iphone", "ipad", "ios", "apple", "macbook", "airpods", "macos", "айфон", "айпад", "эппл", "apple watch", "imac"]

# ОПУТИМИЗАЦИЯ ДЛЯ GITHUB ACTIONS: 1 пост за запуск, без пауз
MAX_POSTS_PER_RUN = 1
SEEN_FILE = "vk_seen_links.txt"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
}

AD_MARKERS = ["подпишись", "реклама", "акция", "скидка", "промокод", "купи", "закажи", "сундук али", "ali-баб", "партнерский материал"]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def load_seen_links():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, 'r', encoding='utf-8') as f:
                return set(line.strip() for line in f if line.strip())
        except:
            return set()
    return set()

def save_seen_links(seen_links):
    with open(SEEN_FILE, 'w', encoding='utf-8') as f:
        for link in list(seen_links)[-500:]:
            f.write(link + '\n')

def commit_seen_file():
    try:
        subprocess.run(['git', 'config', '--global', 'user.email', 'bot@github.com'], check=False, capture_output=True)
        subprocess.run(['git', 'config', '--global', 'user.name', 'VK Bot'], check=False, capture_output=True)
        result = subprocess.run(['git', 'status', '--porcelain', SEEN_FILE], capture_output=True, text=True, check=False)
        if result.stdout.strip():
            subprocess.run(['git', 'add', SEEN_FILE], check=False, capture_output=True)
            subprocess.run(['git', 'commit', '-m', f'Update seen links {datetime.now().strftime("%Y-%m-%d %H:%M")}'], check=False, capture_output=True)
            subprocess.run(['git', 'push'], check=False, capture_output=True)
            log("  ✓ Файл vk_seen_links.txt сохранён в репозиторий")
    except Exception as e:
        log(f"  ⚠ Ошибка коммита: {e}")

def is_relevant(title, text):
    t = (title + " " + text).lower()
    return any(k in t for k in ANDROID_KEYWORDS) or any(k in t for k in IPHONE_KEYWORDS)

def is_ad_text(text):
    t = text.lower()
    return any(marker in t for marker in AD_MARKERS)

def clean_text(text):
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        line = line.strip()
        if not line: continue
        if is_ad_text(line): continue
        if len(line) > 20 and line.isupper(): continue
        if line.upper().startswith(('ЧИТАЙТЕ', 'СМОТРИТЕ', 'ПОДРОБНЕЕ', 'ПОДПИШИСЬ')): continue
        clean_lines.append(line)
    return '\n'.join(clean_lines)

def get_article_content(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None, None
        
        soup = BeautifulSoup(r.content, 'html.parser')
        image_url = None
        
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            image_url = og['content']
            
        if not image_url:
            article = soup.find('article') or soup.find('div', class_=re.compile(r'article|content|post', re.I))
            if article:
                for img in article.find_all('img', src=True):
                    src = img.get('src') or img.get('data-src')
                    if not src: continue
                    if src.startswith('//'): src = 'https:' + src
                    elif src.startswith('/'): src = url.split('/')[0] + '//' + url.split('/')[2] + src
                    if len(src) > 10 and not any(x in src.lower() for x in ['logo', 'icon', 'avatar', 'sprite']):
                        image_url = src
                        break
        
        text = ""
        content = soup.find('article') or soup.find('div', class_=re.compile(r'article|content|entry-content', re.I))
        if content:
            for p in content.find_all(['p', 'h2', 'h3', 'h4']):
                t = p.get_text().strip()
                if len(t) > 30: text += t + "\n\n"
        else:
            for p in soup.find_all('p')[:10]:
                t = p.get_text().strip()
                if len(t) > 30: text += t + "\n\n"
        
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        text = clean_text(text)
        
        if len(text) > 1500:
            text = text[:1500]
            last_nl = text.rfind('\n\n')
            if last_nl > 500: text = text[:last_nl] + "\n\n..."
            
        return text if len(text) > 100 else None, image_url
    except Exception as e:
        log(f"  ⚠ Ошибка парсинга {url}: {e}")
        return None, None

def fetch_news():
    news_list = []
    seen_links = load_seen_links()
    log(f"Загружено {len(seen_links)} опубликованных ссылок из истории")
    log("Начинаю сбор новостей из RSS...")
    
    for source in NEWS_SOURCES:
        try:
            r = requests.get(source, headers=HEADERS, timeout=15)
            if
