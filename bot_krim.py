import os
import sys
import time
import random
import re
import json
import warnings
import requests
import feedparser
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

TG_BOT_TOKEN_KRIM = os.environ.get("TG_BOT_TOKEN_KRIM")
TG_CHAT_KRIM = os.environ.get("TG_CHAT_KRIM", "@kriminal_vestnik")

SEEN_FILE = "seen_titles.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

SOURCES_KRIM = [
    "https://24minsk.by/tag/pistolet/feed",
    "https://www.gs.by/rss",
    "https://www.belarus.kp.ru/online/rss/",
    "https://rg.ru/rss/rubric/criminal/",
    "https://www.mk.ru/incidents/rss.xml",
    "https://russian.rt.com/rss",
]

ZAGOLOVOK_SLOVA = [
    "убийств", "убил", "убила", "убийца", "труп", "задержан", "задержана", "задержали", "задержание",
    "арестован", "арестована", "арест", "осужден", "осуждена", "приговорен", "приговорили", "приговор", "осудили",
    "срок", "колонии", "пожизненное", "кража", "украл", "украла", "ограбление", "ограбил", "обокрали",
    "мошенник", "мошенница", "мошенничество", "мошенники", "наркотик", "наркотики", "закладка", "наркоман",
    "наркокартель", "разбой", "нападение", "напал", "напала", "избил", "избиение", "погиб", "погибла",
    "погибли", "погибший", "гибель", "ранен", "ранена", "ранены", "ранение", "пострадал", "пострадали", "жертва",
    "дтп", "авария", "сбил", "скрылся", "поджог", "поджег", "подожгла", "взрыв", "взорвал", "взорвалась",
    "изнасилован", "изнасилование", "домогательство", "похищен", "похитил", "похитила", "заложник",
    "хулиган", "хулиганство", "дебош", "драка", "вымогатель", "вымогательство", "шантаж", "коррупция",
    "взяточник", "взятка", "бандит", "банда", "преступная группа", "теракт", "террорист", "диверсия", "диверсант",
    "зарезал", "зарезан", "стрелял", "стрельба", "расстрелян", "застрелил", "застрелился", "удушил", "задушил",
    "найден труп", "обнаружен труп", "обнаружено тело", "расчленен", "изувечен", "пропал без вести", "разыскивается", "розыск",
    "ск ", "следователь", "возбуждено дело", "уголовное дело", "уголовное", "полиция", "милиция", "мвд", "омон",
    "росгвардия", "спецназ", "суд", "судья", "прокуратура", "педофил", "педофилия", "штурм", "обыск", "выемка",
    "огнестрельн", "ножевое ранение", "мафия", "картель", "самосуд", "линчевание", "экстрадиция",
    "преступник", "преступление", "правонарушение", "атака", "удар", "ликвидирован", "уничтожен",
    "подозреваемый", "обвиняемый", "расследование", "оружие", "граната", "пистолет", "боеприпасы", "боевик"
]

BLACKLIST_SLOVA = [
    "погода", "прогноз", "температура", "осадки", "ветер", "дождь", "снег",
    "спорт", "футбол", "хоккей", "баскетбол", "олимпиада", "чемпионат", "матч",
    "культура", "выставка", "концерт", "спектакль", "фильм", "кино", "премьера",
    "экономика", "курс валют", "инфляция", "ввп", "бюджет", "налоги", "пенсия",
    "политика", "выборы", "парламент", "президент", "министр", "реформа",
    "наука", "открытие", "исследование", "учёные", "экспедиция", "космос",
    "здоровье", "медицина", "болезнь", "вирус", "вакцина", "лекарство",
    "образование", "школа", "университет", "студенты", "экзамен",
    "туризм", "отпуск", "путешествие", "отель", "авиабилеты",
]

