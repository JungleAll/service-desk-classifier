# Миграции базы данных

## Применение миграций

Для применения миграций используйте скрипт `apply_migration.py`:

```bash
# Из корня проекта
python database/apply_migration.py <имя_файла_миграции>

# Или из папки database
cd database
python apply_migration.py <имя_файла_миграции>
```

### Примеры

```bash
# Применить расширенную миграцию для дообучения (по умолчанию)
python database/apply_migration.py 001_add_retraining_fields_extended.sql

# Применить минимальную миграцию
python database/apply_migration.py 001_add_retraining_fields.sql
```

## Доступные миграции

### 001_add_retraining_fields.sql
**Минимальная схема** - добавляет поля напрямую в таблицу `ticket_events`:
- `actual_type`, `actual_type_set_at`, `actual_type_set_by`
- `feedback_status`, `feedback_correct_type`, `feedback_comment`, `feedback_provided_at`, `feedback_provided_by`
- `training_ready`, `training_ready_at`, `training_used_in_version`

**Используйте**, если хотите быстро начать работу без дополнительных таблиц.

### 001_add_retraining_fields_extended.sql (РЕКОМЕНДУЕТСЯ)
**Расширенная схема** - использует отдельные таблицы для лучшей организации данных:

#### Новые таблицы:
1. **classification_feedback** - обратная связь по классификации
   - Хранит информацию о правильности/неправильности предсказаний
   - Поддерживает типы: 'correct', 'incorrect', 'partial'
   
2. **category_corrections** - история исправлений категорий
   - Отслеживает все изменения категорий тикетов
   - Хранит причину исправления: 'manual_review', 'feedback', 'admin_correction', 'jira_sync'
   
3. **training_data_usage** - отслеживание использования данных в обучении
   - Записывает, какие тикеты использовались в каких версиях моделей
   - Поддерживает типы обучения: 'initial', 'retraining', 'incremental'

#### Минимальные поля в ticket_events:
- `actual_type`, `actual_type_set_at`, `actual_type_set_by`
- `training_ready`, `training_ready_at`, `training_used_in_version`
- `has_feedback`, `has_correction` (флаги для связи с новыми таблицами)

#### Представления (Views):
- `training_ready_tickets` - тикеты, готовые для обучения
- `tickets_with_feedback` - тикеты с обратной связью
- `manual_review_pending` - тикеты, ожидающие ручной разметки

#### Триггеры:
- Автоматическая установка `training_ready` при установке `actual_type`
- Автоматическое обновление флагов `has_feedback` и `has_correction`

**Используйте**, если нужна полная история изменений и лучшая организация данных для production.

## Переменные окружения

Скрипт использует те же переменные окружения, что и приложение:

- `POSTGRES_HOST` (по умолчанию: `localhost`)
- `POSTGRES_PORT` (по умолчанию: `5432`)
- `POSTGRES_DB` (по умолчанию: `service_desk_db`)
- `POSTGRES_USER` (по умолчанию: `postgres`)
- `POSTGRES_PASSWORD` (по умолчанию: `postgres`)

## Проверка примененных миграций

После применения миграции скрипт автоматически проверяет созданные объекты:

```bash
[INFO] Created tables:
   + category_corrections
   + classification_feedback
   + training_data_usage

[INFO] Created views:
   + manual_review_pending
   + tickets_with_feedback
   + training_ready_tickets
```

## Откат миграций

Для отката миграций создайте соответствующий SQL скрипт с префиксом `rollback_`:

```sql
-- rollback_001_add_retraining_fields_extended.sql
DROP VIEW IF EXISTS training_ready_tickets;
DROP VIEW IF EXISTS tickets_with_feedback;
DROP VIEW IF EXISTS manual_review_pending;

DROP TRIGGER IF EXISTS trigger_set_training_ready ON ticket_events;
DROP TRIGGER IF EXISTS trigger_update_has_feedback ON classification_feedback;
DROP TRIGGER IF EXISTS trigger_update_has_correction ON category_corrections;

DROP FUNCTION IF EXISTS set_training_ready_on_actual_type();
DROP FUNCTION IF EXISTS update_has_feedback_flag();
DROP FUNCTION IF EXISTS update_has_correction_flag();

DROP TABLE IF EXISTS training_data_usage;
DROP TABLE IF EXISTS category_corrections;
DROP TABLE IF EXISTS classification_feedback;

ALTER TABLE ticket_events
DROP COLUMN IF EXISTS has_correction,
DROP COLUMN IF EXISTS has_feedback,
DROP COLUMN IF EXISTS training_used_in_version,
DROP COLUMN IF EXISTS training_ready_at,
DROP COLUMN IF EXISTS training_ready,
DROP COLUMN IF EXISTS actual_type_set_by,
DROP COLUMN IF EXISTS actual_type_set_at,
DROP COLUMN IF EXISTS actual_type;
```

## См. также

- [Миграция 001_add_retraining_fields.sql](./001_add_retraining_fields.sql) - минимальная схема
- [Миграция 001_add_retraining_fields_extended.sql](./001_add_retraining_fields_extended.sql) - расширенная схема
- [Схема БД](../schema.sql) - основная схема базы данных

