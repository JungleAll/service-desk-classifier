# Service Desk Classifier Architecture

Документ описывает архитектуру системы автоматической классификации обращений Service Desk с учетом текущей реализации.

**Дата обновления:** 2025-11-19  
**Версия:** 3.4 (актуализировано с учетом фактической реализации: добавлены эндпоинты синхронизации Jira, уточнены статусы и коннекторы)

---

## 1. Диаграмма контейнеров (Container Diagram)

```mermaid
graph TB
    subgraph External["🌍 EXTERNAL SYSTEMS"]
        Users["👤 Users"]
        DataScientists["👨‍💻 Data Scientists"]
        EmailSource["📧 Email"]
        ChatSource["💬 Chat Bot"]
        APISource["🔌 API"]
        JiraSystem["📋 Jira REST API"]
    end
    
    subgraph System["🏢 SERVICE DESK AUTOMATION PLATFORM"]
        subgraph Ingestion["📥 INGESTION LAYER"]
            IngestionAPI["🔹 Ingestion API<br/>FastAPI - Port 8000<br/>POST /tickets<br/>GET /status/{id}<br/>GET /tickets<br/>GET /tickets/{id}<br/>POST /tickets/{id}/cancel<br/>POST /tickets/{id}/reprocess<br/>POST /tickets/batch"]
        end
        
        subgraph Queue["📦 MESSAGE QUEUE & CACHE"]
            Redis["🔸 Redis<br/>DB 0: Queues<br/>- pending_tickets<br/>- failed_tickets<br/>DB 1: Cache<br/>- cache_predictions<br/>(TTL 1 hour)"]
        end
        
        subgraph Config["⚙️ CONFIG LAYER"]
            ConfigAPI["🔹 Config Service<br/>FastAPI - Port 8002<br/>GET /config<br/>POST /config/toggle<br/>POST /config/model-version<br/>PUT /config/threshold<br/>POST /config/jira<br/>GET /config/audit"]
        end
        
        subgraph Processing["⚡ PROCESSING LAYER"]
            MLService["🔹 ML Service<br/>FastAPI - Port 8001<br/>POST /classify<br/>POST /classify/batch<br/>GET /model/status<br/>GET /model/list<br/>POST /reload_model<br/>Worker (Async Queue)"]
        end
        
        subgraph Output["📤 OUTPUT LAYER"]
            OutputService["🔹 Output Service<br/>FastAPI - Port 8003<br/>POST /process_result<br/>GET /health<br/>POST /sync/jira/ticket<br/>POST /sync/jira/batch<br/>POST /sync/jira/jql<br/>POST /sync/jira/all<br/>GET /jira/ticket/{id}<br/>GET /jira/search<br/>- Destination connectors (Jira/FileSystem/Mock)<br/>- DESTINATION_TYPE configuration<br/>- Auto-process decision<br/>- Config Service integration<br/>- Fallback to DB<br/>- Error handling<br/>- Retry mechanisms<br/>- Jira synchronization service"]
        end
        
        subgraph Data["💾 DATA & PERSISTENCE"]
            PostgreSQL["🗄️ PostgreSQL (Port 5432)<br/>- ticket_events<br/>- metrics<br/>- configuration<br/>- config_audit_log<br/>- model_versions<br/>- error_logs<br/>- audit_logs"]
            ModelRegistry["📦 Model Registry<br/>models/v1.0/<br/>- classifier_smote_new.pkl<br/>- vectorizer_smote.pkl<br/>- label_encoder_smote.pkl"]
        end
        
        subgraph Monitoring["📊 MONITORING & ADMIN"]
            Dashboard["🔹 Dashboard<br/>Streamlit - Port 8501<br/>- Demo Classification<br/>- Production Mode<br/>- Monitoring<br/>- Settings Management"]
        end
    end
    
    %% External connections
    Users -->|submit tickets| EmailSource
    Users -->|submit tickets| ChatSource
    Users -->|submit tickets| APISource
    Users -->|view dashboard| Dashboard
    DataScientists -->|trigger retraining| PostgreSQL
    
    EmailSource -->|JSON tickets| IngestionAPI
    ChatSource -->|JSON tickets| IngestionAPI
    APISource -->|JSON tickets| IngestionAPI
    
    %% Internal flow
    IngestionAPI -->|queue job| Redis
    IngestionAPI -->|get config| ConfigAPI
    IngestionAPI -->|save ticket| PostgreSQL
    Redis -->|fetch job| MLService
    
    ConfigAPI -->|store config| PostgreSQL
    MLService -->|load model| ModelRegistry
    MLService -->|cache check/store| Redis
    MLService -->|log prediction| PostgreSQL
    
    MLService -->|classified result| OutputService
    OutputService -->|get config| ConfigAPI
    OutputService -->|send ticket| JiraSystem
    OutputService -->|log result| PostgreSQL
    
    Dashboard -->|read metrics| PostgreSQL
    Dashboard -->|read models| ModelRegistry
    Dashboard -->|manage config| ConfigAPI
    Dashboard -->|check health| MLService
    Dashboard -->|classify text| MLService
    Dashboard -->|production mode| IngestionAPI
    
    style System fill:#E8F4F8,stroke:#2E5C8A,stroke-width:2px
    style Ingestion fill:#B3E5FC,stroke:#01579B
    style Queue fill:#FFF9C4,stroke:#F57F17
    style Processing fill:#C8E6C9,stroke:#1B5E20
    style Output fill:#FFCCBC,stroke:#BF360C
    style Config fill:#F3E5F5,stroke:#4A148C
    style Data fill:#E0E0E0,stroke:#212121
    style Monitoring fill:#C5CAE9,stroke:#1A237E
    style External fill:#F0F0F0,stroke:#999
```

