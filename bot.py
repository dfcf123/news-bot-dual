import os
import re
import json
import time
import random
import requests
import feedparser
from html import escape
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

TG_BOT_TOKEN_WORLD = os.environ.get("TG_BOT_TOKEN_WORLD")
TG_CHAT_WORLD = os.environ.get("TG_CHAT_WORLD", "@dfcf1980")

SEEN_FILE = "/tmp/seen_news.json"
MAX_SEEN = 500
MAX_ATTEMPTS = 25          # сколько страниц максимум скачиваем за запуск
HTTP_TIMEOUT = 15
MAX_CAPTION = 1024

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

RSS_WORLD = [
    # Белорусские государственные СМИ
    "https://www.sb.by/rss/",
    "https://news.onliner.by/feed",
    "https://mvd.gov.by/rss/",
    "https://www.belta.by/rss/",
    "https://naviny.by/rss/",
    "https://charter97.org/rss.php",
    "https://nn.by/rss",
    "https://zviazda.by/rss",
    "https://1tv.by/rss",
    "https://ont.by/rss",
    "https://stv.by/rss",
    "https://mir24.tv/belarus/rss",
    "https://belteleradio.by/rss",

    # Белорусские версии российских СМИ
    "https://kp.by/rss/",
    "https://mk.by/rss/",
    "https://aif.by/rss/",

    # Российские источники с разделом Беларусь
    "https://ria.ru/rss/belarus.xml",
    "https://tass.ru/rss/v2.xml?tag=12",
    "https://lenta.ru/rss/tags/belarus",
]

# Стоп-темы (проверяем ТОЛЬКО заголовок — иначе режем нормальные новости)
BLACKLIST_SLOVA = [
    "погода", "прогноз", "температура", "осадки", "ветер", "дождь", "снег", "метель",
    "циклон", "антициклон", "атмосферный фронт", "гроза", "град", "туман", "гололёд",
    "спорт", "футбол", "хоккей", "баскетбол", "олимпиада", "чемпионат", "матч",
    "культура", "выставка", "концерт", "спектакль", "фильм", "кино", "премьера",
    "наука", "открытие", "исследование", "учёные", "экспедиция", "космос",
    "здоровье", "медицина", "болезнь", "вирус", "вакцина", "лекарство", "больница",
    "образование", "школа", "университет", "студенты", "экзамен", "выпускной",
    "туризм", "отпуск", "путешествие", "отель", "авиабилеты", "курорт",
    "рецепт", "кулинария", "блюдо", "повар", "ресторан", "кафе",
    "мода", "стиль", "дизайнер", "коллекция", "показ мод",
    "гороскоп", "астрология", "знак зодиака", "таро", "гадание",
]

BELARUS_WORDS = [
    "беларусь", "белоруссия", "минск", "белорусский", "белорусская",
    "лукашенко", "президент рб", "совет министров рб", "национальное собрание",
    "гродно", "брест", "гомель", "витебск", "могилёв", "бобруйск",
    "барановичи", "борисов", "пинск", "орша", "мозырь", "солигорск",
    "новополоцк", "лида", "молодечно", "полоцк", "жлобин", "светлогорск",
    "речица", "слуцк", "жодино", "слоним", "кобрин", "волковыск",
    "белта", "онлайнер", "сб беларусь",
    "кдб рб", "мвд рб", "прокуратура рб", "верховный суд рб",
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


def is_russian(text):
    return bool(re.search("[а-яА-ЯёЁ]", text))


def is_belarus_related(zag, tekst):
    # проверяем заголовок + первые 600 символов, чтобы не ловить ложные срабатывания в конце статьи
    haystack = (zag + " " + tekst[:600]).lower()
    return any(s in haystack for s in BELARUS_WORDS)


def is_blacklisted(zag):
    z = zag.lower()
    return any(s in z for s in BLACKLIST_SLOVA)


# ---------- дедупликация между запусками ----------

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def save_seen(seen):
    try:
        # обрезаем по длине — храним последние MAX_SEEN
        lst = list(seen)[-MAX_SEEN:]
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(lst, f, ensure_ascii=False)
    except Exception as e:
        log(f"  Не смог сохранить seen: {e}")


def norm_key(zag, link):
    return (link or zag).strip().lower()


# ---------- парсинг страницы ----------

def skachat_stranitsu(ssylka):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": "https://www.google.com/",
    }
    try:
        r = requests.get(ssylka, headers=headers, timeout=HTTP_TIMEOUT)
        if r.status_code != 200:
            return None, None, None

        soup = BeautifulSoup(r.content, "html.parser")

        # проверка даты (не старше 14 дней)
        try:
            meta_date = soup.find("meta", property="article:published_time")
            if meta_date and meta_date.get("content"):
                date_str = meta_date["content"].split("T")[0]
                pub_date = datetime.strptime(date_str, "%Y-%m-%d")
                if (datetime.now() - pub_date).days > 14:
                    return None, None, None
        except Exception:
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
            except Exception:
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
        log(f"  Ошибка страницы {ssylka[:50]}: {str(e)[:80]}")
        return None, None, None


# ---------- скачивание медиа ----------

ALLOWED_IMAGE = ("image/jpeg", "image/jpg", "image/png")
ALLOWED_VIDEO = ("video/mp4",)


