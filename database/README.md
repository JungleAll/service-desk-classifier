Database Layer (PostgreSQL)

Назначение
- Хранение событий обращений (ticket_events)
- Метрики моделей (metrics)
- Конфигурация системы (configuration)
- История версий моделей (model_versions)
- Логи ошибок (error_logs)
- Аудит действий (audit_logs)
- Аудит изменений конфигурации (config_audit_log)

Файлы
- schema.sql: полная схема БД с индексами
- init_db.py: инициализация/применение схемы

Ключевые таблицы
- ticket_events: расширенные поля (email, priority, metadata, probabilities, jira_link, sent_to_jira_at, cancelled_at, retry_count)
- metrics: имя метрики, значение, model_version, calculated_at
- configuration: key/value, updated_at/by
- model_versions: версия, путь к артефактам, accuracy, is_active, activated_at
- error_logs, audit_logs, config_audit_log

Индексы
- По основным полям для ускорения запросов (см. schema.sql)

Миграции
- На текущем этапе применяются через schema.sql; при расширении проекта рекомендуется Alembic

Подключение
- ENV: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
- См. shared/database.py


