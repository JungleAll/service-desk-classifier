# Инструкция по тестированию пайплайна

## Быстрый старт

### 1. Запуск инфраструктуры

```bash
# Запуск всех сервисов
docker-compose up -d --build

# Ожидание готовности (30-60 секунд)
docker-compose ps

# Проверка логов (опционально)
docker-compose logs -f --tail=50
```

### 2. Установка зависимостей для тестов

```bash
pip install requests psycopg2-binary redis
```

### 3. Запуск комплексного теста

```bash
# Полный тест пайплайна (рекомендуется)
python test_pipeline.py
```

Этот скрипт автоматически:
- ✅ Проверяет работоспособность всех сервисов
- ✅ Создает тестовый тикет
- ✅ Отслеживает обработку до завершения
- ✅ Проверяет данные в PostgreSQL
- ✅ Проверяет кэш в Redis
- ✅ Проверяет создание выходного файла

---

## Детальное тестирование компонентов

### Проверка PostgreSQL

```bash
# Проверка всех данных
python test_postgresql.py

# Проверка конкретного тикета
python test_postgresql.py tick_XXXXXXXX
```

**Что проверяется:**
- Таблица `ticket_events` - записи тикетов
- Таблица `audit_logs` - логи действий
- Таблица `metrics` - метрики модели

### Проверка Redis

```bash
# Общая проверка
python test_redis.py

# Проверка кэша для конкретного текста
python test_redis.py "Текст обращения"
```

**Что проверяется:**
- Очереди (DB 0): `pending_tickets`, `failed_tickets`
- Кэш (DB 1): ключи `cache_predictions:*`
- TTL кэша
- Статистика использования

### Проверка выходных файлов

```bash
# Проверка всех файлов
python test_output_files.py

# Проверка конкретного файла
python test_output_files.py tick_XXXXXXXX_20250118T123456.json
```

**Что проверяется:**
- Наличие файлов в `/app/output`
- Валидность JSON
- Структура данных
- Обязательные поля

**Результат:** Файлы сохраняются локально в `test_outputs/` для демонстрации

---

## Ручная проверка через API

### 1. Создание тикета

```bash
curl -X POST http://localhost:8000/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "text": "У меня не работает принтер",
    "source": "manual_test",
    "email": "test@example.com"
  }'
```

### 2. Проверка статуса

```bash
curl http://localhost:8000/status/tick_XXXXXXXX
```

### 3. Получение деталей

```bash
curl http://localhost:8000/tickets/tick_XXXXXXXX
```

---

## Ручная проверка через SQL

### Подключение к PostgreSQL

```bash
docker exec -it service-desk-postgres psql -U postgres -d service_desk_db
```

### Полезные запросы

```sql
-- Последние 10 тикетов
SELECT ticket_id, status, predicted_type, confidence, created_at
FROM ticket_events
ORDER BY created_at DESC
LIMIT 10;

-- Статистика по статусам
SELECT status, COUNT(*) as count
FROM ticket_events
GROUP BY status;

-- Проверка конкретного тикета
SELECT *
FROM ticket_events
WHERE ticket_id = 'tick_XXXXXXXX';

-- Audit logs для тикета
SELECT *
FROM audit_logs
WHERE ticket_id = 'tick_XXXXXXXX'
ORDER BY created_at DESC;
```

---

## Ручная проверка Redis

### Подключение к Redis

```bash
# Очереди (DB 0)
docker exec -it service-desk-redis redis-cli -n 0

# Кэш (DB 1)
docker exec -it service-desk-redis redis-cli -n 1
```

### Полезные команды

```bash
# Длина очереди
LLEN pending_tickets

# Просмотр очереди
LRANGE pending_tickets 0 -1

# Поиск ключей кэша
KEYS cache_predictions:*

# Получение значения кэша
GET cache_predictions:v1.0:<hash>

# TTL ключа
TTL cache_predictions:v1.0:<hash>
```

---

## Просмотр выходных файлов

### Список файлов

```bash
docker exec -it service-desk-output ls -lh /app/output
```

### Просмотр содержимого

```bash
docker exec -it service-desk-output cat /app/output/tick_XXXXXXXX_20250118T123456.json
```

### Копирование файла локально

```bash
docker cp service-desk-output:/app/output/tick_XXXXXXXX_20250118T123456.json ./output_file.json
```

---

## Устранение проблем

### Проблема: Сервисы не запускаются

```bash
# Проверка логов
docker-compose logs

# Перезапуск
docker-compose restart

# Полная пересборка
docker-compose down
docker-compose up -d --build
```

### Проблема: Тикет застрял в статусе 'queued'

```bash
# Проверка Worker
docker-compose logs ml-service | grep -i worker

# Проверка очереди Redis
docker exec -it service-desk-redis redis-cli -n 0 LLEN pending_tickets
```

### Проблема: Файлы не создаются

```bash
# Проверка DESTINATION_TYPE
docker-compose config | grep DESTINATION_TYPE

# Проверка прав доступа
docker exec -it service-desk-output ls -ld /app/output

# Проверка логов Output Service
docker-compose logs output-service
```

---

## Критерии успешного тестирования

✅ **Все проверки пройдены, если:**

1. **PostgreSQL:**
   - Тикет создан со статусом 'queued'
   - После обработки статус 'completed'
   - Заполнены: predicted_type, confidence, decision
   - Создана запись в audit_logs

2. **Redis:**
   - Задача добавлена в pending_tickets
   - После обработки создан ключ в кэше
   - TTL кэша = 3600 секунд
   - Повторная классификация использует кэш

3. **Выходные файлы:**
   - Файл создан в /app/output
   - Валидный JSON
   - Все обязательные поля присутствуют
   - Файл сохранен локально в test_outputs/

---

## Дополнительные тесты

### Тест кэширования

Создайте два тикета с одинаковым текстом и проверьте, что второй обрабатывается быстрее:

```bash
# Первый тикет
python test_pipeline.py

# Второй тикет (тот же текст)
python test_pipeline.py
```

### Тест пакетной обработки

```bash
curl -X POST http://localhost:8000/tickets/batch \
  -H "Content-Type: application/json" \
  -d '{
    "tickets": [
      {"text": "Проблема 1", "source": "batch"},
      {"text": "Проблема 2", "source": "batch"},
      {"text": "Проблема 3", "source": "batch"}
    ]
  }'
```

---

**Дата создания:** 2025-01-18

