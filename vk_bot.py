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

# Пробуем импортировать Pillow
try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️ WARNING: Pillow не установлен. Карточки не будут создаваться.")

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
            subprocess.run(['git', 'commit', '-m', f'Update seen links'], check=False, capture_output=True)
            subprocess.run(['git', 'push'], check=False, capture_output=True)
            log("  ✓ Файл сохранён в репозиторий")
    except Exception as e:
        log(f"   Ошибка коммита: {e}")

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

def create_simple_card(title, is_iphone=False):
    """Создает ПРОСТУЮ карточку без шрифтов — просто цветной фон с эмодзи"""
    if not PIL_AVAILABLE:
        log("  ⚠ Pillow не доступен, пропускаю создание карточки")
        return None
    
    try:
        width, height = 1200, 630
        gradient = random.choice(GRADIENTS)
        color_start = gradient[0]
        color_end = gradient[1]
        
        img = Image.new('RGB', (width, height), color_start)
        draw = ImageDraw.Draw(img)
        
        # Рисуем градиент
        for y in range(height):
            r = int(color_start[0] + (color_end[0] - color_start[0]) * y / height)
            g = int(color_start[1] + (color_end[1] - color_start[1]) * y / height)
            b = int(color_start[2] + (color_end[2] - color_start[2]) * y / height)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        
        # Эмодзи
        emoji = "🍎" if is_iphone else "🤖"
        
        # Рисуем эмодзи по центру (крупно)
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 200)
        except:
            font_large = ImageFont.load_default()
        
        # Позиция эмодзи
        emoji_width = 150
        emoji_height = 150
        x = (width - emoji_width) // 2
        y = (height - emoji_height) // 2 - 50
        
        draw.text((x, y), emoji, fill=(255, 255, 255), font=font_large)
        
        # Текст заголовка внизу
        if len(title) > 80:
            title = title[:77] + "..."
        
        try:
            font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except:
            font_text = ImageFont.load_default()
        
        draw.text((50, height - 100), title, fill=(255, 255, 255), font=font_text)
        
        temp_file = f"/tmp/vk_card_{int(time.time())}.png"
        img.save(temp_file, 'PNG')
        log(f"   ✅ Карточка создана: {width}x{height}px")
        return temp_file
        
    except Exception as e:
        log(f"  ❌ Ошибка создания карточки: {e}")
        import traceback
        traceback.print_exc()
        return None

def extract_all_images(soup, url):
    images = []
    
    og = soup.find('meta', property='og:image')
    if og and og.get('content'):
        images.append(og['content'])
    
    tw = soup.find('meta', attrs={'name': 'twitter:image'})
    if tw and tw.get('content'):
        images.append(tw['content'])
    
    article = soup.find('article') or soup.find('div', class_=re.compile(r'article|content', re.I))
    if article:
        for img in article.find_all('img', src=True):
            src = img.get('src') or img.get('data-src')
            if src and len(src) > 10:
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = url.split('/')[0] + '//' + url.split('/')[2] + src
                images.append(src)
    
    return images[:3] if images else []

