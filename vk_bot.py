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
    "https://www.macdigger.ru/feed/",
    "https://habr.com/ru/rss/hub/android/",
    "https://habr.com/ru/rss/hub/ios/",
]

ANDROID_KEYWORDS = ["android", "андроид", "google pixel", "samsung", "xiaomi", "oneplus", "redmi", "poco", "realme", "смартфон", "galaxy", "pixel"]
IPHONE_KEYWORDS = ["iphone", "ipad", "ios", "apple", "macbook", "airpods", "macos", "айфон", "айпад", "эппл", "apple watch", "imac"]

MAX_POSTS_PER_RUN = 2
POST_DELAY = 600
SEEN_FILE = "vk_seen_links.txt"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
}
# =============================================


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_seen_links():
    """Загружает опубликованные ссылки из файла"""
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, 'r', encoding='utf-8') as f:
                return set(line.strip() for line in f if line.strip())
        except:
            return set()
    return set()


def save_seen_links(seen_links):
    """Сохраняет ссылки в файл"""
    with open(SEEN_FILE, 'w', encoding='utf-8') as f:
        for link in list(seen_links)[-500:]:
            f.write(link + '\n')


def commit_seen_file():
    """Коммитит файл vk_seen_links.txt в репозиторий"""
    try:
        # Настраиваем git
        subprocess.run(['git', 'config', '--global', 'user.email', 'bot@github.com'], check=False)
        subprocess.run(['git', 'config', '--global', 'user.name', 'VK Bot'], check=False)
        
        # Проверяем, есть ли изменения
        result = subprocess.run(['git', 'status', '--porcelain', SEEN_FILE], 
                              capture_output=True, text=True, check=False)
        
        if result.stdout.strip():  # Есть изменения
            subprocess.run(['git', 'add', SEEN_FILE], check=False)
            subprocess.run(['git', 'commit', '-m', f'Update seen links {datetime.now().strftime("%Y-%m-%d %H:%M")}'], 
                          check=False)
            subprocess.run(['git', 'push'], check=False)
            log("  ✓ Файл vk_seen_links.txt сохранён в репозиторий")
        else:
            log("  ℹ Изменений в vk_seen_links.txt нет")
    except Exception as e:
        log(f"  ⚠ Ошибка коммита: {e}")


def is_relevant(title, text):
    t = (title + " " + text).lower()
    return any(k in t for k in ANDROID_KEYWORDS) or any(k in t for k in IPHONE_KEYWORDS)


def get_article_content(url):
    """Скачивает страницу и извлекает полный текст + главное фото"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None, None
        
        soup = BeautifulSoup(r.content, 'html.parser')
        
        # 1. Ищем главное фото (og:image)
        image_url = None
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            image_url = og['content']
        
        # Если нет og:image, ищем первую большую картинку в article
        if not image_url:
            article = soup.find('article') or soup.find('div', class_=re.compile(r'article|content|post', re.I))
            if article:
                img = article.find('img', src=True)
                if img:
                    src = img['src']
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = url.split('/')[0] + '//' + url.split('/')[2] + src
                    if len(src) > 10:
                        image_url = src
        
        # 2. Извлекаем текст статьи
        text = ""
        
        # Пробуем найти основной контент
        content = None
        for selector in [
            {'name': 'article'},
            {'class': re.compile(r'article|content|post__text|entry-content', re.I)},
            {'itemprop': 'articleBody'},
        ]:
            content = soup.find(**selector)
            if content:
                break
        
        if content:
            # Берём все параграфы
            for p in content.find_all(['p', 'h2', 'h3', 'h4']):
                t = p.get_text().strip()
                if len(t) > 30:
                    text += t + "\n\n"
        else:
            # Фолбэк: берём первые 10 параграфов со страницы
            for p in soup.find_all('p')[:10]:
                t = p.get_text().strip()
                if len(t) > 30:
                    text += t + "\n\n"
        
        # Очищаем текст
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        
        # Обрезаем до разумного размера
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
    """Собираем новости из RSS, затем парсим каждую страницу"""
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
            for entry in feed.entries[:8]:
                link = entry.get('link', '').strip()
                
                # ПРОВЕРКА НА ДУБЛИКАТ
                if not link or link in seen_links:
                    continue
                
                title = entry.get('title', '').strip()
                if not title or len(title) < 10:
                    continue
                
                # Проверяем релевантность
                short_desc = entry.get('description', '') or entry.get('summary', '')
                if not is_relevant(title, short_desc):
                    continue
                
                news_list.append({
                    'title': title,
                    'link': link,
                    'short_desc': short_desc
                })
        except Exception as e:
            log(f"  ⚠ Ошибка RSS {source}: {e}")
            continue
    
    log(f"  ✓ Найдено {len(news_list)} релевантных ссылок. Парсим страницы...")
    
    # Парсим каждую страницу для получения полного текста и фото
    result = []
    for item in news_list[:15]:
        log(f"  📄 Парсим: {item['title'][:60]}...")
        full_text, image_url = get_article_content(item['link'])
        
        if not full_text:
            log(f"  ⚠ Не удалось получить текст, пропускаем")
            continue
        
        if not is_relevant(item['title'], full_text):
            log(f"  ⚠ Статья не по теме, пропускаем")
            continue
        
        result.append({
            'title': item['title'],
            'link': item['link'],
            'text': full_text,
            'image': image_url
        })
        
        if len(result) >= 5:
            break
        
        time.sleep(random.uniform(1, 3))
    
    random.shuffle(result)
    log(f"  ✓ Готово к публикации: {len(result)} статей")
    return result


def download_image(url):
    """Скачивает картинку"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        
        if len(r.content) < 10000:
            log(f"  ⚠ Картинка слишком маленькая ({len(r.content)} байт)")
            return None
        
        if len(r.content) > 10 * 1024 * 1024:
            return None
        
        content_type = r.headers.get('content-type', '').lower()
        if 'png' in content_type:
            ext = '.png'
        elif 'gif' in content_type:
            return None
        else:
            ext = '.jpg'
        
        temp_file = f"/tmp/vk_img_{int(time.time())}_{random.randint(1000, 9999)}{ext}"
        with open(temp_file, 'wb') as f:
            f.write(r.content)
        
        log(f"  ✓ Картинка скачана: {len(r.content) // 1024} КБ")
        return temp_file
        
    except Exception as e:
        log(f"  ⚠ Ошибка скачивания картинки: {e}")
        return None


