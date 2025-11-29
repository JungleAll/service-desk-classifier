# План тестирования пайплайна Service Desk Classifier

**Дата создания:** 2025-01-18  
**Версия:** 1.0  
**Цель:** Комплексная проверка работы всего пайплайна без подключения к Jira

---

## Обзор тестирования

План включает проверку всех компонентов системы:
1. ✅ **PostgreSQL** - записи в базу данных
2. ✅ **Redis** - кэширование и очереди
3. ✅ **Выходные файлы** - результаты обработки в JSON формате

---

## Этап 1: Подготовка окружения

### 1.1 Проверка зависимостей
```bash
# Проверка Docker
docker --version
docker-compose --version

# Проверка Python (для скриптов тестирования)
python --version
pip list | grep -E "requests|psycopg2|redis"
```

### 1.2 Запуск инфраструктуры
```bash
# Запуск всех сервисов
docker-compose up -d --build

# Ожидание готовности (30-60 секунд)
docker-compose ps

# Проверка логов
docker-compose logs -f --tail=50
```

### 1.3 Проверка health endpoints
```bash
# Ingestion Service
curl http://localhost:8000/health

# ML Service
curl http://localhost:8001/health

# Config Service
curl http://localhost:8002/health

# Output Service
curl http://localhost:8003/health
```

**Ожидаемый результат:** Все сервисы возвращают `"status": "healthy"`

---

## Этап 2: Тестирование полного пайплайна

### 2.1 Создание тестового тикета

**Действие:** Отправка POST запроса на создание тикета

```bash
curl -X POST http://localhost:8000/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "text": "У меня не работает принтер, пишет ошибку замятия бумаги",
    "source": "test_script",
    "email": "test@example.com",
    "user_id": "user_123"
  }'
```

**Ожидаемый результат:**
- HTTP 201 Created
- `ticket_id` в формате `tick_XXXXXXXX`
- `status: "queued"`

### 2.2 Проверка PostgreSQL (ticket_events)

**Проверяемые поля:**
- ✅ `ticket_id` - уникальный идентификатор
- ✅ `text` - исходный текст обращения
- ✅ `source` - источник ('test_script')
- ✅ `status` - статус обработки
- ✅ `created_at` - время создания
- ✅ `email`, `user_id` - метаданные

**SQL запрос для проверки:**
```sql
SELECT ticket_id, text, source, status, email, user_id, created_at
FROM ticket_events
WHERE ticket_id = 'tick_XXXXXXXX'
ORDER BY created_at DESC;
```

**Ожидаемый результат:**
- Запись создана со статусом `'queued'`
- Все поля заполнены корректно

### 2.3 Проверка Redis Queue (DB 0)

**Проверка очереди pending_tickets:**
```bash
docker exec -it service-desk-redis redis-cli -n 0 LLEN pending_tickets
docker exec -it service-desk-redis redis-cli -n 0 LRANGE pending_tickets 0 -1
```

**Ожидаемый результат:**
- Очередь содержит задачу с `ticket_id`
- Данные в формате JSON

### 2.4 Ожидание обработки Worker

**Действие:** Polling статуса тикета каждую секунду

```bash
# Скрипт автоматически опрашивает статус
python test_pipeline.py
```

**Ожидаемые переходы статусов:**
1. `queued` → создан и добавлен в очередь
2. `processing` → Worker начал обработку
3. `classified` → ML классификация завершена
4. `completed` → Output Service обработал результат

**Время обработки:** ~2-5 секунд

---

## Этап 3: Проверка ML классификации

### 3.1 Проверка Redis Cache (DB 1)

**Проверка кэша результатов классификации:**
```bash
# Получение всех ключей кэша
docker exec -it service-desk-redis redis-cli -n 1 KEYS "cache_predictions:*"

# Получение значения кэша
docker exec -it service-desk-redis redis-cli -n 1 GET "cache_predictions:v1.0:<hash>"
```

**Ожидаемый результат:**
- Ключ в формате `cache_predictions:v1.0:<md5_hash>`
- Значение содержит JSON с полями:
  - `predicted_type` - предсказанный класс
  - `confidence` - уверенность (0-1)
  - `probabilities` - вероятности всех классов
  - `model_version` - версия модели
  - `decision` - 'auto-process' или 'manual-review'
- TTL установлен на 3600 секунд (1 час)

### 3.2 Проверка PostgreSQL (ticket_events после классификации)

**Проверяемые поля:**
- ✅ `predicted_type` - категория обращения
- ✅ `confidence` - уверенность модели (0-1)
- ✅ `probabilities` - JSONB с вероятностями всех классов
- ✅ `decision` - 'auto-process' или 'manual-review'
- ✅ `model_version` - версия модели ('v1.0')
- ✅ `status` - должен быть 'classified' или 'completed'

**SQL запрос:**
```sql
SELECT 
    ticket_id,
    status,
    predicted_type,
    confidence,
    decision,
    model_version,
    probabilities,
    processed_at
FROM ticket_events
WHERE ticket_id = 'tick_XXXXXXXX';
```