def skachat_fayl(url, tip="foto"):
    try:
        r = requests.get(url, headers={"User-Agent": random.choice(USER_AGENTS)},
                         timeout=30, stream=True)
        if r.status_code != 200:
            return None

        ct = (r.headers.get("content-type") or "").lower()
        if tip == "video":
            if not any(a in ct for a in ALLOWED_VIDEO):
                return None
            ext = ".mp4"
        else:
            if not any(a in ct for a in ALLOWED_IMAGE):
                return None
            ext = ".png" if "png" in ct else ".jpg"

        # ограничение размера (50 МБ)
        content = r.content
        if len(content) > 50 * 1024 * 1024 or len(content) < 1024:
            return None

        put = f"/tmp/news_{tip}_{int(time.time())}{ext}"
        with open(put, "wb") as f:
            f.write(content)
        return put
    except Exception as e:
        log(f"  Ошибка скачивания {tip}: {str(e)[:80]}")
        return None


# ---------- публикация ----------

def build_caption(zag, parts, ssylka):
    head = f"<b>{escape(zag)}</b>\n\n"
    tail = f"🔗 <a href='{escape(ssylka, quote=True)}'>Читать полностью</a>"

    body = ""
    for p in parts[:4]:
        candidate = head + body + escape(p) + "\n\n" + tail
        if len(candidate) > MAX_CAPTION:
            break
        body += escape(p) + "\n\n"

    caption = head + body + tail
    # на случай, если сам head+tail уже длиннее лимита
    if len(caption) > MAX_CAPTION:
        caption = caption[:MAX_CAPTION]
    return caption


def publikovat(token, chat_id, caption, foto_path=None, video_path=None):
    base = f"https://api.telegram.org/bot{token}/"

    def _send(method, files, data):
        try:
            r = requests.post(base + method, data=data, files=files, timeout=90)
            if r.status_code != 200:
                try:
                    err = r.json().get("description", r.text[:200])
                except Exception:
                    err = r.text[:200]
                log(f"  Telegram API {method}: {r.status_code} — {err}")
                return False
            return True
        except Exception as e:
            log(f"  Telegram API {method} exception: {str(e)[:120]}")
            return False

    data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}

    if video_path:
        try:
            with open(video_path, "rb") as f:
                ok = _send("sendVideo",
                           {"video": ("video.mp4", f, "video/mp4")},
                           data)
            if ok:
                return True
        except Exception as e:
            log(f"  sendVideo open error: {e}")

    if foto_path:
        try:
            name = os.path.basename(foto_path)
            mime = "image/png" if name.endswith(".png") else "image/jpeg"
            with open(foto_path, "rb") as f:
                return _send("sendPhoto",
                             {"photo": (name, f, mime)},
                             data)
        except Exception as e:
            log(f"  sendPhoto open error: {e}")

    return False


# ---------- основной цикл ----------

def obrabotat_kanal():
    log("=== Новости Беларуси ===")
    if not TG_BOT_TOKEN_WORLD:
        log("  Токен не задан!")
        return False

    seen = load_seen()
    log(f"  В кэше уже {len(seen)} новостей.")

    vse = []
    zag_headers = {"User-Agent": random.choice(USER_AGENTS)}

    for url in RSS_WORLD:
        try:
            r = requests.get(url, headers=zag_headers, timeout=HTTP_TIMEOUT)
            if r.status_code != 200:
                log(f"  RSS {url[:40]} — ошибка {r.status_code}")
                continue
            feed = feedparser.parse(r.content)
            for entry in feed.entries[:30]:
                zag = ochistit(entry.get("title", "").strip())
                link = entry.get("link", "").strip()
                if zag and len(zag) > 10 and link:
                    vse.append({"zagolovok": zag, "link": link})
        except Exception as e:
            log(f"  Ошибка RSS {url[:40]}: {str(e)[:80]}")

    log(f"  Найдено {len(vse)} новостей.")
    if not vse:
        return False

    random.shuffle(vse)

    attempts = 0
    for novost in vse:
        if attempts >= MAX_ATTEMPTS:
            log("  Достигнут лимит попыток скачивания.")
            break

        key = norm_key(novost["zagolovok"], novost["link"])
        if key in seen:
            continue

        if not is_russian(novost["zagolovok"]):
            continue

        if is_blacklisted(novost["zagolovok"]):
            continue

        attempts += 1
        tekst, kart, video = skachat_stranitsu(novost["link"])
        if not tekst:
            continue

        if not is_russian(tekst):
            continue

        if not is_belarus_related(novost["zagolovok"], tekst):
            continue

        parts = [p.strip() for p in tekst.split("\n\n") if len(p.strip()) > 50]
        if len(parts) < 2:
            continue

        if not kart and not video:
            continue

        log(f"  ✓ Кандидат: {novost['zagolovok'][:60]}...")

        put = None
        tip = None
        if video:
            put = skachat_fayl(video, "video")
            tip = "video"
        if not put and kart:
            put = skachat_fayl(kart, "foto")
            tip = "foto"

        if not put:
            log("  ✗ Медиа не скачалось, пропуск.")
            continue

        try:
            caption = build_caption(novost["zagolovok"], parts, novost["link"])
            ok = publikovat(
                TG_BOT_TOKEN_WORLD,
                TG_CHAT_WORLD,
                caption,
                foto_path=put if tip == "foto" else None,
                video_path=put if tip == "video" else None,
            )
        finally:
            if put and os.path.exists(put):
                try:
                    os.remove(put)
                except Exception:
                    pass

        if ok:
            seen.add(key)
            save_seen(seen)
            log("  ✅ Опубликовано!")
            return True
        else:
            log("  ✗ Ошибка публикации, ищу следующую...")
            continue

    log("  ⚠ Не подошло.")
    return False


if __name__ == "__main__":
    log("Запуск бота...")
    log("🚀 Начинаю поиск новостей Беларуси...")

    if obrabotat_kanal():
        log("✅ Успешно опубликовано!")
    else:
        log("⚠ Не удалось опубликовать ни одной новости.")

    log("Готово.")