---

## 2. Детальная архитектура компонентов (Component Diagram)

```mermaid
graph TB
    subgraph Ingestion["📥 INGESTION LAYER (Port 8000)"]
        IngAPI["FastAPI App"]
        IngModels["Pydantic Models<br/>TicketRequest<br/>TicketResponse<br/>TicketStatusResponse"]
        TicketHandler["Ticket Handler<br/>- Validation<br/>- DB Insert<br/>- Queue Push"]
    end
    
    subgraph ML["⚡ ML LAYER (Port 8001)"]
        MLAPI["FastAPI App"]
        Preprocessor["Text Preprocessor<br/>- Lemmatization<br/>- Stopwords<br/>- Normalization"]
        Classifier["Model Classifier<br/>- LogisticRegression<br/>- TF-IDF Vectorizer<br/>- Label Encoder"]
        MLModels["ML Models<br/>v1.0 (97.49% accuracy)"]
        Worker["Worker<br/>(Async Queue Processor)"]
    end
    
    subgraph Config["⚙️ CONFIG LAYER (Port 8002)"]
        ConfigAPI["FastAPI App"]
        ConfigMgr["Config Manager<br/>- Version Control<br/>- Audit Logging<br/>- Threshold Management"]
    end
    
    subgraph Output["📤 OUTPUT LAYER (Port 8003)"]
        OutputAPI["FastAPI App"]
        ConfigClient["Config Client<br/>- REST API Integration<br/>- Fallback to DB"]
        DestinationFactory["Destination Factory<br/>- DESTINATION_TYPE selector<br/>- Jira/FileSystem/Mock"]
        JiraConn["Jira Connector<br/>- REST API Client<br/>- Retry Logic"]
        FileSystemConn["FileSystem Connector<br/>- JSON file output"]
        MockConn["Mock Connector<br/>- Test mode"]
        AuditLogger["Audit Logger<br/>- Action Tracking<br/>- Error Logging"]
    end
    
    subgraph Data["💾 DATA LAYER"]
        PG["PostgreSQL<br/>- ticket_events<br/>- metrics<br/>- configuration<br/>- model_versions"]
        RedisQueues["Redis DB 0<br/>Queues:<br/>- pending_tickets<br/>- failed_tickets"]
        RedisCache["Redis DB 1<br/>Cache:<br/>- cache_predictions<br/>(TTL 1h)"]
        ModelReg["Model Registry<br/>models/v1.0/"]
    end
    
    subgraph Monitoring["📊 MONITORING"]
        Dashboard["Streamlit Dashboard<br/>- Demo Mode<br/>- Production Mode"]
        WebUI["Web UI<br/>- Classification<br/>- Monitoring<br/>- Settings"]
    end
    
    %% Ingestion flow
    IngAPI --> IngModels
    IngModels --> TicketHandler
    TicketHandler --> PG
    TicketHandler --> RedisQueues
    TicketHandler --> ConfigAPI
    
    %% ML flow
    RedisQueues --> Worker
    Worker --> MLAPI
    MLAPI --> Preprocessor
    Preprocessor --> Classifier
    Classifier --> MLModels
    Classifier --> RedisCache
    Classifier --> PG
    MLAPI --> ConfigAPI
    MLAPI --> OutputAPI
    
    %% Config flow
    ConfigAPI --> ConfigMgr
    ConfigMgr --> PG
    
    %% Output flow
    OutputAPI --> ConfigClient
    ConfigClient --> ConfigAPI
    ConfigClient --> PG
    OutputAPI --> DestinationFactory
    DestinationFactory --> JiraConn
    DestinationFactory --> FileSystemConn
    DestinationFactory --> MockConn
    OutputAPI --> AuditLogger
    JiraConn --> PG
    FileSystemConn --> PG
    MockConn --> PG
    AuditLogger --> PG
    
    %% Dashboard flow
    Dashboard --> WebUI
    WebUI --> PG
    WebUI --> ConfigAPI
    WebUI --> MLAPI
    WebUI --> IngAPI
    
    %% Model registry
    MLModels --> ModelReg
    
    style Ingestion fill:#B3E5FC,stroke:#01579B
    style ML fill:#C8E6C9,stroke:#1B5E20
    style Config fill:#F3E5F5,stroke:#4A148C
    style Output fill:#FFCCBC,stroke:#BF360C
    style Data fill:#E0E0E0,stroke:#212121
    style Monitoring fill:#C5CAE9,stroke:#1A237E
```

