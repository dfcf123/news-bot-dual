import os
import re
import time
import random
import requests
import feedparser
from datetime import datetime
from bs4 import BeautifulSoup
import vk_api

# Читаем настройки из секретов GitHub
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

ANDROID_KEYWORDS = ["android", "андроид", "google pixel", "samsung", "xiaomi", "oneplus", "redmi", "poco", "realme", "смартфон"]
IPHONE_KEYWORDS = ["iphone", "ipad", "ios", "apple", "macbook", "airpods", "macos", "айфон", "айпад", "эппл"]

MAX_POSTS_PER_RUN = 3
POST_DELAY = 600
SEEN_FILE = "vk_seen_links.txt"

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

def is_relevant_news(title, description):
    text = (title + " " + description).lower()
    return any(kw.lower() in text for kw in ANDROID_KEYWORDS) or any(kw.lower() in text for kw in IPHONE_KEYWORDS)

def fetch_news():
    news_list = []
    seen_links = load_seen_links()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Начинаю сбор новостей...")
    
    for source in NEWS_SOURCES:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(source, headers=headers, timeout=15)
            if response.status_code != 200:
                continue
                
            feed = feedparser.parse(response.content)
            for entry in feed.entries[:10]:
                link = entry.get('link', '').strip()
                if link in seen_links:
                    continue
                
                title = entry.get('title', '').strip()
                description = entry.get('description', '') or entry.get('summary', '')
                
                if not title or len(title) < 10 or not is_relevant_news(title, description):
                    continue
                
                image_url = None
                if hasattr(entry, 'media_content') and entry.media_content:
                    for media in entry.media_content:
                        if 'image' in media.get('type', '') or media.get('medium') == 'image':
                            image_url = media.get('url')
                            break
                
                clean_desc = BeautifulSoup(description, 'html.parser').get_text().strip()
                if len(clean_desc) > 400:
                    clean_desc = clean_desc[:400] + "..."
                
                news_list.append({'title': title, 'link': link, 'description': clean_desc, 'image': image_url})
        except Exception as e:
            print(f"  ⚠ Ошибка парсинга {source}: {e}")
            continue
    
    random.shuffle(news_list)
    print(f"  ✓ Найдено {len(news_list)} подходящих новостей")
    return news_list

def download_image(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200 and len(response.content) > 5000:
            temp_file = f"/tmp/vk_img_{int(time.time())}.jpg"
            with open(temp_file, 'wb') as f:
                f.write(response.content)
            return temp_file
    except:
        pass
    return None

def post_to_vk(news_item):
    try:
        vk_session = vk_api.VkApi(token=VK_ACCESS_TOKEN)
        vk = vk_session.get_api()
        
        text = f"📱 {news_item['title']}\n\n{news_item['description']}\n\n🔗 Источник: {news_item['link']}"
        if len(text) > 60000:
            text = text[:59997] + "..."
        
        attachment = None
        temp_file = None
        
        if news_item.get('image'):
            temp_file = download_image(news_item['image'])
            if temp_file:
                try:
                    group_id_clean = VK_GROUP_ID.lstrip('-')
                    upload_url = vk.photos.getWallUploadURL(group_id=group_id_clean)
                    with open(temp_file, 'rb') as f:
                        upload_response = requests.post(upload_url['upload_url'], files={'photo': f})
                    
                    upload_data = upload_response.json()
                    if 'photo' in upload_data:
                        saved_photo = vk.photos.saveWallPhoto(
                            group_id=group_id_clean,
                            photo=upload_data['photo'],
                            server=upload_data['server'],
                            hash=upload_data['hash']
                        )
                        if saved_photo and len(saved_photo) > 0:
                            attachment = f"photo{saved_photo[0]['owner_id']}_{saved_photo[0]['id']}"
                except Exception as e:
                    print(f"  ⚠ Ошибка загрузки фото: {e}")
                finally:
                    try: os.remove(temp_file)
                    except: pass
        
        vk.wall.post(
            owner_id=int(VK_GROUP_ID),
            message=text,
            attachments=attachment if attachment else None,
            from_group=1,
            mark_as_ads=0
        )
        print(f"  ✅ Опубликовано: {news_item['title'][:50]}...")
        return True
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        return False

def main():
    print("=" * 50)
    if not VK_ACCESS_TOKEN or "ВСТАВЬТЕ" in VK_ACCESS_TOKEN:
        print("❌ Ошибка: VK_ACCESS_TOKEN не найден в секретах GitHub!")
        return
    if not VK_GROUP_ID.startswith('-'):
        print("❌ Ошибка: VK_GROUP_ID должен начинаться с минуса!")
        return
    
    try:
        vk_session = vk_api.VkApi(token=VK_ACCESS_TOKEN)
        vk_session.get_api().groups.getById(group_id=VK_GROUP_ID.lstrip('-'))
        print("✅ Авторизация в VK успешна")
    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        return
    
    news_list = fetch_news()
    if not news_list:
        print("Нет новых новостей для публикации")
        return
    
    published_count = 0
    seen_links = load_seen_links()
    
    for news in news_list[:MAX_POSTS_PER_RUN]:
        print(f"\n[{published_count + 1}/{MAX_POSTS_PER_RUN}] Публикую...")
        if post_to_vk(news):
            published_count += 1
            seen_links.add(news['link'])
            save_seen_links(seen_links)
            if published_count < MAX_POSTS_PER_RUN:
                print(f"⏳ Пауза {POST_DELAY} сек...")
                time.sleep(POST_DELAY)
        else:
            time.sleep(60)
            
    print(f"\n✅ Готово! Опубликовано: {published_count}")

if __name__ == "__main__":
    main()