**Ожидаемый результат:**
- `predicted_type` заполнен (например, 'Оборудование')
- `confidence` > 0.5
- `decision` зависит от `confidence` и порога (по умолчанию 0.7)
- `probabilities` содержит JSON с вероятностями всех категорий

### 3.3 Проверка метрик в PostgreSQL

**Проверка таблицы metrics:**
```sql
SELECT 
    model_version,
    metric_name,
    metric_value,
    calculated_at
FROM metrics
WHERE model_version = 'v1.0'
ORDER BY calculated_at DESC
LIMIT 10;
```

**Ожидаемый результат:**
- Запись с `metric_name = 'classification_count'`
- `metric_value = 1` (или больше, если было несколько запросов)

---

## Этап 4: Проверка Output Service

### 4.1 Проверка обработки результата

**Проверка таблицы audit_logs:**
```sql
SELECT 
    ticket_id,
    action,
    service_name,
    status,
    details,
    created_at
FROM audit_logs
WHERE ticket_id = 'tick_XXXXXXXX'
ORDER BY created_at DESC;
```

**Ожидаемый результат:**
- Запись с `action = 'classification_completed'`
- `service_name = 'output'`
- `status = 'success'`
- `details` содержит JSON с результатами

### 4.2 Проверка финального статуса в ticket_events

**Проверяемые поля:**
- ✅ `status = 'completed'`
- ✅ `jira_ticket_id` - ID созданного файла (формат `FS-YYYYMMDD...` или `MOCK-...`)
- ✅ `jira_link` - путь к файлу (для FileSystem) или NULL (для Mock)
- ✅ `priority` - приоритет ('medium', 'low', 'high')
- ✅ `processed_at` - время завершения обработки
- ✅ `sent_to_jira_at` - время отправки (для FileSystem/Mock)

**SQL запрос:**
```sql
SELECT 
    ticket_id,
    status,
    predicted_type,
    confidence,
    decision,
    jira_ticket_id,
    jira_link,
    priority,
    processed_at,
    sent_to_jira_at
FROM ticket_events
WHERE ticket_id = 'tick_XXXXXXXX';
```

**Ожидаемый результат:**
- `status = 'completed'`
- `jira_ticket_id` начинается с `FS-` (FileSystem) или `MOCK-` (Mock)
- `jira_link` содержит путь к файлу (для FileSystem) или NULL (для Mock)
- `priority` установлен на основе `decision`

---

## Этап 5: Проверка выходных файлов

### 5.1 Проверка создания файла (FileSystem Connector)

**Действие:** Проверка наличия файла в директории output

```bash
# Список файлов в контейнере
docker exec -it service-desk-output ls -lh /app/output

# Просмотр содержимого файла
docker exec -it service-desk-output cat /app/output/tick_XXXXXXXX_YYYYMMDDTHHMMSS.json
```

**Ожидаемый результат:**
- Файл существует в формате `{ticket_id}_{timestamp}.json`
- Содержимое файла - валидный JSON

### 5.2 Проверка структуры выходного файла

**Проверяемые поля в JSON:**
- ✅ `ticket_id` - идентификатор тикета
- ✅ `summary` - краткое описание (с категорией)
- ✅ `description` - полное описание с метаданными
- ✅ `priority` - приоритет
- ✅ `predicted_type` - предсказанная категория
- ✅ `confidence` - уверенность модели
- ✅ `model_version` - версия модели
- ✅ `decision` - решение ('auto-process' или 'manual-review')
- ✅ `email`, `user_id` - метаданные пользователя
- ✅ `probabilities` - вероятности всех классов
- ✅ `metadata` - дополнительные метаданные

**Пример структуры:**
```json
{
  "ticket_id": "tick_XXXXXXXX",
  "summary": "[Оборудование] У меня не работает принтер...",
  "description": "Текст обращения: ...\nПредсказанный тип: Оборудование\n...",
  "priority": "medium",
  "predicted_type": "Оборудование",
  "confidence": 0.95,
  "model_version": "v1.0",
  "decision": "auto-process",
  "email": "test@example.com",
  "user_id": "user_123",
  "probabilities": {...},
  "metadata": {...}
}
```

### 5.3 Проверка Mock Connector (опционально)

**Если DESTINATION_TYPE=mock:**
- Файл НЕ создается
- `jira_ticket_id` в формате `MOCK-YYYYMMDDHHMMSS`
- `jira_link` = NULL

---

## Этап 6: Тестирование кэширования

### 6.1 Повторная классификация того же текста

**Действие:** Создание второго тикета с тем же текстом

```bash
curl -X POST http://localhost:8000/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "text": "У меня не работает принтер, пишет ошибку замятия бумаги",
    "source": "test_script_2"
  }'
```

**Ожидаемый результат:**
- Время обработки значительно меньше (кэш используется)
- Результат классификации идентичен первому
- В Redis кэше используется тот же ключ

