import os
import time
import random
import re
import requests
import feedparser
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# НАСТРОЙКИ
TG_BOT_TOKEN_SMART = os.environ.get("TG_BOT_TOKEN_SMART")
TG_CHAT_SMART = os.environ.get("TG_CHAT_SMART", "@smartpravda_news")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# РАБОЧИЕ РУССКОЯЗЫЧНЫЕ ИСТОЧНИКИ
RSS_SMART = [
    "https://www.ixbt.com/rss/allnews.xml",
    "https://habr.com/ru/rss/hub/smartphones/",
    "https://www.ferra.ru/rss.xml",
    "https://www.3dnews.ru/rss.xml",
    "https://appleinsider.ru/feed/",
    "https://www.mobile-review.com/news/rss.xml",
    "https://vc.ru/rss",
    "https://tech.onliner.by/feed",
    "https://itc.ua/feed/",
]

KEYWORDS = [
    "iphone", "айфон", "apple", "самсунг", "samsung", "xiaomi", "сяоми", "редми", "redmi",
    "huawei", "хуавей", "honor", "онор", "oneplus", "ванплас", "google pixel", "пиксель",
    "смартфон", "телефон", "гаджет", "android", "андроид", "ios", "айос",
    "процессор", "чип", "snapdragon", "экран", "дисплей", "камера", "батарея",
    "аккумулятор", "зарядка", "5g", "флагман", "бюджетник", "обзор", "тест", "сравнение",
    "анонс", "презентация", "выход", "релиз", "цена", "стоимость", "скидка", "распродажа",
    "прошивка", "обновление", "android 14", "android 15", "ios 17", "ios 18",
    "macbook", "макбук", "ipad", "айпад", "watch", "часы", "airpods", "наушники",
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


def is_smart(zag, tekst):
    """Проверяет русский язык и ключевые слова."""
    if not is_russian(zag) and not is_russian(tekst):
        return False
    z = zag.lower()
    t = tekst.lower()
    return any(s in z or s in t for s in KEYWORDS)


def skachat_stranitsu(ssylka):
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        r = requests.get(ssylka, headers=headers, timeout=20)
        r.encoding = "utf-8"
        if r.status_code != 200:
            return None, None
        
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Проверка даты (не старше 14 дней)
        try:
            meta_date = soup.find("meta", property="article:published_time")
            if meta_date and meta_date.get("content"):
                date_str = meta_date["content"].split("T")[0]
                pub_date = datetime.strptime(date_str, "%Y-%m-%d")
                if (datetime.now() - pub_date).days > 14:
                    return None, None
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
        
        tekst = ochistit(tekst)
        if len(tekst) > 5000:
            tekst = tekst[:5000]
        if kartinka and not kartinka.startswith("http"):
            kartinka = urljoin(ssylka, kartinka)
        
        return tekst, kartinka
    except:
        return None, None


def skachat_fayl(url):
    try:
        r = requests.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=30)
        if r.status_code != 200 or len(r.content) > 50 * 1024 * 1024:
            return None
        ext = ".png" if "png" in r.headers.get("content-type", "") else ".jpg"
        put = f"/tmp/smart_news{ext}"
        with open(put, "wb") as f:
            f.write(r.content)
        return put
    except:
        return None


def publikovat(token, chat_id, zag, parts, ssylka, foto_path):
    base = f"https://api.telegram.org/bot{token}/"
    
    caption = f"<b>{zag}</b>\n\n"
    for p in parts[:4]:
        caption += f"{p}\n\n"
    caption += f"🔗 <a href='{ssylka}'>Читать полностью</a>"
    
    if len(caption) > 1020:
        caption = caption[:1010] + "...</a>"
    
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


def obrabotat():
    log("=== Смарт-Правда ===")
    if not TG_BOT_TOKEN_SMART:
        log("  Токен не задан!")
        return False
    
    vse = []
    zag_headers = {"User-Agent": random.choice(USER_AGENTS)}
    
    for url in RSS_SMART:
        try:
            r = requests.get(url, headers=zag_headers, timeout=15)
            if r.status_code != 200:
                log(f"  RSS {url[:30]}... — ошибка {r.status_code}")
                continue
            feed = feedparser.parse(r.text)
            for entry in feed.entries[:30]:
                zag = ochistit(entry.get("title", "").strip())
                link = entry.get("link", "").strip()
                if zag and len(zag) > 10 and link:
                    vse.append({"zagolovok": zag, "link": link})
        except Exception as e:
            log(f"  Ошибка RSS {url[:30]}...: {str(e)[:50]}")
    
    log(f"  Найдено {len(vse)} новостей.")
    if not vse:
        return False
    
    random.shuffle(vse)
    
    for novost in vse:
        tekst, kart = skachat_stranitsu(novost["link"])
        if not tekst:
            continue
        
        if not is_russian(novost["zagolovok"]) and not is_russian(tekst):
            continue
        
        if not is_smart(novost["zagolovok"], tekst):
            continue
        
        parts = [p.strip() for p in tekst.split("\n\n") if len(p.strip()) > 50]
        if len(parts) < 2:
            continue
        
        if not kart:
            continue
        
        log(f"  ✓ Найдена: {novost['zagolovok'][:50]}...")
        seen_titles.add(novost["zagolovok"])
        
        put = skachat_fayl(kart)
        if put:
            ok = publikovat(
                TG_BOT_TOKEN_SMART, TG_CHAT_SMART,
                ochistit(novost["zagolovok"]),
                [ochistit(x) for x in parts],
                novost["link"],
                put,
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
    log("Запуск бота Смарт-Правда...")
    if obrabotat():
        log("✅ Успех!")
    else:
        log("⚠ Не удалось опубликовать.")
    log("Готово.")