---

## 3. Поток данных (Data Flow Diagram)

```mermaid
sequenceDiagram
    participant Client as 👤 Client
    participant Ingestion as 📥 Ingestion Service<br/>(Port 8000)
    participant RedisQ as 📦 Redis Queue<br/>(DB 0)
    participant RedisC as 💾 Redis Cache<br/>(DB 1)
    participant ML as ⚡ ML Service<br/>(Port 8001)
    participant Config as ⚙️ Config Service<br/>(Port 8002)
    participant Output as 📤 Output Service<br/>(Port 8003)
    participant PG as 🗄️ PostgreSQL
    participant Jira as 📋 Jira API
    participant Dashboard as 📊 Dashboard<br/>(Port 8501)

    %% Ticket Creation Flow
    Client->>Ingestion: POST /tickets<br/>{text, source, ...}
    Ingestion->>Config: GET /config<br/>(check service_enabled)
    Config-->>Ingestion: {service_enabled: true}
    Ingestion->>PG: INSERT ticket_events<br/>(status: 'queued')
    Ingestion->>RedisQ: RPUSH pending_tickets<br/>{ticket_id, text, ...}
    Ingestion-->>Client: 201 Created<br/>{ticket_id, status: 'queued'}

    %% Classification Flow (Worker Mode)
    ML->>RedisQ: BLPOP pending_tickets<br/>(timeout: 5s)
    RedisQ-->>ML: {ticket_id, text, ...}
    ML->>PG: UPDATE ticket_events<br/>(status: 'processing')
    ML->>RedisC: GET cache_predictions:...
    alt Cache Hit
        RedisC-->>ML: Cached result
    else Cache Miss
        ML->>Config: GET /config<br/>(get model_version, threshold)
        Config-->>ML: {current_model_version: 'v1.0', ...}
        ML->>ML: Preprocess text
        ML->>ML: Vectorize (TF-IDF)
        ML->>ML: Classify (LogisticRegression)
        ML->>ML: Calculate confidence
        ML->>RedisC: SETEX cache_predictions:...<br/>(TTL: 3600s)
    end
    ML->>PG: UPDATE ticket_events<br/>(predicted_type, confidence,<br/>status: 'classified')
    ML->>Output: POST /process_result<br/>{ticket_id, result, ...}

    %% Output Processing
    Output->>Config: GET /config<br/>(get priorities, jira_config)
    alt Config Service Available
        Config-->>Output: {jira_enabled: true,<br/>jira_url: '...',<br/>auto_process_priority: 'medium',<br/>manual_review_priority: 'low'}
    else Config Service Unavailable
        Output->>PG: SELECT configuration<br/>(fallback to DB)
        PG-->>Output: {jira_enabled: true, ...}
    end
    Output->>Output: Determine priority<br/>(based on decision)
    Output->>Jira: POST /issue<br/>(create ticket)
    Jira-->>Output: {issue_key: 'SD-123', ...}
    Output->>PG: UPDATE ticket_events<br/>(jira_ticket_id, priority,<br/>status: 'completed')
    Output->>PG: INSERT audit_logs<br/>(action: 'jira_created')

    %% Dashboard Flow (Demo Mode)
    Dashboard->>ML: POST /classify<br/>{text, ...}
    ML->>RedisC: GET cache_predictions:...
    alt Cache Hit
        RedisC-->>ML: Cached result
    else Cache Miss
        ML->>ML: Classify text
        ML->>RedisC: SETEX cache_predictions:...
    end
    ML-->>Dashboard: {predicted_type, confidence, ...}

    %% Dashboard Flow (Production Mode)
    Dashboard->>Ingestion: POST /tickets<br/>{text, source: 'dashboard', ...}
    Ingestion->>PG: INSERT ticket_events
    Ingestion->>RedisQ: RPUSH pending_tickets
    Ingestion-->>Dashboard: {ticket_id, status: 'queued'}
    Dashboard->>Ingestion: GET /status/{ticket_id}<br/>(polling)
    Note over Dashboard,Ingestion: Wait for processing...
    Ingestion-->>Dashboard: {status: 'completed', ...}
    Dashboard->>Ingestion: GET /tickets/{ticket_id}
    Ingestion-->>Dashboard: {predicted_type, confidence, ...}
```

