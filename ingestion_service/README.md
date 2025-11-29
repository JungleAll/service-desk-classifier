Service Desk Ingestion Service (Port 8000)

Назначение
- Прием обращений из внешних источников (email/chat/api/web)
- Валидация и запись в PostgreSQL (ticket_events)
- Постановка задач в Redis очередь pending_tickets
- Предоставление статусов и деталей обращений

Эндпойнты
- POST /tickets: создать обращение (201 Created)
- GET /tickets: список обращений (фильтры, пагинация)
- GET /tickets/{ticket_id}: детали обращения
- GET /status/{ticket_id}: статус обработки с прогрессом
- POST /tickets/{ticket_id}/cancel: отменить обработку
- POST /tickets/{ticket_id}/reprocess: переотправить в очередь (202 Accepted)
- POST /tickets/batch: пакетная загрузка обращений (202 Accepted)
- GET /health: проверка работоспособности (PostgreSQL, Redis)

Модели/поля
- TicketRequest: text, source [email|chat|api|web], user_id?, email?, priority [low|medium|high|critical], category_hint?, metadata?
- TicketResponse: ticket_id (tick_XXXXXXXX), status, message, created_at, estimated_processing_time

Конфигурация (env)
- POSTGRES_*: параметры подключения к базе (см. shared/database.py)
- REDIS_*: параметры Redis (см. shared/redis_client.py)
- CONFIG_SERVICE_URL: URL Config Service (по умолчанию: http://localhost:8002)
- LOG_LEVEL: уровень логирования (по умолчанию: INFO)

Запуск локально
- uvicorn ingestion_service.app:app --host 0.0.0.0 --port 8000

Запуск в Docker
- docker-compose up ingestion_service

Зависимости
- FastAPI, pydantic, psycopg2-binary, redis, httpx (см. requirements.txt)

Интеграции
- PostgreSQL: таблица ticket_events (см. database/schema.sql)
- Redis: очереди pending_tickets/failed_tickets
- Config Service (порт 8002): чтение конфигурации

Health/Observability
- Логирование структурированное через стандартный logging
- Ошибки пишутся в таблицу error_logs


