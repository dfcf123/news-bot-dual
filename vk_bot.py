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
from PIL import Image, ImageDraw, ImageFont
import io

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

# Градиенты для карточек (начальный и конечный цвет)
GRADIENTS = [
    ((66, 134, 244), (119, 94, 200)),    # Синий → Фиолетовый
    ((233, 69, 96), (225, 48, 108)),     # Красный → Розовый
    ((0, 188, 212), (0, 150, 136)),      # Голубой → Бирюзовый
    ((255, 152, 0), (255, 87, 34)),      # Оранжевый → Красный
    ((76, 175, 80), (56, 142, 60)),      # Зеленый → Темно-зеленый
    ((156, 39, 176), (103, 58, 183)),    # Фиолетовый → Индиго
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

def create_gradient_card(title, is_iphone=False):
    """Создает красивую карточку с градиентом и заголовком"""
    try:
        # Параметры карточки
        width, height = 1200, 630
        padding = 60
        
        # Выбираем случайный градиент
        gradient = random.choice(GRADIENTS)
        color_start = gradient[0]
        color_end = gradient[1]
        
        # Создаем изображение с градиентом
        img = Image.new('RGB', (width, height), color_start)
        draw = ImageDraw.Draw(img)
        
        # Рисуем градиент
        for y in range(height):
            r = int(color_start[0] + (color_end[0] - color_start[0]) * y / height)
            g = int(color_start[1] + (color_end[1] - color_start[1]) * y / height)
            b = int(color_start[2] + (color_end[2] - color_start[2]) * y / height)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        
        # Добавляем полупрозрачный оверлей
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 40))
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(img)
        
        # Эмодзи
        emoji = "🍎" if is_iphone else "🤖"
        
        # Пытаемся загрузить шрифты (системные)
        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56)
            font_emoji = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 72)
            font_source = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        except:
            # Fallback на стандартный шрифт
            font_title = ImageFont.load_default()
            font_emoji = ImageFont.load_default()
            font_source = ImageFont.load_default()
        
        # Рисуем эмодзи
        draw.text((padding, padding), emoji, fill=(255, 255, 255), font=font_emoji)
        
        # Обрезаем заголовок если слишком длинный
        max_chars = 70
        if len(title) > max_chars:
            title = title[:max_chars-3] + "..."
        
        # Рисуем заголовок (перенос строк)
        words = title.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + " " + word if current_line else word
            # Примерная проверка длины
            if len(test_line) < 60:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        
        # Рисуем строки заголовка
        y_offset = padding + 100
        for line in lines[:3]:  # Максимум 3 строки
            draw.text((padding, y_offset), line, fill=(255, 255, 255), font=font_title)
            y_offset += 70
        
        # Добавляем логотип/подпись внизу
        source_text = "Лучшее на ANDROID и IPHONE"
        draw.text((padding, height - 80), source_text, fill=(255, 255, 255, 180), font=font_source)
        
        # Сохраняем во временный файл
        temp_file = f"/tmp/vk_card_{int(time.time())}_{random.randint(1000, 9999)}.png"
        img.save(temp_file, 'PNG', quality=95)
        
        log(f"   Создана карточка: {width}x{height}px")
        return temp_file
        
    except Exception as e:
        log(f"  ⚠ Ошибка создания карточки: {e}")
        return None

def extract_all_images(soup, url):
    """Извлекает ВСЕ возможные источники картинок со страницы"""
    images = []
    
    # 1. Open Graph (og:image)
    og = soup.find('meta', property='og:image')
    if og and og.get('content'):
        images.append({'url': og['content'], 'source': 'og:image', 'priority': 1})
    
    # 2. Twitter Card
    tw = soup.find('meta', attrs={'name': 'twitter:image'})
    if tw and tw.get('content'):
        images.append({'url': tw['content'], 'source': 'twitter:image', 'priority': 1})
    
    # 3. JSON-LD (Schema.org)
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if 'image' in data:
                if isinstance(data['image'], str):
                    images.append({'url': data['image'], 'source': 'json-ld', 'priority': 2})
                elif isinstance(data['image'], list) and len(data['image']) > 0:
                    images.append({'url': data['image'][0], 'source': 'json-ld', 'priority': 2})
                elif isinstance(data['image'], dict) and 'url' in data['image']:
                    images.append({'url': data['image']['url'], 'source': 'json-ld', 'priority': 2})
        except:
            pass
    
    # 4. Microdata (itemprop="image")
    for img in soup.find_all(attrs={'itemprop': 'image'}):
        src = img.get('content') or img.get('src')
        if src:
            images.append({'url': src, 'source': 'microdata', 'priority': 2})
    
    # 5. Первая большая картинка в article
    article = soup.find('article') or soup.find('div', class_=re.compile(r'article|content|post', re.I))
    if article:
        for img in article.find_all('img', src=True):
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                width = img.get('width') or img.get('data-width', '0')
                height = img.get('height') or img.get('data-height', '0')
                try:
                    if int(width) > 200 and int(height) > 200:
                        images.append({'url': src, 'source': 'article-img', 'priority': 3})
                except:
                    if not any(x in src.lower() for x in ['logo', 'icon', 'avatar', 'sprite', 'thumb']):
                        images.append({'url': src, 'source': 'article-img', 'priority': 3})
    
    # 6. Все картинки с class содержащим 'main', 'featured', 'hero'
    for img in soup.find_all('img', class_=re.compile(r'main|featured|hero|primary', re.I)):
        src = img.get('src') or img.get('data-src')
        if src:
            images.append({'url': src, 'source': 'class-match', 'priority': 2})
    
    # Сортируем по приоритету
    images.sort(key=lambda x: x['priority'])
    
    cleaned = []
    for img in images:
        url_clean = img['url']
        if url_clean.startswith('//'):
            url_clean = 'https:' + url_clean
        elif url_clean.startswith('/'):
            url_clean = url.split('/')[0] + '//' + url.split('/')[2] + url_clean
        if len(url_clean) > 10 and url_clean not in cleaned:
            cleaned.append(url_clean)
    
    return cleaned