---

## 4. Архитектура Redis (Redis Architecture)

```mermaid
graph LR
    subgraph Redis["🔸 Redis Server"]
        subgraph DB0["Database 0: Queues"]
            PendingQueue["pending_tickets<br/>List (RPUSH/BLPOP)<br/>No TTL"]
            FailedQueue["failed_tickets<br/>List (RPUSH/LPOP)<br/>No TTL"]
        end
        
        subgraph DB1["Database 1: Cache"]
            CachePredictions["cache_predictions:<br/>{version}:{hash}<br/>String (SETEX/GET)<br/>TTL: 3600s"]
        end
    end
    
    subgraph Services["Services"]
        Ingestion["Ingestion Service<br/>Port 8000"]
        ML["ML Service<br/>Port 8001"]
        Worker["ML Worker<br/>(Async)"]
    end
    
    Ingestion -->|RPUSH| PendingQueue
    Worker -->|BLPOP| PendingQueue
    Worker -->|RPUSH| FailedQueue
    ML -->|GET| CachePredictions
    ML -->|SETEX| CachePredictions
    
    style DB0 fill:#FFF9C4,stroke:#F57F17
    style DB1 fill:#E1F5FE,stroke:#0277BD
    style Redis fill:#FFEBEE,stroke:#C62828
```

---

## 5. Режимы работы Dashboard (Dashboard Modes)

```mermaid
graph TB
    subgraph Dashboard["📊 Dashboard (Port 8501)"]
        ModeSelector["Mode Selector<br/>demo | production"]
        
        subgraph DemoMode["⚡ Demo Mode"]
            DemoClient["API Client"]
            DirectML["Direct ML Service<br/>POST /classify"]
        end
        
        subgraph ProdMode["🔒 Production Mode"]
            ProdClient["API Client"]
            IngestionFlow["Ingestion Service<br/>POST /tickets"]
            Polling["Status Polling<br/>GET /status/{id}"]
        end
    end
    
    subgraph Services["Services"]
        ML["ML Service<br/>Port 8001"]
        Ingestion["Ingestion Service<br/>Port 8000"]
        RedisQ["Redis Queue<br/>DB 0"]
        PG["PostgreSQL"]
    end
    
    ModeSelector -->|demo| DemoMode
    ModeSelector -->|production| ProdMode
    
    DemoClient --> DirectML
    DirectML --> ML
    
    ProdClient --> IngestionFlow
    IngestionFlow --> RedisQ
    IngestionFlow --> PG
    ProdClient --> Polling
    Polling --> Ingestion
    
    style DemoMode fill:#C8E6C9,stroke:#1B5E20
    style ProdMode fill:#FFCCBC,stroke:#BF360C
    style Dashboard fill:#C5CAE9,stroke:#1A237E
```

