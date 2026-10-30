import asyncio
import datetime
import json
import logging
import os
import re
import shutil
import time
import urllib.parse
from logging.handlers import RotatingFileHandler
from pathlib import Path

import aiohttp
import discord
import feedparser
from discord.ext import commands, tasks

import config


BASE_DIR = Path(__file__).resolve().parent
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
TAG_RE = re.compile(r"<[^<]+?>")
SPACE_RE = re.compile(r"\s+")
IMG_SRC_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
IMG_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp|gif|avif)(?:\?|$)", re.I)


def _setup_logger():
    log_dir = BASE_DIR / config.LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    log = logging.getLogger("dota_news_bot")
    log.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    log.propagate = False

    if not log.handlers:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

        file_handler = RotatingFileHandler(
            log_dir / config.LOG_FILE,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        log.addHandler(console_handler)

    return log


logger = _setup_logger()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.check
async def only_owner(ctx):
    allowed = ctx.author.id == config.OWNER_ID
    if not allowed:
        logger.warning(
            "Отклонена команда %s от %s (ID %s): нет доступа.",
            ctx.command,
            ctx.author,
            ctx.author.id,
        )
    return allowed


def resolve_link(link):
    """Bing News отдаёт ссылки через редирект — достаём оригинальный URL."""
    parsed = urllib.parse.urlparse(link)
    if parsed.netloc.endswith("bing.com"):
        query = urllib.parse.parse_qs(parsed.query)
        original = query.get("url")
        if original:
            link = urllib.parse.unquote(original[0])
            parsed = urllib.parse.urlparse(link)

    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    cleaned = [(key, value) for key, value in query if not key.startswith("utm_")]
    if len(cleaned) == len(query):
        return link

    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(cleaned)))


def extract_image(entry, base_url):
    """Ищет картинку записи в стандартных и провайдерских полях RSS."""
    for key in ("media_content", "media_thumbnail"):
        for media in entry.get(key) or []:
            image = media.get("url")
            if image:
                return image

    for enclosure in entry.get("enclosures") or []:
        image = enclosure.get("href") or enclosure.get("url")
        ctype = (enclosure.get("type") or "").lower()
        if image and (ctype.startswith("image/") or IMG_EXT_RE.search(image)):
            return image

    relative = entry.get("dotabuff_image")
    if relative:
        return urllib.parse.urljoin("https://www.dotabuff.com/", relative)

    bing_image = entry.get("news_image")
    if bing_image:
        bing_image = bing_image.replace("http://", "https://", 1)
        bing_image = bing_image.replace("{0}", str(config.IMAGE_WIDTH))
        return bing_image.replace("{1}", str(config.IMAGE_HEIGHT))

    image = entry.get("image")
    if isinstance(image, dict):
        image = image.get("href") or image.get("url")
    if image:
        return urllib.parse.urljoin(base_url, image)

    html = entry.get("summary", "")
    content = entry.get("content")
    if content and content[0].get("value"):
        html = content[0]["value"] + html

    match = IMG_SRC_RE.search(html)
    if match:
        return urllib.parse.urljoin(base_url, match.group(1))

    return None


async def is_valid_image(session, url):
    """Проверяет, что ссылка действительно отдаёт картинку."""
    if not url or len(url) > 2000 or not url.startswith(("http://", "https://")):
        return False

    try:
        timeout = aiohttp.ClientTimeout(total=config.IMAGE_TIMEOUT)
        async with session.get(url, timeout=timeout) as response:
            if response.status != 200:
                return False
            ctype = (response.headers.get("Content-Type") or "").lower()
            if not ctype.startswith("image/"):
                return False
            await response.content.read(16)
            return True
    except Exception as error:
        logger.debug("Картинка недоступна (%s): %s", error, url)
        return False


