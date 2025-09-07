#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$BASE_DIR"


if [[ -x "$BASE_DIR/.venv/bin/python" ]]; then
  PYTHON="$BASE_DIR/.venv/bin/python"
else
  PYTHON="$(command -v python3 || command -v python)"
fi

mkdir -p "$BASE_DIR/logs"
LOG_FILE="$BASE_DIR/logs/bot.log"
PID_FILE="$BASE_DIR/bot.pid"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "⚠️ Бот уже запущен (PID $(cat "$PID_FILE"))."
  exit 0
fi

echo "▶️ Запуск бота..."
nohup "$PYTHON" "$BASE_DIR/bot.py" >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "✅ Бот запущен. PID: $(cat "$PID_FILE")"
echo "📄 Логи: $LOG_FILE"
