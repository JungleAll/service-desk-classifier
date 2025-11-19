Service Desk Config Service (Port 8002)

Назначение
- Централизованное хранение и управление конфигурацией системы
- Переключение версий моделей (с поддержкой gradual rollout)
- Управление порогами уверенности, флагами функциональности
- Настройка интеграции с Jira и аудит изменений

Эндпойнты
- GET /config: получить текущую конфигурацию (расширенный ответ)
- POST /config/toggle: включить/отключить автоклассификацию (reason optional)
- POST /config/model-version: переключить версию модели (gradual_rollout, rollout_percentage)
- POST /config/model-switch: алиас
- PUT /config/threshold: изменить порог уверенности (apply_retroactive)
- POST /config/jira: настроить Jira (url/user/api_token/project_key)
- GET /config/audit: история изменений (limit/offset/changed_field)
- GET /health: здоровье сервиса/подключение к БД

Схема БД
- configuration (key,value,updated_at,updated_by)
- config_audit_log (field,old_value,new_value,changed_by,reason,changed_at)
- model_versions (история, активная версия) — чтение/обновление статусов

Конфигурация (env)
- POSTGRES_*: подключение к БД (POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD)
- API_HOST: хост для запуска сервиса (по умолчанию: 0.0.0.0)
- API_PORT: порт для запуска сервиса (по умолчанию: 8002)
- LOG_LEVEL: уровень логирования (по умолчанию: INFO)

Запуск
- uvicorn config_service.app:app --host 0.0.0.0 --port 8002
- docker-compose up config_service

Безопасность/Аудит
- Все изменения конфигурации логируются в config_audit_log
- Метаданные обновлений: updated_by, reason

Интеграции
- ML Service (порт 8001) читает: confidence_threshold, current_model_version (при старте и перед классификацией)
- Output Service (порт 8003) читает: jira_enabled, jira_* и приоритеты (auto_process_priority, manual_review_priority)
- Ingestion Service (порт 8000) проверяет: service_enabled перед созданием обращений
- Dashboard (порт 8501) использует: GET /config, POST /config/toggle, POST /config/model-version, PUT /config/threshold