async def fetch_source(session, name, url):
    """Загружает и парсит один RSS-источник. Ошибка одного не ломает остальные."""
    logger.info("[%s] Проверяю источник: %s", name, url)
    timeout = aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT)
    text = None

    for attempt in range(config.RETRY_COUNT + 1):
        try:
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    text = await response.text(errors="replace")
                    break
                retryable = response.status == 429 or response.status >= 500
                if retryable and attempt < config.RETRY_COUNT:
                    logger.warning(
                        "[%s] HTTP %s, повтор через %ss (попытка %d/%d)",
                        name,
                        response.status,
                        config.RETRY_DELAY,
                        attempt + 1,
                        config.RETRY_COUNT,
                    )
                else:
                    logger.warning("[%s] HTTP %s — источник пропущен", name, response.status)
                    return name, []
        except Exception as error:
            if attempt < config.RETRY_COUNT:
                logger.warning(
                    "[%s] Ошибка запроса (%s), повтор через %ss",
                    name,
                    error,
                    config.RETRY_DELAY,
                )
            else:
                logger.error("[%s] Не удалось загрузить RSS: %s", name, error)
                return name, []

        await asyncio.sleep(config.RETRY_DELAY)

    if text is None:
        return name, []

    feed = feedparser.parse(text)
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        hours=config.NEWS_WINDOW_HOURS
    )
    items = []
    skipped_old = 0
    undated = 0

    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = resolve_link(entry.get("link", "").strip())
        if not title or not link:
            continue

        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if published:
            published_at = datetime.datetime(*published[:6], tzinfo=datetime.timezone.utc)
            if published_at < cutoff:
                skipped_old += 1
                continue
        else:
            undated += 1

        summary = SPACE_RE.sub(" ", TAG_RE.sub("", entry.get("summary", ""))).strip()
        summary = summary[: config.MAX_SUMMARY_LENGTH].strip()

        image = extract_image(entry, link)
        items.append({"title": title, "link": link, "summary": summary, "image": image})
        if len(items) >= config.MAX_ITEMS_PER_SOURCE:
            break

    if items:
        logger.info(
            "[%s] Источник ответил: %d записей "
            "(пропущено старых: %d, без даты: %d)",
            name,
            len(items),
            skipped_old,
            undated,
        )
    else:
        logger.warning(
            "[%s] Нет записей за последние %d ч (пропущено старых: %d)",
            name,
            config.NEWS_WINDOW_HOURS,
            skipped_old,
        )

    return name, items


async def fetch_all_news():
    """Параллельно собирает материалы для дайджеста из всех источников."""
    total = len(config.RSS_SOURCES)
    logger.info(
        "Начинаю сбор дайджеста из %d источников (окно: %d ч)",
        total,
        config.NEWS_WINDOW_HOURS,
    )
    started = time.perf_counter()

    headers = {"User-Agent": config.USER_AGENT}
    async with aiohttp.ClientSession(headers=headers) as session:
        results = await asyncio.gather(
            *(fetch_source(session, name, url) for name, url in config.RSS_SOURCES.items())
        )

    news = {name: items for name, items in results if items}
    elapsed = time.perf_counter() - started
    ok = len(news)
    failed = [name for name, items in results if not items]
    logger.info("Сбор завершён за %.2f с: ответили %d/%d источников", elapsed, ok, total)
    if failed:
        logger.warning("Без материалов остались: %s", ", ".join(failed))

    return news


def build_news_context(news):
    """Готовит компактный текст материалов для opencode."""
    lines = []
    for source, items in news.items():
        lines.append(f"== {source} ==")
        for item in items:
            line = f"- {item['title']}"
            if item["summary"]:
                line += f": {item['summary']}"
            line += f" [источник: {source}; ссылка: {item['link']}]"
            lines.append(line)
        lines.append("")

    return "\n".join(lines).strip()[: config.MAX_PROMPT_LENGTH]


def resolve_opencode():
    """Ищет исполняемый файл opencode (npm-обёртка на Windows — это .cmd)."""
    if config.OPENCODE_EXE:
        return config.OPENCODE_EXE

    for executable in ("opencode.exe", "opencode"):
        found = shutil.which(executable)
        if not found:
            continue
        real_exe = Path(found).parent / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
        return str(real_exe) if real_exe.exists() else found

    appdata = os.getenv("APPDATA")
    if appdata:
        real_exe = Path(appdata) / "npm" / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
        if real_exe.exists():
            return str(real_exe)

    return "opencode"


def parse_opencode_output(raw):
    """Достаёт текст ответа и статистику токенов из JSON-потока opencode."""
    chunks = []
    usage = {
        "input": 0,
        "output": 0,
        "reasoning": 0,
        "cache_read": 0,
        "cache_write": 0,
        "total": 0,
    }
    cost = 0.0
    steps = 0

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type")
        part = event.get("part") or {}

        if event_type == "text" and part.get("type") == "text" and part.get("text"):
            chunks.append(part["text"])

        elif event_type == "step_finish":
            tokens = part.get("tokens") or {}
            for key in ("input", "output", "reasoning", "total"):
                usage[key] += int(tokens.get(key) or 0)
            cache = tokens.get("cache") or {}
            usage["cache_read"] += int(cache.get("read") or 0)
            usage["cache_write"] += int(cache.get("write") or 0)
            cost += float(part.get("cost") or 0)
            steps += 1

    text = "".join(chunks).strip()
    if not text:
        cleaned = ANSI_RE.sub("", raw).strip()
        text = "" if cleaned.startswith("{") else cleaned

    return text, usage, cost, steps


