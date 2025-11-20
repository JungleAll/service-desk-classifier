# Руководство по синхронизации данных из Jira для дообучения модели

## Обзор

Сервис синхронизации позволяет получать данные из Jira и обновлять поля в PostgreSQL для подготовки данных к дообучению модели. Это особенно полезно, когда операторы вручную корректируют категории тикетов в Jira.

## Как это работает

1. **Получение данных из Jira**: Сервис получает данные тикета через Jira REST API
2. **Извлечение категории**: Категория извлекается из Jira (custom field, labels, components и т.д.)
3. **Сравнение с predicted_type**: Если категория отличается от предсказанной моделью, она сохраняется как `actual_type`
4. **Обновление полей для обучения**: Тикет помечается как `training_ready`, если он был с `decision='manual-review'`
5. **Обратная связь**: Обновляется `feedback_status='incorrect'` и `feedback_correct_type`

## Использование API

### 1. Синхронизация одного тикета

```bash
curl -X POST "http://localhost:8003/sync/jira/ticket" \
  -H "Content-Type: application/json" \
  -d '{
    "jira_ticket_id": "SD-123",
    "category_field": "customfield_10001"
  }'
```

**Ответ:**
```json
{
  "success": true,
  "jira_ticket_id": "SD-123",
  "ticket_id": "tick_20251119123456",
  "updated_fields": ["actual_type", "training_ready", "feedback_status"],
  "errors": []
}
```

### 2. Пакетная синхронизация

```bash
curl -X POST "http://localhost:8003/sync/jira/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "jira_ticket_ids": ["SD-123", "SD-124", "SD-125"],
    "category_field": "customfield_10001"
  }'
```

### 3. Синхронизация по JQL запросу

```bash
curl -X POST "http://localhost:8003/sync/jira/jql" \
  -H "Content-Type: application/json" \
  -d '{
    "jql": "project = SD AND status = Resolved AND updated >= -7d",
    "category_field": "customfield_10001",
    "max_results": 100
  }'
```

**Примеры JQL запросов:**
- `"project = SD AND status = Resolved"` — все решенные тикеты
- `"project = SD AND updated >= -7d"` — тикеты, обновленные за последние 7 дней
- `"project = SD AND labels = 'training-ready'"` — тикеты с меткой training-ready
- `"project = SD AND assignee = currentUser()"` — тикеты, назначенные текущему пользователю

### 4. Синхронизация всех тикетов

```bash
curl -X POST "http://localhost:8003/sync/jira/all" \
  -H "Content-Type: application/json" \
  -d '{
    "category_field": "customfield_10001",
    "limit": 100
  }'
```

## Настройка извлечения категории

Категория извлекается из Jira в следующем порядке приоритета:

1. **Custom field** (если указан `category_field`)
2. **Labels** (первый label, если есть)
3. **Issue type name** (если не стандартный: Task, Bug, Story, Epic)
4. **Component name** (первый компонент)

### Настройка custom field для категории

Чтобы использовать custom field для категории, нужно:

1. **Найти ID custom field в Jira:**
   - Откройте тикет в Jira
   - Посмотрите на URL или используйте API: `GET /rest/api/3/field`
   - Custom field обычно имеет формат `customfield_10001`

2. **Указать в запросе:**
   ```json
   {
     "jira_ticket_id": "SD-123",
     "category_field": "customfield_10001"
   }
   ```

## Обновляемые поля в PostgreSQL

После синхронизации обновляются следующие поля в таблице `ticket_events`:

| Поле | Описание | Когда обновляется |
|------|----------|-------------------|
| `actual_type` | Фактическая категория из Jira | Если категория отличается от `predicted_type` |
| `actual_type_set_at` | Время установки категории | При установке `actual_type` |
| `actual_type_set_by` | Кто установил категорию | Всегда "jira_sync" |
| `training_ready` | Готовность для обучения | Если `decision='manual-review'` и `actual_type` установлена |
| `training_ready_at` | Время готовности | При установке `training_ready` |
| `feedback_status` | Статус обратной связи | Если категория отличается от `predicted_type` → "incorrect" |
| `feedback_correct_type` | Правильная категория | Если `feedback_status='incorrect'` |
| `feedback_provided_at` | Время обратной связи | При установке `feedback_status` |
| `feedback_provided_by` | Кто предоставил обратную связь | Всегда "jira_sync" |

