FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements
COPY ingestion_service/requirements.txt .
COPY shared/requirements.txt ./shared_requirements.txt
COPY shared/ ./shared/

# Установка Python зависимостей
RUN pip install --no-cache-dir -r shared_requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Копирование кода сервиса
COPY ingestion_service/ ./ingestion_service/

# Создание __init__.py для shared, если его нет
RUN touch shared/__init__.py || true

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "ingestion_service.app:app", "--host", "0.0.0.0", "--port", "8000"]

