import os
import sys
import time
import random
import re
import requests
import feedparser
from datetime import datetime
from urllib.parse import urljoin

TG_BOT_TOKEN_WORLD = os.environ.get("TG_BOT_TOKEN_WORLD")
TG_BOT_TOKEN_KRIM = os.environ.get("TG_BOT_TOKEN_KRIM")
TG_CHAT_WORLD = os.environ.get("TG_CHAT_WORLD", "@dfcf1980")
TG_CHAT_KRIM = os.environ.get("TG_CHAT_KRIM", "@kriminal_vestnik")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

RSS_WORLD = [
    "https://ria.ru/export/rss2/archive/index.xml",
    "https://tass.ru/rss/v2.xml",
    "https://lenta.ru/rss",
    "https://news.rbc.ru/rbc_news.rss",
]

RSS_KRIM = [
    "https://rg.ru/rss/rubric/criminal/",
    "https://ren.tv/rss",
    "https://russian.rt.com/rss",
    "https://www.sb.by/rss/",
    "https://news.onliner.by/feed",
    "https://www.kp.ru/daily/incidents/rss/",
    "https://www.mk.ru/incidents/rss.xml",
    "https://mvd.gov.by/rss/",
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
    if not any(s in z for s in ZAGOLOVOK_SLOVA):
        return False
    n = [s for s in TEKST_SLOVA if s in t]
    return len(n) >= 2


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
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
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
            for p in soup.find_all("p")[:20]:
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
        if len(tekst) > 3500:
            tekst = tekst[:3500]
        if kartinka and not kartinka.startswith("http"):
            kartinka = urljoin(ssylka, kartinka)
        if video_url and not video_url.startswith("http"):
            video_url = urljoin(ssylka, video_url)
        return tekst, kartinka, video_url
    except Exception as e:
        log(f"  Ошибка страницы: {e}")
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


def publikovat(token, chat_id, msg, foto_path=None, video_path=None):
    base = f"https://api.telegram.org/bot{token}/"
    if video_path:
        try:
            with open(video_path, "rb") as f:
                r = requests.post(
                    base + "sendVideo",
                    data={"chat_id": chat_id, "caption": msg, "parse_mode": "HTML"},
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
                    data={"chat_id": chat_id, "caption": msg, "parse_mode": "HTML"},
                    files={"photo": f},
                    timeout=30,
                )
            return r.status_code == 200
        except:
            return False
    return False


def obrabotat_kanal(name, token, chat_id, rss_list, strict_kriminal):
    log(f"=== {name} ===")
    if not token:
        log(f"  Токен не задан, пропускаю.")
        return False
    
    zag = {"User-Agent": random.choice(USER_AGENTS)}
    vse = []
    for url in rss_list:
        try:
            r = requests.get(url, headers=zag, timeout=15)
            r.encoding = "utf-8"
            if r.status_code != 200:
                continue
            feed = feedparser.parse(r.text)
            for entry in feed.entries[:30]:
                zagolovok = ochistit(entry.get("title", "").strip())
                ssylka = entry.get("link", "").strip()
                opisanie = ochistit(entry.get("description", entry.get("summary", "")).strip())
                if zagolovok and len(zagolovok) > 10 and ssylka:
                    vse.append({"zagolovok": zagolovok, "ssylka": ssylka, "opisanie": opisanie})
        except Exception as e:
            log(f"  Ошибка RSS {url}: {e}")
    
    log(f"  Найдено {len(vse)} новостей.")
    if not vse:
        return False
    
    random.shuffle(vse)
    
    for novost in vse:
        tekst, kart, video = skachat_stranitsu(novost["ssylka"])
        if not tekst:
            if novost.get("opisanie"):
                tekst = novost["opisanie"]
            else:
                continue
        if strict_kriminal and not is_kriminal(novost["zagolovok"], tekst):
            continue
        parts = [p.strip() for p in tekst.split("\n\n") if len(p.strip()) > 50]
        if len(parts) < 2:
            continue
        if not kart and not video:
            continue
        
        msg = f"<b>{ochistit(novost['zagolovok'])}</b>\n\n"
        for p in [ochistit(x) for x in parts[:3]]:
            msg += f"{p}\n\n"
        msg += f"🔗 <a href='{novost['ssylka']}'>Читать полностью</a>"
        if len(msg) > 1000:
            msg = msg[:990] + "...</a>"
        
        put = None
        tip = None
        if video:
            put = skachat_fayl(video, "video")
            tip = "video"
        if not put and kart:
            put = skachat_fayl(kart, "foto")
            tip = "foto"
        
        if put:
            ok = publikovat(token, chat_id, msg, foto_path=put if tip == "foto" else None, video_path=put if tip == "video" else None)
            if ok:
                log(f"  Опубликовано: {novost['zagolovok'][:60]}")
                return True
            else:
                log(f"  Ошибка публикации")
    
    log(f"  Ни одна новость не подошла.")
    return False


if __name__ == "__main__":
    log("Запуск бота...")
    obrabotat_kanal("Мировые", TG_BOT_TOKEN_WORLD, TG_CHAT_WORLD, RSS_WORLD, False)
    obrabotat_kanal("Криминал", TG_BOT_TOKEN_KRIM, TG_CHAT_KRIM, RSS_KRIM, True)
    log("Готово.")
