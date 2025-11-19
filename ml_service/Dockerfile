FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements
COPY ml_service/requirements.txt ./ml_requirements.txt
COPY shared/requirements.txt ./shared_requirements.txt
COPY shared/ ./shared/

# Установка Python зависимостей
# Сначала устанавливаем зависимости из shared, затем из ml_service
# Удаляем строки с -r ../shared/requirements.txt из ml_requirements.txt
RUN python3 -c "import sys; lines = [l for l in open('ml_requirements.txt') if not l.strip().startswith('-r') and 'shared/requirements.txt' not in l]; open('ml_requirements_clean.txt', 'w').writelines(lines)" && \
    pip install --no-cache-dir -r shared_requirements.txt && \
    pip install --no-cache-dir -r ml_requirements_clean.txt

# Копирование кода сервиса
COPY ml_service/ ./ml_service/

# Создание __init__.py для shared, если его нет
RUN touch shared/__init__.py || true

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "ml_service.app:app", "--host", "0.0.0.0", "--port", "8001"]