---

## 6. Жизненный цикл тикета (Ticket Lifecycle)

```mermaid
stateDiagram-v2
    [*] --> queued: POST /tickets
    
    queued --> processing: Worker picks up
    queued --> cancelled: POST /cancel
    
    processing --> classified: ML classification done
    processing --> failed: Error occurred
    
    classified --> completed: Output Service done
    classified --> classified: Output Service error\n(остается в classified,\nтолько error_message)
    
    failed --> queued: POST /reprocess
    completed --> queued: POST /reprocess\n(force=true)
    cancelled --> queued: POST /reprocess
    failed --> [*]: Manual resolution
    
    completed --> [*]: Ticket closed
    cancelled --> [*]: Ticket cancelled
    
    note right of queued
        Status: queued
        Stored in: PostgreSQL
        Queued in: Redis DB 0
        POST /reprocess возвращает
        status='queued_for_reprocessing'
        но в БД сохраняется как 'queued'
    end note
    
    note right of processing
        Status: processing
        Worker processing
        ML Service classifying
        Только если status='queued'
    end note
    
    note right of classified
        Status: classified
        predicted_type set
        confidence calculated
        decision made
        Ready for Output Service
        При ошибке Output Service
        остается в classified
    end note
    
    note right of completed
        Status: completed
        Sent to destination
        (Jira/FileSystem/Mock)
        jira_ticket_id set
        sent_to_jira_at set
    end note
    
    note right of failed
        Status: failed
        error_message set
        Может быть переобработан
        через POST /reprocess
    end note
```

---

## Разделение ответственности сервисов

### 1. Ingestion Service (Port 8000)
- ✅ Прием и валидация обращений (`POST /tickets`)
- ✅ Управление жизненным циклом тикетов
- ✅ Постановка в очередь Redis (DB 0)
- ✅ Сохранение в PostgreSQL (`ticket_events`)
- ✅ Проверка конфигурации через Config Service
- ❌ **НЕ выполняет классификацию** - классификация находится в ML Service

### 2. ML Service (Port 8001)
- ✅ Классификация текста через ML модель (`POST /classify`)
- ✅ Кэширование результатов в Redis (DB 1)
- ✅ Управление моделями (загрузка, перезагрузка, переключение версий)
- ✅ Автоматическая обработка очереди через Worker
- ✅ Запись метрик в PostgreSQL
- ✅ Проверка версии модели из Config Service

### 3. Config Service (Port 8002)
- ✅ Централизованное управление конфигурацией
- ✅ Аудит изменений (`config_audit_log`)
- ✅ Управление версиями моделей
- ✅ Управление порогами уверенности
- ✅ Управление настройками Jira

### 4. Output Service (Port 8003)
- ✅ Обработка результатов классификации
- ✅ Плагинные коннекторы назначения (Destination Connectors):
  - **Jira Connector:** отправка в Jira REST API (требует `DESTINATION_TYPE=jira`)
    - Поддерживает стандартный Jira REST API (`/rest/api/3/issue`)
    - Поддерживает Jira Service Desk API (`/rest/servicedeskapi/request`) при `JIRA_USE_SERVICEDESK_API=true`
  - **FileSystem Connector:** сохранение JSON файлов в `OUTPUT_DIR` (по умолчанию, `DESTINATION_TYPE=filesystem` или `fs` или `file`)
  - **Mock Connector:** тестовый режим без отправки (`DESTINATION_TYPE=mock`)
