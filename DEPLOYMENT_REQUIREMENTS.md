# Требования к развертыванию и текущее состояние приложения

**Дата создания:** 2025-01-18 08:10:00  
**Версия:** 1.0  
**Последнее обновление:** 2025-01-18 08:10:00

## 📋 Содержание

1. [Требуется ли PostgreSQL и Redis?](#требуется-ли-postgresql-и-redis)
2. [Как сейчас работает приложение](#как-сейчас-работает-приложение)
3. [Варианты развертывания](#варианты-развертывания)
4. [Минимальная конфигурация для тестирования](#минимальная-конфигурация-для-тестирования)
5. [Полная конфигурация для production](#полная-конфигурация-для-production)

---

## Требуется ли PostgreSQL и Redis?

### ✅ PostgreSQL - **КРИТИЧНО** требуется

**Что не работает без PostgreSQL:**

| Сервис | Функции, требующие PostgreSQL | Статус без БД |
|--------|------------------------------|---------------|
| **Ingestion Service** | ❌ Создание обращений<br>❌ Сохранение в `ticket_events`<br>❌ Получение списка обращений<br>❌ Получение деталей обращения | 🚫 **НЕ РАБОТАЕТ** |
| **ML Service** | ❌ Запись метрик в `metrics`<br>✅ Классификация текста (работает) | ⚠️ **ЧАСТИЧНО** |
| **Config Service** | ❌ Сохранение конфигурации<br>❌ Аудит изменений<br>❌ История изменений | 🚫 **НЕ РАБОТАЕТ** |
| **Output Service** | ❌ Обновление `ticket_events`<br>❌ Запись в `audit_logs`<br>❌ Логирование ошибок | 🚫 **НЕ РАБОТАЕТ** |

**Вывод:** PostgreSQL **обязательно** требуется для полноценной работы приложения.

### ✅ Redis - **ЖЕЛАТЕЛЬНО**, но не критично

**Что не работает без Redis:**

| Функция | Статус без Redis |
|---------|------------------|
| **Очередь тикетов** | ❌ Тикеты не попадают в очередь<br>❌ Worker не может обработать очередь |
| **Кэш предсказаний** | ⚠️ Каждое предсказание будет вычисляться заново (медленнее) |
| **Автоматическая обработка** | ❌ Worker не может работать без очереди |

**Что работает без Redis:**

| Функция | Статус |
|---------|--------|
| **REST API классификация** | ✅ Работает (через POST /classify) |
| **Ручная обработка** | ✅ Работает (без очереди) |
| **Создание обращений** | ⚠️ Работает, но не попадает в очередь |

**Вывод:** Redis **желательно** для полноценной работы, но можно тестировать без него в ограниченном режиме.

---

## Как сейчас работает приложение

### Текущая архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    ТЕКУЩЕЕ СОСТОЯНИЕ                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│  PostgreSQL │      │    Redis    │      │   Config    │
│   (БД)      │◄─────┤  (Очередь)  │◄─────┤  Service    │
│             │      │             │      │   (8002)    │
└─────┬───────┘      └──────┬──────┘      └─────┬───────┘
      │                     │                    │
      │                     │                    │
      ▼                     ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│  Ingestion Service (8000)                                    │
│  ├─ POST /tickets      → сохраняет в БД + очередь Redis      │
│  ├─ GET /tickets       → читает из БД                        │
│  └─ GET /status/{id}   → читает из БД                        │
└─────────────────────────────────────────────────────────────┘
      │
      │ (очередь Redis)
      ▼
┌─────────────────────────────────────────────────────────────┐
│  ML Service (8001)                                           │
│  ├─ POST /classify     → кэш Redis + метрики в БД            │
│  ├─ Worker (опц.)      → обрабатывает очередь Redis          │
│  └─ Запись метрик      → в БД (только через REST API)        │
└─────────────────────────────────────────────────────────────┘
      │
      │ (HTTP API)
      ▼
┌─────────────────────────────────────────────────────────────┐
│  Output Service (8003)                                       │
│  ├─ POST /process_result → обновляет БД + audit_logs         │
│  └─ Отправка в Jira/FS → логирование в БД                    │
└─────────────────────────────────────────────────────────────┘
```

### Поток данных

#### 1. Создание обращения (с PostgreSQL и Redis)

```
Клиент → Ingestion Service (POST /tickets)
  ├─ Валидация данных
  ├─ Генерация ticket_id
  ├─ Сохранение в PostgreSQL (ticket_events) ✅
  ├─ Добавление в очередь Redis (pending_tickets) ✅
  └─ Возврат ticket_id клиенту

Статус: queued
```

#### 2. Классификация (с PostgreSQL и Redis)

**Через REST API:**
```
Клиент → ML Service (POST /classify)
  ├─ Проверка кэша Redis ✅
  │   ├─ Если есть → возврат из кэша (быстро)
  │   └─ Если нет → классификация модели
  ├─ Классификация через модель
  ├─ Сохранение в кэш Redis (TTL 1 час) ✅
  ├─ Запись метрики в PostgreSQL (metrics) ✅
  └─ Возврат результата

Результат: predicted_type, confidence, probabilities
```

**Через Worker (требует Redis):**
```
Worker → Redis (pop_from_queue)
  ├─ Получение тикета из очереди ✅
  ├─ Обновление статуса в PostgreSQL (processing) ✅
  ├─ Классификация через модель
  ├─ Обновление статуса в PostgreSQL (classified) ✅
  ├─ Отправка в Output Service
  └─ Обновление статуса в PostgreSQL (completed) ✅

Статус: queued → processing → classified → completed
```

#### 3. Обработка результата (требует PostgreSQL)

```
ML Service → Output Service (POST /process_result)
  ├─ Обновление ticket_events в PostgreSQL ✅
  ├─ Отправка в Jira/FileSystem/Mock
  ├─ Запись в audit_logs (PostgreSQL) ✅
  └─ Возврат результата

Статус: completed
```

### Что работает БЕЗ PostgreSQL и Redis

#### Минимальный режим (только ML Service)

```
┌─────────────────────────────────────────────────────────────┐
│  ML Service (8001) - РАБОТАЕТ БЕЗ БД                        │
│  ├─ POST /classify     → классификация (без кэша)            │
│  ├─ POST /classify/batch → пакетная классификация            │
│  ├─ GET /model/status  → статус модели                       │
│  └─ GET /health        → healthcheck                         │
└─────────────────────────────────────────────────────────────┘
```

**Ограничения:**
- ❌ Нет сохранения результатов
- ❌ Нет метрик
- ❌ Нет кэширования (медленнее)
- ⚠️ Каждое предсказание вычисляется заново

**Использование:**
```bash
# Только классификация текста
curl -X POST http://localhost:8001/classify \
  -H "Content-Type: application/json" \
  -d '{"text": "Не могу войти в систему"}'
```

---

## Варианты развертывания

### Вариант 1: Docker Compose (рекомендуется) ✅

**Преимущества:**
- ✅ Автоматическое развертывание PostgreSQL и Redis
- ✅ Автоматическая инициализация БД
- ✅ Изоляция всех компонентов
- ✅ Легкое управление

**Команды:**
```bash
# Запуск всех сервисов
docker compose up -d

# Остановка
docker compose down

# Остановка с удалением данных
docker compose down -v
```

**Что запускается:**
- PostgreSQL (порт 5432)
- Redis (порт 6379)
- Ingestion Service (порт 8000)
- ML Service (порт 8001)
- Config Service (порт 8002)
- Output Service (порт 8003)
- Dashboard (порт 8501)

### Вариант 2: Локальная установка PostgreSQL и Redis

**Шаг 1: Установка PostgreSQL**
```bash
# Windows (Chocolatey)
choco install postgresql

# Mac (Homebrew)
brew install postgresql

# Linux (Ubuntu/Debian)
sudo apt-get install postgresql
```

**Шаг 2: Установка Redis**
```bash
# Windows (Chocolatey)
choco install redis-64

# Mac (Homebrew)
brew install redis

# Linux (Ubuntu/Debian)
sudo apt-get install redis-server
```

**Шаг 3: Настройка PostgreSQL**
```bash
# Создание базы данных
createdb service_desk_db

# Или через psql
psql -U postgres
CREATE DATABASE service_desk_db;
\q

# Инициализация схемы
psql -U postgres -d service_desk_db -f database/schema.sql
```

**Шаг 4: Запуск сервисов**
```bash
# Запуск PostgreSQL
# Windows: services.msc → PostgreSQL
# Mac/Linux: sudo service postgresql start

# Запуск Redis
# Windows: redis-server
# Mac/Linux: redis-server

# Запуск сервисов приложения
python config_service/run.py    # Порт 8002
python ml_service/run.py         # Порт 8001
python ingestion_service/run.py  # Порт 8000
python output_service/run.py     # Порт 8003
streamlit run dashboard/app.py   # Порт 8501
```

### Вариант 3: Минимальный режим (только ML Service)

**Для чего подходит:**
- ✅ Тестирование классификации текста
- ✅ Демонстрация ML функционала
- ✅ Разработка без БД

**Ограничения:**
- ❌ Нет сохранения данных
- ❌ Нет метрик
- ❌ Нет кэширования
- ❌ Нет автоматической обработки

**Запуск:**
```bash
# Только ML Service
cd ml_service
python run.py

# Тестирование
curl -X POST http://localhost:8001/classify \
  -H "Content-Type: application/json" \
  -d '{"text": "Не могу войти в систему"}'
```

---

## Минимальная конфигурация для тестирования

### Требования для базового тестирования

**Обязательно:**
- ✅ PostgreSQL (для сохранения данных)
- ✅ Config Service (для конфигурации)
- ✅ ML Service (для классификации)
- ✅ Ingestion Service (для создания обращений)

**Опционально:**
- ⚠️ Redis (для очереди и кэша)
- ⚠️ Output Service (для обработки результатов)
- ⚠️ Worker (для автоматической обработки)

### Минимальный набор для тестирования

```bash
# 1. Запуск PostgreSQL
docker run -d \
  --name postgres \
  -e POSTGRES_DB=service_desk_db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  -v $(pwd)/database/schema.sql:/docker-entrypoint-initdb.d/schema.sql \
  postgres:15-alpine

# 2. Запуск Redis (опционально)
docker run -d \
  --name redis \
  -p 6379:6379 \
  redis:7-alpine

# 3. Запуск сервисов
python config_service/run.py
python ml_service/run.py
python ingestion_service/run.py
python output_service/run.py
```

### Переменные окружения

```bash
# PostgreSQL
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=service_desk_db
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=postgres

# Redis (опционально)
export REDIS_HOST=localhost
export REDIS_PORT=6379

# Config Service
export CONFIG_SERVICE_URL=http://localhost:8002

# Output Service
export OUTPUT_SERVICE_URL=http://localhost:8003
```

---

## Полная конфигурация для production

### Требования для production

**Обязательно:**
- ✅ PostgreSQL (с backup и мониторингом)
- ✅ Redis (с persistence и мониторингом)
- ✅ Все сервисы (Ingestion, ML, Config, Output)
- ✅ Worker (для автоматической обработки)
- ✅ Мониторинг и логирование
- ✅ Резервное копирование

### Docker Compose для production

```bash
# Запуск всех сервисов
docker compose up -d

# Проверка статуса
docker compose ps

# Просмотр логов
docker compose logs -f

# Остановка
docker compose down
```

### Переменные окружения для production

```env
# PostgreSQL
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=service_desk_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<secure_password>

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=<secure_password>

# Worker
WORKER_ENABLED=true
WORKER_QUEUE_TIMEOUT=5
WORKER_DELAY=0.1

# Output Service
DESTINATION_TYPE=jira  # или filesystem
OUTPUT_DIR=/app/output
```

---

## Текущее состояние приложения

### Что работает сейчас

✅ **Работает полностью:**
- Создание обращений (требует PostgreSQL)
- Классификация текста (работает без БД, но без метрик)
- Управление конфигурацией (требует PostgreSQL)
- Обработка результатов (требует PostgreSQL)
- Аудит событий (требует PostgreSQL)

⚠️ **Работает частично:**
- Кэширование предсказаний (требует Redis)
- Автоматическая обработка очереди (требует Redis)
- Worker (требует Redis)

❌ **Не работает без инфраструктуры:**
- Сохранение обращений (требует PostgreSQL)
- История обработки (требует PostgreSQL)
- Метрики классификаций (требует PostgreSQL)

### Рекомендации

1. **Для базового тестирования:** PostgreSQL обязательно, Redis опционально
2. **Для полноценного тестирования:** PostgreSQL и Redis обязательны
3. **Для production:** PostgreSQL и Redis обязательны с мониторингом

---

## Выводы

### Требуется ли PostgreSQL и Redis для полноценной проверки?

**PostgreSQL:** ✅ **ДА, обязательно**
- Без PostgreSQL большинство функций не работают
- Нет сохранения данных, метрик, аудита

**Redis:** ✅ **ДА, желательно**
- Без Redis нет очереди и кэша
- Можно тестировать в ограниченном режиме
- Worker не может работать без Redis

### Как сейчас работает приложение?

1. **С PostgreSQL и Redis:** Полная функциональность
2. **Только с PostgreSQL:** Базовые функции работают, но нет очереди и кэша
3. **Без инфраструктуры:** Только классификация текста через REST API

### Рекомендации для тестирования

**Минимально:** PostgreSQL + Config Service + ML Service + Ingestion Service  
**Рекомендуется:** PostgreSQL + Redis + все сервисы  
**Оптимально:** Docker Compose (все автоматически)

---

**Дата создания:** 2025-11-18  
**Версия:** 1.0