def get_article_content(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None, None
        
        soup = BeautifulSoup(r.content, 'html.parser')
        all_images = extract_all_images(soup, url)
        log(f"   Найдено картинок: {len(all_images)}")
        
        # Извлекаем текст
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
        
        main_image = all_images[0] if all_images else None
        
        return text if len(text) > 100 else None, main_image
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
        log(f"  ⬇️ Скачиваю: {url[:80]}...")
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            log(f"  ⚠ Статус {r.status_code}")
            return None
        if len(r.content) < 10000:
            log(f"  ⚠ Картинка слишком маленькая ({len(r.content)} байт)")
            return None
        if len(r.content) > 10 * 1024 * 1024:
            log(f"  ⚠ Картинка слишком большая")
            return None
        
        ext = '.png' if 'png' in r.headers.get('content-type', '').lower() else '.jpg'
        temp_file = f"/tmp/vk_img_{int(time.time())}_{random.randint(1000, 9999)}{ext}"
        with open(temp_file, 'wb') as f:
            f.write(r.content)
        log(f"  ✓ Скачано: {len(r.content) // 1024} КБ")
        return temp_file
    except Exception as e:
        log(f"  ⚠ Ошибка скачивания: {e}")
        return None

def upload_photo_to_vk(vk, group_id_int, temp_file):
    try:
        upload_server = vk.photos.getWallUploadServer(group_id=group_id_int)
        upload_url = upload_server['upload_url']
        
        log(f"  📤 Загружаю на сервер ВК...")
        
        with open(temp_file, 'rb') as f:
            files = {'photo': f}
            response = requests.post(upload_url, files=files)
        
        upload_data = response.json()
        
        if 'photo' not in upload_data or 'server' not in upload_data or 'hash' not in upload_data:
            log(f"   Ошибка: {upload_data}")
            return None
        
        log(f"  💾 Сохраняю фото...")
        saved_photo = vk.photos.saveWallPhoto(
            group_id=group_id_int,
            photo=upload_data['photo'],
            server=upload_data['server'],
            hash=upload_data['hash']
        )
        
        if saved_photo and len(saved_photo) > 0:
            photo_id = f"photo{saved_photo[0]['owner_id']}_{saved_photo[0]['id']}"
            log(f"  ✓ Фото: {photo_id}")
            return photo_id
        else:
            log(f"  ⚠ Ошибка сохранения")
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
        
        is_iphone = any(k in (news_item['title'] + news_item['text']).lower() for k in IPHONE_KEYWORDS)
        
        if news_item.get('image'):
            log(f"  🖼 Нашёл фото: {news_item['image'][:80]}...")
            temp_file = download_image(news_item['image'])
            
            if temp_file:
                group_id_int = int(VK_GROUP_ID.lstrip('-'))
                attachment = upload_photo_to_vk(vk, group_id_int, temp_file)
                
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
                
                if attachment:
                    log(f"  ✅ Фото загружено!")
                else:
                    log(f"   Создаю текстовую карточку...")
                    temp_file = create_gradient_card(news_item['title'], is_iphone)
                    if temp_file:
                        attachment = upload_photo_to_vk(vk, group_id_int, temp_file)
                        try:
                            os.remove(temp_file)
                        except:
                            pass
            else:
                log(f"  ⚠ Не удалось скачать фото. Создаю карточку...")
                temp_file = create_gradient_card(news_item['title'], is_iphone)
                if temp_file:
                    group_id_int = int(VK_GROUP_ID.lstrip('-'))
                    attachment = upload_photo_to_vk(vk, group_id_int, temp_file)
                    try:
                        os.remove(temp_file)
                    except:
                        pass
        else:
            log(f"   Фото не найдено. Создаю текстовую карточку...")
            temp_file = create_gradient_card(news_item['title'], is_iphone)
            if temp_file:
                group_id_int = int(VK_GROUP_ID.lstrip('-'))
                attachment = upload_photo_to_vk(vk, group_id_int, temp_file)
                try:
                    os.remove(temp_file)
                except:
                    pass
        
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
    log("VK News Bot - с генерацией карточек")
    log("=" * 60)
    
    if not VK_ACCESS_TOKEN or "ВСТАВЬТЕ" in VK_ACCESS_TOKEN or not VK_GROUP_ID.startswith('-'):
        log("❌ Ошибка настроек!")
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