def get_article_content(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None, None
        
        soup = BeautifulSoup(r.content, 'html.parser')
        all_images = extract_all_images(soup, url)
        log(f"   Найдено картинок: {len(all_images)}")
        
        text = ""
        content = soup.find('article') or soup.find('div', class_=re.compile(r'article|content', re.I))
        if content:
            for p in content.find_all(['p', 'h2', 'h3']):
                t = p.get_text().strip()
                if len(t) > 30:
                    text += t + "\n\n"
        
        text = clean_text(text)[:1500]
        main_image = all_images[0] if all_images else None
        
        return text if len(text) > 100 else None, main_image
    except Exception as e:
        log(f"  ⚠ Ошибка парсинга: {e}")
        return None, None

def fetch_news():
    news_list = []
    seen_links = load_seen_links()
    log(f"Загружено {len(seen_links)} ссылок из истории")
    log("Сбор новостей из RSS...")
    
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
            log(f"  ⚠ Ошибка RSS {source}: {e}")
    
    log(f"  ✓ Найдено {len(news_list)} ссылок. Парсим...")
    
    result = []
    for item in news_list[:10]:
        log(f"  📄 {item['title'][:60]}...")
        full_text, image_url = get_article_content(item['link'])
        
        if not full_text or is_ad_text(full_text):
            continue
            
        result.append({'title': item['title'], 'link': item['link'], 'text': full_text, 'image': image_url})
        if len(result) >= 3:
            break
    
    log(f"  ✓ Готово: {len(result)} статей")
    return result

def download_image(url):
    try:
        log(f"  ⬇️ Скачиваю: {url[:60]}...")
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200 or len(r.content) < 10000:
            return None
        
        ext = '.jpg'
        temp_file = f"/tmp/vk_img_{int(time.time())}.jpg"
        with open(temp_file, 'wb') as f:
            f.write(r.content)
        log(f"  ✓ Скачано: {len(r.content) // 1024} КБ")
        return temp_file
    except Exception as e:
        log(f"  ⚠ Ошибка: {e}")
        return None

def upload_photo_to_vk(vk, group_id_int, temp_file):
    try:
        upload_server = vk.photos.getWallUploadServer(group_id=group_id_int)
        
        with open(temp_file, 'rb') as f:
            response = requests.post(upload_server['upload_url'], files={'photo': f})
        
        data = response.json()
        if 'photo' not in data:
            return None
        
        saved = vk.photos.saveWallPhoto(
            group_id=group_id_int,
            photo=data['photo'],
            server=data['server'],
            hash=data['hash']
        )
        
        if saved:
            return f"photo{saved[0]['owner_id']}_{saved[0]['id']}"
        return None
    except Exception as e:
        log(f"  ❌ Ошибка загрузки: {e}")
        return None

def post_to_vk(news_item):
    try:
        vk_session = vk_api.VkApi(token=VK_ACCESS_TOKEN)
        vk = vk_session.get_api()
        
        is_iphone = any(k in news_item['title'].lower() for k in IPHONE_KEYWORDS)
        emoji = "🍎" if is_iphone else "🤖"
        
        post_text = f"{emoji} {news_item['title']}\n\n{news_item['text']}\n\nИсточник: {news_item['link']}\n\n#Android #iPhone #Технологии"
        
        attachment = None
        temp_file = None
        
        # Пробуем скачать фото
        if news_item.get('image'):
            log(f"  🖼 Нашёл фото")
            temp_file = download_image(news_item['image'])
            
            if temp_file:
                attachment = upload_photo_to_vk(vk, int(VK_GROUP_ID.lstrip('-')), temp_file)
                try:
                    os.remove(temp_file)
                except:
                    pass
                
                if not attachment:
                    log(f"   Не загрузилось, создаю карточку...")
        
        # Если фото нет — создаем карточку
        if not attachment:
            log(f"   Создаю текстовую карточку...")
            temp_file = create_simple_card(news_item['title'], is_iphone)
            
            if temp_file:
                attachment = upload_photo_to_vk(vk, int(VK_GROUP_ID.lstrip('-')), temp_file)
                try:
                    os.remove(temp_file)
                except:
                    pass
        
        # Публикуем
        vk.wall.post(
            owner_id=int(VK_GROUP_ID),
            message=post_text[:4000],
            attachments=attachment,
            from_group=1
        )
        
        log(f"  ✅ Опубликовано!")
        return True
        
    except Exception as e:
        log(f"  ❌ Ошибка: {e}")
        return False

def main():
    log("=" * 60)
    log("VK News Bot")
    log("=" * 60)
    
    if not PIL_AVAILABLE:
        log("⚠️ Pillow не установлен — карточки создаваться не будут")
        log("Убедитесь что в requirements.txt есть строка: Pillow")
    
    if not VK_ACCESS_TOKEN or not VK_GROUP_ID.startswith('-'):
        log("❌ Ошибка настроек!")
        return
    
    try:
        vk_api.VkApi(token=VK_ACCESS_TOKEN).get_api()
        log("✅ Авторизация успешна")
    except Exception as e:
        log(f"❌ Ошибка: {e}")
        return
    
    news_list = fetch_news()
    if not news_list:
        log("❌ Нет новостей")
        return
    
    seen_links = load_seen_links()
    for news in news_list[:MAX_POSTS_PER_RUN]:
        log(f"\n[1/{MAX_POSTS_PER_RUN}] Публикую...")
        if post_to_vk(news):
            seen_links.add(news['link'])
            save_seen_links(seen_links)
            commit_seen_file()
            break
    
    log(f"\n{'=' * 60}")
    log("✅ Готово!")

if __name__ == "__main__":
    main()