def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_seen(seen_set):
    titles_list = list(seen_set)[-1000:]
    with open(SEEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(titles_list, f, ensure_ascii=False)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def ochistit(tekst):
    if not tekst:
        return ""
    if isinstance(tekst, bytes):
        tekst = tekst.decode("utf-8", errors="replace")
    tekst = tekst.encode("utf-8", errors="replace").decode("utf-8")
    tekst = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", tekst)
    tekst = re.sub(r"[ \t]+", " ", tekst)
    tekst = re.sub(r"\n\s*\n", "\n\n", tekst)
    return tekst.strip()

def is_kriminal(zag, tekst):
    z = zag.lower()
    t = tekst.lower()
    if any(s in z or s in t for s in BLACKLIST_SLOVA):
        return False
    zag_matches = [s for s in ZAGOLOVOK_SLOVA if s in z]
    tekst_matches = [s for s in ZAGOLOVOK_SLOVA if s in t]
    if len(zag_matches) >= 1 and len(tekst_matches) >= 1:
        return True
    return False

def skachat_stranitsu(ssylka):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Referer": "https://yandex.ru/",
    }
    try:
        r = requests.get(ssylka, headers=headers, timeout=20)
        if r.status_code != 200:
            return None, [], None, r.status_code
        
        soup = BeautifulSoup(r.content, "html.parser")
        
        try:
            meta_date = soup.find("meta", property="article:published_time")
            if meta_date and meta_date.get("content"):
                date_str = meta_date["content"].split("T")[0]
                pub_date = datetime.strptime(date_str, "%Y-%m-%d")
                if (datetime.now() - pub_date).days > 14:
                    return None, [], None, 200
        except:
            pass
        
        tekst = ""
        for sel in ["article", "[class*='article']", "[class*='content']", "div[itemprop='articleBody']"]:
            try:
                els = soup.select(sel)
                if els:
                    for el in els:
                        for p in el.find_all("p"):
                            t = p.get_text().strip()
                            if len(t) > 50:
                                tekst += t + "\n\n"
                    if tekst:
                        break
            except:
                continue
        
        if not tekst:
            for p in soup.find_all("p")[:30]:
                t = p.get_text().strip()
                if len(t) > 50:
                    tekst += t + "\n\n"
        
        if len(tekst) < 200:
            return None, [], None, 403 
        
        kartinki = []
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            src = og["content"]
            if not src.startswith("http"):
                src = urljoin(ssylka, src)
            kartinki.append(src)
            
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src and len(src) > 20:
                if not src.startswith("http"):
                    src = urljoin(ssylka, src)
                if src not in kartinki:
                    kartinki.append(src)
        
        video_url = None
        ogv = soup.find("meta", property="og:video")
        if ogv and ogv.get("content") and ".mp4" in ogv["content"]:
            video_url = ogv["content"]
        if not video_url:
            vt = soup.find("video")
            if vt:
                src = vt.get("src") or (vt.find("source").get("src") if vt.find("source") else None)
                if src and ".mp4" in src:
                    video_url = src if src.startswith("http") else urljoin(ssylka, src)
        
        tekst = ochistit(tekst)
        if len(tekst) > 5000:
            tekst = tekst[:5000]
        if video_url and not video_url.startswith("http"):
            video_url = urljoin(ssylka, video_url)
        
        return tekst, kartinki, video_url, 200
    except Exception:
        return None, [], None, 0

def skachat_fayl(url, tip="foto"):
    try:
        r = requests.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=30)
        if r.status_code != 200:
            return None
        if len(r.content) < 3000:
            return None
        if len(r.content) > 50 * 1024 * 1024:
            return None
        ext = ".mp4" if tip == "video" else (".png" if "png" in r.headers.get("content-type", "").lower() else ".jpg")
        put = f"/tmp/news_{tip}{ext}"
        with open(put, "wb") as f:
            f.write(r.content)
        return put
    except Exception:
        return None

def publikovat(token, chat_id, zag, parts, ssylka, foto_path=None, video_path=None):
    base = f"https://api.telegram.org/bot{token}/"
    
    # Экранируем спецсимволы HTML, чтобы Telegram не ругался на плохой формат
    zag_safe = zag.replace("<", "&lt;").replace(">", "&gt;")
    
    caption = f"<b>{zag_safe}</b>\n\n"
    for p in parts[:4]:
        p_safe = p.replace("<", "&lt;").replace(">", "&gt;")
        caption += f"{p_safe}\n\n"
    caption += f"🔗 <a href='{ssylka}'>Читать полностью</a>"
    
    if len(caption) > 1020:
        caption = caption[:1010] + "...</a>"
    
    if video_path:
        try:
            with open(video_path, "rb") as f:
                r = requests.post(
                    base + "sendVideo",
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"video": f},
                    timeout=60,
                )
                if r.status_code != 200:
                    log(f"  ✗ Ошибка Telegram API (Видео): {r.text}")
                return r.status_code == 200
        except Exception as e:
            log(f"  ✗ Исключение при отправке видео: {e}")
            return False
    
    if foto_path:
        try:
            with open(foto_path, "rb") as f:
                r = requests.post(
                    base + "sendPhoto",
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"photo": f},
                    timeout=30,
                )
                if r.status_code != 200:
                    log(f"  ✗ Ошибка Telegram API (Фото): {r.text}")
                return r.status_code == 200
        except Exception as e:
            log(f"  ✗ Исключение при отправке фото: {e}")
            return False
    
    return False

