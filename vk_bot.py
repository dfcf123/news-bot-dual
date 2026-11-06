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
import json

# Проверяем доступность библиотеки Pillow для создания карточек
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Читаем настройки из переменных окружения GitHub (НЕ МЕНЯЙ ЭТИ СТРОКИ!)
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

MAX_POSTS_PER_RUN = 1
SEEN_FILE = "vk_seen_links.txt"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
}

AD_MARKERS = ["подпишись", "реклама", "акция", "скидка", "промокод", "купи", "закажи", "сундук али", "ali-баб", "партнерский материал"]

GRADIENTS = [
    ((66, 134, 244), (119, 94, 200)),
    ((233, 69, 96), (225, 48, 108)),
    ((0, 188, 212), (0, 150, 136)),
    ((255, 152, 0), (255, 87, 34)),
]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def load_seen_links():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, 'r', encoding='utf-8') as f:
                return set(line.strip() for line in f if line.strip())
        except Exception:
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
            subprocess.run(['git', 'commit', '-m', 'Update seen links'], check=False, capture_output=True)
            subprocess.run(['git', 'push'], check=False, capture_output=True)
            log("✓ Файл истории сохранён в репозиторий")
    except Exception as e:
        log(f"Ошибка коммита: {e}")

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
        if not line or is_ad_text(line):
            continue
        if len(line) > 20 and line.isupper():
            continue
        clean_lines.append(line)
    return '\n'.join(clean_lines)

