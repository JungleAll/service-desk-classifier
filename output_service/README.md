Service Desk Output Service (Port 8003)

Назначение
- Постобработка результатов классификации
- Отправка результата в целевую систему (плагинные коннекторы)
- Логирование в PostgreSQL (audit_logs, ticket_events)

Плагинные коннекторы (DESTINATION_TYPE)
- filesystem (по умолчанию): FileSystemConnector — сохраняет JSON в OUTPUT_DIR (./out)
- mock: MockConnector — генерирует MOCK-<ts>, ничего не отправляет
- jira: JiraConnector — отправляет тикеты в Jira REST API (retry, ссылка)

Интерфейс ITicketDestination
- async process_and_send(payload) -> (external_id, link, retry_count)
- async validate_connection()
- get_name()

Эндпойнты
- POST /process_result: принять результат ML, записать в БД, отправить в выбранное назначение при decision=auto-process
- GET /health: здоровье сервиса/подключения

Конфигурация (env)
- DESTINATION_TYPE: filesystem | mock | jira (default: filesystem)
- OUTPUT_DIR: каталог для файлов (filesystem), default: ./out
- POSTGRES_*: подключение к БД (POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD)
- API_HOST: хост для запуска сервиса (по умолчанию: 0.0.0.0)
- API_PORT: порт для запуска сервиса (по умолчанию: 8003)
- CONFIG_SERVICE_URL: URL Config Service (по умолчанию: http://localhost:8002)
- CONFIG_SERVICE_TIMEOUT: таймаут запросов к Config Service в секундах (по умолчанию: 2.0)
- JIRA_URL, JIRA_USER, JIRA_API_TOKEN, JIRA_PROJECT_KEY: для jira-коннектора (fallback, приоритет у Config Service)
- JIRA_VALIDATE_CONNECTION: включить проверку подключения к Jira (по умолчанию: false)
- MAX_RETRY_ATTEMPTS: максимальное количество попыток отправки в Jira (по умолчанию: 3)
- RETRY_DELAY: задержка между попытками в секундах (по умолчанию: 5)
- LOG_LEVEL: уровень логирования (по умолчанию: INFO)

Обновления ticket_events
- Статус: completed
- Поля: predicted_type, confidence, decision, model_version, probabilities, priority, email, metadata
- Интеграция: jira_ticket_id, jira_link, sent_to_jira_at (если применимо), retry_count

Запуск
- uvicorn output_service.app:app --host 0.0.0.0 --port 8003
- docker-compose up output_service

Интеграции
- Config Service (порт 8002): чтение приоритетов (auto_process_priority, manual_review_priority) и Jira конфигурации (jira_enabled, jira_url) через REST API с fallback на БД
- ML Service Worker: автоматическая отправка результатов классификации при decision=auto-process
- PostgreSQL: обновление ticket_events и запись в audit_logs

Примечание: Output Service использует Config Service API для получения конфигурации. При недоступности Config Service автоматически используется fallback на прямое чтение из БД.

Отладка без Jira
- Установить DESTINATION_TYPE=filesystem или DESTINATION_TYPE=mock
- Проверить файлы в OUTPUT_DIR или ответы MOCK


