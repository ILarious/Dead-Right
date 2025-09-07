#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PID_FILE="$BASE_DIR/bot.pid"

stop_pid() {
  local pid="$1"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true

    for _ in {1..20}; do
      if kill -0 "$pid" 2>/dev/null; then
        sleep 0.5
      else
        break
      fi
    done

    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "🛑 Бот остановлен (PID $pid)"
  else
    echo "ℹ️ Процесс с PID $pid не найден"
  fi
}

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  stop_pid "$PID"
  rm -f "$PID_FILE"
else

  PIDS="$(pgrep -f "[p]ython.*bot.py" || true)"
  if [[ -n "${PIDS:-}" ]]; then
    for p in $PIDS; do stop_pid "$p"; done
  else
    echo "❌ Бот не найден"
  fi
fi

