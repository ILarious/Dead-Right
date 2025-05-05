#!/bin/bash
PID=$(ps aux | grep '/opt/alt/python311/bin/python3.11 bot.py' | grep -v grep | awk '{print $2}')
if [ -n "$PID" ]; then
    kill "$PID"
    echo "🛑 Бот остановлен (PID $PID)"
else
    echo "❌ Бот не найден"
fi
