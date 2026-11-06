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
TG_BOT_TOKEN_KRIM = os.environ.get("TG_BOT_TOKEN_KRIM")
TG_CHAT_WORLD = os.environ.get("TG_CHAT_WORLD", "@dfcf1980")
TG_CHAT_KRIM = os.environ.get("TG_CHAT_KRIM", "@kriminal_vestnik")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

RSS_WORLD = [
    "https://ria.ru/export/rss2/archive/index.xml",
    "https://tass.ru/rss/v2.xml",
    "https://lenta.ru/rss",
    "https://news.rbc.ru/rbc_news.rss",
    "https://news.mail.ru/rss/",
    "https://vz.ru/rss",
]

SOURCES_KRIM = [
    "https://www.mk.ru/incidents/rss.xml",
    "https://newinform.com/rss",
    "https://rg.ru/rss/rubric/criminal/",
    "https://russian.rt.com/rss",
    "https://www.vesti.ru/rss",
    "https://www.mzk2.ru/feed",
    "https://noctu.ru/feed",
    "https://www.mk.ru/incidents/",
    "https://newinform.com/category/proisshestviya/",
    "https://rg.ru/rubric/criminal/",
    "https://www.kp.ru/daily/incidents/",
    "https://www.vesti.ru/incidents"
]

ZAGOLOVOK_SLOVA = [
    "убийств", "убил", "убила", "убийца", "труп", "задержан", "задержана", "задержали",
    "арестован", "арестована", "осужден", "осуждена", "приговорен", "приговорили",
    "кража", "украл", "украла", "ограбление", "ограбил", "обокрали", "мошенник",
    "мошенница", "мошенничество", "мошенники", "наркотик", "наркотики", "закладка",
    "наркоман", "разбой", "нападение", "напал", "напала", "избил", "избиение",
    "погиб", "погибла", "погибли", "погибший", "ранен", "ранена", "ранены", "ранение",
    "дтп", "авария", "сбил", "поджог", "поджег", "подожгла", "взрыв", "взорвал",
    "взорвалась", "изнасилован", "изнасилование", "домогательство", "похищен",
    "похитил", "похитила", "заложник", "хулиган", "хулиганство", "дебош", "драка",
    "вымогатель", "вымогательство", "шантаж", "коррупция", "взяточник", "взятка",
    "бандит", "банда", "преступная группа", "теракт", "террорист", "диверсия",
    "зарезал", "зарезан", "стрелял", "стрельба", "расстрелян", "застрелил",
    "застрелился", "удушил", "задушил", "найден труп", "обнаружен труп",
    "обнаружено тело", "расчленен", "изувечен", "пропал без вести", "разыскивается",
    "ск ", "следователь", "возбуждено дело", "уголовное дело", "полиция", "милиция",
    "мвд", "омон", "росгвардия", "спецназ", "суд", "судья", "приговор", "прокуратура",
    "жертва", "потерпевший", "потерпевшая", "педофил", "педофилия", "штурм", "обыск",
    "выемка", "огнестрельн", "ножевое ранение", "скрылся с места", "сбил и скрылся",
]

TEKST_SLOVA = ZAGOLOVOK_SLOVA + [
    "преступление", "преступник", "правонарушение", "криминал", "криминальный",
    "оперативник", "допрос", "экспертиза", "свидетель", "очевидец", "хищение",
    "растрата", "аферист", "афера", "рэкет",
]

