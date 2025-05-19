# ===========================
# Мультиетапна збірка для tradingruhal
# ===========================

# --- Етап 1: build dependencies ---
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /app

# Оновлення та встановлення build-залежностей
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        build-essential \
        gcc \
        libffi-dev \
        libssl-dev \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# Копіюємо лише requirements для ефективного кешування
COPY requirements.txt .

# Оновлення pip та встановлення залежностей у build-образі
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# --- Етап 2: фінальний образ ---
FROM python:${PYTHON_VERSION}-slim

WORKDIR /app

# Встановлення runtime-залежностей та timezone (за потреби)
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# Копіюємо встановлені залежності з build-образу
COPY --from=builder /install /usr/local

# Копіюємо лише необхідні файли проекту (ігноруйте зайві через .dockerignore)
COPY . .

# Безпека: створення non-root користувача
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Встановлення часової зони (за потреби)
ENV TZ=Europe/Kyiv

# Передача чутливих змінних через ARG (у продакшені краще через secrets)
ARG BINANCE_API_KEY
ARG BINANCE_API_SECRET
ENV BINANCE_API_KEY=${BINANCE_API_KEY}
ENV BINANCE_API_SECRET=${BINANCE_API_SECRET}

# HEALTHCHECK: перевірка, що контейнер "живий"
HEALTHCHECK --interval=1m --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import socket; s=socket.socket(); s.connect(('binance.com', 443))" || exit 1

# Відкрийте порт, якщо сервіс — веб (наприклад, FastAPI/Flask)
# EXPOSE 8000

# Інформативна команда запуску
# Змініть на свій основний скрипт або менеджер процесів (uvicorn, gunicorn тощо)
CMD ["python", "main.py"]
