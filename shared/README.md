Shared Utilities

Назначение
- Общие утилиты для микросервисов: база данных и Redis

Файлы
- database.py: пул подключений к PostgreSQL, контекстный менеджер курсора
- redis_client.py: клиент Redis, префиксы ключей и TTL для кэша предсказаний
- requirements.txt: зависимости общего уровня

ENV для PostgreSQL
- POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

ENV для Redis
- REDIS_HOST, REDIS_PORT, REDIS_PASSWORD (опционально)
- REDIS_DB_QUEUES (по умолчанию: 0) - база данных для очередей
- REDIS_DB_CACHE (по умолчанию: 1) - база данных для кэша
- Ключевые сущности:
  - DB 0 (очереди): pending_tickets, failed_tickets
  - DB 1 (кэш): cache_predictions (TTL 1 час)
- **Архитектура Redis:** Разделение на разные базы данных для изоляции очередей и кэша
  - См. `REDIS_ARCHITECTURE.md` для подробностей

Рекомендации
- Импортировать из shared вместо дублирования кода
- Следить за единым форматом логирования и обработкой ошибок


