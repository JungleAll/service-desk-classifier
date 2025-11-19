Service Desk Classifier — Microservices Platform

Описание
- Платформа автоматизации обработки обращений Service Desk на базе микросервисов
- Классификация текста (ML), управление конфигурацией, постановка в очередь, вывод в внешние системы (Jira / файловая система / mock), мониторинг

Архитектура
- Ingestion Service (Port 8000): прием обращений, запись в БД, постановка в Redis очередь
- ML Service (Port 8001): предобработка, инференс модели, метрики, кэширование в Redis
- Config Service (Port 8002): конфигурация, пороги, переключение версий моделей, аудит
- Output Service (Port 8003): постобработка и публикация результата (плагинные коннекторы)
- Database (PostgreSQL): ticket_events, metrics, configuration, model_versions, audit/error logs
- Redis: очереди и кэш предсказаний
- Dashboard (Port 8501): мониторинг/демо/управление

Быстрый старт
1) Docker Compose (рекомендуется)
- Требования: Docker, Docker Compose
- Запуск: docker-compose up -d
- Проверка: 
  - Ingestion: http://localhost:8000/docs
  - ML: http://localhost:8001/docs
  - Config: http://localhost:8002/docs
  - Output: http://localhost:8003/docs
  - Dashboard: http://localhost:8501

2) Локальный запуск сервисов
- Подготовьте .env (см. переменные ниже) и установите зависимости из requirements.txt каждого сервиса
- Запуск (пример): uvicorn <service>.app:app --host 0.0.0.0 --port <port>

Переменные окружения (основные)
- PostgreSQL (shared/database.py): POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
- Redis (shared/redis_client.py): REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD?
- Output Service:
  - DESTINATION_TYPE: filesystem | mock | jira (default: filesystem)
  - OUTPUT_DIR: каталог для сохранения файлов (filesystem), default: ./out
  - JIRA_URL, JIRA_USER, JIRA_API_TOKEN, JIRA_PROJECT_KEY (для jira)
- ML Service: ML_SERVICE_HOST/PORT (по умолчанию 0.0.0.0:8001), пути к моделям в ml_service/config.py
- Общие: LOG_LEVEL=INFO

Основные сценарии
- Создать обращение: POST /tickets (Ingestion)
- Проверить статус: GET /status/{ticket_id} (Ingestion)
- Классифицировать текст: POST /classify (ML)
- Обработать результат: POST /process_result (Output)
- Прочитать/изменить конфигурацию: GET /config, POST /config/toggle, PUT /config/threshold (Config)

Ключевые возможности
- Плагинные коннекторы вывода (filesystem/mock/jira) через ITicketDestination и DESTINATION_TYPE
- Кэш предсказаний (Redis), метрики, аудит конфигурации
- Совместимость с Docker/Docker Compose, Health endpoints

Документация компонентов
- Ingestion: ingestion_service/README.md
- ML: ml_service/README.md
- Config: config_service/README.md
- Output: output_service/README.md
- Database: database/README.md
- Shared utils: shared/README.md
- Dashboard: dashboard/README.md

Полезные материалы
- README-ARCHITECTURE.md — архитектурные диаграммы
- startup-guide.md — подробное руководство по запуску (включает быстрый старт и Docker Compose)
- API_IMPLEMENTATION_GUIDE.md — руководство по реализации API
- API_IMPLEMENTATION_STATUS.md — статус реализации API

Лицензия
- Для внутреннего использования в рамках проекта (при необходимости добавьте LICENCE) 