- ✅ Выбор коннектора через переменную окружения `DESTINATION_TYPE`
- ✅ Определение приоритетов из Config Service (auto_process_priority, manual_review_priority)
- ✅ Интеграция с Config Service API с fallback на БД
- ✅ Retry механизмы для Jira
- ✅ Аудит действий (`audit_logs`)
- ✅ Отправка только при `decision=auto-process`
- ✅ Синхронизация данных из Jira для дообучения модели (JiraSyncService)
  - Синхронизация actual_type, feedback_status из Jira в PostgreSQL
  - Поддержка пакетной синхронизации и синхронизации по JQL

### 5. Dashboard (Port 8501)
- ✅ **Demo режим:** Прямая классификация через ML Service (без логирования в БД)
- ✅ **Production режим:** Полный pipeline через Ingestion Service (с логированием в `ticket_events`)
- ✅ Мониторинг системы
- ✅ Управление конфигурацией
- ✅ Просмотр метрик и истории

---

## Ключевые эндпоинты

### Ingestion Service (Port 8000)
- `POST /tickets` - создание обращения
- `GET /tickets` - список обращений (с фильтрацией)
- `GET /tickets/{id}` - детали обращения
- `GET /status/{ticket_id}` - статус обработки с прогрессом
- `POST /tickets/{id}/cancel` - отменить обработку
- `POST /tickets/{id}/reprocess` - переобработать
- `POST /tickets/batch` - пакетная загрузка
- `GET /health` - проверка работоспособности

### ML Service (Port 8001)
- `POST /classify` - **классификация текста (только здесь!)**
- `POST /classify/batch` - пакетная классификация
- `GET /model/status` - статус модели
- `GET /model/list` - список моделей
- `POST /reload_model` - перезагрузка модели
- `GET /health` - проверка работоспособности

### Config Service (Port 8002)
- `GET /config` - текущая конфигурация
- `POST /config/toggle` - включить/отключить сервис
- `POST /config/model-version` - переключить версию модели
- `POST /config/model-switch` - алиас для `/config/model-version`
- `PUT /config/threshold` - изменить порог уверенности
- `POST /config/jira` - настройка Jira
- `GET /config/audit` - история изменений
- `GET /health` - проверка работоспособности

### Output Service (Port 8003)
- `POST /process_result` - обработка результата классификации
  - Принимает результаты классификации от ML Service Worker
  - Определяет приоритет на основе decision (auto-process/manual-review)
  - Отправляет в выбранное назначение при `decision=auto-process`
  - Обновляет `ticket_events` и записывает в `audit_logs`
- `GET /health` - проверка работоспособности
  - Проверяет подключение к PostgreSQL
  - Показывает статус Jira (если `DESTINATION_TYPE=jira`)
- `POST /sync/jira/ticket` - синхронизация одного тикета из Jira
  - Получает данные тикета из Jira и обновляет actual_type, feedback_status в PostgreSQL
- `POST /sync/jira/batch` - пакетная синхронизация тикетов из Jira
- `POST /sync/jira/jql` - синхронизация тикетов по JQL запросу
- `POST /sync/jira/all` - синхронизация всех тикетов с jira_ticket_id
- `GET /jira/ticket/{jira_ticket_id}` - получение данных тикета из Jira (без синхронизации)
- `GET /jira/search` - поиск тикетов в Jira по JQL (без синхронизации)

---

## Поток данных

### 1. Создание обращения (Production Flow)
```
Клиент → Ingestion Service (POST /tickets)
  → Проверка Config Service (service_enabled)
  → Сохранение в PostgreSQL (ticket_events, status: 'queued')
  → Добавление в очередь Redis DB 0 (pending_tickets)
  → Ответ клиенту (ticket_id, status: 'queued', created_at, estimated_processing_time: 2000ms)
```

