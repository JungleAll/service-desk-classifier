FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements
COPY output_service/requirements.txt .
COPY shared/requirements.txt ./shared_requirements.txt
COPY shared/ ./shared/

# Установка Python зависимостей
RUN pip install --no-cache-dir -r shared_requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Копирование кода сервиса
COPY output_service/ ./output_service/

# Создание __init__.py для shared, если его нет
RUN touch shared/__init__.py || true

EXPOSE 8003

CMD ["python", "-m", "uvicorn", "output_service.app:app", "--host", "0.0.0.0", "--port", "8003"]

