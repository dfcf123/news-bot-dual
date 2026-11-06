import os
import sys
import time
import random
import re
import requests
import feedparser
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

TG_BOT_TOKEN_WORLD = os.environ.get("TG_BOT_TOKEN_WORLD")
TG_CHAT_WORLD = os.environ.get("TG_CHAT_WORLD", "@dfcf1980")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# ============================================================
# ИСТОЧНИКИ: БЕЛАРУСЬ + МИР (ТОЛЬКО НА РУССКОМ)
# ============================================================
RSS_WORLD = [
    # --- БЕЛОРУССКИЕ ИСТОЧНИКИ (основа) ---
    "https://www.sb.by/rss/",
    "https://news.onliner.by/feed",
    "https://www.belta.by/rss/",
    "https://naviny.by/rss/",
    "https://nn.by/rss",
    "https://zviazda.by/rss",
    "https://1tv.by/rss",
    "https://ont.by/rss",
    "https://stv.by/rss",
    "https://mir24.tv/belarus/rss",
    "https://belteleradio.by/rss",
    
    # --- МИРОВЫЕ НОВОСТИ НА РУССКОМ ---
    # РИА Новости (глобальные новости) [citation:2][citation:14]
    "https://ria.ru/export/rss2/archive/index.xml",
    # ТАСС (мировые новости) [citation:3][citation:8]
    "https://tass.ru/rss/v2.xml",
    # Lenta.ru (общие новости)
    "https://lenta.ru/rss",
    # РБК (мировые новости)
    "https://news.rbc.ru/rbc_news.rss",
    # ИноСМИ (переводы мировых СМИ на русский) [citation:2]
    "https://inosmi.ru/rss",
    # RT на русском (мировые новости)
    "https://russian.rt.com/rss",
    # Sputnik Беларусь (Беларусь + мир) [citation:5]
    "https://sputnik.by/export/rss2/index.xml",
    # АиФ (общие новости) [citation:13]
    "https://aif.ru/rss/news.php",
]

# Чёрный список: только погода и явно нерелевантное
BLACKLIST_SLOVA = [
    "погода", "прогноз", "температура", "осадки", "ветер", "дождь", "снег", "метель",
    "циклон", "антициклон", "атмосферный фронт", "гроза", "град", "туман", "гололёд",
]

seen_titles = set()


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


def is_russian(text):
    """Проверяет наличие кириллицы."""
    return bool(re.search('[а-яА-ЯёЁ]', text))


def is_weather(zag):
    """Проверяет, что новость о погоде (только по заголовку)."""
    return any(s in zag.lower() for s in BLACKLIST_SLOVA)


def skachat_stranitsu(ssylka):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": "https://www.google.com/",
    }
    try:
        r = requests.get(ssylka, headers=headers, timeout=20)
        r.encoding = "utf-8"
        if r.status_code != 200:
            return None, None, None
        
        soup = BeautifulSoup(r.content, "html.parser")
        
        # Проверка даты (не старше 14 дней)
        try:
            meta_date = soup.find("meta", property="article:published_time")
            if meta_date and meta_date.get("content"):
                date_str = meta_date["content"].split("T")[0]
                pub_date = datetime.strptime(date_str, "%Y-%m-%d")
                if (datetime.now() - pub_date).days > 14:
                    return None, None, None
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
        
        kartinka = None
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            kartinka = og["content"]
        if not kartinka:
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src")
                if src and len(src) > 20:
                    if not src.startswith("http"):
                        src = urljoin(ssylka, src)
                    kartinka = src
                    break
        
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
        if kartinka and not kartinka.startswith("http"):
            kartinka = urljoin(ssylka, kartinka)
        if video_url and not video_url.startswith("http"):
            video_url = urljoin(ssylka, video_url)
        
        return tekst, kartinka, video_url
    except Exception as e:
        return None, None, None


def skachat_fayl(url, tip="foto"):
    try:
        r = requests.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=30)
        if r.status_code != 200:
            return None
        if len(r.content) > 50 * 1024 * 1024:
            return None
        
        if tip == "video":
            ext = ".mp4"
        else:
            ct = r.headers.get("content-type", "")
            ext = ".png" if "png" in ct else ".jpg"
        
        put = f"/tmp/news_{tip}{ext}"
        with open(put, "wb") as f:
            f.write(r.content)
        return put
    except:
        return None