### 2. Классификация (Worker Mode)
```
ML Service Worker → Redis DB 0 (BLPOP pending_tickets, timeout: 5s)
  → Проверка статуса тикета в БД (должен быть 'queued')
  → Обновление статуса в PostgreSQL (status: 'processing')
  → Проверка версии модели из Config Service (автоперезагрузка при несоответствии)
  → Проверка кэша Redis DB 1 (cache_predictions:{version}:{hash})
  → Если нет в кэше:
    → Получение порога уверенности из Config Service
    → Предобработка текста
    → Векторизация (TF-IDF)
    → Классификация (LogisticRegression)
    → Сохранение в кэш Redis DB 1 (TTL: 3600s)
  → Определение decision (auto-process/manual-review) по порогу
  → Обновление PostgreSQL (predicted_type, confidence, probabilities, decision, model_version, status: 'classified', processed_at)
  → Отправка в Output Service (POST /process_result)
```

### 3. Обработка результата
```
Output Service (POST /process_result)
  → Получение конфигурации из Config Service API (GET /config):
    - Приоритеты (auto_process_priority, manual_review_priority)
    - Jira конфигурация (jira_enabled, jira_url, jira_user, jira_api_token, jira_project_key)
  → Fallback на БД при недоступности Config Service
  → Определение приоритета на основе decision:
    - decision='auto-process' → auto_process_priority (default: 'medium')
    - decision='manual-review' → manual_review_priority (default: 'low')
  → Выбор коннектора назначения через DESTINATION_TYPE:
    - DESTINATION_TYPE=jira → JiraConnector
    - DESTINATION_TYPE=filesystem → FileSystemConnector (по умолчанию)
    - DESTINATION_TYPE=mock → MockConnector
  → Отправка в назначение при decision=auto-process:
    - Jira: создание тикета через REST API с retry механизмами (MAX_RETRY_ATTEMPTS)
    - FileSystem: сохранение JSON в OUTPUT_DIR (default: ./out), формат: {ticket_id}_{timestamp}.json
    - Mock: генерация external_id в формате MOCK-{timestamp} без реальной отправки
  → Обновление PostgreSQL:
    - ticket_events: jira_ticket_id (или external_id), jira_link (или file path), priority, status: 'completed', sent_to_jira_at
    - audit_logs: запись действия (jira_created/filesystem_saved/mock_generated)
```

### 4. Dashboard - Demo Mode
```
Dashboard → ML Service (POST /classify)
  → Проверка кэша Redis DB 1
  → Классификация (если нет в кэше)
  → Сохранение в кэш
  → Возврат результата
  ❌ НЕ создает запись в ticket_events
```

### 5. Dashboard - Production Mode
```
Dashboard → Ingestion Service (POST /tickets)
  → Создание записи в ticket_events
  → Добавление в очередь Redis DB 0
  → Polling статуса (GET /status/{ticket_id})
  → Получение результата (GET /tickets/{ticket_id})
  ✅ Создает запись в ticket_events
```

---

## Интеграции между сервисами

- **Ingestion ↔ Config:** Проверка `service_enabled` перед созданием обращений
- **ML ↔ Config:** Чтение `current_model_version` и `confidence_threshold`, автоматическая перезагрузка модели при несоответствии
- **ML ↔ Output:** Отправка результатов классификации через Worker
- **Output ↔ Config:** Чтение приоритетов (auto_process_priority, manual_review_priority) и Jira конфигурации (jira_enabled, jira_url) через REST API с автоматическим fallback на БД при недоступности Config Service
- **Dashboard ↔ ML/Config:** Управление конфигурацией и классификация текста
- **Dashboard ↔ Ingestion:** Production режим с полным логированием

---

## Архитектурные решения

### Разделение Redis на базы данных
- **DB 0 (Queues):** Очереди задач (pending_tickets, failed_tickets)
  - Временные данные, удаляются после обработки
  - Использует Redis List структуру данных
  - Операции: `RPUSH` (добавление в конец), `BLPOP`/`LPOP` (извлечение из начала)
  - Нет TTL (данные живут до обработки)
  - Высокая производительность операций вставки/извлечения
  - Переменные окружения: `REDIS_DB_QUEUES=0` (по умолчанию)

- **DB 1 (Cache):** Кэш результатов (cache_predictions)
  - Данные с TTL (3600 секунд по умолчанию)
  - Использует Redis String структуру данных
  - Операции: `SETEX` (установка с TTL), `GET` (получение)
  - Формат ключа: `cache_predictions:{model_version}:{text_hash}`
    - `model_version` - версия модели (например, v1.0)
    - `text_hash` - MD5 хэш текста обращения
  - Автоматическое удаление устаревших данных
  - Оптимизация повторных запросов
  - Переменные окружения: `REDIS_DB_CACHE=1` (по умолчанию)

