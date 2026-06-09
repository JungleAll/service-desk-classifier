Service Desk Classifier — API Reference

Назначение
- Сводное описание REST API всех модулей платформы: Ingestion, ML, Config, Output, Dashboard (ссылки).
- Форматы запросов/ответов, коды ошибок, заметки по аутентификации и интеграции.

Общие положения
- Базовый формат: JSON запросы и ответы.
- Аутентификация: не требуется для демо; в проде добавьте OAuth/JWT/Key (вне рамок данного референса).
- CORS: включен для всех сервисов.
- Коды ошибок: 200/201 OK/Created; 202 Accepted; 400 Validation/Bad Request; 404 Not Found; 500 Internal; 503 Service Unavailable.
- Статус: Документ обновлен и соответствует текущей реализации всех сервисов (проверено 2025-01-19, обновлено 2025-01-19).
- Изменения:
  - Добавлен endpoint GET /metrics/unavailability в Ingestion Service для метрик недоступности
  - Обновлен GET /health в Ingestion Service (добавлен config_service)
  - Обновлен GET /health в Config Service (добавлена информация о fallback механизме)
  - Улучшены сообщения об ошибках во всех сервисах (понятные для пользователей)

Сервисы и базовые URL
- Ingestion Service: http://localhost:8000
- ML Service: http://localhost:8001
- Config Service: http://localhost:8002
- Output Service: http://localhost:8003
- Dashboard (Streamlit): http://localhost:8501


1) Ingestion Service (Port 8000)

1.1 POST /tickets — Создать обращение
- Request
  - text: string (min 3) — текст обращения
  - source: string — 'email' | 'chat' | 'api' | 'web' (валидируется)
  - user_id?: string — ID пользователя
  - email?: string — email отправителя
  - priority?: string — 'low' | 'medium' | 'high' | 'critical' (default: 'medium', валидируется)
  - category_hint?: string — подсказка о категории
  - metadata?: object — дополнительные метаданные
- Response (201 Created)
  - ticket_id: string (формат 'tick_XXXXXXXX')
  - status: 'queued'
  - message: string — сообщение о результате
  - created_at: ISO datetime
  - estimated_processing_time: number (ms, default: 2000)
- Errors: 
  - 400 — некорректные параметры (неверный source, priority, слишком короткий text)
  - 503 — сервис отключен через Config Service ИЛИ база данных PostgreSQL недоступна
    - Сообщение: "Сервис автоматической классификации отключен" (если отключен через Config Service)
    - Сообщение: "База данных PostgreSQL недоступна. Пожалуйста, повторите попытку позже." (если БД недоступна)
  - 500 — внутренняя ошибка
    - Сообщение: "Внутренняя ошибка при создании обращения. Обратитесь к администратору системы. (ID: {ticket_id})"
    - Включает ID тикета для отслеживания проблемы

1.2 GET /tickets — Список обращений
- Query: 
  - limit?: number (default: 50, min: 1, max: 1000) — количество результатов
  - offset?: number (default: 0, min: 0) — смещение для пагинации
  - status?: string — фильтр по статусу (алиас для status_filter)
  - source?: string — фильтр по источнику
  - priority?: string — фильтр по приоритету
  - date_from?: string (YYYY-MM-DD) — фильтр с даты
  - date_to?: string (YYYY-MM-DD) — фильтр по дату
  - sort?: string (default: "-created_at") — сортировка (префикс "-" для DESC, поддерживаемые поля: created_at, updated_at, processed_at, status)
- Response (200)
  - tickets: Ticket[] (массив объектов обращений)
  - total: number — общее количество
  - page: number — текущая страница (вычисляется из offset/limit)
  - pages: number — всего страниц
- Errors:
  - 503 — база данных PostgreSQL недоступна
    - Сообщение: "База данных PostgreSQL недоступна. Пожалуйста, повторите попытку позже."
  - 500 — внутренняя ошибка
    - Сообщение: "Внутренняя ошибка при получении списка обращений. Обратитесь к администратору системы."