async def summarize_with_opencode(context):
    """Вызывает локальный opencode и возвращает краткую выжимку."""
    command = [resolve_opencode(), "run", "--command", config.OPENCODE_COMMAND]
    command += ["--format", "json"]
    if config.OPENCODE_MODEL:
        command += ["--model", config.OPENCODE_MODEL]
    command.append(context)

    logger.info(
        "Отправляю %d символов в opencode (%s)",
        len(context),
        " ".join(command[:4]),
    )
    started = time.perf_counter()

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(BASE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.error("opencode не найден. Укажите путь в OPENCODE_EXE.")
        return None

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=config.OPENCODE_TIMEOUT
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        logger.error("opencode не ответил за %ss и был остановлен.", config.OPENCODE_TIMEOUT)
        return None

    elapsed = time.perf_counter() - started
    stderr_text = stderr.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        logger.error("opencode завершился с кодом %s: %s", process.returncode, stderr_text)
        return None

    text, usage, cost, steps = parse_opencode_output(stdout.decode("utf-8", errors="replace"))

    logger.info(
        "opencode: %.2f с, шагов=%d, токены input=%d output=%d reasoning=%d "
        "cache_read=%d cache_write=%d total=%d, стоимость=$%.6f",
        elapsed,
        steps,
        usage["input"],
        usage["output"],
        usage["reasoning"],
        usage["cache_read"],
        usage["cache_write"],
        usage["total"],
        cost,
    )

    if not text:
        logger.error("opencode вернул пустой ответ. stderr: %s", stderr_text or "—")
        return None

    logger.info("opencode вернул выжимку из %d символов", len(text))
    return text


def build_fallback_summary(news):
    """Простая выжимка на случай, если opencode недоступен."""
    lines = []
    for source, items in news.items():
        for item in items:
            title = item["title"]
            if len(title) > config.MAX_TITLE_LENGTH:
                title = title[: config.MAX_TITLE_LENGTH - 3] + "..."
            lines.append(f"- {title} ([{source}]({item['link']}))")
    return "\n".join(lines) or "Материалы не найдены."


def hours_label(hours):
    if hours % 10 == 1 and hours % 100 != 11:
        return "час"
    if hours % 10 in (2, 3, 4) and hours % 100 not in (12, 13, 14):
        return "часа"
    return "часов"


async def build_digest_embeds(news):
    context = build_news_context(news)
    summary = None

    if config.OPENCODE_ENABLED:
        summary = await summarize_with_opencode(context)

    if summary:
        logger.info("Использую выжимку opencode.")
    else:
        logger.warning("Использую резервную сводку без opencode.")
        summary = build_fallback_summary(news)

    summary = summary[: config.MAX_DESCRIPTION_LENGTH]
    window = config.NEWS_WINDOW_HOURS
    window_label = f"{window} {hours_label(window)}"

    main_embed = discord.Embed(
        title=config.EMBED_TITLE,
        description=f"Дайджест за {window_label}\n\n{summary}",
        color=discord.Color(config.EMBED_COLOR),
    )
    embeds = [main_embed]

    if not config.SHOW_IMAGES:
        return embeds

    candidates = []
    for source, items in news.items():
        for item in items:
            if item.get("image"):
                candidates.append((source, item))
    candidates = candidates[: config.MAX_IMAGE_CHECKS]

    if not candidates:
        logger.info("Картинки: ни у одной записи нет изображения.")
        return embeds

    headers = {"User-Agent": config.USER_AGENT}
    async with aiohttp.ClientSession(headers=headers) as session:
        checks = await asyncio.gather(
            *(is_valid_image(session, item["image"]) for _, item in candidates)
        )

    max_images = min(config.MAX_DIGEST_IMAGES, 9)
    added = 0
    for (source, item), valid in zip(candidates, checks):
        if not valid or added >= max_images:
            continue

        title = item["title"]
        if len(title) > 200:
            title = title[:197] + "..."

        card = discord.Embed(
            title=title,
            url=item["link"],
            color=discord.Color(config.EMBED_COLOR),
        )
        card.set_author(name=source[:256])
        card.set_image(url=item["image"])
        embeds.append(card)
        added += 1

    logger.info("Картинки: добавлено %d из %d кандидатов.", added, len(candidates))
    return embeds


async def send_digest(channel):
    news = await fetch_all_news()
    if not news:
        logger.error("Нет материалов ни из одного источника.")
        await channel.send("Не удалось собрать дайджест Dota 2. 😔")
        return

    embeds = await build_digest_embeds(news)
    await channel.send(embeds=embeds)
    logger.info("Дайджест отправлен в канал %s", getattr(channel, "id", "?"))


def load_last_patch():
    path = BASE_DIR / config.PATCH_STATE_FILE
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file).get("patch_number")
    except FileNotFoundError:
        return None
    except Exception as error:
        logger.warning("Патчи: не удалось прочитать состояние: %s", error)
        return None