### 6.2 Проверка TTL кэша

**Действие:** Проверка времени жизни кэша

```bash
# Проверка TTL ключа
docker exec -it service-desk-redis redis-cli -n 1 TTL "cache_predictions:v1.0:<hash>"
```

**Ожидаемый результат:**
- TTL > 0 и < 3600 (уменьшается со временем)
- После 3600 секунд ключ автоматически удаляется

---

## Этап 7: Тестирование граничных случаев

### 7.1 Низкая уверенность (manual-review)

**Действие:** Создание тикета с текстом, который даст низкую уверенность

**Ожидаемый результат:**
- `decision = 'manual-review'`
- `priority` установлен в `manual_review_priority` (из Config Service)
- Файл НЕ создается (только при `auto-process`)

### 7.2 Пакетная обработка

**Действие:** Создание нескольких тикетов одновременно

```bash
curl -X POST http://localhost:8000/tickets/batch \
  -H "Content-Type: application/json" \
  -d '{
    "tickets": [
      {"text": "Проблема с компьютером", "source": "batch_test"},
      {"text": "Вопрос по программному обеспечению", "source": "batch_test"},
      {"text": "Нужна помощь с настройкой", "source": "batch_test"}
    ]
  }'
```

**Ожидаемый результат:**
- Все тикеты обработаны
- Созданы соответствующие файлы
- Записи в БД для каждого тикета

---

## Этап 8: Верификация данных

### 8.1 Сводная таблица проверок

| Компонент | Проверка | Ожидаемый результат | Статус |
|-----------|----------|---------------------|--------|
| **PostgreSQL** | | | |
| | ticket_events.created | Запись создана со статусом 'queued' | ⬜ |
| | ticket_events.classified | predicted_type, confidence заполнены | ⬜ |
| | ticket_events.completed | status='completed', jira_ticket_id установлен | ⬜ |
| | audit_logs | Запись с action='classification_completed' | ⬜ |
| | metrics | Запись с metric_name='classification_count' | ⬜ |
| **Redis** | | | |
| | Queue (DB 0) | Задача в pending_tickets | ⬜ |
| | Cache (DB 1) | Ключ cache_predictions:v1.0:<hash> | ⬜ |
| | Cache TTL | TTL = 3600 секунд | ⬜ |
| | Cache reuse | Повторная классификация использует кэш | ⬜ |
| **Output Files** | | | |
| | File creation | Файл создан в /app/output | ⬜ |
| | File format | Валидный JSON | ⬜ |
| | File content | Все обязательные поля присутствуют | ⬜ |
| | File naming | Формат {ticket_id}_{timestamp}.json | ⬜ |

### 8.2 SQL запросы для финальной проверки

```sql
-- Общая статистика по тикетам
SELECT 
    status,
    COUNT(*) as count,
    AVG(confidence) as avg_confidence,
    COUNT(CASE WHEN decision = 'auto-process' THEN 1 END) as auto_processed,
    COUNT(CASE WHEN decision = 'manual-review' THEN 1 END) as manual_review
FROM ticket_events
WHERE source = 'test_script'
GROUP BY status;

-- Проверка всех созданных файлов
SELECT 
    ticket_id,
    jira_ticket_id,
    jira_link,
    status,
    decision,
    processed_at
FROM ticket_events
WHERE jira_ticket_id IS NOT NULL
ORDER BY processed_at DESC;

-- Статистика по кэшу (через метрики)
SELECT 
    model_version,
    COUNT(*) as total_classifications,
    MAX(calculated_at) as last_classification
FROM metrics
WHERE metric_name = 'classification_count'
GROUP BY model_version;
```

---

## Автоматизированное тестирование

### Запуск автоматических тестов

```bash
# Полный тест пайплайна
python test_pipeline.py

# Проверка PostgreSQL
python test_postgresql.py

# Проверка Redis
python test_redis.py

# Проверка выходных файлов
python test_output_files.py
```

---

## Критерии успешного тестирования

✅ **Все проверки пройдены, если:**
1. Тикет успешно создан и обработан (status = 'completed')
2. Запись в PostgreSQL содержит все необходимые поля
3. Кэш в Redis создан и используется при повторных запросах
4. Выходной файл создан и содержит корректные данные
5. Audit logs записаны корректно
6. Метрики обновлены

---

## Устранение проблем

### Проблема: Тикет застрял в статусе 'queued'
- **Причина:** Worker не запущен или Redis недоступен
- **Решение:** Проверить `WORKER_ENABLED=true` в ml-service

### Проблема: Кэш не работает
- **Причина:** Redis DB 1 недоступен или ключ не создается
- **Решение:** Проверить подключение к Redis и логи ML Service

### Проблема: Файл не создается
- **Причина:** Неправильный DESTINATION_TYPE или проблемы с правами доступа
- **Решение:** Проверить `DESTINATION_TYPE=filesystem` и права на директорию

---

**Дата последнего обновления:** 2025-01-18