1.3 GET /tickets/{ticket_id} — Детали обращения
- Response (200)
  - ticket_id: string
  - text: string
  - source: string
  - user_id?: string
  - email?: string
  - priority?: string
  - status: string — 'queued' | 'processing' | 'classified' | 'completed' | 'failed' | 'cancelled'
  - predicted_type?: string — предсказанный тип (если классифицирован)
  - confidence?: number — уверенность модели (если классифицирован)
  - probabilities?: Dict<string, number> — вероятности для всех классов в формате JSONB (если классифицирован)
  - decision?: string — решение ('auto-process' | 'manual-review', если классифицирован)
  - model_version?: string — версия модели, использованная для классификации
  - jira_issue_id?: string — ID тикета в Jira (или external_id для FileSystem/Mock). В БД хранится как jira_ticket_id, в ответе маппится в jira_issue_id
  - jira_link?: string — ссылка на тикет в Jira (или путь к файлу для FileSystem)
  - created_at: ISO datetime
  - processed_at?: ISO datetime — время завершения классификации
  - sent_to_jira_at?: ISO datetime — время отправки в destination
  - error_message?: string — сообщение об ошибке (если есть)
  - retry_count?: number — количество попыток
- Errors: 
  - 404 — обращение не найдено
  - 503 — база данных PostgreSQL недоступна
    - Сообщение: "База данных PostgreSQL недоступна. Пожалуйста, повторите попытку позже."
  - 500 — внутренняя ошибка
    - Сообщение: "Внутренняя ошибка при получении деталей обращения. Обратитесь к администратору системы."

1.4 GET /status/{ticket_id} — Статус обработки
- Response (200)
  - ticket_id: string
  - status: 'queued' | 'processing' | 'classified' | 'completed' | 'failed' | 'cancelled'
    - 'queued': тикет создан и поставлен в очередь
    - 'processing': тикет обрабатывается ML Service Worker
    - 'classified': классификация завершена, ожидает обработки Output Service
    - 'completed': полностью обработан (отправлен в destination)
    - 'failed': ошибка при обработке
    - 'cancelled': отменен пользователем
  - progress?: 0..100 — прогресс обработки в процентах (вычисляется на основе статуса)
  - steps?: object — объект с шагами обработки (received, validated, queued, processing, classified, sent_to_jira, completed)
  - current_step?: string — текущий шаг обработки (совпадает со status)
  - errors?: string[] — массив ошибок (если есть, из error_message)
  - retry_count?: number — количество попыток
  - text?: string — текст обращения
  - source?: string — источник
  - predicted_type?: string — предсказанный тип (если классифицирован)
  - confidence?: number — уверенность модели (если классифицирован)
  - decision?: string — решение ('auto-process' | 'manual-review', если классифицирован)
  - jira_ticket_id?: string — ID тикета в Jira или external_id (если отправлен). В GET /tickets/{ticket_id} возвращается как jira_issue_id
  - created_at?: ISO datetime
  - processed_at?: ISO datetime — время завершения классификации
  - error_message?: string — сообщение об ошибке (если есть)
- Errors:
  - 404 — обращение не найдено
  - 503 — база данных PostgreSQL недоступна
    - Сообщение: "База данных PostgreSQL недоступна. Пожалуйста, повторите попытку позже."
  - 500 — внутренняя ошибка
    - Сообщение: "Внутренняя ошибка при получении статуса обращения. Обратитесь к администратору системы."

1.5 POST /tickets/{ticket_id}/cancel — Отменить обработку
- Request
  - reason: string — причина отмены
  - comment?: string — дополнительный комментарий
- Response (200)
  - ticket_id: string
  - status: 'cancelled'
  - cancelled_at: ISO datetime
- Errors: 
  - 404 — обращение не найдено
  - 400 — нельзя отменить (уже completed/cancelled)
  - 503 — база данных PostgreSQL недоступна
    - Сообщение: "База данных PostgreSQL недоступна. Пожалуйста, повторите попытку позже."
  - 500 — внутренняя ошибка
    - Сообщение: "Внутренняя ошибка при отмене обращения. Обратитесь к администратору системы."

1.6 POST /tickets/{ticket_id}/reprocess — Переотправить в очередь
- Request
  - text?: string — опционально заменить исходный текст
  - force?: boolean (default: false) — принудительно переоформить даже если уже обработано (completed)
- Response (202 Accepted)
  - ticket_id: string
  - status: 'queued_for_reprocessing' (в БД устанавливается 'queued')
  - previous_classification?: string — предыдущая классификация predicted_type (если была)
  - requeued_at: ISO datetime
