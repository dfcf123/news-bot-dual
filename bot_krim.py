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

TG_BOT_TOKEN_KRIM = os.environ.get("TG_BOT_TOKEN_KRIM")
TG_CHAT_KRIM = os.environ.get("TG_CHAT_KRIM", "@kriminal_vestnik")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

RSS_KRIM = [
    "https://24minsk.by/tag/pistolet/feed",
    "https://www.gs.by/rss",
    "https://news.mail.ru/society/",
    "https://www.belarus.kp.ru/online/",
    "https://rg.ru/rss/rubric/criminal/",
    "https://www.mk.ru/incidents/rss.xml",
    "https://spbnews78.ru/rss",
    "https://russiatoday.ru/rss",
    "https://tass.ru/rss/v2.xml",
    "https://vz.ru/rss",
]

ZAGOLOVOK_SLOVA = [
    "убийств", "убил", "убила", "убийца", "труп", "задержан", "задержана", "задержали",
    "арестован", "арестована", "осужден", "осуждена", "приговорен", "приговорили",
    "приговор", "осудили", "срок", "колонии", "пожизненное",
    "кража", "украл", "украла", "ограбление", "ограбил", "обокрали", "мошенник",
    "мошенница", "мошенничество", "мошенники", "наркотик", "наркотики", "закладка",
    "наркоман", "наркокартель", "разбой", "нападение", "напал", "напала", "избил", "избиение",
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
    "мвд", "омон", "росгвардия", "спецназ", "суд", "судья", "прокуратура",
    "жертва", "потерпевший", "потерпевшая", "педофил", "педофилия", "штурм", "обыск",
    "выемка", "огнестрельн", "ножевое ранение", "скрылся с места", "сбил и скрылся",
    "мафия", "картель", "самосуд", "линчевание", "экстрадиция",
]

BLACKLIST_SLOVA = [
    "погода", "прогноз", "температура", "осадки", "ветер", "дождь", "снег",
    "спорт", "футбол", "хоккей", "баскетбол", "олимпиада", "чемпионат", "матч",
    "культура", "выставка", "концерт", "спектакль", "фильм", "кино", "премьера",
    "наука", "открытие", "исследование", "учёные", "экспедиция", "космос",
    "здоровье", "медицина", "болезнь", "вирус", "вакцина", "лекарство",
    "образование", "школа", "университет", "студенты", "экзамен",
    "туризм", "отпуск", "путешествие", "отель", "авиабилеты",
]


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
    if not any(s in z for s in ZAGOLOVOK_SLOVA):
        return False
    specific = [s for s in ZAGOLOVOK_SLOVA if s in t and s not in ["полиция", "милиция", "суд", "судья", "прокуратура", "мвд"]]
    if len(specific) < 1:
        return False
    return True


def skachat_stranitsu(ssylka):
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        r = requests.get(ssylka, headers=headers, timeout=20)
        r.encoding = "utf-8"
        if r.status_code != 200:
            return None, None, None
        soup = BeautifulSoup(r.content, "html.parser")
        tekst = ""
        for sel in ["article", "[class*='article']", "[class*='content']"]:
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
        return tekst, kartinka, None
    except:
        return None, None, None


def skachat_fayl(url, tip="foto"):
    try:
        r = requests.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=30)
        if r.status_code != 200 or len(r.content) > 50 * 1024 * 1024:
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
                r = requests.post(base + "sendVideo", data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}, files={"video": f}, timeout=60)
            if r.status_code != 200:
                log(f"  ✗ Ошибка видео: {r.text[:100]}")
            return r.status_code == 200
        except Exception as e:
            log(f"  ✗ Исключение видео: {e}")
            return False
            
    if foto_path:
        try:
            with open(foto_path, "rb") as f:
                r = requests.post(base + "sendPhoto", data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}, files={"photo": f}, timeout=30)
            if r.status_code != 200:
                log(f"  ✗ Ошибка фото: {r.text[:100]}")
            return r.status_code == 200
        except Exception as e:
            log(f"  ✗ Исключение фото: {e}")
            return False
            
    # Если нет медиа — отправляем как текст
    text_msg = f"<b>{zag}</b>\n\n"
    for p in parts[:8]:
        text_msg += f"{p}\n\n"
    text_msg += f"🔗 <a href='{ssylka}'>Читать полностью</a>"
    if len(text_msg) > 4000:
        text_msg = text_msg[:3990] + "...</a>"
        
    try:
        r = requests.post(base + "sendMessage", data={"chat_id": chat_id, "text": text_msg, "parse_mode": "HTML"}, timeout=30)
        if r.status_code != 200:
            log(f"  ✗ Ошибка текста: {r.text[:100]}")
        return r.status_code == 200
    except Exception as e:
        log(f"  ✗ Исключение текста: {e}")
        return False


def sobrat_novosti(sources):
    vse = []
    seen = set()
    for source in sources:
        try:
            r = requests.get(source, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=15)
            if r.status_code == 200:
                feed = feedparser.parse(r.content)
                for entry in feed.entries[:30]:
                    zag = ochistit(entry.get("title", "").strip())
                    link = entry.get("link", "").strip()
                    if zag and len(zag) > 10 and link and link not in seen:
                        seen.add(link)
                        vse.append({"zagolovok": zag, "link": link})
        except:
            pass
    random.shuffle(vse)
    return vse[:100]


def obrabotat_kanal():
    log("=== Криминальный вестник ===")
    if not TG_BOT_TOKEN_KRIM:
        log("Токен не задан!")
        return False
    log("Сбор пула новостей...")
    vse = sobrat_novosti(RSS_KRIM)
    log(f"Найдено {len(vse)} ссылок. Перебор...")
    for i, n in enumerate(vse, 1):
        if i % 10 == 0:
            log(f"Проверено {i}/{len(vse)}...")
        tekst, kart, video = skachat_stranitsu(n["link"])
        if not tekst:
            continue
        if not is_kriminal(n["zagolovok"], tekst):
            continue
        parts = [p.strip() for p in tekst.split("\n\n") if len(p.strip()) > 50]
        if len(parts) < 2:
            continue
            
        log(f"  [{i}] ✓ ПОДХОДИТ: {n['zagolovok'][:50]}...")
        
        put = None
        tip = None
        if video:
            put = skachat_fayl(video, "video")
            tip = "video"
        if not put and kart:
            put = skachat_fayl(kart, "foto")
            tip = "foto"
            
        if not put:
            log(f"  [{i}] ⚠ Не удалось скачать медиа, пробую как текст...")
            
        if publikovat(TG_BOT_TOKEN_KRIM, TG_CHAT_KRIM, ochistit(n["zagolovok"]), [ochistit(x) for x in parts], n["link"], foto_path=put if tip=="foto" else None, video_path=put if tip=="video" else None):
            log(f"  ✅ Опубликовано: {n['zagolovok'][:60]}")
            return True
        else:
            log(f"  ✗ Не удалось опубликовать, ищу следующую...")
            
    log("⚠ Ничего не подошло.")
    return False


if __name__ == "__main__":
    log("Запуск...")
    if obrabotat_kanal():
        log("✅ Успех!")
    else:
        log("⚠ Неудача.")
    log("Готово.")
