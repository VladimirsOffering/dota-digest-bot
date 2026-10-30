#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-dota-digest-bot}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-${SCRIPT_DIR}/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

log() { printf '%s\n' "$*"; }
die() { printf 'Ошибка: %s\n' "$*" >&2; exit 1; }

if [[ "$(id -u)" -ne 0 ]]; then
    die "Запустите с sudo: sudo bash $0"
fi

command -v systemctl >/dev/null 2>&1 || die "systemctl не найден. Нужна система с systemd."
command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "Не найден $PYTHON_BIN."
[[ -f "$SCRIPT_DIR/bot.py" ]] || die "bot.py не найден рядом со скриптом."
[[ -f "$SCRIPT_DIR/.opencode/skill/dota-digest/SKILL.md" ]] \
    || die "Не найден .opencode/skill/dota-digest/SKILL.md (нужен для промпта)."
[[ -f "$SCRIPT_DIR/.opencode/skill/patch-digest/SKILL.md" ]] \
    || die "Не найден .opencode/skill/patch-digest/SKILL.md (нужен для промпта)."

"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
    || die "Нужен Python 3.10 или новее."

BOT_USER="${BOT_USER:-${SUDO_USER:-root}}"
id -u "$BOT_USER" >/dev/null 2>&1 || die "Пользователь $BOT_USER не существует."
BOT_GROUP="${BOT_GROUP:-$(id -gn "$BOT_USER")}"

if [[ "$BOT_USER" == "root" ]]; then
    log "Внимание: сервис будет работать от root. Можно задать BOT_USER=имя."
fi

created=0
if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    [[ -f "$SCRIPT_DIR/env-example" ]] || die "Не найден env-example."
    cp "$SCRIPT_DIR/env-example" "$SCRIPT_DIR/.env"
    chown "$BOT_USER:$BOT_GROUP" "$SCRIPT_DIR/.env" || true
    log "Создан .env из env-example."
    created=1
fi

if [[ ! -f "$SCRIPT_DIR/config.py" ]]; then
    [[ -f "$SCRIPT_DIR/config-example.py" ]] || die "Не найден config-example.py."
    cp "$SCRIPT_DIR/config-example.py" "$SCRIPT_DIR/config.py"
    chown "$BOT_USER:$BOT_GROUP" "$SCRIPT_DIR/config.py" || true
    log "Создан config.py из config-example.py."
    created=1
fi

if [[ "$created" -eq 1 ]]; then
    log ""
    log "Заполните .env (BOT_TOKEN, DEEPSEEK_API_KEY) и config.py (CHANNEL_ID, OWNER_ID),"
    log "затем запустите скрипт снова."
    exit 1
fi

if grep -q '^BOT_TOKEN=your_discord_bot_token_here' "$SCRIPT_DIR/.env"; then
    die "Укажите BOT_TOKEN в $SCRIPT_DIR/.env"
fi

if grep -q '123456789012345678' "$SCRIPT_DIR/config.py"; then
    die "Укажите реальные CHANNEL_ID и OWNER_ID в $SCRIPT_DIR/config.py"
fi

if grep -q '^DEEPSEEK_API_KEY=your_deepseek_api_key_here' "$SCRIPT_DIR/.env"; then
    log "Внимание: DEEPSEEK_API_KEY не заполнен. Понадобится fallback на opencode."
fi

chown "$BOT_USER:$BOT_GROUP" "$SCRIPT_DIR/.env" "$SCRIPT_DIR/config.py" 2>/dev/null || true
mkdir -p "$SCRIPT_DIR/logs" "$SCRIPT_DIR/data"
chown -R "$BOT_USER:$BOT_GROUP" "$SCRIPT_DIR/logs" "$SCRIPT_DIR/data" 2>/dev/null || true

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    log "Создаю виртуальное окружение: $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR" \
        || die "Не удалось создать venv. Установите python3-venv: sudo apt install python3-venv python3-full"
fi

log "Устанавливаю зависимости..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV_DIR/bin/python" -m pip install discord.py aiohttp feedparser python-dotenv

if command -v sudo >/dev/null 2>&1; then
    sudo -u "$BOT_USER" test -r "$SCRIPT_DIR/bot.py" \
        || die "Пользователь $BOT_USER не может прочитать $SCRIPT_DIR. Проверьте права."
    sudo -u "$BOT_USER" test -r "$SCRIPT_DIR/.env" \
        || die "Пользователь $BOT_USER не может прочитать .env."
fi

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Dota 2 Digest Discord Bot
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=${BOT_USER}
Group=${BOT_GROUP}
WorkingDirectory="${SCRIPT_DIR}"
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONUTF8=1
ExecStart="${VENV_DIR}/bin/python" "${SCRIPT_DIR}/bot.py"
Restart=always
RestartSec=5
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME.service"
systemctl restart "$SERVICE_NAME.service"

sleep 2
if systemctl is-active --quiet "$SERVICE_NAME.service"; then
    log ""
    log "Готово: сервис $SERVICE_NAME запущен и включён в автозапуск."
    log "Логи: journalctl -u $SERVICE_NAME -f"
else
    log ""
    log "Сервис установлен, но не запустился. Проверьте:"
    log "  systemctl status $SERVICE_NAME"
    log "  journalctl -u $SERVICE_NAME -n 50 --no-pager"
    exit 1
fi