- Поведение:
  - Проверяет текущий статус тикета
  - Если статус 'completed' и force=false → ошибка 400
  - Обновляет статус на 'queued' в БД
  - Опционально обновляет текст, если передан
  - Тикет будет обработан Worker'ом заново
- Errors: 
  - 404 — обращение не найдено
  - 400 — нельзя переоформить без force (если уже completed)
  - 503 — база данных PostgreSQL недоступна
    - Сообщение: "База данных PostgreSQL недоступна. Пожалуйста, повторите попытку позже."
  - 500 — внутренняя ошибка
    - Сообщение: "Внутренняя ошибка при переоформлении обращения. Обратитесь к администратору системы."

1.7 POST /tickets/batch — Пакетная загрузка
- Request
  - tickets: TicketRequest[] — массив запросов на создание обращений
- Response (202 Accepted)
  - batch_id: string — уникальный ID пакета
  - total: number — общее количество обращений в пакете
  - queued: number — количество успешно поставленных в очередь
  - failed: number — количество неудачных попыток
  - estimated_time: number — оценка времени обработки в миллисекундах

1.8 GET /health — Здоровье сервиса (Ingestion)
- Response (200|503)
  - status: 'healthy' | 'unhealthy'
  - redis: 'connected' | 'disconnected' — статус подключения к Redis (очередь)
  - postgresql: 'connected' | 'disconnected' — статус подключения к PostgreSQL
  - config_service: 'connected' | 'disconnected' — статус подключения к Config Service
- Поведение:
  - Автоматически обновляет метрики недоступности при проверке
  - Проверяет доступность всех зависимых сервисов
- Статус 503: возвращается, если Redis или PostgreSQL недоступны

1.9 GET /metrics/unavailability — Метрики недоступности сервисов
- Response (200)
  - config_service: объект с метриками недоступности Config Service
  - postgresql: объект с метриками недоступности PostgreSQL
  - redis: объект с метриками недоступности Redis
- Для каждого сервиса возвращается:
  - total_unavailability_count: number — общее количество событий недоступности
  - is_available: boolean — доступен ли сервис сейчас
  - last_unavailable_at?: ISO datetime — время последней недоступности
  - last_successful_check_at?: ISO datetime — время последней успешной проверки
  - time_since_unavailable_seconds?: number — секунд с последней недоступности
  - time_since_successful_seconds?: number — секунд с последней успешной проверки
  - recent_events_count: number — количество недавних событий
  - recent_events: Array<{timestamp: ISO datetime, service: string, error?: string}> — последние 10 событий недоступности
- Использование:
  - Мониторинг доступности соседних сервисов
  - Анализ истории недоступности для выявления проблемных периодов
  - Настройка алертов при длительной недоступности
  - Отладка проблем с подключением к зависимым сервисам


2) ML Service (Port 8001)

2.1 POST /classify — Классификация текста
- Request
  - text: string (min 3)
  - return_probabilities?: boolean (default true)
  - top_n?: number (0..20, опционально ограничить количество вероятностей; 0 или None - вернуть все)
- Response (200)
  - predicted_type: string
  - confidence: number (0..1)
  - probabilities: Array<{category: string, score: number}> (отсортировано по убыванию; пустой массив, если return_probabilities=false)
  - model_version: string — версия модели, использованная для классификации
  - decision: 'auto-process' | 'manual-review' (определяется по confidence_threshold из Config Service)
  - processing_time_ms: number — время обработки в миллисекундах
- Поведение:
  - Проверяет кэш Redis DB 1 (ключ: cache_predictions:{version}:{hash}, где hash — MD5 хэш текста)
  - Если кэш найден → возвращает результат из кэша (быстро)
  - Если кэш не найден:
    - Проверяет версию модели из Config Service перед классификацией (автоперезагрузка при несоответствии)
    - Выполняет классификацию через модель
    - Сохраняет результат в кэш (TTL: 3600s)
  - Определяет decision на основе confidence_threshold из Config Service
  - Версия модели включается в ключ кэша, чтобы после переключения версии не использовать старые результаты
- Errors: 400 (некорректный текст), 503 (модель не загружена)

