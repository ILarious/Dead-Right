#!/bin/bash
PID=$(ps aux | grep '/opt/alt/python311/bin/python3.11 bot.py' | grep -v grep | awk '{print $2}')
if [ -n "$PID" ]; then
    echo "✅ Бот запущен (PID $PID)"
else
    echo "❌ Бот не работает"
fi
