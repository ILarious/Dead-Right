#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PID_FILE="$BASE_DIR/bot.pid"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "✅ Бот запущен (PID $PID)"
    exit 0
  else
    echo "⚠️ PID-файл есть, но процесса нет. Удалите $PID_FILE при необходимости."
    exit 1
  fi
else

  if pgrep -f "[p]ython.*bot.py" >/dev/null 2>&1; then
    echo "✅ Бот запущен (найден по имени процесса), но нет bot.pid"
    exit 0
  fi
  echo "❌ Бот не работает"
  exit 3
fi