2.2 POST /classify/batch — Пакетная классификация
- Request: { texts: string[] }
- Response (200)
  - results: Array<{ text, predicted_type, confidence }>
  - total_time_ms: number

2.3 GET /model/status — Статус модели
- Response (200)
  - model_version: string
  - model_name?: string
  - status?: 'loaded' | 'not_loaded'
  - is_loaded: boolean
  - num_classes?: number
  - classes?: string[]
  - accuracy?: number, precision?: number, recall?: number, f1_score?: number
  - loaded_at?: ISO datetime
  - memory_usage_mb?: number
  - classifier_path: string
  - vectorizer_path: string
  - label_encoder_path: string

2.4 GET /model/list — Список моделей
- Response (200): { models: Array<{ version, name, accuracy?, is_active, created_at? }> }

2.5 GET /health — Состояние сервиса
- Response (200|503)
  - status: 'healthy' | 'unhealthy'
  - model_loaded: boolean
  - model_version?: string
  - uptime_seconds?: number
  - requests_total?: number
  - errors_total?: number
  - avg_latency_ms?: number
  - message: string
  - reason?: string

2.6 POST /reload_model — Перезагрузка модели
- Response (200)
  - success: boolean — успешна ли перезагрузка
  - message: string — сообщение о результате
  - model_version?: string — версия модели после перезагрузки
- Errors: 503 (если не удалось перезагрузить)

2.7 GET /worker/diagnostics — Диагностика Worker и очереди
- Response (200)
  - worker_enabled: boolean — включен ли Worker (WORKER_ENABLED)
  - worker_running: boolean — запущен ли Worker
  - model_loaded: boolean — загружена ли модель
  - queue_pending_length: number — количество тикетов в очереди pending_tickets
  - queue_failed_length: number — количество тикетов в очереди failed_tickets
  - redis_connected: boolean — подключен ли Redis
  - message: string — сообщение о статусе
- Использование: проверка состояния Worker и очереди при проблемах с обработкой тикетов


3) Config Service (Port 8002)

3.1 GET /config — Текущая конфигурация
- Response (200)
  - auto_classification_enabled: boolean
  - service_enabled: boolean
  - confidence_threshold: number
  - model_version: string
  - current_model_version: string
  - jira_integration_enabled: boolean
  - jira_enabled: boolean
  - jira_project_key?: string
  - auto_process_priority?: 'low'|'medium'|'high'|'critical'
  - manual_review_priority?: 'low'|'medium'|'high'|'critical'
  - max_retry_attempts: number
  - retry_delay_seconds?: number
  - timeout_seconds?: number
  - batch_processing_enabled?: boolean
  - batch_size?: number
  - updated_at?: ISO datetime
  - updated_by?: string
  - all_config?: object

3.2 POST /config/toggle — Включить/отключить автоклассификацию
- Request: { enabled: boolean, reason?: string }
- Response (200)
  - auto_classification_enabled: boolean
  - service_enabled: boolean
  - message: string
  - updated_at: ISO datetime

3.3 POST /config/model-version — Переключение версии модели
- Request: { version: string, gradual_rollout?: boolean, rollout_percentage?: number }
- Response (200)
  - model_version: string
  - current_model_version: string
  - message: string
  - previous_version?: string
  - switched_at: ISO datetime
  - active_models?: Record<string, number> (% трафика)

3.4 POST /config/model-switch — Алиас model-version
- Request/Response: аналогично 3.3

3.5 PUT /config/threshold — Изменение порога уверенности
- Request: { threshold: number(0..1), apply_retroactive?: boolean }
- Response (200)
  - confidence_threshold: number
  - previous_threshold?: number
  - message: string
  - affected_tickets?: number
  - updated_at: ISO datetime

3.6 POST /config/jira — Настройка Jira
- Request: { jira_url, jira_user, jira_api_token, jira_project_key, custom_field_mapping?: Record<string,string> }
- Response (200)
  - status: 'configured'
  - connection_test: 'successful'
  - project_key: string
  - available_issue_types?: string[]

3.7 GET /config/audit — История изменений конфигурации
- Query: limit=50, offset=0, changed_field?
- Response (200): { changes: Array<{ id, field, old_value?, new_value?, changed_by, reason?, changed_at }>, total }

