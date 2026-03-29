# Используем официальный легкий образ Python
FROM python:3.11-slim

# Установка системных зависимостей для корректной работы Pillow и Python
RUN apt-get update && apt-get install -y \
    build-essential \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    tk-dev \
    tcl-dev \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию в контейнере
WORKDIR /app

# Устанавливаем переменные окружения
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Сначала копируем только requirements.txt для эффективного кэширования слоев Docker
COPY requirements.txt .

# Установка Python-зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта в контейнер
COPY . .

# Открываем порт 5000 (стандартный для Flask)
EXPOSE 5000

# Команда запуска приложения (через Gunicorn для продакшена)
# Если gunicorn не в реквайрментах, доставим или используем flask run
CMD ["python", "app.py"]
