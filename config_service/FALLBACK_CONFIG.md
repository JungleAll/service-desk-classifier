# Fallback механизм конфигурации

## Описание

Config Service теперь поддерживает fallback механизм через файл конфигурации, который позволяет сервису продолжать работу при недоступности PostgreSQL.

## Как это работает

1. **При нормальной работе:**
   - Конфигурация хранится в PostgreSQL
   - При каждом изменении конфигурации через API файл fallback автоматически обновляется
   - Периодически (по умолчанию каждые 5 минут) конфигурация синхронизируется из БД в файл

2. **При недоступности PostgreSQL:**
   - Config Service автоматически переключается на чтение из файла fallback
   - Все запросы к `/config` продолжают работать с последней синхронизированной конфигурацией
   - Healthcheck endpoint показывает статус `degraded` вместо `unhealthy`

3. **При восстановлении PostgreSQL:**
   - Фоновая задача синхронизации автоматически обновит файл из БД
   - Сервис продолжит работу без перезапуска

## Настройка

### Переменные окружения

- `CONFIG_FALLBACK_ENABLED` (по умолчанию: `true`)
  - Включить/выключить fallback механизм
  
- `CONFIG_FALLBACK_DIR` (по умолчанию: `./config_cache`)
  - Директория для хранения файла fallback конфигурации
  
- `CONFIG_SYNC_INTERVAL` (по умолчанию: `300`)
  - Интервал синхронизации конфигурации из БД в файл (в секундах)

### Пример настройки в docker-compose.yml

```yaml
config_service:
  environment:
    - CONFIG_FALLBACK_ENABLED=true
    - CONFIG_FALLBACK_DIR=/app/config_cache
    - CONFIG_SYNC_INTERVAL=300
  volumes:
    - ./config_cache:/app/config_cache
```

## Структура файла конфигурации

Файл `config_fallback.json` имеет следующую структуру:

```json
{
  "config": {
    "service_enabled": "true",
    "confidence_threshold": "0.7",
    "current_model_version": "v1.0",
    "jira_enabled": "true",
    "jira_url": "https://jira.example.com",
    ...
  },
  "updated_at": "2025-01-19T12:00:00.000000",
  "source": "postgresql"
}
```

## Healthcheck

Endpoint `/health` теперь возвращает дополнительную информацию:

```json
{
  "status": "degraded",  // или "healthy" или "unhealthy"
  "postgresql": "disconnected",
  "fallback_enabled": true,
  "fallback_file": {
    "exists": true,
    "path": "/app/config_cache/config_fallback.json",
    "updated_at": "2025-01-19T12:00:00.000000",
    "keys_count": 15
  },
  "sync_task_running": true
}
```

**Статусы:**
- `healthy` - PostgreSQL доступен
- `degraded` - PostgreSQL недоступен, но fallback файл работает
- `unhealthy` - PostgreSQL недоступен и fallback файл отсутствует или не работает

## Логирование

Все операции с fallback механизмом логируются:

- `INFO` - успешная синхронизация конфигурации
- `WARNING` - PostgreSQL недоступен, используется fallback
- `ERROR` - ошибки при работе с файлом fallback

## Ручное управление

### Просмотр информации о fallback файле

```python
from config_service.config_fallback import get_config_file_info

info = get_config_file_info()
print(info)
```

### Принудительная синхронизация

```python
from config_service.config_fallback import sync_config_from_db

success = sync_config_from_db()
```

## Безопасность

⚠️ **Важно:** Файл fallback содержит конфигурацию в открытом виде (включая Jira credentials, если они настроены). Убедитесь, что:

1. Файл доступен только для процесса Config Service
2. Директория `CONFIG_FALLBACK_DIR` имеет правильные права доступа
3. Файл не попадает в систему контроля версий (добавьте в `.gitignore`)

## Отключение fallback

Если вы хотите отключить fallback механизм:

```bash
export CONFIG_FALLBACK_ENABLED=false
```

В этом случае Config Service будет работать только с PostgreSQL и вернется к поведению без fallback (ошибка 503 при недоступности БД).