def create_card(title, is_iphone=False):
    if not PIL_AVAILABLE:
        log("Pillow не доступен, карточка не будет создана")
        return None
    
    try:
        width, height = 1200, 630
        gradient = random.choice(GRADIENTS)
        
        img = Image.new('RGB', (width, height), gradient[0])
        draw = ImageDraw.Draw(img)
        
        for y in range(height):
            r = int(gradient[0][0] + (gradient[1][0] - gradient[0][0]) * y / height)
            g = int(gradient[0][1] + (gradient[1][1] - gradient[0][1]) * y / height)
            b = int(gradient[0][2] + (gradient[1][2] - gradient[0][2]) * y / height)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        
        emoji = "🍎" if is_iphone else "🤖"
        try:
            font_emoji = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 150)
        except Exception:
            font_emoji = ImageFont.load_default()
        
        draw.text((width//2 - 75, height//2 - 150), emoji, fill=(255, 255, 255), font=font_emoji)
        
        if len(title) > 80:
            title = title[:77] + "..."
        
        try:
            font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        except Exception:
            font_text = ImageFont.load_default()
        
        draw.text((50, height - 80), title, fill=(255, 255, 255), font=font_text)
        
        temp_file = f"/tmp/vk_card_{int(time.time())}.png"
        img.save(temp_file, 'PNG')
        log("Карточка успешно создана")
        return temp_file
        
    except Exception as e:
        log(f"Ошибка создания карточки: {e}")
        return None

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
            article = soup.find('article')
            if article:
                img = article.find('img', src=True)
                if img:
                    image_url = img.get('src')
        
        text = ""
        content = soup.find('article')
        if content:
            for p in content.find_all(['p', 'h2', 'h3']):
                t = p.get_text().strip()
                if len(t) > 30:
                    text += t + "\n\n"
        
        text = clean_text(text)[:1500]
        
        return text if len(text) > 100 else None, image_url
    except Exception as e:
        log(f"Ошибка парсинга: {e}")
        return None, None

def fetch_news():
    news_list = []
    seen_links = load_seen_links()
    log(f"Загружено {len(seen_links)} ссылок из истории")
    
    for source in NEWS_SOURCES:
        try:
            r = requests.get(source, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            
            feed = feedparser.parse(r.content)
            for entry in feed.entries[:5]:
                link = entry.get('link', '').strip()
                if not link or link in seen_links:
                    continue
                
                title = entry.get('title', '').strip()
                if not title or len(title) < 10:
                    continue
                
                if not is_relevant(title, entry.get('description', '')):
                    continue
                
                news_list.append({'title': title, 'link': link})
        except Exception as e:
            log(f"Ошибка RSS {source}: {e}")
    
    log(f"Найдено {len(news_list)} релевантных ссылок")
    
    result = []
    for item in news_list[:10]:
        log(f"Парсим: {item['title'][:50]}...")
        full_text, image_url = get_article_content(item['link'])
        
        if not full_text or is_ad_text(full_text):
            continue
        
        result.append({
            'title': item['title'],
            'link': item['link'],
            'text': full_text,
            'image': image_url
        })
        
        if len(result) >= 3:
            break
    
    log(f"Готово к публикации: {len(result)} статей")
    return result

def download_image(url):
    try:
        log(f"Скачиваю фото...")
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200 or len(r.content) < 10000:
            return None
        
        temp_file = f"/tmp/vk_img_{int(time.time())}.jpg"
        with open(temp_file, 'wb') as f:
            f.write(r.content)
        log(f"Фото скачано: {len(r.content) // 1024} КБ")
        return temp_file
    except Exception as e:
        log(f"Ошибка скачивания: {e}")
        return None

def upload_photo_to_vk(vk, group_id, temp_file):
    try:
        log(f"Загружаю фото в ВК...")
        
        upload_server = vk.photos.getWallUploadServer(group_id=group_id)
        upload_url = upload_server['upload_url']
        
        with open(temp_file, 'rb') as f:
            response = requests.post(upload_url, files={'photo': f})
        
        data = response.json()
        if 'photo' not in data or 'server' not in data or 'hash' not in data:
            log(f"Ошибка ответа сервера ВК: {data}")
            return None
        
        log(f"Сохраняю фото...")
        saved = vk.photos.saveWallPhoto(
            group_id=group_id,
            photo=data['photo'],
            server=data['server'],
            hash=data['hash']
        )
        
        if saved and len(saved) > 0:
            photo_id = f"photo{saved[0]['owner_id']}_{saved[0]['id']}"
            log(f"Фото успешно сохранено: {photo_id}")
            return photo_id
        else:
            log(f"Ошибка сохранения фото: {saved}")
            return None
            
    except vk_api.exceptions.ApiError as e:
        log(f"API ошибка ВК: {e}")
        return None
    except Exception as e:
        log(f"Ошибка загрузки: {e}")
        return None

def post_to_vk(news_item):
    try:
        vk_session = vk_api.VkApi(token=VK_ACCESS_TOKEN)
        vk = vk_session.get_api()
        
        group_id = int(VK_GROUP_ID.lstrip('-'))
        is_iphone = any(k in news_item['title'].lower() for k in IPHONE_KEYWORDS)
        emoji = "🍎" if is_iphone else "🤖"
        
        post_text = f"{emoji} {news_item['title']}\n\n{news_item['text']}\n\nИсточник: {news_item['link']}\n\n#Android #iPhone #Технологии"
        
        attachment = None
        temp_file = None
        
        if news_item.get('image'):
            log(f"Нашёл фото в статье")
            temp_file = download_image(news_item['image'])
            
            if temp_file:
                attachment = upload_photo_to_vk(vk, group_id, temp_file)
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
                
                if not attachment:
                    log(f"Фото не загрузилось, создаю карточку")
        
        if not attachment:
            log(f"Создаю текстовую карточку...")
            temp_file = create_card(news_item['title'], is_iphone)
            
            if temp_file:
                attachment = upload_photo_to_vk(vk, group_id, temp_file)
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
        
        log(f"Публикую пост...")
        vk.wall.post(
            owner_id=int(VK_GROUP_ID),
            message=post_text[:4000],
            attachments=attachment,
            from_group=1
        )
        
        log(f"✅ Опубликовано!")
        return True
        
    except Exception as e:
        log(f"❌ Ошибка публикации: {e}")
        return False

def main():
    log("=" * 60)
    log("VK News Bot запущен")
    log("=" * 60)
    
    if not PIL_AVAILABLE:
        log("⚠️ Библиотека Pillow не найдена. Карточки создаваться не будут.")
    
    if not VK_ACCESS_TOKEN or not VK_GROUP_ID.startswith('-'):
        log("❌ Ошибка: Токен или ID группы не заданы в Secrets GitHub!")
        return
    
    try:
        vk_api.VkApi(token=VK_ACCESS_TOKEN).get_api()
        log("✅ Авторизация в ВК успешна")
    except Exception as e:
        log(f"❌ Ошибка авторизации: {e}")
        return
    
    news_list = fetch_news()
    if not news_list:
        log("❌ Нет новых подходящих новостей для публикации")
        return
    
    seen_links = load_seen_links()
    for news in news_list[:MAX_POSTS_PER_RUN]:
        log(f"\n[1/{MAX_POSTS_PER_RUN}] Начинаю публикацию...")
        if post_to_vk(news):
            seen_links.add(news['link'])
            save_seen_links(seen_links)
            commit_seen_file()
            break
    
    log(f"\n{'=' * 60}")
    log("✅ Работа бота завершена успешно!")
    log(f"{'=' * 60}")

if __name__ == "__main__":
    main()