**Общие переменные окружения Redis:**
- `REDIS_HOST` - хост Redis (по умолчанию: localhost)
- `REDIS_PORT` - порт Redis (по умолчанию: 6379)
- `REDIS_PASSWORD` - пароль Redis (опционально)

### Режимы работы Dashboard
- **Demo Mode:** Быстрая классификация без логирования (для тестирования)
- **Production Mode:** Полный pipeline с логированием в `ticket_events` (для production)

### Асинхронная обработка
- Worker в ML Service обрабатывает очередь Redis асинхронно
- Поддержка retry механизмов для failed tickets
- Неблокирующая обработка большого количества тикетов

### Интеграция Output Service с Config Service
- Output Service получает конфигурацию через REST API (GET /config)
- Автоматический fallback на прямое чтение из БД при недоступности Config Service
- Получаемые параметры:
  - Приоритеты: `auto_process_priority`, `manual_review_priority`
  - Jira конфигурация: `jira_enabled`, `jira_url` (для JiraConnector)
- Обеспечивает отказоустойчивость системы

### Destination Connectors в Output Service
- **Плагинная архитектура:** выбор коннектора через переменную окружения `DESTINATION_TYPE`
- **JiraConnector:** отправка тикетов в Jira REST API
  - Требует `DESTINATION_TYPE=jira`
  - Использует конфигурацию из Config Service (jira_url, jira_user, jira_api_token)
  - Поддерживает два режима:
    - Стандартный Jira REST API (`/rest/api/3/issue`) - по умолчанию
    - Jira Service Desk API (`/rest/servicedeskapi/request`) - при `JIRA_USE_SERVICEDESK_API=true`
  - Для Service Desk API требуется `JIRA_SERVICE_DESK_ID` и `JIRA_REQUEST_TYPE_ID`
  - Поддерживает retry механизмы (MAX_RETRY_ATTEMPTS)
  - Опциональная проверка подключения через `JIRA_VALIDATE_CONNECTION`
- **FileSystemConnector:** сохранение результатов в JSON файлы
  - По умолчанию (`DESTINATION_TYPE=filesystem`, `fs` или `file`)
  - Сохраняет в директорию `OUTPUT_DIR` (по умолчанию `./out`)
  - Формат файла: `{ticket_id}_{timestamp}.json`
  - Поддерживает нормализацию кодировки UTF-8 (исправление проблем с Windows-1251)
- **MockConnector:** тестовый режим
  - `DESTINATION_TYPE=mock`
  - Генерирует external_id в формате `MOCK-{timestamp}` без реальной отправки
  - Используется для тестирования без внешних зависимостей

### Jira Synchronization Service
- **Назначение:** Синхронизация данных из Jira в PostgreSQL для дообучения модели
- **Функциональность:**
  - Извлечение категории из Jira (custom fields, labels, components, issue type)
  - Обновление `actual_type` в PostgreSQL при расхождении с `predicted_type`
  - Обновление `feedback_status` и `feedback_correct_type` для обратной связи
  - Пометка тикетов как `training_ready` для дообучения
- **Эндпоинты:**
  - `POST /sync/jira/ticket` - синхронизация одного тикета
  - `POST /sync/jira/batch` - пакетная синхронизация
  - `POST /sync/jira/jql` - синхронизация по JQL запросу
  - `POST /sync/jira/all` - синхронизация всех тикетов с jira_ticket_id
  - `GET /jira/ticket/{jira_ticket_id}` - получение данных из Jira (без синхронизации)
  - `GET /jira/search` - поиск в Jira по JQL (без синхронизации)

---

**Важно:** `POST /classify` находится **только в ML Service (Port 8001)**, а не в Ingestion Service. Это правильное разделение ответственности в микросервисной архитектуре.

**Дата обновления:** 2025-11-19  
**Версия:** 3.4 (актуализировано с учетом фактической реализации: добавлены эндпоинты синхронизации Jira, уточнены статусы и коннекторы)

