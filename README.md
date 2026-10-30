# Dota 2 News Bot

Discord-бот для дайджеста новостей Dota 2. Собирает материалы из нескольких RSS-источников, передаёт их в DeepSeek API (по умолчанию) или локальному [opencode](https://opencode.ai) для краткой выжимки и публикует результат в канал. Отдельно следит за выходом новых патчей и делает ИИ-выжимку главных изменений.

## Возможности

- Сбор новостей из Steam, Reddit r/DotA2, Bing News, Dotabuff и Dota2.ru.
- Фильтр по времени: только записи за последние `NEWS_WINDOW_HOURS` часов.
- DeepSeek выбирает 5–8 самых важных и популярных новостей, а не пересказывает всё подряд.
- Каждый пункт выжимки содержит ссылку на источник.
- Карточки с картинками для новостей, у которых есть изображение.
- Ежедневная автоматическая отправка в заданное локальное время.
- Ручной запуск дайджеста командой `!dotanews` (доступно только владельцу).
- Мониторинг патчей раз в минуту через официальный datafeed Dota 2.
- При выходе нового патча — ИИ-выжимка основных изменений; без ИИ, если модель недоступна.
- Fallback на локальный opencode, если DeepSeek API недоступен.
- Логи с источниками, количеством записей и токенами вызовов LLM.

## Требования

- Python 3.10+
- Discord-бот с включённым **Message Content Intent**
- Ключ DeepSeek API (для основного режима)
- Доступ бота к каналу: просмотр, отправка сообщений, встраивание ссылок (Embed Links)
- Опционально: установленный и настроенный opencode как fallback

Зависимости Python:

```bash
pip install discord.py aiohttp feedparser python-dotenv
```

## Установка

### 1. Клонирование и зависимости

```bash
git clone <repo-url>
cd dota_news_bot

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install discord.py aiohttp feedparser python-dotenv
```

### 2. Настройка

Создайте локальные файлы из шаблонов:

```bash
# Windows
copy env-example .env
copy config-example.py config.py

# Linux/macOS
cp env-example .env
cp config-example.py config.py
```

В `.env` укажите токен бота и ключ DeepSeek:

```env
BOT_TOKEN=your_discord_bot_token
DEEPSEEK_API_KEY=your_deepseek_api_key
```

Опционально в `.env`:

```env
OWNER_ID=123456789012345678
OPENCODE_EXE=C:\path\to\opencode.exe
OPENCODE_MODEL=deepseek/deepseek-flash
```

Если `DEEPSEEK_API_KEY` не задан, бот попробует взять ключ из `~/.local/share/opencode/auth.json` (временный fallback). Для переносимости лучше всегда задавать ключ явно в `.env`.

В `config.py` задайте как минимум `CHANNEL_ID` и `OWNER_ID`. Остальные настройки — источники, расписание, лимиты, картинки и патчи — также находятся там.

Файлы `.env` и `config.py` добавлены в `.gitignore` и не должны попадать в репозиторий.

### 3. Discord

1. Создайте приложение и бота в Discord Developer Portal.
2. Включите **Message Content Intent** в настройках бота.
3. Пригласите бота на сервер с правами на чтение канала, отправку сообщений и Embed Links.
4. Скопируйте ID канала и укажите его в `config.py` как `CHANNEL_ID`.

### 4. Запуск

Windows:

```bat
start.bat
```

Или вручную:

```bash
python bot.py
```

## Команды

| Команда | Описание |
| --- | --- |
| `!dotanews` | Собрать и отправить дайджест в текущий канал |
| `!digest` | Алиас `!dotanews` |
| `!help` | Встроенная справка |

Команды может использовать только пользователь с ID `OWNER_ID`. Автоматические задачи (ежедневный дайджест и мониторинг патчей) работают независимо от команд.

## Как это работает

### Ежедневный дайджест

1. Параллельно запрашиваются все RSS-источники из `RSS_SOURCES`.
2. Записи старше `NEWS_WINDOW_HOURS` отбрасываются.
3. Из каждого источника берётся до `MAX_ITEMS_PER_SOURCE` кандидатов.
4. Текст передаётся в DeepSeek API. Правила выжимки берутся из навыка `dota-digest`: модель выбирает главные новости и оформляет их на русском со ссылками на источники.
5. В канал отправляется embed с выжимкой и карточки с картинками (до `MAX_DIGEST_IMAGES`).
6. Если DeepSeek недоступен, бот пробует opencode; если и он недоступен — отправляется резервный список заголовков.

### Мониторинг патчей

1. Каждые `PATCH_CHECK_INTERVAL` секунд запрашивается `datafeed/patchnoteslist`.
2. Последний патч сравнивается с сохранённым в `data/last_patch.json`.
3. При первом запуске текущий патч сохраняется как базовый без публикации.
4. При появлении нового патча загружаются патчноуты и названия героев/предметов, формируется текст изменений.
5. Текст передаётся в DeepSeek API. Правила выжимки берутся из навыка `patch-digest`; для больших патчей текст обрезается до `MAX_PATCH_FILE_CHARS`.
6. В канал уходит сообщение «Новый патч Dota 2 — версия» со ссылкой на страницу патча и выжимкой.
7. Если LLM недоступен, отправляется простое сообщение о выходе патча.

## Основные настройки

В `config.py`:

- `CHANNEL_ID` — канал для публикаций.
- `OWNER_ID` — ID пользователя, которому разрешены команды.
- `RSS_SOURCES` — словарь источников `"Название": "URL RSS"`.
- `NEWS_WINDOW_HOURS` — окно новостей в часах.
- `MAX_ITEMS_PER_SOURCE` — сколько кандидатов брать из каждого источника.
- `SEND_HOUR`, `SEND_MINUTE`, `SEND_TZ` — время ежедневной отправки (локальное время машины).
- `SHOW_IMAGES`, `MAX_DIGEST_IMAGES` — карточки с картинками.
- `LLM_BACKEND` — `"deepseek"` (по умолчанию) или `"opencode"`.
- `DEEPSEEK_API_KEY`, `DEEPSEEK_API_URL`, `DEEPSEEK_MODEL` — доступ к DeepSeek API.
- `DEEPSEEK_TIMEOUT`, `DEEPSEEK_MAX_TOKENS`, `DEEPSEEK_TEMPERATURE` — параметры запроса.
- `OPENCODE_ENABLED`, `OPENCODE_EXE`, `OPENCODE_MODEL` — fallback на локальный opencode.
- `PATCH_MONITOR_ENABLED`, `PATCH_CHECK_INTERVAL` — мониторинг патчей.
- `PATCH_SUMMARY_ENABLED` — ИИ-выжимка патчноутов.
- `LOG_DIR`, `LOG_FILE`, `LOG_LEVEL` — логирование.

Чтобы полностью отказаться от opencode, установите `OPENCODE_ENABLED = False`. Для возврата на opencode задайте `LLM_BACKEND = "opencode"`.

## Логи и состояние

- `logs/bot.log` — основной лог с ротацией (1 МБ, 3 файла).
- В логах: проверенные источники, количество записей, ошибки HTTP, время сбора, токены DeepSeek; для opencode — ещё и стоимость.
- `data/last_patch.json` — последний увиденный патч.
- `data/patch_notes_<version>.txt` — временный файл патчноутов для opencode-fallback, удаляется после обработки.
- `logs/` и `data/` не попадают в git.

## Структура проекта

```text
bot.py                     — логика бота, сбор, DeepSeek/opencode, патчи
config.py                  — локальная конфигурация (не в git)
config-example.py          — шаблон config.py
env-example                — шаблон .env
start.bat                  — запуск на Windows
.opencode/
  skill/dota-digest/       — правила выжимки новостей (системный промпт)
  skill/patch-digest/      — правила выжимки патчноутов (системный промпт)
  command/dota-digest.md   — команда для opencode-fallback
  command/patch-digest.md  — ручная команда для патчей
examples/
  patch_7.41f_digest.md    — пример ИИ-выжимки патча
```

## Пример

Пример выжимки патча: [examples/patch_7.41f_digest.md](examples/patch_7.41f_digest.md).

## Ограничения

- Reddit может отвечать `429 Too Many Requests`; бот делает повтор, но источник может быть пропущен.
- У Steam может не быть новостей за выбранное окно — это нормально.
- Dota2.ru не отдаёт картинки в RSS, поэтому его карточки могут быть без изображения.
- Для работы ИИ-выжимки нужен ключ DeepSeek API; opencode нужен только для fallback.
- DeepSeek API возвращает токены, но не стоимость запроса — в логах есть только токены.
- API патчей Dota 2 неофициальный и может измениться.
- Выжимка генерируется моделью; в промпте запрещено выдумывать факты, но результат стоит проверять.