3.8 GET /health — Здоровье сервиса
- Response (200|503)
  - status: 'healthy' | 'unhealthy' | 'degraded' — статус сервиса
  - postgresql: 'connected' | 'disconnected' — статус подключения к PostgreSQL
  - fallback_enabled: boolean — включен ли fallback механизм
  - fallback_file?: object — информация о fallback файле (если fallback_enabled=true)
    - exists: boolean — существует ли файл fallback конфигурации
    - path: string — путь к файлу fallback конфигурации
    - updated_at?: ISO datetime — время последнего обновления файла
    - keys_count: number — количество ключей конфигурации в файле
  - sync_task_running?: boolean — запущена ли задача синхронизации (если fallback_enabled=true)
- Статусы:
  - 'healthy': PostgreSQL доступен, конфигурация работает нормально
  - 'degraded': PostgreSQL недоступен, но fallback файл работает (сервис продолжает функционировать)
  - 'unhealthy': PostgreSQL недоступен и fallback файл отсутствует или не работает
- Статус 503: возвращается только если PostgreSQL недоступен И fallback не работает
- Поведение:
  - При недоступности PostgreSQL Config Service автоматически переключается на fallback файл
  - Fallback файл синхронизируется из БД при старте и периодически (настраивается через CONFIG_SYNC_INTERVAL)
  - При каждом изменении конфигурации через API файл обновляется автоматически

Переменные окружения (Config Service)
- CONFIG_FALLBACK_ENABLED: 'true'|'false' (default: 'true') — включить/выключить fallback механизм
- CONFIG_FALLBACK_DIR: string (default: './config_cache') — директория для хранения файла fallback конфигурации
- CONFIG_SYNC_INTERVAL: number (default: 300) — интервал синхронизации конфигурации из БД в файл (в секундах)


4) Output Service (Port 8003)

4.1 POST /process_result — Обработка результата классификации
- Request
  - ticket_id: string
  - predicted_type: string
  - confidence: number (0..1)
  - decision: 'auto-process' | 'manual-review'
  - model_version: string
  - text: string
  - source?: string
  - user_id?: string
  - email?: string
  - priority?: 'low'|'medium'|'high'|'critical'
  - probabilities?: Record<string, number>
  - metadata?: object
- Поведение
  - Получает конфигурацию из Config Service API (GET /config) с fallback на БД
  - Определяет приоритет на основе decision:
    - decision='auto-process' → auto_process_priority (default: 'medium')
    - decision='manual-review' → manual_review_priority (default: 'low')
  - При decision='auto-process' — публикация в целевую систему через выбранный коннектор:
    - DESTINATION_TYPE=jira → JiraConnector (создает тикет через Jira REST API или Service Desk API в зависимости от конфигурации)
    - DESTINATION_TYPE=filesystem → FileSystemConnector (сохраняет JSON в OUTPUT_DIR)
    - DESTINATION_TYPE=mock → MockConnector (генерирует MOCK-{timestamp})
  - При decision='manual-review' — только обновление БД, без отправки
  - Обновляет запись в ticket_events (status='completed', external_id, link, priority, sent_to_jira_at)
  - Записывает в audit_logs (action, status, details, retry_count)
