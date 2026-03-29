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

# Copy all project files, ensuring site.db is included
COPY . .
# Explicitly ensure site.db is in the root
COPY site.db /app/site.db


# Expose the Flask port
EXPOSE 5000

# Start command
CMD ["python", "app.py"]