def publikovat(token, chat_id, zag, parts, ssylka, foto_path=None, video_path=None):
    base = f"https://api.telegram.org/bot{token}/"
    
    # Формируем caption без поломки HTML
    caption = f"<b>{zag}</b>\n\n"
    tail = f"🔗 <a href='{ssylka}'>Читать полностью</a>"
    
    for p in parts[:4]:
        candidate = caption + p + "\n\n" + tail
        if len(candidate) > 1020:
            break
        caption += p + "\n\n"
    
    caption += tail
    
    if video_path:
        try:
            with open(video_path, "rb") as f:
                r = requests.post(
                    base + "sendVideo",
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"video": f},
                    timeout=60,
                )
            return r.status_code == 200
        except:
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
            return r.status_code == 200
        except:
            return False
    
    return False


def obrabotat_kanal():
    log("=== Новости Беларуси и мира ===")
    if not TG_BOT_TOKEN_WORLD:
        log("  Токен не задан!")
        return False
    
    vse = []
    zag_headers = {"User-Agent": random.choice(USER_AGENTS)}
    
    for url in RSS_WORLD:
        try:
            r = requests.get(url, headers=zag_headers, timeout=15)
            if r.status_code != 200:
                log(f"  RSS {url[:35]}... — ошибка {r.status_code}")
                continue
            
            # ВАЖНО: feedparser работает с bytes, не с text
            feed = feedparser.parse(r.content)
            
            for entry in feed.entries[:30]:
                zag = ochistit(entry.get("title", "").strip())
                link = entry.get("link", "").strip()
                
                # Проверяем дату из RSS до скачивания страницы
                if "published_parsed" in entry:
                    try:
                        pub_date = datetime(*entry.published_parsed[:6])
                        if (datetime.now() - pub_date).days > 14:
                            continue
                    except:
                        pass
                
                if zag and len(zag) > 10 and link:
                    vse.append({"zagolovok": zag, "link": link})
        except Exception as e:
            log(f"  Ошибка RSS {url[:35]}...: {str(e)[:60]}")
    
    log(f"  Найдено {len(vse)} новостей.")
    if not vse:
        return False
    
    random.shuffle(vse)
    
    for novost in vse:
        # Только русский язык
        if not is_russian(novost["zagolovok"]):
            continue
        
        # Не погода
        if is_weather(novost["zagolovok"]):
            continue
        
        tekst, kart, video = skachat_stranitsu(novost["link"])
        if not tekst:
            continue
        
        if not is_russian(tekst):
            continue
        
        parts = [p.strip() for p in tekst.split("\n\n") if len(p.strip()) > 50]
        if len(parts) < 2:
            continue
        
        # МЕДИА ОБЯЗАТЕЛЬНО
        if not kart and not video:
            continue
        
        log(f"  ✓ Найдена: {novost['zagolovok'][:60]}...")
        seen_titles.add(novost["zagolovok"])
        
        put = None
        tip = None
        if video:
            put = skachat_fayl(video, "video")
            tip = "video"
        if not put and kart:
            put = skachat_fayl(kart, "foto")
            tip = "foto"
        
        if put:
            ok = publikovat(
                TG_BOT_TOKEN_WORLD, TG_CHAT_WORLD,
                ochistit(novost["zagolovok"]),
                [ochistit(x) for x in parts],
                novost["link"],
                foto_path=put if tip == "foto" else None,
                video_path=put if tip == "video" else None,
            )
            if ok:
                log(f"  ✅ Опубликовано!")
                return True
            else:
                log(f"  ✗ Ошибка публикации, ищу следующую...")
                continue
    
    log("  ⚠ Не подошло.")
    return False


if __name__ == "__main__":
    log("Запуск бота...")
    log("🚀 Начинаю поиск новостей Беларуси и мира...")
    
    if obrabotat_kanal():
        log("✅ Успешно опубликовано!")
    else:
        log("⚠ Не удалось опубликовать ни одной новости.")
    
    log("Готово.")