- Response (200)
  - success: boolean
  - message: string
  - ticket_id: string
  - jira_ticket_id?: string — external_id для всех коннекторов: Jira issue key (например, SD-123), FileSystem filename (например, FS-20251119T063936), Mock ID (например, MOCK-20251119063936)
  - jira_link?: string — ссылка для Jira (например, https://jira.example.com/browse/SD-123), путь к файлу для FileSystem (абсолютный путь), null для Mock
  - status: 'completed'
  - processed_at?: ISO datetime
  - retry_count?: number

4.2 GET /health — Здоровье сервиса
- Response (200|503)
  - status: 'healthy' | 'unhealthy'
  - postgresql: 'connected' | 'disconnected'
  - jira_enabled: boolean — включена ли интеграция с Jira

4.3 POST /sync/jira/ticket — Синхронизация одного тикета из Jira
- Request
  - jira_ticket_id: string — ключ тикета в Jira (например, SD-123)
  - ticket_id?: string — ID тикета в нашей системе (опционально, будет найден автоматически)
  - category_field?: string — имя custom field для категории в Jira (например, "customfield_10001")
- Response (200)
  - success: boolean — успешно ли выполнена синхронизация
  - jira_ticket_id: string — ключ тикета в Jira
  - ticket_id?: string — ID тикета в нашей системе
  - updated_fields: string[] — список обновленных полей (actual_type, feedback_status, training_ready и т.д.)
  - errors: string[] — список ошибок при синхронизации
- Поведение:
  - Получает данные тикета из Jira по jira_ticket_id
  - Извлекает категорию из Jira (custom field, labels, components, issue type)
  - Если категория отличается от predicted_type, обновляет actual_type в PostgreSQL
  - Помечает тикет как training_ready, если decision='manual-review' и actual_type установлена
  - Обновляет feedback_status='incorrect' и feedback_correct_type, если категория отличается
- Errors: 500 (ошибка синхронизации), 404 (тикет не найден в БД)

4.4 POST /sync/jira/batch — Пакетная синхронизация тикетов из Jira
- Request
  - jira_ticket_ids: string[] — список ключей тикетов в Jira
  - category_field?: string — имя custom field для категории
- Response (200)
  - total: number — общее количество тикетов
  - successful: number — успешно синхронизировано
  - failed: number — не удалось синхронизировать
  - details: SyncResultResponse[] — детали по каждому тикету

4.5 POST /sync/jira/jql — Синхронизация тикетов по JQL запросу
- Request
  - jql: string — JQL запрос для поиска тикетов в Jira
  - category_field?: string — имя custom field для категории
  - max_results?: number (default: 100, max: 1000) — максимальное количество тикетов
- Response (200): аналогично 4.4
- Примеры JQL:
  - "project = SD AND status = Resolved"
  - "project = SD AND updated >= -7d"
  - "project = SD AND labels = 'training-ready'"

4.6 POST /sync/jira/all — Синхронизация всех тикетов с jira_ticket_id
- Request
  - category_field?: string — имя custom field для категории
  - limit?: number (default: 100, max: 1000) — максимальное количество тикетов
- Response (200): аналогично 4.4
- Поведение:
  - Находит все тикеты в БД, у которых есть jira_ticket_id
  - Синхронизирует их с данными из Jira
  - Сортирует по sent_to_jira_at DESC, затем по created_at DESC

4.7 GET /jira/ticket/{jira_ticket_id} — Получить данные тикета из Jira
- Path parameters
  - jira_ticket_id: string — ключ тикета в Jira (например, SD-123)
- Query parameters
  - expand?: string — список полей для расширения через запятую (например, "fields,changelog")
- Response (200)
  - Данные тикета из Jira REST API (полный объект issue)
  - Содержит fields, key, id, self и другие стандартные поля Jira API
  - Формат ответа соответствует Jira REST API v3
- Поведение:
  - Получает данные тикета из Jira через REST API
  - Не выполняет синхронизацию с PostgreSQL
  - Используется для просмотра данных тикета без обновления БД
- Errors: 
  - 404 (тикет не найден в Jira или нет доступа)
  - 503 (Jira клиент отключен или не настроен)
  - 500 (ошибка запроса к Jira)

4.8 GET /jira/search — Поиск тикетов в Jira по JQL
- Query parameters
  - jql: string — JQL запрос (обязательный, например, "project = SD AND status = Resolved")
  - fields?: string — список полей через запятую (например, "key,summary,status"). Если не указан, возвращаются все поля
  - max_results?: number (default: 50, max: 1000) — максимальное количество результатов
  - start_at?: number (default: 0) — смещение для пагинации
- Response (200)
  - expand: string — расширенные поля
  - startAt: number — смещение
  - maxResults: number — максимальное количество результатов
  - total: number — общее количество найденных тикетов
  - issues: Array<Issue> — массив тикетов из Jira (формат соответствует Jira REST API v3)
- Поведение:
  - Выполняет поиск тикетов в Jira по JQL запросу
  - Не выполняет синхронизацию с PostgreSQL
  - Используется для просмотра и фильтрации тикетов в Jira
- Примеры JQL:
  - "project = SD AND status = Resolved"
  - "project = SD AND updated >= -7d"
  - "project = SD AND assignee = currentUser()"
  - "project = SD AND labels = 'training-ready'"
- Errors: 
  - 503 (Jira клиент отключен или не настроен)
  - 500 (ошибка запроса к Jira или не удалось выполнить поиск)

Коннекторы (ITicketDestination)
- process_and_send(payload) -> (external_id, link, retry_count)
- validate_connection()
- get_name()

Переменные окружения (Output)
- DESTINATION_TYPE: 'filesystem'|'mock'|'jira'|'fs'|'file' (default: 'filesystem')
  - 'filesystem', 'fs', 'file' → FileSystemConnector
  - 'jira' → JiraConnector
  - 'mock' → MockConnector
- OUTPUT_DIR: каталог для файлов (filesystem; default './out')
- Jira коннектор (стандартный API):
  - JIRA_URL: URL Jira сервера (обязательно)
  - JIRA_USER: имя пользователя Jira (обязательно)
  - JIRA_API_TOKEN: API токен Jira (обязательно)
  - JIRA_PROJECT_KEY: ключ проекта Jira (обязательно)
  - JIRA_ENABLED: 'true'|'false' (default: 'true') — включить/выключить Jira коннектор
- Jira коннектор (Service Desk API):
  - JIRA_USE_SERVICEDESK_API: 'true'|'false' (default: 'false') — использовать Service Desk API вместо стандартного
  - JIRA_SERVICE_DESK_ID: ID Service Desk проекта (обязательно при JIRA_USE_SERVICEDESK_API=true)
  - JIRA_REQUEST_TYPE_ID: ID типа запроса (Request Type) (обязательно при JIRA_USE_SERVICEDESK_API=true)
- JIRA_VALIDATE_CONNECTION: 'true'|'false' (default: 'false') — проверять подключение к Jira при валидации коннектора
  
Примечание: Service Desk API (`/rest/servicedeskapi/request`) рекомендуется для работы с Jira Service Management проектами, так как учитывает специфику Service Desk (service projects, request types, SLA и т.д.). Стандартный API (`/rest/api/3/issue`) подходит для обычных Jira проектов.


5) Dashboard (Port 8501)
- UI на Streamlit.
- Взаимодействует с Ingestion/ML/Config/Output API (см. dashboard/utils/api_client.py).
- **Режимы работы:**
  - **Demo Mode** (по умолчанию): Прямая классификация через ML Service без логирования в БД
  - **Production Mode**: Полный pipeline через Ingestion Service с логированием в ticket_events
