# Руководство по файловому выводу Output Service

## 📍 Где находятся файлы

### Текущая настройка (по умолчанию)

В `docker-compose.yml` используется **Docker volume** `output_data`, который маппится на `/app/output` внутри контейнера:

```yaml
output-service:
  volumes:
    - output_data:/app/output  # Docker volume (не доступен напрямую на хосте)
  environment:
    - OUTPUT_DIR=/app/output
```

**Файлы находятся:** Внутри Docker контейнера по пути `/app/output/`

### Как получить доступ к файлам

#### Способ 1: Просмотр файлов внутри контейнера

```bash
# Список всех файлов
docker exec service-desk-output ls -la /app/output

# Поиск файла по ticket_id
docker exec service-desk-output ls -la /app/output | grep tick_d476c3aa

# Просмотр содержимого файла
docker exec service-desk-output cat /app/output/tick_d476c3aa_*.json

# Windows PowerShell:
docker exec service-desk-output ls -la /app/output
docker exec service-desk-output cat /app/output/tick_d476c3aa_*.json
```

#### Способ 2: Копирование файла на хост

```bash
# Копирование конкретного файла
docker cp service-desk-output:/app/output/tick_d476c3aa_*.json ./output_file.json

# Копирование всех файлов
docker cp service-desk-output:/app/output/. ./out/

# Windows PowerShell:
docker cp service-desk-output:/app/output/tick_d476c3aa_*.json .\output_file.json
```

#### Способ 3: Настройка bind mount (рекомендуется для демо)

**Измените `docker-compose.yml`:**

```yaml
output-service:
  volumes:
    # Замените Docker volume на bind mount
    - ./out:/app/output  # Вместо: - output_data:/app/output
```

**После изменения:**
```bash
# Создайте папку на хосте
mkdir -p ./out

# Пересоздайте контейнер
docker-compose down
docker-compose up -d
```

**Теперь файлы будут доступны:**
- **Windows:** `C:\04_LM\ai_hack\service-desk-classifier\out\`
- **Linux/Mac:** `./out/` (относительно корня проекта)

## 🔍 Поиск файла для тикета `tick_d476c3aa`

### Если файл уже создан:

```bash
# Поиск внутри контейнера
docker exec service-desk-output sh -c "ls -la /app/output/tick_d476c3aa_*.json"

# Просмотр содержимого
docker exec service-desk-output cat /app/output/tick_d476c3aa_*.json

# Копирование на хост
docker cp service-desk-output:/app/output/tick_d476c3aa_*.json ./tick_d476c3aa_output.json
```

### Если файл еще не создан:

Файл создается только после успешной обработки тикета (статус `completed`).

**Проверьте статус тикета:**
```bash
# Через API
curl -s "http://localhost:8000/status/tick_d476c3aa" | jq

# Или через Swagger: http://localhost:8000/docs#/
# GET /status/{ticket_id}
```

**Если тикет в статусе `queued` или `processing`:**
- Дождитесь завершения обработки
- Или переобработайте тикет: `POST /tickets/tick_d476c3aa/reprocess`

## 📝 Формат имени файла

Файлы создаются в формате: `{ticket_id}_{timestamp}.json`

**Пример:**
- `tick_d476c3aa_20251129T084833.json`
- `tick_XXXXXXXX_YYYYMMDDTHHMMSS.json`

Где:
- `ticket_id` - ID тикета (например, `tick_d476c3aa`)
- `timestamp` - Время создания в формате `YYYYMMDDTHHMMSS` (UTC)

## 🔧 Настройка пути вывода

### Переменная окружения OUTPUT_DIR

**В docker-compose.yml:**
```yaml
output-service:
  environment:
    - OUTPUT_DIR=/app/output  # Путь внутри контейнера
```

**Для bind mount на хосте:**
```yaml
output-service:
  volumes:
    - ./out:/app/output  # Маппинг ./out (хост) -> /app/output (контейнер)
  environment:
    - OUTPUT_DIR=/app/output  # Путь внутри контейнера (не меняется)
```

**Для другой папки на хосте:**
```yaml
output-service:
  volumes:
    - C:/MyOutput:/app/output  # Windows абсолютный путь
    # или
    - /home/user/output:/app/output  # Linux абсолютный путь
```

## 📊 Проверка настройки

```bash
# Проверить, какой volume используется
docker inspect service-desk-output | grep -A 10 "Mounts"

# Проверить переменную OUTPUT_DIR
docker exec service-desk-output env | grep OUTPUT_DIR

# Проверить, существует ли директория
docker exec service-desk-output ls -ld /app/output
```

## 🧹 Очистка файлов

**Если используете bind mount:**
```bash
# На хосте
rm -rf ./out/*
mkdir -p ./out

# Windows PowerShell:
Remove-Item .\out\* -Recurse -Force
New-Item -ItemType Directory -Path .\out -Force
```

**Если используете Docker volume:**
```bash
# Внутри контейнера
docker exec service-desk-output sh -c "rm -rf /app/output/*"
```

## 💡 Рекомендации для демонстрации

1. **Используйте bind mount** для прямого доступа к файлам:
   ```yaml
   volumes:
     - ./out:/app/output
   ```

2. **Создайте папку заранее:**
   ```bash
   mkdir -p ./out
   ```

3. **Откройте папку в проводнике перед демо:**
   ```bash
   # Windows
   explorer .\out
   
   # Linux
   nautilus ./out
   
   # Mac
   open ./out
   ```

4. **Покажите файлы в реальном времени** - они будут появляться сразу после обработки тикетов.