## Автоматическая синхронизация

Для автоматической синхронизации можно настроить cron job или scheduled task:

### Пример cron job (каждый час)

```bash
# Синхронизация тикетов, обновленных за последний час
0 * * * * curl -X POST "http://localhost:8003/sync/jira/jql" \
  -H "Content-Type: application/json" \
  -d '{"jql": "project = SD AND updated >= -1h", "max_results": 100}'
```

### Пример Python скрипта

```python
import asyncio
import httpx

async def sync_recent_tickets():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8003/sync/jira/jql",
            json={
                "jql": "project = SD AND updated >= -1h",
                "max_results": 100
            }
        )
        print(response.json())

# Запуск каждые 30 минут
asyncio.run(sync_recent_tickets())
```

## Использование данных для дообучения

После синхронизации тикеты с `training_ready=TRUE` можно использовать для дообучения модели:

```sql
-- Получить тикеты, готовые для обучения
SELECT 
    ticket_id,
    text,
    actual_type as category,
    predicted_type,
    confidence
FROM training_ready_tickets
WHERE training_used_in_version IS NULL
ORDER BY training_ready_at DESC;
```

Представление `training_ready_tickets` автоматически фильтрует тикеты:
- `training_ready = TRUE`
- `actual_type IS NOT NULL`
- `training_used_in_version IS NULL` (еще не использованы в обучении)

## Мониторинг синхронизации

### Проверка успешности синхронизации

```sql
-- Тикеты с обновленной категорией
SELECT 
    ticket_id,
    jira_ticket_id,
    predicted_type,
    actual_type,
    actual_type_set_at,
    training_ready
FROM ticket_events
WHERE actual_type IS NOT NULL
  AND actual_type != predicted_type
ORDER BY actual_type_set_at DESC;
```

### Статистика по обратной связи

```sql
-- Статистика обратной связи
SELECT 
    feedback_status,
    COUNT(*) as count
FROM ticket_events
WHERE feedback_status != 'none'
GROUP BY feedback_status;
```

## Устранение неполадок

### Ошибка: "Тикет с jira_ticket_id не найден в БД"

**Причина**: Тикет не был создан через наше приложение или `jira_ticket_id` не сохранен в БД.

**Решение**: Убедитесь, что тикет был создан через Output Service и имеет `jira_ticket_id` в таблице `ticket_events`.

### Ошибка: "Не удалось получить тикет из Jira"

**Причины**:
- Неверный `jira_ticket_id`
- Нет доступа к тикету в Jira
- Jira недоступен

**Решение**: Проверьте доступ к Jira и правильность `jira_ticket_id`.

### Категория не извлекается

**Причины**:
- Custom field не указан или указан неверно
- Категория хранится в нестандартном месте

**Решение**: 
1. Проверьте структуру данных тикета в Jira через API
2. Укажите правильный `category_field`
3. Используйте labels или components для хранения категории

## Интеграция с процессом дообучения

После синхронизации данных из Jira:

1. **Сбор данных для обучения:**
   ```sql
   SELECT text, actual_type 
   FROM training_ready_tickets 
   WHERE training_used_in_version IS NULL;
   ```

2. **Дообучение модели** на собранных данных

3. **Пометка использованных тикетов:**
   ```sql
   UPDATE ticket_events
   SET training_used_in_version = 'v1.1'
   WHERE ticket_id IN (SELECT ticket_id FROM training_ready_tickets);
   ```

## См. также

- [Миграция 001_add_retraining_fields.sql](../database/migrations/001_add_retraining_fields.sql) — структура полей для дообучения
- [API Reference](../API_REFERENCE.md) — полная документация API
- [Jira Service Desk Setup](./JIRA_SERVICEDESK_SETUP.md) — настройка интеграции с Jira