- **Используемые API:**

**ML Service:**
  - `POST /classify` — классификация текста (Demo Mode)
  - `GET /health` — проверка работоспособности
  - `GET /model/status` — информация о модели
  - `POST /reload_model` — перезагрузка модели

**Config Service:**
  - `GET /config` — получение текущей конфигурации
  - `POST /config/toggle` — включение/отключение автоклассификации
  - `POST /config/model-version` — переключение версии модели
  - `PUT /config/threshold` — изменение порога уверенности

**Ingestion Service (Production Mode):**
  - `POST /tickets` — создание тикета
  - `GET /status/{ticket_id}` — проверка статуса обработки (polling)
  - `GET /tickets/{ticket_id}` — получение деталей тикета

**Основные потоки:**
  - **Demo классификация**: POST /classify (ML) → результат сразу (без создания записи в БД)
  - **Production классификация**: POST /tickets (Ingestion) → polling GET /status/{ticket_id} → GET /tickets/{ticket_id} (с полным логированием)
  - **Мониторинг**: читает метрики/события из БД через прямые SQL запросы
  - **Настройки**: использует эндпойнты Config Service для управления конфигурацией


Ошибки и обработка
- 400 ValidationError: некорректные параметры
  - Сообщения содержат описание проблемы валидации
- 404 Not Found: запись не найдена (ticket_id и т.п.)
  - Сообщения указывают, какой ресурс не найден
- 500 Internal Server Error: внутренняя ошибка сервиса
  - Сообщения понятны для пользователей: "Внутренняя ошибка при [операции]. Обратитесь к администратору системы."
  - Для критичных операций (создание тикета) включает ID для отслеживания
