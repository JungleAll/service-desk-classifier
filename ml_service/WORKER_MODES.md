# Режимы работы Worker: Когда он должен быть disabled

## 📋 Обзор

ML Service поддерживает два режима работы:
1. **Режим REST API (без Worker)** - по умолчанию, `WORKER_ENABLED=false`
2. **Режим с Worker (автоматическая обработка)** - `WORKER_ENABLED=true`

## 🔴 Когда Worker должен быть DISABLED

Worker **отключен по умолчанию** и должен оставаться disabled в следующих сценариях:

### 1. Демонстрация и презентация
- **Цель:** Показать работу системы в контролируемом режиме
- **Преимущества:** 
  - Полный контроль над процессом
  - Можно показать каждый шаг вручную
  - Легко объяснить, что происходит
- **Использование:** Swagger UI, Dashboard Demo Mode

### 2. Разработка и тестирование
- **Цель:** Отладка отдельных компонентов
- **Преимущества:**
  - Можно тестировать каждый сервис отдельно
  - Легко воспроизвести ошибки
  - Не нужно настраивать Redis и Worker
- **Использование:** Unit-тесты, интеграционные тесты

### 3. On-demand классификация
- **Цель:** Классификация по требованию через REST API
- **Преимущества:**
  - Немедленный ответ
  - Не требует очереди Redis
  - Простая интеграция
- **Использование:** Прямые вызовы `POST /classify`

### 4. Отладка отдельных компонентов
- **Цель:** Проверка работы конкретного сервиса
- **Преимущества:**
  - Изоляция компонентов
  - Проще найти проблему
- **Использование:** Тестирование ML Service без полного pipeline

## ✅ Когда Worker должен быть ENABLED

Worker должен быть включен в следующих сценариях:

### 1. Production окружение
- **Цель:** Автоматическая обработка тикетов
- **Требования:**
  - Redis запущен и доступен
  - Все сервисы настроены
  - Модель загружена

### 2. Автоматическая обработка большого количества тикетов
- **Цель:** Обработка потока тикетов из Ingestion Service
- **Требования:**
  - Тикеты создаются через `POST /tickets`
  - Тикеты попадают в очередь Redis
  - Worker автоматически обрабатывает очередь

### 3. Полная автоматизация потока данных
- **Цель:** End-to-end обработка без ручного вмешательства
- **Поток:**
  ```
  Ingestion Service → Redis Queue → Worker → ML Service → Output Service → Jira/FileSystem
  ```

## ⚠️ Проблема: Тикеты в очереди, но Worker disabled

### Симптомы:
- Тикет создан через `POST /tickets` в Ingestion Service
- Тикет в статусе `queued` в БД
- Тикет добавлен в очередь Redis (`pending_tickets`)
- Но тикет не обрабатывается (остается в `queued`)

### Причина:
Worker disabled (`WORKER_ENABLED=false`), поэтому тикеты в очереди не обрабатываются автоматически.

### Решения:

#### Решение 1: Включить Worker (рекомендуется для production)

```bash
# Установите переменную окружения
export WORKER_ENABLED=true

# Перезапустите ML Service
# После этого Worker автоматически обработает все тикеты из очереди
```

#### Решение 2: Ручная обработка через REST API (для тестирования)

Если Worker disabled, можно обработать тикет вручную:

**Шаг 1: Получить данные тикета из БД**
```bash
curl http://localhost:8000/tickets/tick_d476c3aa
```

**Шаг 2: Классифицировать текст через ML Service**
```bash
curl -X POST "http://localhost:8001/classify" \
  -H "Content-Type: application/json" \
  -d '{"text": "Принтер HP LaserJet не печатает, горит красная лампочка"}'
```

**Шаг 3: Отправить результат в Output Service**
```bash
curl -X POST "http://localhost:8003/process_result" \
  -H "Content-Type: application/json" \
  -d '{
    "ticket_id": "tick_d476c3aa",
    "text": "Принтер HP LaserJet не печатает, горит красная лампочка",
    "predicted_type": "Запрос на обслуживание",
    "confidence": 0.95,
    "decision": "auto-process",
    "model_version": "v1.0",
    "source": "email"
  }'
```

