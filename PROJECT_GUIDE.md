# Путеводитель по проекту Service Desk Classifier

## Оглавление

1. [Обзор проекта](#обзор-проекта)
2. [Архитектура системы](#архитектура-системы)
3. [Технологический стек](#технологический-стек)
4. [Структура проекта](#структура-проекта)
5. [Компоненты системы](#компоненты-системы)
6. [Установка и запуск](#установка-и-запуск)
7. [API документация](#api-документация)
8. [Модели машинного обучения](#модели-машинного-обучения)
9. [База данных](#база-данных)
10. [Redis и кэширование](#redis-и-кэширование)
11. [Тестирование](#тестирование)
12. [Мониторинг и логирование](#мониторинг-и-логирование)
13. [Развертывание](#развертывание)
14. [Дополнительные материалы](#дополнительные-материалы)

---

## Обзор проекта

**Service Desk Classifier** — это микросервисная платформа для автоматической классификации обращений в Service Desk с использованием машинного обучения. Система классифицирует текстовые обращения на 17 категорий и автоматически направляет их на обработку или ручную проверку в зависимости от уровня уверенности модели.

### Ключевые возможности

- **Автоматическая классификация** обращений на 17 категорий (TF-IDF + Logistic Regression)
- **Микросервисная архитектура** для масштабируемости и надежности
- **Интеграция с Jira** для автоматической публикации тикетов
- **Кэширование результатов** для повышения производительности
- **Мониторинг и аудит** всех операций
- **Гибкая конфигурация** через централизованный Config Service
- **Веб-интерфейс** для демонстрации и управления

### Основные категории классификации

1. HR: Перевод через увольнение
2. HR: Приём
3. HR: Техническое увольнение
4. HR: Увольнение
5. Заказ визиток
6. Заказ гостевого пропуска
7. Запрос на обслуживание
8. Заявка на билет и проживание
9. Заявка на выход сотрудника
10. Заявка на согласование ВМ
11. Изменение персональных данных
12. Изменение условий работы
13. Подзадача
14. Подзадача основные средства
15. Подзадача увольнение
16. Согласование VDI
17. Уведомление о работах

---

## Архитектура системы

### Общая архитектура

Система построена на основе микросервисной архитектуры и состоит из следующих компонентов:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Ingestion  │────▶│     ML      │────▶│   Output    │────▶│    Jira     │
│   Service   │     │   Service   │     │   Service   │     │             │
│  (Port 8000)│     │ (Port 8001) │     │ (Port 8003) │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
       │                    │                    │
       │                    │                    │
       ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────┐
│                    PostgreSQL                            │
│  (ticket_events, configuration, metrics, audit_logs)     │
└─────────────────────────────────────────────────────────┘
       │
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│                      Redis                               │
│  DB 0: Очереди (pending_tickets, failed_tickets)        │
│  DB 1: Кэш (cache_predictions)                          │
└─────────────────────────────────────────────────────────┘
       │
       │
       ▼
┌─────────────┐     ┌─────────────┐
│   Config    │     │  Dashboard  │
│   Service   │     │ (Port 8501) │
│ (Port 8002) │     │             │
└─────────────┘     └─────────────┘
```

### Поток обработки обращения

#### Режим 1: REST API (без Worker)

```
Клиент → POST /tickets (Ingestion) → PostgreSQL
                                      ↓
                              Redis Queue (pending_tickets)
                                      ↓
                              POST /classify (ML Service) → Результат
```

#### Режим 2: С Worker (автоматическая обработка)

```
Клиент → POST /tickets (Ingestion) → PostgreSQL
                                      ↓
                              Redis Queue (pending_tickets)
                                      ↓
                              Worker (ML Service) → Классификация
                                      ↓
                              POST /process_result (Output Service) → Jira/FileSystem
```

---

## Технологический стек

### Backend
- **Python 3.11+** — основной язык разработки
- **FastAPI** — веб-фреймворк для создания REST API
- **Uvicorn** — ASGI сервер для запуска FastAPI приложений
- **Pydantic** — валидация данных

### Machine Learning
- **scikit-learn** — библиотека машинного обучения
- **pymorphy3** — морфологический анализ русского языка
- **nltk** — обработка естественного языка (стоп-слова)

### База данных и кэширование
- **PostgreSQL 15** — основная база данных
- **Redis 7** — очереди и кэширование

### Frontend
- **Streamlit** — веб-интерфейс для демонстрации и мониторинга

### Инфраструктура
- **Docker & Docker Compose** — контейнеризация и оркестрация
- **psycopg2** — драйвер PostgreSQL для Python
- **httpx** — асинхронный HTTP клиент

---

## Структура проекта

```
service-desk-classifier/
├── ingestion_service/          # Сервис приема обращений
│   ├── app.py                  # FastAPI приложение
│   ├── models.py               # Pydantic модели
│   ├── config.py               # Конфигурация
│   ├── metrics.py              # Метрики
│   ├── run.py                  # Скрипт запуска
│   ├── Dockerfile              # Docker образ
│   ├── requirements.txt        # Зависимости
│   └── README.md               # Документация
│
├── ml_service/                 # ML сервис классификации
│   ├── app.py                  # FastAPI приложение
│   ├── classifier.py           # Класс для работы с моделью
│   ├── preprocessor.py         # Предобработка текста
│   ├── worker.py               # Worker для обработки очереди
│   ├── models.py               # Pydantic модели
│   ├── config.py               # Конфигурация
│   ├── run.py                  # Скрипт запуска
│   ├── Dockerfile              # Docker образ
│   ├── requirements.txt        # Зависимости
│   ├── README.md               # Документация
│   └── WORKER_MODES.md         # Описание режимов работы
│
├── config_service/             # Сервис конфигурации
│   ├── app.py                  # FastAPI приложение
│   ├── models.py               # Pydantic модели
│   ├── config.py               # Конфигурация
│   ├── config_fallback.py      # Fallback конфигурация
│   ├── run.py                  # Скрипт запуска
│   ├── Dockerfile              # Docker образ
│   ├── requirements.txt        # Зависимости
│   ├── README.md               # Документация
│   └── FALLBACK_CONFIG.md      # Описание fallback
│
├── output_service/             # Сервис вывода результатов
│   ├── app.py                  # FastAPI приложение
│   ├── jira_client.py          # Клиент Jira
│   ├── jira_sync.py            # Синхронизация с Jira
│   ├── models.py               # Pydantic модели
│   ├── config.py               # Конфигурация
│   ├── run.py                  # Скрипт запуска
│   ├── Dockerfile              # Docker образ
│   ├── requirements.txt        # Зависимости
│   ├── README.md               # Документация
│   ├── JIRA_SERVICEDESK_SETUP.md
│   ├── JIRA_SYNC_GUIDE.md
│   └── VERIFICATION_REPORT.md
│
├── dashboard/                  # Веб-интерфейс
│   ├── app.py                  # Главное приложение Streamlit
│   ├── pages/                  # Страницы Dashboard
│   │   ├── demo.py             # Демо классификации
│   │   ├── monitoring.py       # Мониторинг
│   │   └── settings.py         # Управление
│   ├── utils/                  # Утилиты
│   │   ├── api_client.py       # HTTP клиент
│   │   └── config.py           # Конфигурация
│   ├── Dockerfile              # Docker образ
│   ├── requirements.txt        # Зависимости
│   └── README-dash.md          # Документация
│
├── shared/                     # Общие утилиты
│   ├── database.py             # Пул подключений PostgreSQL
│   ├── redis_client.py         # Клиент Redis
│   ├── logger.py               # Централизованное логирование
│   ├── requirements.txt        # Зависимости
│   ├── README.md               # Документация
│   └── REDIS_ARCHITECTURE.md   # Архитектура Redis
│
├── database/                   # База данных
│   ├── schema.sql              # Схема БД
│   ├── init_db.py              # Инициализация БД
│   ├── migrations/             # Миграции
│   └── README.md               # Документация
│
├── models/                     # Модели ML
│   └── v1.0/                   # Версия модели
│       ├── classifier.pkl          # не в репозитории
│       ├── vectorizer.pkl
│       ├── label_encoder.pkl
│       ├── config.json
│       └── README_models.md
│
├── notebooks/                  # Jupyter notebooks
│   ├── 01_eda.ipynb            # Exploratory Data Analysis
│   ├── 02_preprocessing.ipynb  # Предобработка данных
│   ├── 03_model_training.ipynb # Обучение модели
│   └── 04_testevaluation.ipynb # Тестирование и оценка
│
├── check_scripts/              # Скрипты проверки
│   ├── test_*.py               # Тестовые скрипты
│   └── check_*.py              # Скрипты проверки
│
├── app_tests/                  # Тесты производительности
│   ├── load_tests/             # Нагрузочные тесты
│   └── documentation/          # Документация по тестам
│
├── demo_data/                  # Демо данные
│   ├── batch_tickets.csv
│   └── batch_tickets.json
│
├── docker-compose.yml          # Docker Compose конфигурация
├── README.md                   # Основная документация
├── startup-guide.md            # Руководство по запуску
└── LICENSE                     # Лицензия
```

---

## Компоненты системы

### 1. Ingestion Service (Порт 8000)

**Назначение:** Прием обращений из внешних источников, валидация, запись в БД и постановка в очередь Redis.

**Основные функции:**
- Прием обращений через REST API
- Валидация данных
- Запись в PostgreSQL (таблица `ticket_events`)
- Постановка в очередь Redis (`pending_tickets`)
- Предоставление статусов обработки

**API Endpoints:**
- `POST /tickets` — создать обращение
- `GET /tickets` — список обращений с фильтрацией
- `GET /tickets/{ticket_id}` — детали обращения
- `GET /status/{ticket_id}` — статус обработки
- `POST /tickets/{ticket_id}/cancel` — отменить обработку
- `POST /tickets/{ticket_id}/reprocess` — переотправить в очередь
- `POST /tickets/batch` — пакетная загрузка обращений
- `GET /health` — проверка работоспособности

**Документация:** `ingestion_service/README.md`

---

### 2. ML Service (Порт 8001)

**Назначение:** Классификация текстовых обращений с использованием обученной ML модели.

**Основные функции:**
- Классификация текста на 17 категорий
- Предобработка текста (лемматизация, удаление стоп-слов)
- Кэширование результатов в Redis
- Два режима работы: REST API и Worker

**API Endpoints:**
- `POST /classify` — классификация текста
- `POST /classify/batch` — пакетная классификация
- `GET /model/status` — информация о модели
- `GET /model/list` — список доступных моделей
- `POST /reload_model` — hot reload модели
- `GET /health` — проверка работоспособности

**Режимы работы:**
1. **REST API режим** (по умолчанию) — классификация по запросу
2. **Worker режим** — автоматическая обработка очереди Redis

**Документация:** `ml_service/README.md`, `ml_service/WORKER_MODES.md`

---

### 3. Config Service (Порт 8002)

**Назначение:** Централизованное хранение и управление конфигурацией системы.

**Основные функции:**
- Управление версиями моделей
- Настройка порогов уверенности
- Управление флагами функциональности
- Аудит изменений конфигурации
- Настройка интеграции с Jira

**API Endpoints:**
- `GET /config` — получить текущую конфигурацию
- `POST /config/toggle` — включить/отключить автоклассификацию
- `POST /config/model-version` — переключить версию модели
- `PUT /config/threshold` — изменить порог уверенности
- `POST /config/jira` — настроить Jira
- `GET /config/audit` — история изменений
- `GET /health` — проверка работоспособности

**Документация:** `config_service/README.md`

---

### 4. Output Service (Порт 8003)

**Назначение:** Постобработка результатов классификации и отправка в целевую систему.

**Основные функции:**
- Отправка результатов в Jira/Filesystem/Mock
- Обновление статусов в БД
- Логирование операций
- Retry механизм для Jira

**Плагинные коннекторы:**
- **filesystem** — сохранение JSON файлов
- **mock** — генерация mock результатов
- **jira** — отправка в Jira Service Desk

**API Endpoints:**
- `POST /process_result` — обработать результат классификации
- `GET /health` — проверка работоспособности

**Документация:** `output_service/README.md`

---

### 5. Dashboard (Порт 8501)

**Назначение:** Веб-интерфейс для демонстрации и управления системой.

**Основные функции:**
- **Demo классификации** — интерактивная классификация текстов
- **Мониторинг** — отслеживание статуса системы и метрик
- **Управление** — настройка параметров классификации

**Документация:** `dashboard/README-dash.md`

---

### 6. Shared Utilities

**Назначение:** Общие утилиты для всех микросервисов.

**Модули:**
- `database.py` — пул подключений к PostgreSQL
- `redis_client.py` — клиент Redis (очереди и кэш)
- `logger.py` — централизованное логирование с JSON форматом

**Документация:** `shared/README.md`, `shared/REDIS_ARCHITECTURE.md`

---

## Установка и запуск

### Требования

- Python 3.11+
- Docker и Docker Compose (рекомендуется)
- PostgreSQL 15 (если запускаете локально)
- Redis 7 (если запускаете локально)

### Способ 1: Docker Compose (Рекомендуется)

1. **Клонируйте репозиторий:**
```bash
git clone <repository-url>
cd service-desk-classifier
```

2. **Обучите модель и разместите артефакты в `models/v1.0/`** (см. [quick-start-guide.md](quick-start-guide.md)):
```
models/v1.0/
├── classifier.pkl
├── vectorizer.pkl
├── label_encoder.pkl
└── config.json
```

3. **Запустите все сервисы:**
```bash
docker-compose up -d
```

4. **Проверьте статус:**
```bash
docker-compose ps
```

5. **Откройте Dashboard:**
```
http://localhost:8501
```

### Способ 2: Локальный запуск

Подробное руководство см. в `startup-guide.md`.

**Быстрый старт:**

1. **Создайте виртуальное окружение:**
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# или
source venv/bin/activate  # Linux/Mac
```

2. **Установите зависимости:**
```bash
cd ml_service
pip install -r requirements.txt
cd ../dashboard
pip install -r requirements.txt
```

3. **Запустите PostgreSQL и Redis** (через Docker или локально)

4. **Запустите ML Service:**
```bash
cd ml_service
python run.py
```

5. **Запустите Dashboard:**
```bash
cd dashboard
streamlit run app.py
```

### Переменные окружения

Основные переменные окружения для каждого сервиса описаны в соответствующих README файлах.

**Общие переменные:**
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- `LOG_LEVEL` (по умолчанию: `INFO`)

---

## API документация

После запуска сервисов документация API доступна автоматически:

- **Ingestion Service:** http://localhost:8000/docs
- **ML Service:** http://localhost:8001/docs
- **Config Service:** http://localhost:8002/docs
- **Output Service:** http://localhost:8003/docs

### Примеры использования

#### Создание обращения через Ingestion Service

```bash
curl -X POST "http://localhost:8000/tickets" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Не могу войти в систему",
    "source": "api",
    "priority": "medium"
  }'
```

#### Классификация текста через ML Service

```bash
curl -X POST "http://localhost:8001/classify" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Увольнение Иванова И.И. с должности менеджера"
  }'
```

**Ответ:**
```json
{
  "predicted_type": "HR: Увольнение",
  "confidence": 0.98,
  "probabilities": {
    "HR: Увольнение": 0.98,
    "HR: Техническое увольнение": 0.01,
    ...
  },
  "model_version": "v1.0",
  "decision": "auto-process",
  "processing_time_ms": 45
}
```

#### Получение конфигурации

```bash
curl http://localhost:8002/config
```

---

## Модели машинного обучения

### Текущая модель (v1.0)

- **Алгоритм:** LogisticRegression + TF-IDF
- **Количество классов:** 17 (настраивается при обучении)
- **Файлы модели** (не в репозитории, обучаются локально):
  - `classifier.pkl` — классификатор
  - `vectorizer.pkl` — векторизатор текста
  - `label_encoder.pkl` — кодировщик меток

### Предобработка текста

1. **Очистка:**
   - Удаление email адресов
   - Удаление URL
   - Удаление дат
   - Замена чисел на токен `NUM`
   - Удаление специальных символов
   - Приведение к нижнему регистру

2. **Лемматизация:**
   - Преобразование слов в начальную форму (pymorphy3)
   - Удаление стоп-слов (nltk)
   - Удаление слов короче 3 символов

### Обучение модели

Процесс обучения описан в Jupyter notebooks:
- `notebooks/01_eda.ipynb` — анализ данных
- `notebooks/02_preprocessing.ipynb` — предобработка
- `notebooks/03_model_training.ipynb` — обучение
- `notebooks/04_testevaluation.ipynb` — тестирование

### Переключение версий моделей

Версия модели управляется через Config Service:

```bash
curl -X POST "http://localhost:8002/config/model-version" \
  -H "Content-Type: application/json" \
  -d '{
    "version": "v1.0",
    "gradual_rollout": false,
    "rollout_percentage": 100
  }'
```

---

## База данных

### Схема базы данных

Основные таблицы:

1. **ticket_events** — события обращений
   - `ticket_id`, `text`, `source`, `status`
   - `predicted_type`, `confidence`, `decision`
   - `jira_ticket_id`, `jira_link`
   - `created_at`, `processed_at`

2. **configuration** — конфигурация системы
   - `key`, `value`, `updated_at`, `updated_by`

3. **model_versions** — версии моделей
   - `version`, `model_path`, `accuracy`, `is_active`

4. **metrics** — метрики модели
   - `model_version`, `metric_name`, `metric_value`

5. **config_audit_log** — аудит изменений конфигурации
   - `field`, `old_value`, `new_value`, `changed_by`

6. **error_logs** — логи ошибок
7. **audit_logs** — логи аудита

Полная схема БД: `database/schema.sql`

### Инициализация БД

При использовании Docker Compose БД инициализируется автоматически через `database/schema.sql`.

Для локального запуска:

```bash
python database/init_db.py
```

### Миграции

Миграции находятся в `database/migrations/`. Для применения:

```bash
python database/apply_migration.py
```

---

## Redis и кэширование

### Архитектура Redis

Redis разделен на две базы данных:

- **DB 0 (Очереди):** 
  - `pending_tickets` — очередь тикетов для обработки
  - `failed_tickets` — очередь неудачно обработанных тикетов

- **DB 1 (Кэш):**
  - `cache_predictions` — кэш результатов классификации (TTL: 1 час)

### Использование кэша

Кэш автоматически используется ML Service для ускорения повторных запросов. Ключ кэша формируется на основе:
- Хэш текста запроса
- Версия модели

Подробнее: `shared/REDIS_ARCHITECTURE.md`

---

## Тестирование

### Скрипты проверки

В директории `check_scripts/` находятся скрипты для проверки различных компонентов:

- `test_pipeline.py` — тестирование полного pipeline
- `test_cache_reuse.py` — тестирование кэша
- `test_batch_processing.py` — тестирование пакетной обработки
- `check_metrics.py` — проверка метрик
- и другие

### Нагрузочное тестирование

Нагрузочные тесты находятся в `app_tests/load_tests/`:

- `simple_load_test.py` — простой нагрузочный тест
- `load_test_unique.py` — тест с уникальными запросами
- `load_test_overlapping.py` — тест с повторяющимися запросами

Документация: `app_tests/documentation/LOAD_TEST_INSTRUCTIONS.md`

### Пример запуска тестов

```bash
cd check_scripts
python test_pipeline.py
```

---

## Мониторинг и логирование

### Логирование

Все сервисы используют централизованное логирование через `shared/logger.py`:

- **Формат:** JSON для файлов, стандартный для stdout
- **Расположение:** `./logs/` (локально) или `/app/logs/` (Docker)
- **Ротация:** автоматическая при достижении 10MB

**Файлы логов:**
- `ingestion.log`
- `ml.log`
- `ml.worker.log`
- `config.log`
- `output.log`

### Мониторинг через Dashboard

Dashboard предоставляет:
- Статус системы и метрики
- Историю классификаций
- Информацию о модели

### Health Checks

Все сервисы предоставляют endpoint `/health`:

```bash
curl http://localhost:8001/health
```

**Ответ:**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "model_version": "v1.0",
  "message": "Сервис работает нормально"
}
```

---

## Развертывание

### Production развертывание

1. **Настройте переменные окружения:**
   - Обновите `.env` файл с production значениями
   - Настройте PostgreSQL и Redis
   - Настройте Jira интеграцию

2. **Соберите Docker образы:**
```bash
docker-compose build
```

3. **Запустите сервисы:**
```bash
docker-compose up -d
```

4. **Настройте reverse proxy** (nginx/traefik) для маршрутизации

5. **Настройте мониторинг** (Prometheus, Grafana)

### Масштабирование

Для масштабирования можно:
- Запустить несколько экземпляров ML Service Worker
- Использовать Redis Cluster для очередей
- Настроить PostgreSQL репликацию

---

## Дополнительные материалы

### Документация компонентов

- **Ingestion Service:** `ingestion_service/README.md`
- **ML Service:** `ml_service/README.md`
- **Config Service:** `config_service/README.md`
- **Output Service:** `output_service/README.md`
- **Dashboard:** `dashboard/README-dash.md`
- **Database:** `database/README.md`
- **Shared:** `shared/README.md`

### Руководства

- **Запуск системы:** `startup-guide.md`
- **Redis архитектура:** `shared/REDIS_ARCHITECTURE.md`
- **Jira интеграция:** `output_service/JIRA_SYNC_GUIDE.md`

### Jupyter Notebooks

- `notebooks/01_eda.ipynb` — анализ данных
- `notebooks/02_preprocessing.ipynb` — предобработка
- `notebooks/03_model_training.ipynb` — обучение модели
- `notebooks/04_testevaluation.ipynb` — тестирование

### Скрипты и утилиты

- `check_scripts/` — скрипты проверки компонентов
- `app_tests/` — нагрузочное тестирование
- `scripts/` — вспомогательные скрипты

---

## Контакты и поддержка

При возникновении вопросов обращайтесь к:
- Документации компонентов в соответствующих README файлах
- Руководству по запуску: `startup-guide.md`
- Swagger UI документации: http://localhost:{PORT}/docs

---

## Заключение

Этот проект представляет собой полнофункциональную платформу для автоматической классификации обращений Service Desk с использованием микросервисной архитектуры и машинного обучения. Система готова к использованию в production среде и может быть легко масштабирована и настроена под конкретные требования.

**Основные преимущества проекта:**
- Модульная архитектура
- Высокая точность классификации (на демо-данных)
- Гибкая конфигурация
- Полный аудит и мониторинг
- Готовность к production-развертыванию