def sobrat_novosti_kriminal(sources):
    vse_novosti = []
    zag_headers = {"User-Agent": random.choice(USER_AGENTS)}
    seen_links = set()
    
    for source in sources:
        try:
            r = requests.get(source, headers=zag_headers, timeout=15)
            if r.status_code == 200:
                feed = feedparser.parse(r.content)
                for entry in feed.entries[:30]:
                    zag = ochistit(entry.get("title", "").strip())
                    link = entry.get("link", "").strip()
                    if zag and len(zag) > 10 and link and link not in seen_links:
                        seen_links.add(link)
                        vse_novosti.append({"zagolovok": zag, "link": link})
        except:
            pass
    
    random.shuffle(vse_novosti)
    return vse_novosti[:200]

def obrabotat_kanal():
    log("=== Криминальный вестник (РБ + РФ) ===")
    if not TG_BOT_TOKEN_KRIM:
        log("  Токен не задан!")
        return False
    
    seen_titles = load_seen()
    log(f"  Загружено {len(seen_titles)} заголовков из истории.")
    
    log("  Сбор пула новостей...")
    vse_novosti = sobrat_novosti_kriminal(SOURCES_KRIM)
    log(f"  Найдено {len(vse_novosti)} уникальных ссылок. Начинаю перебор...")
    
    for i, novost in enumerate(vse_novosti, 1):
        if i % 10 == 0:
            log(f"  Проверено {i} из {len(vse_novosti)}...")
            
        if novost["zagolovok"] in seen_titles:
            continue
            
        tekst, kartinki, video, status = skachat_stranitsu(novost["link"])
        
        if not tekst:
            log(f"  [{i}] Пропуск: сайт вернул статус {status} или пустой текст.")
            continue
            
        if not is_kriminal(novost["zagolovok"], tekst):
            log(f"  [{i}] Пропуск (фильтры): {novost['zagolovok'][:60]}")
            continue
            
        parts = [p.strip() for p in tekst.split("\n\n") if len(p.strip()) > 50]
        if len(parts) < 1:
            log(f"  [{i}] Пропуск: слишком мало текста.")
            continue
            
        put = None
        tip = None
        
        if video:
            put = skachat_fayl(video, "video")
            if put:
                tip = "video"
        
        if not put and kartinki:
            for img_url in kartinki[:3]:
                put = skachat_fayl(img_url, "foto")
                if put:
                    tip = "foto"
                    break
                    
        if not put:
            log(f"  [{i}] Пропуск: не удалось скачать валидное медиа.")
            continue
            
        log(f"  [{i}] ✓ ПОДХОДИТ: {novost['zagolovok'][:50]}...")
        
        ok = publikovat(
            TG_BOT_TOKEN_KRIM, TG_CHAT_KRIM,
            ochistit(novost["zagolovok"]),
            [ochistit(x) for x in parts],
            novost["link"],
            foto_path=put if tip == "foto" else None,
            video_path=put if tip == "video" else None,
        )
        
        if ok:
            log(f"  ✅ Опубликовано: {novost['zagolovok'][:60]}")
            seen_titles.add(novost["zagolovok"])
            save_seen(seen_titles)
            return True
        else:
            # Ошибка уже залогирована внутри publikovat, просто продолжаем
            continue
                
    log("  ⚠ Перебран весь пул, подходящих новостей с медиа не найдено.")
    return False

if __name__ == "__main__":
    log("Запуск бота...")
    log("🚀 Начинаю поиск криминальных новостей...")
    
    if obrabotat_kanal():
        log("✅ Успешно опубликовано!")
    else:
        log("⚠ Не удалось опубликовать ни одной новости.")
    
    log("Готово.")
