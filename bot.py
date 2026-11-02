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

# ТОЛЬКО криминальные русскоязычные источники
RSS_KRIM = [
    "https://rg.ru/rss/rubric/criminal/",
    "https://www.kp.ru/daily/incidents/rss/",
    "https://www.mk.ru/incidents/rss.xml",
    "https://mvd.gov.by/rss/",
    "https://crimea.ria.ru/crime/rss/",
    "https://news.onliner.by/feed",
    "https://fontanka.ru/incidents/rss/",
    "https://www.161.ru/incidents/rss/",
    "https://www.e1.ru/incidents/rss/",
    "https://ngs.ru/incidents/rss/",
    "https://www.rosbalt.ru/rss/crime/",
    "https://pravo.ru/rss/",
    "https://sledcom.ru/rss",
    "https://112.ru/rss/",
    "https://kubnews.ru/rss/",
    "https://www.don24.ru/rss/",
    "https://5-tv.ru/rss/incidents/",
]

# ЖЁСТКИЕ криминальные слова — только для заголовка
# Убраны "суд", "судья", "приговор", "прокуратура", "следователь" — они бывают в политике
ZAGOLOVOK_SLOVA = [
    "убийств", "убийство", "убил", "убила", "убийца", "убили",
    "труп", "трупа", "трупы", "обнаружен труп", "найден труп", "обнаружено тело",
    "задержан", "задержана", "задержали", "задержание",
    "арестован", "арестована", "арестовали", "арест",
    "осужден", "осуждена", "осудили", "приговорен", "приговорили", "приговор",
    "кража", "кражи", "украл", "украла", "украли",
    "ограбление", "ограбил", "ограбили", "обокрали", "обокрал",
    "мошенник", "мошенница", "мошенничество", "мошенники", "аферист", "аферистка", "афера",
    "наркотик", "наркотики", "наркоман", "закладка", "закладчик", "наркоторговец",
    "разбой", "разбойник", "разбойное",
    "нападение", "напал", "напала", "напали", "вооруженное нападение",
    "избил", "избиение", "побои", "истязание",
    "погиб", "погибла", "погибли", "погибший", "погибших",
    "ранен", "ранена", "ранены", "ранение", "раненый",
    "дтп", "авария", "сбил", "сбила", "сбили", "сбил и скрылся",
    "поджог", "поджег", "подожгла", "поджоги",
    "взрыв", "взорвал", "взорвала", "взорвали", "взрывное устройство",
    "изнасилован", "изнасилование", "изнасиловал", "изнасиловала",
    "домогательство", "домогательства",
    "похищен", "похищена", "похитил", "похитила", "похитили", "похищение", "заложник", "заложники", "выкуп",
    "хулиган", "хулиганство", "дебош", "драка", "поножовщина",
    "вымогатель", "вымогательство", "шантаж", "шантажист",
    "коррупция", "коррупционер", "взяточник", "взяточничество", "взятка", "откат",
    "бандит", "бандитизм", "банда", "преступная группа", "преступная группировка",
    "теракт", "террорист", "террористический", "диверсия", "диверсант",
    "зарезал", "зарезан", "зарезали", "ножевое ранение", "ножевое",
    "стрелял", "стреляли", "стрельба", "расстрелян", "расстреляли", "застрелил", "застрелился", "застрелили",
    "удушил", "задушил", "задушена", "удушение",
    "расчленен", "расчленил", "изувечен", "изувечила",
    "пропал без вести", "пропала без вести", "разыскивается", "розыск",
    "ск ", "следователь", "возбуждено дело", "уголовное дело", "уголовка",
    "полиция", "милиция", "мвд", "омон", "росгвардия", "спецназ", "оперативник", "опер",
    "жертва", "жертвы", "потерпевший", "потерпевшая",
    "педофил", "педофилия", "педофилка", "маньяк", "серийный",
    "штурм", "обыск", "выемка", "задержание", "арест",
    "огнестрельн", "самосуд", "линчевание", "расправа", "убийство",
    "скрылся с места", "скрылся", "попытка побега", "побег из",
    "суд", "судья", "судебный", "прокуратура", "прокурор", "приговор",
    "преступление", "преступник", "преступники", "правонарушение",
    "криминал", "криминальный", "криминальный мир",
    "допрос", "экспертиза", "судмедэкспертиза", "вскрытие",
    "свидетель", "очевидец", "показания",
    "хищение", "растрата", "мошенничество", "рэкет", "рэкетир",
    "покушение", "покушался", "покушались",
    "незаконн", "незаконное хранение", "незаконный оборот",
    "контрабанда", "контрабандист",
    "эксгумация", "могила", "захоронение", "кладбище",
    "опознан", "опознана", "опознали", "неопознанн",
    "обезврежен", "обезвредили", "нейтрализован",
    "ликвидирован", "ликвидировали", "уничтожен",
    "самоубийство", "суицид", "повесился", "повесилась", "выбросился", "выбросилась",
    "насилие", "жестокое обращение", "истязание", "пытки",
    "шпионаж", "шпион", "госизмена", "государственная измена",
    "фальшивомонетчик", "фальшивые деньги", "подделка",
    "неуплата", "уклонение от налогов", "налоговое мошенничество",
    "отмывание", "отмывание денег", "легализация",
    "незаконное предпринимательство", "незаконная деятельность",
]