def upload_photo(vk, group_id_clean, temp_file):
    """Загружает фото на сервер ВК"""
    try:
        upload_url = vk.photos.getWallUploadURL(group_id=group_id_clean)
        
        with open(temp_file, 'rb') as f:
            upload_response = requests.post(upload_url['upload_url'], files={'photo': f})
        
        upload_data = upload_response.json()
        
        if 'photo' not in upload_data:
            log(f"  ⚠ Ошибка загрузки: {upload_data}")
            return None
        
        saved = vk.photos.saveWallPhoto(
            group_id=group_id_clean,
            photo=upload_data['photo'],
            server=upload_data['server'],
            hash=upload_data['hash']
        )
        
        if saved and len(saved) > 0:
            return f"photo{saved[0]['owner_id']}_{saved[0]['id']}"
        
    except Exception as e:
        log(f"  ⚠ Ошибка загрузки фото в ВК: {e}")
    return None


def format_post(news_item):
    """Форматирует красивый пост"""
    title = news_item['title']
    text = news_item['text']
    link = news_item['link']
    
    t = (title + " " + text).lower()
    if any(k in t for k in IPHONE_KEYWORDS):
        emoji = "🍎"
    else:
        emoji = "🤖"
    
    post = f"{emoji} <b>{title}</b>\n\n"
    post += f"{text}\n\n"
    post += f"🔗 <a href=\"{link}\">Читать полностью</a>\n\n"
    post += f"#Android #iPhone #Технологии #Новости"
    
    if len(post) > 4000:
        post = post[:3990] + "..."
    
    return post


def post_to_vk(news_item):
    """Публикует пост в ВК"""
    try:
        vk_session = vk_api.VkApi(token=VK_ACCESS_TOKEN)
        vk = vk_session.get_api()
        
        post_text = format_post(news_item)
        
        attachment = None
        temp_file = None
        
        if news_item.get('image'):
            log(f"  🖼 Загружаю фото: {news_item['image'][:60]}...")
            temp_file = download_image(news_item['image'])
            
            if temp_file:
                group_id_clean = VK_GROUP_ID.lstrip('-')
                attachment = upload_photo(vk, group_id_clean, temp_file)
                
                try:
                    os.remove(temp_file)
                except:
                    pass
                
                if attachment:
                    log(f"  ✓ Фото загружено: {attachment}")
                else:
                    log(f"  ⚠ Фото не загружено, публикуем без него")
        
        vk.wall.post(
            owner_id=int(VK_GROUP_ID),
            message=post_text,
            attachments=attachment if attachment else None,
            from_group=1,
            mark_as_ads=0
        )
        
        log(f"  ✅ Опубликовано: {news_item['title'][:60]}...")
        return True
        
    except vk_api.exceptions.ApiError as e:
        log(f"  ❌ Ошибка API ВК: {e}")
        return False
    except Exception as e:
        log(f"  ❌ Ошибка: {e}")
        return False


def main():
    log("=" * 60)
    log("VK News Bot - Автопостинг Android/iPhone новостей")
    log("=" * 60)
    
    if not VK_ACCESS_TOKEN or "ВСТАВЬТЕ" in VK_ACCESS_TOKEN:
        log("❌ Ошибка: VK_ACCESS_TOKEN не найден!")
        return
    
    if not VK_GROUP_ID.startswith('-'):
        log("❌ Ошибка: VK_GROUP_ID должен начинаться с минуса!")
        return
    
    try:
        vk_session = vk_api.VkApi(token=VK_ACCESS_TOKEN)
        api = vk_session.get_api()
        api.groups.getById(group_id=VK_GROUP_ID.lstrip('-'))
        log("✅ Авторизация в VK успешна")
    except Exception as e:
        log(f"❌ Ошибка авторизации: {e}")
        return
    
    news_list = fetch_news()
    
    if not news_list:
        log("❌ Нет новых новостей для публикации")
        return
    
    published_count = 0
    seen_links = load_seen_links()
    
    for news in news_list[:MAX_POSTS_PER_RUN]:
        log(f"\n[{published_count + 1}/{MAX_POSTS_PER_RUN}] Публикую...")
        
        if post_to_vk(news):
            published_count += 1
            seen_links.add(news['link'])
            save_seen_links(seen_links)
            
            # СОХРАНЯЕМ ФАЙЛ В РЕПОЗИТОРИЙ
            commit_seen_file()
            
            if published_count < MAX_POSTS_PER_RUN:
                log(f"⏳ Пауза {POST_DELAY} секунд...")
                time.sleep(POST_DELAY)
        else:
            log("Пропускаю из-за ошибки")
            time.sleep(60)
    
    log(f"\n{'=' * 60}")
    log(f"✅ Готово! Опубликовано: {published_count} из {MAX_POSTS_PER_RUN}")
    log(f"{'=' * 60}")


if __name__ == "__main__":
    main()