def save_last_patch(patch):
    path = BASE_DIR / config.PATCH_STATE_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(path.name + ".tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(patch, file, ensure_ascii=False, indent=2)
        temp_path.replace(path)
    except Exception as error:
        logger.error("Патчи: не удалось сохранить состояние: %s", error)


async def fetch_latest_patch():
    timeout = aiohttp.ClientTimeout(total=config.PATCH_REQUEST_TIMEOUT)
    headers = {"User-Agent": config.USER_AGENT}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(config.PATCH_LIST_URL, timeout=timeout) as response:
                if response.status != 200:
                    logger.warning("Патчи: HTTP %s", response.status)
                    return None
                data = await response.json(content_type=None)
    except Exception as error:
        logger.warning("Патчи: ошибка запроса: %s", error)
        return None

    patches = data.get("patches") or []
    if not patches:
        logger.warning("Патчи: API вернул пустой список.")
        return None

    latest = patches[-1]
    number = latest.get("patch_number") or latest.get("patch_name")
    if not number:
        logger.warning("Патчи: не удалось определить номер последнего патча.")
        return None

    return {
        "patch_number": number,
        "patch_timestamp": latest.get("patch_timestamp"),
        "patch_slug": latest.get("patch_website") or number,
    }


def clean_patch_note(note):
    text = note.get("note", "") if isinstance(note, dict) else str(note)
    text = SPACE_RE.sub(" ", TAG_RE.sub(" ", text)).strip()
    info = note.get("info") if isinstance(note, dict) else None
    if info:
        info = SPACE_RE.sub(" ", TAG_RE.sub(" ", info)).strip()
        if info:
            text = f"{text} ({info})"
    return text[: config.MAX_PATCH_NOTE_LENGTH].strip()


def format_patch_notes(notes):
    result = []
    for note in notes or []:
        text = clean_patch_note(note)
        if text:
            result.append(text)
    return result


def patch_name_map(data, key):
    result = {}
    if not isinstance(data, dict):
        return result

    rows = ((data.get("result") or {}).get("data") or {}).get(key) or []
    for row in rows:
        if isinstance(row, dict) and row.get("id") is not None:
            result[row["id"]] = row.get("name_loc") or row.get("name") or f"#{row['id']}"
    return result


async def fetch_json(session, url, timeout):
    async with session.get(url, timeout=timeout) as response:
        if response.status != 200:
            logger.warning("Патчи: HTTP %s для %s", response.status, url)
            return None
        return await response.json(content_type=None)


async def fetch_patch_context(version):
    """Собирает патчноуты и названия героев/предметов в компактный текст."""
    timeout = aiohttp.ClientTimeout(total=config.PATCH_META_TIMEOUT)
    headers = {"User-Agent": config.USER_AGENT}
    urls = [
        config.PATCH_NOTES_URL.format(version=version),
        config.PATCH_HERO_LIST_URL,
        config.PATCH_ITEM_LIST_URL,
        config.PATCH_ABILITY_LIST_URL,
    ]

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            results = await asyncio.gather(
                *(fetch_json(session, url, timeout) for url in urls),
                return_exceptions=True,
            )
    except Exception as error:
        logger.warning("Патчи: не удалось загрузить патчноуты %s: %s", version, error)
        return None

    notes, heroes, items, abilities = [
        None if isinstance(result, Exception) else result for result in results
    ]
    if not isinstance(notes, dict):
        logger.warning("Патчи: патчноуты %s недоступны.", version)
        return None

    hero_names = patch_name_map(heroes, "heroes")
    item_names = patch_name_map(items, "itemabilities")
    ability_names = patch_name_map(abilities, "itemabilities")

    lines = [f"Patch {notes.get('patch_number') or version}", ""]

    for section in notes.get("general_notes") or []:
        title = (section.get("title") or "General Changes").strip()
        note_list = format_patch_notes(section.get("generic"))
        if not note_list:
            continue
        lines.append(f"{title}:")
        lines.extend(f"- {note}" for note in note_list)
        lines.append("")

    neutral_sections = []
    neutral_items = []
    for entry in notes.get("neutral_items") or []:
        note_list = format_patch_notes(entry.get("ability_notes"))
        if not note_list:
            continue
        if entry.get("is_general_note"):
            neutral_sections.append((entry.get("title") or "Neutral Items", note_list))
        else:
            label = (
                item_names.get(entry.get("ability_id"))
                or entry.get("title")
                or f"#{entry.get('ability_id')}"
            )
            neutral_items.append((label, note_list))

    for title, note_list in neutral_sections:
        lines.append(f"{title}:")
        lines.extend(f"- {note}" for note in note_list)
        lines.append("")

    item_rows = []
    for entry in notes.get("items") or []:
        note_list = format_patch_notes(entry.get("ability_notes"))
        if not note_list:
            continue
        label = item_names.get(entry.get("ability_id")) or f"#{entry.get('ability_id')}"
        item_rows.append((label, note_list))

    if item_rows:
        lines.append("Items:")
        for label, note_list in item_rows:
            lines.append(f"- {label}: " + "; ".join(note_list))
        lines.append("")

    if neutral_items:
        lines.append("Neutral Items:")
        for label, note_list in neutral_items:
            lines.append(f"- {label}: " + "; ".join(note_list))
        lines.append("")

    creep_rows = []
    for creep in notes.get("neutral_creeps") or []:
        note_list = format_patch_notes(creep.get("neutral_creep_notes"))
        if not note_list:
            continue
        label = creep.get("localized_name") or creep.get("name") or "Neutral creep"
        creep_rows.append((label, note_list))

    if creep_rows:
        lines.append("Neutral Creeps:")
        for label, note_list in creep_rows:
            lines.append(f"- {label}: " + "; ".join(note_list))
        lines.append("")

    hero_rows = []
    for hero in notes.get("heroes") or []:
        parts = format_patch_notes(hero.get("hero_notes"))

        for ability in hero.get("abilities") or []:
            ability_notes = format_patch_notes(ability.get("ability_notes"))
            if ability_notes:
                ability_name = ability_names.get(ability.get("ability_id"))
                prefix = f"{ability_name}: " if ability_name else ""
                parts.append(prefix + "; ".join(ability_notes))

        talent_notes = format_patch_notes(hero.get("talent_notes"))
        if talent_notes:
            parts.append("Talents: " + "; ".join(talent_notes))

        if parts:
            label = hero_names.get(hero.get("hero_id")) or f"#{hero.get('hero_id')}"
            hero_rows.append((label, parts))

    if hero_rows:
        lines.append("Heroes:")
        for label, parts in hero_rows:
            lines.append(f"- {label}: " + "; ".join(parts))
        lines.append("")

    text = "\n".join(lines).strip()
    if len(text) > config.MAX_PATCH_FILE_CHARS:
        text = text[: config.MAX_PATCH_FILE_CHARS].rstrip()
        text += "\n\n[Patch notes truncated]"

    logger.info(
        "Патчи: подготовлен текст изменений %s (%d символов).",
        version,
        len(text),
    )
    return text


async def summarize_patch_with_opencode(version, context):
    safe_version = re.sub(r"[^A-Za-z0-9._-]", "_", version)
    note_path = BASE_DIR / "data" / f"patch_notes_{safe_version}.txt"
    try:
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(context, encoding="utf-8")

        command = [
            resolve_opencode(),
            "run",
            "--format",
            "json",
            (
                f"Загрузи навык {config.PATCH_SUMMARY_SKILL} через инструмент skill и сделай "
                f"краткую выжимку главных изменений патча {version} на русском языке. "
                f"Патчноуты приложены файлом и доступны по пути: {note_path}. "
                "Если вложенный файл обрезан, дочитай его инструментом read (только этот файл). "
                "Других инструментов не вызывай. Ответь только готовой выжимкой."
            ),
            f"--file={note_path}",
        ]
        logger.info(
            "Патчи: отправляю изменения %s в opencode (%d символов).",
            version,
            len(context),
        )
        started = time.perf_counter()

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(BASE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=config.PATCH_SUMMARY_TIMEOUT
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.error(
                "Патчи: opencode не ответил за %ss.", config.PATCH_SUMMARY_TIMEOUT
            )
            return None

        elapsed = time.perf_counter() - started
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if process.returncode != 0:
            logger.error(
                "Патчи: opencode завершился с кодом %s: %s",
                process.returncode,
                stderr_text,
            )
            return None

        text, usage, cost, steps = parse_opencode_output(
            stdout.decode("utf-8", errors="replace")
        )
        logger.info(
            "Патчи: opencode %.2f с, шагов=%d, токены input=%d output=%d "
            "reasoning=%d cache_read=%d cache_write=%d total=%d, стоимость=$%.6f",
            elapsed,
            steps,
            usage["input"],
            usage["output"],
            usage["reasoning"],
            usage["cache_read"],
            usage["cache_write"],
            usage["total"],
            cost,
        )

        if not text:
            logger.error("Патчи: opencode вернул пустой ответ.")
            return None
        return text
    except FileNotFoundError:
        logger.error("Патчи: opencode не найден. Укажите путь в OPENCODE_EXE.")
        return None
    except Exception as error:
        logger.error("Патчи: ошибка вызова opencode: %s", error)
        return None
    finally:
        try:
            note_path.unlink()
        except OSError:
            pass


async def check_patch_update():
    latest = await fetch_latest_patch()
    if not latest:
        return

    number = latest["patch_number"]
    previous = load_last_patch()

    if previous is None:
        save_last_patch(latest)
        logger.info("Патчи: базовый патч %s сохранён.", number)
        return

    if number == previous:
        logger.debug("Патчи: без изменений (%s).", number)
        return

    channel = bot.get_channel(config.CHANNEL_ID)
    if not channel:
        logger.error("Патчи: канал с ID %s не найден.", config.CHANNEL_ID)
        return

    url = config.PATCH_URL_TEMPLATE.format(
        version=latest.get("patch_slug") or number
    )

    summary = None
    if config.PATCH_SUMMARY_ENABLED:
        context = await fetch_patch_context(number)
        if context:
            summary = await summarize_patch_with_opencode(number, context)

    if summary:
        description = summary[: config.MAX_DESCRIPTION_LENGTH]
        logger.info("Патчи: использую выжимку opencode.")
    else:
        description = f"Вышел патч **{number}**.\n[Открыть страницу патча]({url})"
        logger.warning("Патчи: использую простое сообщение без opencode.")

    embed = discord.Embed(
        title=f"🆕 Новый патч Dota 2 — {number}",
        url=url,
        description=description,
        color=discord.Color(config.EMBED_COLOR),
    )
    await channel.send(embed=embed)
    save_last_patch(latest)
    logger.info("Патчи: опубликован новый патч %s (было %s).", number, previous)


@tasks.loop(seconds=max(1, config.PATCH_CHECK_INTERVAL))
async def patch_monitor_task():
    await check_patch_update()


@patch_monitor_task.before_loop
async def before_patch_monitor():
    await bot.wait_until_ready()


@tasks.loop(time=config.SEND_TIME)
async def daily_news_task():
    """Задача, выполняемая раз в день."""
    channel = bot.get_channel(config.CHANNEL_ID)
    if not channel:
        logger.error("Канал с ID %s не найден.", config.CHANNEL_ID)
        return

    await send_digest(channel)


@daily_news_task.before_loop
async def before_daily_news():
    await bot.wait_until_ready()


@bot.command(name="dotanews", aliases=["digest"])
async def digest_command(ctx):
    """Ручной запуск дайджеста по команде !dotanews."""
    await ctx.send("Собираю дайджест, это может занять пару минут...")
    await send_digest(ctx.channel)


@bot.event
async def on_ready():
    logger.info("Бот %s готов к работе!", bot.user)
    if not daily_news_task.is_running():
        daily_news_task.start()
    if config.PATCH_MONITOR_ENABLED and not patch_monitor_task.is_running():
        patch_monitor_task.start()
        logger.info(
            "Мониторинг патчей запущен (интервал %ss).",
            config.PATCH_CHECK_INTERVAL,
        )


if __name__ == "__main__":
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан. Проверьте .env файл.")
    bot.run(config.BOT_TOKEN)
