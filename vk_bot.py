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
        if not line:
            continue
        if is_ad_text(line):
            continue
        if len(line) > 20 and line.isupper():
            continue
        if line.upper().startswith(('ЧИТАЙТЕ', 'СМОТРИТЕ', 'ПОДРОБНЕЕ', 'ПОДПИШИСЬ')):
            continue
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
                    if not src:
                        continue
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = url.split('/')[0] + '//' + url.split('/')[2] + src
                    if len(src) > 10 and not any(x in src.lower() for x in ['logo', 'icon', 'avatar', 'sprite']):
                        image_url = src
                        break
        
        text = ""
        content = soup.find('article') or soup.find('div', class_=re.compile(r'article|content|entry-content', re.I))
        if content:
            for p in content.find_all(['p', 'h2', 'h3', 'h4']):
                t = p.get_text().strip()
                if len(t) > 30:
                    text += t + "\n\n"
        else:
            for p in soup.find_all('p')[:10]:
                t = p.get_text().strip()
                if len(t) > 30:
                    text += t + "\n\n"
        
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        text = clean_text(text)
        
        if len(text) > 1500:
            text = text[:1500]
            last_nl = text.rfind('\n\n')
            if last_nl > 500:
                text = text[:last_nl] + "\n\n..."
            
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
                
                short_desc = entry.get('description', '') or entry.get('summary', '')
                if not is_relevant(title, short_desc):
                    continue
                
                news_list.append({'title': title, 'link': link, 'short_desc': short_desc})
        except Exception as e:
            log(f"  ⚠ Ошибка RSS {source}: {e}")
            continue
    
    log(f"  ✓ Найдено {len(news_list)} релевантных ссылок. Парсим страницы...")
    
    result = []
    for item in news_list[:10]:
        log(f"  📄 Парсим: {item['title'][:60]}...")
        full_text, image_url = get_article_content(item['link'])
        
        if not full_text:
            continue
        if not is_relevant(item['title'], full_text):
            continue
        if is_ad_text(full_text):
            continue
            
        result.append({'title': item['title'], 'link': item['link'], 'text': full_text, 'image': image_url})
        if len(result) >= 3:
            break
        time.sleep(random.uniform(1, 2))
    
    random.shuffle(result)
    log(f"  ✓ Готово к публикации: {len(result)} статей")
    return result

def download_image(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        if len(r.content) < 10000 or len(r.content) > 10 * 1024 * 1024:
            return None
        
        ext = '.png' if 'png' in r.headers.get('content-type', '').lower() else '.jpg'
        temp_file = f"/tmp/vk_img_{int(time.time())}_{random.randint(1000, 9999)}{ext}"
        with open(temp_file, 'wb') as f:
            f.write(r.content)
        log(f"  ✓ Картинка скачана: {len(r.content) // 1024} КБ")
        return temp_file
    except Exception as e:
        log(f"  ⚠ Ошибка скачивания картинки: {e}")
        return None

def upload_photo_to_vk(vk, group_id_int, temp_file):
    """Загружает фото через upload URL для стены"""
    try:
        # Получаем URL для загрузки
        upload_server = vk.photos.getWallUploadServer(group_id=group_id_int)
        upload_url = upload_server['upload_url']
        
        log(f"  📤 Загружаю фото на сервер ВК...")
        
        # Загружаем файл
        with open(temp_file, 'rb') as f:
            files = {'photo': f}
            response = requests.post(upload_url, files=files)
        
        upload_data = response.json()
        
        if 'photo' not in upload_data or 'server' not in upload_data or 'hash' not in upload_data:
            log(f"  ⚠ Ошибка: сервер не вернул нужные данные: {upload_data}")
            return None
        
        # Сохраняем фото
        log(f"  💾 Сохраняю фото в ВК...")
        saved_photo = vk.photos.saveWallPhoto(
            group_id=group_id_int,
            photo=upload_data['photo'],
            server=upload_data['server'],
            hash=upload_data['hash']
        )
        
        if saved_photo and len(saved_photo) > 0:
            photo_id = f"photo{saved_photo[0]['owner_id']}_{saved_photo[0]['id']}"
            log(f"  ✓ Фото сохранено: {photo_id}")
            return photo_id
        else:
            log(f"  ⚠ Ошибка сохранения фото: {saved_photo}")
            return None
            
    except Exception as e:
        log(f"  ❌ Ошибка загрузки фото: {e}")
        return None

def format_post(news_item):
    title = news_item['title']
    text = news_item['text']
    link = news_item['link']
    
    emoji = "🍎" if any(k in (title + text).lower() for k in IPHONE_KEYWORDS) else "🤖"
    
    post = f"{emoji} {title}\n\n{text}\n\nИсточник: {link}\n\n#Android #iPhone #Технологии #Новости"
    return post[:3990] + "..." if len(post) > 4000 else post

def post_to_vk(news_item):
    try:
        vk_session = vk_api.VkApi(token=VK_ACCESS_TOKEN)
        vk = vk_session.get_api()
        
        post_text = format_post(news_item)
        attachment = None
        temp_file = None
        
        if news_item.get('image'):
            log(f"  🖼 Найдено фото: {news_item['image'][:80]}...")
            temp_file = download_image(news_item['image'])
            
            if temp_file:
                group_id_int = int(VK_GROUP_ID.lstrip('-'))
                attachment = upload_photo_to_vk(vk, group_id_int, temp_file)
                
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
                
                if attachment:
                    log(f"  ✅ Фото загружено успешно!")
                else:
                    log(f"  ⚠ Публикуем без фото")
        
        log(f"  📝 Публикую пост...")
        vk.wall.post(
            owner_id=int(VK_GROUP_ID),
            message=post_text,
            attachments=attachment if attachment else None,
            from_group=1,
            mark_as_ads=0
        )
        log(f"  ✅ Опубликовано: {news_item['title'][:60]}...")
        return True
    except Exception as e:
        log(f"  ❌ Ошибка: {e}")
        return False

def main():
    log("=" * 60)
    log("VK News Bot - Оптимизирован для GitHub Actions")
    log("=" * 60)
    
    if not VK_ACCESS_TOKEN or "ВСТАВЬТЕ" in VK_ACCESS_TOKEN or not VK_GROUP_ID.startswith('-'):
        log(" Ошибка настроек!")
        return
    
    try:
        vk_api.VkApi(token=VK_ACCESS_TOKEN).get_api().groups.getById(group_id=int(VK_GROUP_ID.lstrip('-')))
        log("✅ Авторизация в VK успешна")
    except Exception as e:
        log(f"❌ Ошибка авторизации: {e}")
        return
    
    news_list = fetch_news()
    if not news_list:
        log("❌ Нет новых новостей для публикации")
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
    log("✅ Готово! Скрипт завершен.")
    log(f"{'=' * 60}")

if __name__ == "__main__":
    main()
