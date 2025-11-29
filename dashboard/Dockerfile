FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements
COPY dashboard/requirements.txt .
COPY shared/requirements.txt ./shared_requirements.txt
COPY shared/ ./shared/

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r shared_requirements.txt

# Копирование кода dashboard
COPY dashboard/ ./dashboard/

# Создание __init__.py для shared, если его нет
RUN touch shared/__init__.py || true

EXPOSE 8501

# Запуск Streamlit
CMD ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]