# Слова для текста — расширенный список
TEKST_SLOVA = ZAGOLOVOK_SLOVA + [
    "преступление", "преступник", "правонарушение", "криминал", "криминальный",
    "оперативник", "допрос", "экспертиза", "свидетель", "очевидец", "хищение",
    "растрата", "аферист", "афера", "рэкет",
    "соучастник", "соучастие", "подельник", "подельники",
    "орудие преступления", "орудие убийства", "нож", "пистолет", "автомат",
    "кровь", "кровотечение", "смерть", "смертельная",
    "тело", "останки", "труп", "покойник",
    "место преступления", "место происшествия",
    "оперативные мероприятия", "оперативники", "опергруппа",
    "возбуждено уголовное дело", "возбуждено дело",
    "проводится проверка", "проводится расследование",
    "установлены личности", "установлены лица",
    "приняты меры", "применены меры",
    "задержаны подозреваемые", "задержаны подозреваемый",
    "изъято", "изъяты", "конфисковано",
    "наркотические средства", "наркотические вещества",
    "огнестрельное оружие", "боеприпасы", "взрывчатка",
    "краденое", "похищенное", "награбленное",
    "потерпевший", "потерпевшая", "потерпевшие",
    "подозреваемый", "подозреваемая", "подозреваемые",
    "обвиняемый", "обвиняемая", "обвиняемые",
    "подсудимый", "подсудимая", "подсудимые",
    "осужденный", "осужденная", "осужденные",
    "лишение свободы", "тюремное заключение", "колония", "СИЗО", "изолятор",
    "условный срок", "реальный срок", "штраф", "компенсация",
    "судебное заседание", "судебный процесс", "судебное разбирательство",
    "приговорен к", "приговорена к", "осужден к",
    "пожизненное", "пожизненное лишение",
    "смягчающие обстоятельства", "отягчающие обстоятельства",
    "явка с повинной", "чистосердечное признание",
    "мотив", "мотивы преступления", "корыстный мотив",
    "соучастие", "соучастник", "пособник", "подстрекатель",
    "рецидив", "рецидивист", "судимость", "судим",
    "амнистия", "помилование", "УДО", "условно-досрочное",
    "международный розыск", "интерпол", "ордер на арест",
    "экстрадиция", "выдача", "депортация",
    "криминальная хроника", "сводка происшествий", "оперативная сводка",
    "правоохранительные органы", "органы внутренних дел",
    "уголовный кодекс", "ук рф", "статья ук",
    "убийство", "умышленное убийство", "неосторожное убийство",
    "тяжкие телесные повреждения", "тяжкий вред здоровью",
    "средней тяжести", "легкий вред здоровью",
    "истязание", "пытки", "жестокое обращение",
    "похищение человека", "торговля людьми",
    "незаконное лишение свободы", "захват заложников",
    "бандитизм", "организация преступного сообщества",
    "легализация преступных доходов", "отмывание денег",
    "контрабанда", "незаконный оборот",
    "фальсификация", "подделка документов",
    "мошенничество в сфере", "финансовое мошенничество",
    "киберпреступление", "кибермошенничество", "хакер",
    "терроризм", "террористический акт", "экстремизм",
    "вандализм", "осквернение",
    "незаконное хранение оружия", "незаконное хранение наркотиков",
    "самоубийство", "доведение до самоубийства",
    "халатность", "служебная халатность", "превышение полномочий",
    "взяточничество", "коммерческий подкуп",
    "злоупотребление полномочиями", "превышение должностных полномочий",
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
    """УЖЕСТЧЁННЫЙ фильтр: минимум 2 совпадения в заголовке И 4 в тексте."""
    z = zag.lower()
    t = tekst.lower()
    
    zag_matches = [s for s in ZAGOLOVOK_SLOVA if s in z]
    tekst_matches = [s for s in TEKST_SLOVA if s in t]
    
    # Нужно минимум 2 слова в заголовке И 4 в тексте
    if len(zag_matches) < 2:
        return False
    if len(tekst_matches) < 4:
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


def publikovat(token, chat_id, zag, parts, ssylka, foto_path=None, video_path=None):
    """Публикует ОДНО сообщение с медиа и подписью."""
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
                    if zagolovok not in seen_titles:
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
                novost["ssylka"],
                foto_path=put if tip == "foto" else None,
                video_path=put if tip == "video" else None,
            )
            if ok:
                log(f"  Опубликовано: {novost['zagolovok'][:60]}")
                return True
            else:
                log(f"  Ошибка публикации")
    
    log(f"  Ни одна новость не подошла.")
    return False


if __name__ == "__main__":
    log("Запуск бота...")
    
    if random.random() < 0.3:
        log("Случайный пропуск запуска (рандомизация интервала).")
        sys.exit(0)
    
    obrabotat_kanal("Мировые", TG_BOT_TOKEN_WORLD, TG_CHAT_WORLD, RSS_WORLD, False)
    obrabotat_kanal("Криминал", TG_BOT_TOKEN_KRIM, TG_CHAT_KRIM, RSS_KRIM, True)
    log("Готово.")
