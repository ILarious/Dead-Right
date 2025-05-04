# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальные файлы проекта
COPY . .

# Устанавливаем переменную окружения (лучше задавать через docker run или .env)
ENV BOT_TOKEN=${BOT_TOKEN}

# Команда запуска
CMD ["python", "bot.py"]