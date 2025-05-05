#!/bin/bash
cd /home/users/j/j44835216/Dead-Right
echo "▶️ Запуск бота..."
nohup /opt/alt/python311/bin/python3.11 bot.py > bot.log 2>&1 &
echo "✅ Бот запущен. PID: $!"
