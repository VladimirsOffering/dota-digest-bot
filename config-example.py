# Пример конфигурации.
# Скопируйте этот файл в config.py и замените значения-заглушки на свои.

import os
from datetime import datetime, time

from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

# --- СЕКРЕТЫ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- ДОСТУП ---
# Команды бота может использовать только этот пользователь.
# Замените заглушку на свой Discord ID или задайте OWNER_ID в .env.
OWNER_ID = int(os.getenv("OWNER_ID", "123456789012345678"))

# --- КАНАЛ ---
CHANNEL_ID = 123456789012345678  # ID канала для дайджеста

# --- ИСТОЧНИКИ ДАЙДЖЕСТА ---
# Можно добавлять/убирать источники: "Название": "ссылка на RSS".
RSS_SOURCES = {
    "Steam": (
        "https://store.steampowered.com/feeds/news/app/570/"
        "?cc=US&l=english&snr=1_2108_9__2107"
    ),
    "Reddit r/DotA2": "https://www.reddit.com/r/DotA2/.rss",
    "Bing News": "https://www.bing.com/news/search?q=Dota+2&format=RSS",
    "Dotabuff": "https://www.dotabuff.com/blog.rss",
    "Dota2.ru": "https://dota2.ru/news/rss/",
}

# Некоторые сайты (например, Reddit) отдают 403 без User-Agent.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) dota-news-bot/1.0"
REQUEST_TIMEOUT = 20        # Таймаут запроса к источнику, секунд
RETRY_COUNT = 1             # Повторы запроса при HTTP 429/5xx
RETRY_DELAY = 5             # Пауза между повторами, секунд

# --- РАСПИСАНИЕ ---
# Время отправки — локальное время машины (часовой пояс определяется автоматически).
SEND_HOUR = 18
SEND_MINUTE = 0
SEND_TZ = datetime.now().astimezone().tzinfo
SEND_TIME = time(hour=SEND_HOUR, minute=SEND_MINUTE, tzinfo=SEND_TZ)

# --- ФОРМАТИРОВАНИЕ СВОДКИ ---
MAX_ITEMS_PER_SOURCE = 5    # Сколько кандидатов брать из каждого источника
NEWS_WINDOW_HOURS = 24      # Брать только записи за последние N часов
MAX_TITLE_LENGTH = 100      # Максимальная длина заголовка
MAX_SUMMARY_LENGTH = 250    # Максимальная длина описания из RSS
MAX_DESCRIPTION_LENGTH = 3000  # Лимит Discord — 4096

# --- КАРТИНКИ ---
SHOW_IMAGES = True          # Добавлять карточки с картинками к сводке
MAX_DIGEST_IMAGES = 4       # Сколько карточек с картинками прикреплять (embed'ов всего <= 10)
MAX_IMAGE_CHECKS = 8        # Сколько ссылок на картинки проверять за один запуск
IMAGE_TIMEOUT = 10          # Таймаут проверки картинки, секунд
IMAGE_WIDTH = 640           # Размер для картинок Bing
IMAGE_HEIGHT = 360

# --- OPENCODE (локальная выжимка) ---
OPENCODE_ENABLED = True
OPENCODE_EXE = os.getenv("OPENCODE_EXE")   # Путь к opencode.exe (необязательно)
OPENCODE_MODEL = os.getenv("OPENCODE_MODEL")  # Например, "deepseek/deepseek-flash"
OPENCODE_COMMAND = "dota-digest"           # Команда из .opencode/command
OPENCODE_TIMEOUT = 240                      # Таймаут вызова opencode, секунд
MAX_PROMPT_LENGTH = 16000                   # Ограничение на аргументы командной строки

# --- DEEPSEEK API ---
LLM_BACKEND = "deepseek"                    # "deepseek" или "opencode"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_TIMEOUT = 180                      # Таймаут запроса к API, секунд
DEEPSEEK_MAX_TOKENS = 2500                  # Максимум токенов в ответе
DEEPSEEK_TEMPERATURE = 0.3
DEEPSEEK_RETRY_COUNT = 2                    # Повторы при 429/5xx
DEEPSEEK_RETRY_DELAY = 5                    # Пауза между повторами, секунд

# --- МОНИТОРИНГ ПАТЧЕЙ ---
PATCH_MONITOR_ENABLED = True
PATCH_LIST_URL = "https://www.dota2.com/datafeed/patchnoteslist?language=english"
PATCH_URL_TEMPLATE = "https://www.dota2.com/patches/{version}"
PATCH_CHECK_INTERVAL = 60   # Как часто проверять патчи, секунд
PATCH_REQUEST_TIMEOUT = 20  # Таймаут запроса к API, секунд
PATCH_STATE_FILE = "data/last_patch.json"  # Где хранить последний увиденный патч

# --- ИИ-ВЫЖИМКА ПАТЧА ---
PATCH_SUMMARY_ENABLED = True
PATCH_SUMMARY_SKILL = "patch-digest"        # Навык из .opencode/skill
PATCH_SUMMARY_TIMEOUT = 300                 # Таймаут вызова opencode, секунд
PATCH_NOTES_URL = "https://www.dota2.com/datafeed/patchnotes?version={version}&language=english"
PATCH_HERO_LIST_URL = "https://www.dota2.com/datafeed/herolist?language=english"
PATCH_ITEM_LIST_URL = "https://www.dota2.com/datafeed/itemlist?language=english"
PATCH_ABILITY_LIST_URL = "https://www.dota2.com/datafeed/abilitylist?language=english"
PATCH_META_TIMEOUT = 60                     # Таймаут загрузки списков героев/предметов
MAX_PATCH_NOTE_LENGTH = 300                 # Максимальная длина одной строки изменений
MAX_PATCH_FILE_CHARS = 100000               # Лимит текста патчноутов для модели

# --- ЛОГИ ---
LOG_DIR = "logs"            # Папка для локальных логов (рядом с config.py)
LOG_FILE = "bot.log"        # Имя файла лога
LOG_LEVEL = "INFO"          # DEBUG / INFO / WARNING / ERROR

# --- КОСМЕТИКА EMBED ---
EMBED_TITLE = "📰 Дайджест Dota 2"
EMBED_COLOR = 0xE53935      # Красный (Dota-стиль), в hex