**Шаг 4: Обновить статус тикета в БД (опционально)**
```sql
UPDATE ticket_events 
SET status = 'classified', 
    predicted_type = 'Запрос на обслуживание',
    confidence = 0.95,
    decision = 'auto-process',
    processed_at = CURRENT_TIMESTAMP
WHERE ticket_id = 'tick_d476c3aa';
```

#### Решение 3: Использовать Dashboard в Demo режиме

Dashboard в Demo режиме использует прямой вызов `POST /classify` без Worker:

1. Откройте Dashboard: `http://localhost:8501`
2. Выберите **Demo Mode**
3. Введите текст тикета
4. Нажмите "Классифицировать"
5. Результат будет получен сразу (без создания записи в `ticket_events`)

**Ограничение:** Demo режим не создает запись в `ticket_events`, только классифицирует текст.

#### Решение 4: Использовать Dashboard в Production режиме (с Worker)

1. Включите Worker: `export WORKER_ENABLED=true`
2. Перезапустите ML Service
3. Откройте Dashboard: `http://localhost:8501`
4. Выберите **Production Mode**
5. Введите текст тикета
6. Тикет будет создан через Ingestion Service и автоматически обработан Worker'ом

## 🔍 Диагностика текущего режима

### Проверка статуса Worker:

```bash
curl http://localhost:8001/worker/diagnostics
```

**Ответ при Worker disabled:**
```json
{
  "worker_enabled": false,
  "worker_running": false,
  "model_loaded": true,
  "queue_pending_length": 1,
  "queue_failed_length": 0,
  "redis_connected": true,
  "message": "Worker отключен (WORKER_ENABLED=false). Установите WORKER_ENABLED=true для автоматической обработки очереди. В очереди 1 тикет(ов) ожидают обработки."
}
```

**Ответ при Worker enabled:**
```json
{
  "worker_enabled": true,
  "worker_running": true,
  "model_loaded": true,
  "queue_pending_length": 0,
  "queue_failed_length": 0,
  "redis_connected": true,
  "message": "Все системы работают нормально."
}
```

### Проверка через health endpoint:

```bash
curl http://localhost:8001/health
```

**Worker disabled:**
```json
{
  "status": "healthy",
  "message": "Сервис работает нормально"
}
```

**Worker enabled:**
```json
{
  "status": "healthy",
  "message": "Сервис работает нормально (Worker: running)"
}
```

## 📊 Сравнение режимов

| Характеристика | REST API (Worker disabled) | Worker (Worker enabled) |
|----------------|---------------------------|------------------------|
| **Автоматическая обработка** | ❌ Нет | ✅ Да |
| **Требует Redis** | ❌ Нет (только для кэша) | ✅ Да (для очереди) |
| **Создание тикетов через Ingestion** | ⚠️ Тикеты в очереди не обрабатываются | ✅ Автоматически обрабатываются |
| **Ручная классификация** | ✅ `POST /classify` | ✅ `POST /classify` |
| **Подходит для production** | ❌ Нет | ✅ Да |
| **Подходит для тестирования** | ✅ Да | ⚠️ Сложнее отлаживать |
| **Масштабируемость** | ❌ Ограничена | ✅ Высокая (несколько worker'ов) |

## 🎯 Рекомендации

### Для вашего случая (тикет в очереди, но не обрабатывается):

**Если вы в режиме разработки/тестирования:**
1. Используйте ручную обработку через `POST /classify` (Решение 2)
2. Или используйте Dashboard в Demo режиме (Решение 3)

**Если вы готовы к production:**
1. Включите Worker: `export WORKER_ENABLED=true`
2. Перезапустите ML Service
3. Worker автоматически обработает все тикеты из очереди

**Для переобработки существующего тикета:**
```bash
# После включения Worker
curl -X POST "http://localhost:8000/tickets/tick_d476c3aa/reprocess"
```

## 📝 Выводы

1. **Worker disabled по умолчанию** - это нормально для разработки и тестирования
2. **Тикеты в очереди не обрабатываются** автоматически, если Worker disabled
3. **Для production** нужно включить Worker: `WORKER_ENABLED=true`
4. **Для тестирования** можно использовать ручную обработку через REST API
5. **Dashboard Demo Mode** не требует Worker и работает напрямую с ML Service

## 🔗 Связанные документы

- `ml_service/README.md` - Подробное описание режимов работы
- `DIAGNOSTICS.md` - Диагностика проблем
- `ARCHITECTURE.md` - Архитектура системы

