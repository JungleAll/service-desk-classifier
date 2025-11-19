# Диагностика pipeline обработки тикетов

## Проблема
Тикеты не появляются в БД после создания в production режиме.

## Возможные причины

1. **Тикеты не создаются** - ошибка в Ingestion Service
2. **Тикеты не попадают в очередь Redis** - проблема с подключением к Redis
3. **Worker не обрабатывает тикеты** - worker отключен или не работает
4. **Worker обрабатывает, но не обновляет БД** - ошибка при сохранении результатов

## Диагностика

### 1. Запустить скрипт диагностики

```powershell
.\diagnose_ticket_pipeline.ps1
```

### 2. Проверить статус всех сервисов

```powershell
# Ingestion Service
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method GET

# ML Service
Invoke-RestMethod -Uri "http://localhost:8001/health" -Method GET

# Worker
Invoke-RestMethod -Uri "http://localhost:8001/worker/status" -Method GET
```

### 3. Проверить очередь Redis

```powershell
# Длина очереди
docker-compose exec redis redis-cli LLEN pending_tickets

# Просмотр элементов в очереди (если есть)
docker-compose exec redis redis-cli LRANGE pending_tickets 0 -1
```

### 4. Проверить логи Ingestion Service

```powershell
docker-compose logs --tail=100 ingestion-service | Select-String -Pattern "ticket|обращение|error|Error|created|создан"
```

Ожидаемые сообщения при создании тикета:
```
Обращение tick_XXXXXXXX создано и добавлено в очередь
```

### 5. Проверить логи ML Service (Worker)

```powershell
docker-compose logs --tail=100 ml-service | Select-String -Pattern "Worker:|тикет|ticket|очередь|queue|Получен тикет"
```

Ожидаемые сообщения при обработке тикета:
```
Worker: Получен тикет tick_XXXXXXXX из очереди, начинаю обработку...
Worker: Проверка версии модели перед классификацией...
Обработка тикета tick_XXXXXXXX: ...
Тикет tick_XXXXXXXX классифицирован: ...
```

### 6. Проверить БД напрямую

```sql
-- Все тикеты (включая с ошибками)
SELECT ticket_id, status, model_version, predicted_type, 
       created_at, updated_at, error_message
FROM ticket_events
ORDER BY created_at DESC
LIMIT 20;

-- Только тикеты со статусом 'queued' (ожидают обработки)
SELECT ticket_id, status, created_at, updated_at
FROM ticket_events
WHERE status = 'queued'
ORDER BY created_at DESC;

-- Тикеты с ошибками
SELECT ticket_id, status, error_message, created_at
FROM ticket_events
WHERE status = 'failed'
ORDER BY created_at DESC
LIMIT 10;
```

### 7. Тест создания тикета через API

```powershell
$body = @{
    text = "Тестовый тикет для диагностики"
    source = "dashboard"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:8000/tickets" -Method POST -Body $body -ContentType "application/json"
$response | ConvertTo-Json

# Запомните ticket_id из ответа
$ticketId = $response.ticket_id

# Проверьте статус тикета
Invoke-RestMethod -Uri "http://localhost:8000/status/$ticketId" -Method GET | ConvertTo-Json
```

### 8. Мониторинг в реальном времени

**Терминал 1 - Логи Ingestion Service:**
```powershell
docker-compose logs -f ingestion-service
```

**Терминал 2 - Логи ML Service (Worker):**
```powershell
docker-compose logs -f ml-service | Select-String -Pattern "Worker:|тикет|ticket"
```

**Терминал 3 - Создайте тикет в Dashboard:**
1. Откройте http://localhost:8501/demo
2. Переключите режим на "production"
3. Введите текст и нажмите "Классифицировать"

**Смотрите логи в обоих терминалах** - должны появиться сообщения о создании и обработке тикета.

## Решения для частых проблем

### Проблема 1: Worker отключен

**Симптомы:**
- `worker_enabled: false` в статусе worker
- Тикеты создаются, но не обрабатываются

**Решение:**
1. Проверьте `docker-compose.yml`:
   ```yaml
   environment:
     - WORKER_ENABLED=true
   ```
2. Перезапустите ML Service:
   ```powershell
   docker-compose restart ml-service
   ```

### Проблема 2: Тикеты не попадают в очередь Redis

**Симптомы:**
- Тикеты создаются в БД со статусом 'queued'
- Но очередь Redis пуста
- Worker не получает тикеты

**Решение:**
1. Проверьте подключение к Redis:
   ```powershell
   docker-compose exec redis redis-cli PING
   ```
2. Проверьте логи Ingestion Service на ошибки Redis
3. Перезапустите Ingestion Service:
   ```powershell
   docker-compose restart ingestion-service
   ```

### Проблема 3: Worker не обрабатывает тикеты

**Симптомы:**
- Worker включен и запущен
- Очередь Redis не пуста
- Но тикеты не обрабатываются

**Решение:**
1. Проверьте логи worker на ошибки:
   ```powershell
   docker-compose logs ml-service | Select-String -Pattern "Worker:|Error|error|ошибка" -Context 3
   ```
2. Перезапустите ML Service:
   ```powershell
   docker-compose restart ml-service
   ```

### Проблема 4: Тикеты обрабатываются, но не обновляются в БД

**Симптомы:**
- В логах видно обработку тикета
- Но в БД статус остается 'queued'

**Решение:**
1. Проверьте подключение к БД из ML Service
2. Проверьте логи на ошибки SQL:
   ```powershell
   docker-compose logs ml-service | Select-String -Pattern "UPDATE ticket_events|SQL|database|БД" -Context 2
   ```

## Проверка полного pipeline

1. **Создание тикета:**
   - Ingestion Service получает запрос
   - Создает запись в БД со статусом 'queued'
   - Добавляет тикет в очередь Redis

2. **Обработка тикета:**
   - Worker получает тикет из очереди Redis
   - Обновляет статус на 'processing'
   - Классифицирует текст
   - Обновляет статус на 'classified' с результатами

3. **Проверка результата:**
   - Тикет должен быть в БД со статусом 'classified'
   - Должны быть заполнены: `predicted_type`, `confidence`, `model_version`

## Дополнительные команды

### Очистить очередь Redis

```powershell
docker-compose exec redis redis-cli DEL pending_tickets
```

### Проверить все очереди Redis

```powershell
docker-compose exec redis redis-cli KEYS "*ticket*"
```

### Просмотреть последние ошибки в БД

```sql
SELECT service_name, error_type, error_message, ticket_id, created_at
FROM error_logs
ORDER BY created_at DESC
LIMIT 10;
```