BLACKLIST_SLOVA = [
    "погода", "прогноз", "температура", "осадки", "ветер", "дождь", "снег",
    "спорт", "футбол", "хоккей", "баскетбол", "олимпиада", "чемпионат", "матч",
    "культура", "выставка", "концерт", "спектакль", "фильм", "кино", "премьера",
    "экономика", "курс валют", "инфляция", "ввп", "бюджет", "налоги", "пенсия",
    "политика", "выборы", "парламент", "президент", "министр", "закон", "реформа",
    "наука", "открытие", "исследование", "учёные", "экспедиция", "космос",
    "здоровье", "медицина", "болезнь", "вирус", "вакцина", "лекарство",
    "образование", "школа", "университет", "студенты", "экзамен",
    "туризм", "отпуск", "путешествие", "отель", "авиабилеты",
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


def is_kriminal(zag, tekst):
    """Ужесточённая проверка на криминальную тематику."""
    z = zag.lower()
    t = tekst.lower()
    
    if any(s in z or s in t for s in BLACKLIST_SLOVA):
        return False
    
    zag_krim = [s for s in ZAGOLOVOK_SLOVA if s in z]
    if len(zag_krim) < 2:
        return False
    
    tekst_krim_specific = [s for s in ZAGOLOVOK_SLOVA if s in t and s not in ["полиция", "милиция", "суд", "судья", "прокуратура", "мвд"]]
    if len(tekst_krim_specific) < 3:
        return False
    
    return True


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
        
        soup = BeautifulSoup(r.text, "html.parser")
        
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
        ext = ".mp4" if tip == "video" else (".png" if "png" in r.headers.get("content-type", "") else ".jpg")
        put = f"/tmp/news_{tip}{ext}"
        with open(put, "wb") as f:
            f.write(r.content)
        return put
    except:
        return None


def publikovat(token, chat_id, zag, parts, ssylka, foto_path=None, video_path=None):
    base = f"https://api.telegram.org/bot{token}/"
    
    caption = f"<b>{zag}</b>\n\n"
    for p in parts[:4]:
        caption += f"{p}\n\n"
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


def sobrat_novosti_kriminal(sources):
    vse_novosti = []
    zag_headers = {"User-Agent": random.choice(USER_AGENTS)}
    seen_links = set()
    
    for source in sources:
        if source.endswith('.xml') or 'rss' in source.lower():
            try:
                r = requests.get(source, headers=zag_headers, timeout=15)
                if r.status_code == 200:
                    feed = feedparser.parse(r.text)
                    for entry in feed.entries[:30]:
                        zag = ochistit(entry.get("title", "").strip())
                        link = entry.get("link", "").strip()
                        if zag and len(zag) > 10 and link and link not in seen_links:
                            seen_links.add(link)
                            vse_novosti.append({"zagolovok": zag, "link": link})
            except:
                pass
        else:
            try:
                r = requests.get(source, headers=zag_headers, timeout=15)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        title = a.get_text(strip=True)
                        if len(title) > 30 and href.startswith('http') and href.count('/') >= 4:
                            if not any(x in href.lower() for x in ['/page/', '/tag/', '/author/', 'login', 'search', 'rubric']):
                                title = re.sub(r'\s+', ' ', title)
                                if href not in seen_links:
                                    seen_links.add(href)
                                    vse_novosti.append({"zagolovok": title, "link": href})
            except:
                pass
    
    random.shuffle(vse_novosti)
    return vse_novosti[:150]


def obrabotat_kanal(name, token, chat_id, sources_list, strict_kriminal):
    log(f"=== {name} ===")
    if not token:
        log(f"  Токен не задан, пропускаю.")
        return False
    
    log(f"  Сбор пула новостей (RSS + HTML разделы)...")
    vse_novosti = sobrat_novosti_kriminal(sources_list) if strict_kriminal else []
    
    if not strict_kriminal:
        zag_headers = {"User-Agent": random.choice(USER_AGENTS)}
        for url in sources_list:
            try:
                r = requests.get(url, headers=zag_headers, timeout=15)
                if r.status_code == 200:
                    feed = feedparser.parse(r.text)
                    for entry in feed.entries[:30]:
                        zag = ochistit(entry.get("title", "").strip())
                        link = entry.get("link", "").strip()
                        if zag and len(zag) > 10 and link and link not in [x['link'] for x in vse_novosti]:
                            vse_novosti.append({"zagolovok": zag, "link": link})
            except:
                pass
        random.shuffle(vse_novosti)

    log(f"  Найдено {len(vse_novosti)} уникальных ссылок. Начинаю глубокий перебор...")
    
    for i, novost in enumerate(vse_novosti, 1):
        if i % 20 == 0:
            log(f"  Проверено {i} из {len(vse_novosti)}...")
            
        tekst, kart, video = skachat_stranitsu(novost["link"])
        
        if not tekst:
            continue
            
        if strict_kriminal and not is_kriminal(novost["zagolovok"], tekst):
            continue
            
        parts = [p.strip() for p in tekst.split("\n\n") if len(p.strip()) > 50]
        if len(parts) < 2:
            continue
            
        if not kart and not video:
            continue
            
        log(f"  ✓ Подходящая новость найдена: {novost['zagolovok'][:50]}...")
        
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
                token, chat_id,
                ochistit(novost["zagolovok"]),
                [ochistit(x) for x in parts],
                novost["link"],
                foto_path=put if tip == "foto" else None,
                video_path=put if tip == "video" else None,
            )
            if ok:
                log(f"  ✅ Опубликовано: {novost['zagolovok'][:60]}")
                return True
            else:
                log(f"  ✗ Ошибка публикации, ищу следующую...")
                continue
                
    log(f"  ⚠ Перебран весь пул, подходящих новостей с медиа не найдено.")
    return False


if __name__ == "__main__":
    log("Запуск бота...")
    
    if False:  # Отключено: random.random() < 0.2:
        log(" Случайный пропуск.")
        sys.exit(0)
    
    log("🚀 Начинаю глубокий поиск и публикацию...")
    
    world_ok = obrabotat_kanal("Мировые", TG_BOT_TOKEN_WORLD, TG_CHAT_WORLD, RSS_WORLD, False)
    krim_ok = obrabotat_kanal("Криминал", TG_BOT_TOKEN_KRIM, TG_CHAT_KRIM, SOURCES_KRIM, True)
    
    if world_ok or krim_ok:
        log("✅ Успешно опубликовано!")
    else:
        log("⚠ Не удалось опубликовать ни одной новости.")
    
    log("Готово.")
