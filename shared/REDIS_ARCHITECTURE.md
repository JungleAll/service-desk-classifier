# Архитектура Redis в Service Desk Classifier

## Обзор

Redis используется для двух различных целей, которые концептуально разделены на разные базы данных:

1. **Очереди задач** (DB 0) - для асинхронной обработки тикетов
2. **Кэш результатов** (DB 1) - для кэширования результатов классификации

## Разделение на базы данных

### DB 0: Очереди (Queues)

**Назначение:** Хранение очередей задач для асинхронной обработки

**Используется для:**
- `pending_tickets` - очередь тикетов, ожидающих классификации
- `failed_tickets` - очередь тикетов, которые не удалось обработать

**Характеристики:**
- Данные временные, удаляются после обработки
- Использует структуру данных Redis List (LPUSH/RPOP, BLPOP)
- Нет TTL (данные живут до обработки)
- Высокая производительность операций вставки/извлечения

**Переменные окружения:**
```bash
REDIS_DB_QUEUES=0  # По умолчанию
```

### DB 1: Кэш (Cache)

**Назначение:** Кэширование результатов классификации для ускорения повторных запросов

**Используется для:**
- `cache_predictions` - кэш результатов классификации текстов

**Характеристики:**
- Данные с TTL (время жизни)
- Использует структуру данных Redis String (SET/GET с TTL)
- TTL по умолчанию: 3600 секунд (1 час)
- Автоматическое удаление устаревших данных

**Переменные окружения:**
```bash
REDIS_DB_CACHE=1  # По умолчанию
```

## Преимущества разделения

1. **Изоляция данных**
   - Очереди и кэш не смешиваются
   - Легче управлять и мониторить

2. **Разные политики управления**
   - Очереди: быстрая обработка, без TTL
   - Кэш: TTL для автоматической очистки

3. **Упрощение мониторинга**
   - Отдельные метрики для очередей и кэша
   - Легче отслеживать производительность

4. **Оптимизация производительности**
   - Можно настроить разные политики persistence для разных баз
   - Раздельное масштабирование при необходимости

5. **Безопасность**
   - Можно настроить разные права доступа для разных баз

## API

### Очереди (DB 0)

```python
from shared.redis_client import (
    push_to_queue,
    pop_from_queue,
    get_queue_length,
    clear_queue,
    get_queue_info,
    QUEUE_PENDING_TICKETS,
    QUEUE_FAILED_TICKETS
)

# Добавление в очередь
push_to_queue(QUEUE_PENDING_TICKETS, {"ticket_id": "tick_123", "text": "..."})

# Извлечение из очереди
ticket = pop_from_queue(QUEUE_PENDING_TICKETS, timeout=5)

# Получение длины очереди
length = get_queue_length(QUEUE_PENDING_TICKETS)

# Очистка очереди
clear_queue(QUEUE_PENDING_TICKETS)

# Информация об очередях
info = get_queue_info()
```

### Кэш (DB 1)

```python
from shared.redis_client import (
    get_cache,
    set_cache,
    delete_cache,
    clear_cache,
    get_cache_info,
    CACHE_PREDICTIONS
)

# Установка в кэш
set_cache("key", {"value": "data"}, ttl=3600)

# Получение из кэша
value = get_cache("key")

# Удаление из кэша
delete_cache("key")

# Очистка всего кэша
clear_cache()  # или clear_cache("pattern:*")

# Информация о кэше
info = get_cache_info()
```

## Низкоуровневый доступ

Если нужен прямой доступ к клиентам Redis:

```python
from shared.redis_client import (
    get_redis_queue_client,
    get_redis_cache_client
)

# Клиент для очередей (DB 0)
queue_client = get_redis_queue_client()

# Клиент для кэша (DB 1)
cache_client = get_redis_cache_client()
```

## Конфигурация

### Переменные окружения

```bash
# Основные настройки Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=  # Опционально

# Номера баз данных
REDIS_DB_QUEUES=0  # Очереди
REDIS_DB_CACHE=1   # Кэш
```

### Docker Compose

В `docker-compose.yml` Redis уже настроен и готов к использованию:

```yaml
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
```

## Мониторинг

### Проверка состояния очередей

```python
from shared.redis_client import get_queue_info

info = get_queue_info()
print(f"Pending tickets: {info['pending_tickets']}")
print(f"Failed tickets: {info['failed_tickets']}")
```

### Проверка состояния кэша

```python
from shared.redis_client import get_cache_info

info = get_cache_info()
print(f"Cache keys: {info['keys']}")
print(f"Memory used: {info['used_memory']}")
```

### Через Redis CLI

```bash
# Подключение к Redis
redis-cli

# Переключение на DB 0 (очереди)
SELECT 0
KEYS *
LLEN pending_tickets
LLEN failed_tickets

# Переключение на DB 1 (кэш)
SELECT 1
KEYS *
DBSIZE
```

## Миграция

Если у вас уже есть данные в одной базе данных, можно перенести их:

```python
# Пример миграции (выполнить один раз)
from shared.redis_client import (
    get_redis_queue_client,
    get_redis_cache_client
)

# Если данные были в DB 0, переносим кэш в DB 1
old_client = get_redis_queue_client()
new_cache_client = get_redis_cache_client()

# Перенос ключей кэша
for key in old_client.keys("cache_predictions:*"):
    value = old_client.get(key)
    ttl = old_client.ttl(key)
    if value:
        new_cache_client.setex(key, ttl if ttl > 0 else 3600, value)
        old_client.delete(key)
```

## Рекомендации

1. **Для production:**
   - Используйте разные базы данных (как настроено)
   - Настройте persistence для DB 0 (очереди важнее)
   - Настройте maxmemory-policy для DB 1 (кэш можно очищать)

2. **Для разработки:**
   - Можно использовать одну базу данных, но рекомендуется разделение

3. **Мониторинг:**
   - Отслеживайте длину очередей
   - Мониторьте использование памяти кэша
   - Настройте алерты при переполнении

## Обратная совместимость

Функция `get_redis_client()` сохранена для обратной совместимости, но возвращает клиент для очередей (DB 0) и выводит предупреждение. Для новых проектов рекомендуется использовать специализированные функции.