- 503 Service Unavailable: зависимые подсистемы недоступны
  - Модель не загружена (ML Service)
  - БД/Redis/Jira недоступны
  - Сообщения понятны: "База данных PostgreSQL недоступна. Пожалуйста, повторите попытку позже."
  - Config Service: "Сервис автоматической классификации отключен" (если отключен через Config Service)
  
**Улучшенные сообщения об ошибках:**
- Все сообщения об ошибках теперь понятны для конечных пользователей
- Технические детали скрыты, но логируются для администраторов
- Сообщения содержат рекомендации (повторить попытку, обратиться к администратору)
- Для временных проблем (БД, Redis) используется статус 503 с понятными сообщениями

Версионирование API
- Текущая версия: v1 (без префикса). Для дальнейшего развития рекомендуется ввести /v1 префикс.

Интеграции между сервисами

Ниже описаны API вызовы, которые выполняются внутри системы между сервисами. Эти интеграции автоматические и не требуют ручного вызова, но важно понимать их для отладки и мониторинга.

1) Ingestion Service → Config Service
- GET /config — используется для проверки service_enabled перед созданием тикетов
  - Вызывается в: POST /tickets (перед созданием тикета)
  - Fallback: если Config Service недоступен, используется значение по умолчанию (True)
  - Цель: предотвратить создание тикетов, когда сервис отключен через Config Service

2) ML Service → Config Service
- GET /config — используется для:
  - Проверки current_model_version перед классификацией (автоперезагрузка модели при несоответствии)
  - Получения confidence_threshold для определения decision (auto-process vs manual-review)
  - Вызывается в:
    - POST /classify (REST API) — проверка версии модели и порога уверенности
    - Worker (асинхронная обработка очереди) — проверка версии модели перед классификацией, получение порога уверенности
  - Fallback: если Config Service недоступен, используются значения по умолчанию
  - Таймаут: 1.5-2.0 секунды (не блокирует классификацию)

3) ML Service (Worker) → Output Service
- POST /process_result — отправка результатов классификации для дальнейшей обработки
  - Вызывается в: Worker после успешной классификации тикета
  - Payload: { ticket_id, predicted_type, confidence, decision, model_version, text, source, user_id, email, priority, probabilities }
  - Поведение: Worker автоматически отправляет результат в Output Service после обновления статуса на 'classified'
  - Обработка ошибок: при ошибке Output Service тикет остается в статусе 'classified' (не переходит в 'failed'), ошибка записывается в error_message

4) Output Service → Config Service
- GET /config — используется для получения:
  - Приоритетов: auto_process_priority, manual_review_priority
  - Jira конфигурации: jira_enabled, jira_url, jira_user, jira_api_token, jira_project_key
  - Вызывается в: POST /process_result (перед определением приоритета и отправкой в destination)
  - Fallback: если Config Service недоступен, используется прямое чтение из БД (таблица configuration)
  - Таймаут: CONFIG_SERVICE_TIMEOUT (по умолчанию 5 секунд)
  - Цель: отказоустойчивость — система продолжает работать даже при недоступности Config Service

5) Dashboard → Все сервисы
- Использует API всех сервисов для демонстрации и управления (см. раздел 5) Dashboard)

Важные замечания по интеграциям:
- Все внутренние API вызовы имеют таймауты и обработку ошибок
- При недоступности зависимого сервиса система использует fallback механизмы (значения по умолчанию или прямое чтение из БД)
- Worker в ML Service автоматически обрабатывает очередь и интегрируется с Config Service и Output Service
- Output Service имеет встроенный fallback на БД при недоступности Config Service API
- Config Service имеет fallback механизм через файл конфигурации при недоступности PostgreSQL
  - Файл синхронизируется из БД при старте и периодически (настраивается через CONFIG_SYNC_INTERVAL)
  - При каждом изменении конфигурации через API файл обновляется автоматически
  - При недоступности PostgreSQL Config Service продолжает работать в режиме 'degraded' используя fallback файл
- Ingestion Service отслеживает метрики недоступности всех соседних сервисов
  - Метрики доступны через GET /metrics/unavailability
  - Автоматически обновляются при всех операциях с зависимыми сервисами
  - Позволяют отслеживать историю недоступности и настраивать алерты

Ссылки
- Архитектура: ARCHITECTURE.md
- Быстрый старт: startup-guide.md
- Подробный запуск: startup-guide.md


