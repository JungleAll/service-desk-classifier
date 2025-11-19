# Подтверждение: Одна модель в обоих режимах

## ✅ Результат проверки

**Подтверждено:** В режимах **demo** и **production** используется **одна и та же модель**.

## Детальная проверка

### 1. Один экземпляр классификатора

**Файл:** `ml_service/app.py:44`
```python
# Глобальный экземпляр классификатора
classifier = ServiceDeskClassifier()
```

Этот экземпляр создается **один раз** при старте ML Service.

### 2. Использование в Demo режиме

**Поток:**
```
Dashboard (demo) 
  → POST /classify 
  → ml_service/app.py:190 (classify_text)
  → ml_service/app.py:272 (classifier.predict)
```

**Код:**
```python
# ml_service/app.py:190-272
async def classify_text(request: ClassifyRequest) -> ClassifyResponse:
    # Использует глобальный classifier
    result = classifier.predict(request.text, top_n=request.top_n)
```

### 3. Использование в Production режиме

**Поток:**
```
Dashboard (production)
  → Ingestion Service
  → Redis очередь
  → Worker (ml_service/worker.py)
  → ml_service/worker.py:121 (classifier.predict)
```

**Код:**
```python
# ml_service/app.py:106
worker_task = start_worker(classifier)  # Передается тот же экземпляр

# ml_service/worker.py:28-121
async def process_ticket_from_queue(..., classifier: ServiceDeskClassifier, ...):
    # Использует переданный экземпляр
    result = classifier.predict(text)
```

### 4. Одинаковая проверка версии модели

**Demo режим (REST API):**
```python
# ml_service/app.py:218-234
desired_version = cfg.get("current_model_version")
if desired_version and desired_version != classifier.model_version:
    classifier.reload_model()  # Перезагружает тот же экземпляр
result = classifier.predict(request.text)
```

**Production режим (Worker):**
```python
# ml_service/worker.py:90-121
desired_version = cfg.get("current_model_version")
if desired_version and desired_version != classifier.model_version:
    classifier.reload_model()  # Перезагружает тот же экземпляр
result = classifier.predict(text)
```

### 5. Одинаковые файлы модели

Оба режима используют пути из таблицы `model_versions` в БД:
- Версия: `v1.0`
- Модель: `models/v1.0/classifier_smote_new.pkl`
- Векторизатор: `models/v1.0/vectorizer_smote.pkl`
- Энкодер: `models/v1.0/label_encoder_smote.pkl`

## Визуальная схема

```
┌─────────────────────────────────────────────────────────┐
│              ML Service (ml_service/app.py)             │
│                                                          │
│  classifier = ServiceDeskClassifier()  ← ОДИН ЭКЗЕМПЛЯР │
│                                                          │
│  ┌────────────────────┐    ┌──────────────────────┐  │
│  │  REST API          │    │  Worker               │  │
│  │  /classify         │    │  process_ticket_...   │  │
│  │                    │    │                       │  │
│  │  classifier.       │    │  classifier.         │  │
│  │    predict()       │    │    predict()         │  │
│  └────────────────────┘    └──────────────────────┘  │
│         ↑                           ↑                   │
│         │                           │                   │
│         └─────── ОДИН ЭКЗЕМПЛЯР ─────┘                   │
└─────────────────────────────────────────────────────────┘
         ↑                           ↑
         │                           │
    Demo режим              Production режим
    (прямой вызов)          (через очередь)
```

## Разница между режимами

| Аспект | Demo режим | Production режим |
|--------|------------|------------------|
| **Модель** | ✅ Одна и та же | ✅ Одна и та же |
| **Экземпляр classifier** | ✅ Один и тот же | ✅ Один и тот же |
| **Файлы модели** | ✅ Одинаковые | ✅ Одинаковые |
| **Метод классификации** | ✅ `classifier.predict()` | ✅ `classifier.predict()` |
| **Проверка версии** | ✅ Есть | ✅ Есть |
| **Логирование в БД** | ❌ Нет | ✅ Есть |
| **Очередь Redis** | ❌ Не используется | ✅ Используется |
| **Worker** | ❌ Не используется | ✅ Используется |

## Практическая проверка

### Тест: Сравнение результатов

1. **Создайте тикет в demo режиме:**
   - Текст: "Не могу войти в сетевой диск S:"
   - Запомните: `predicted_type`, `confidence`, `model_version`

2. **Создайте тикет в production режиме:**
   - Тот же текст
   - Сравните результаты

**Ожидаемый результат:** Результаты должны быть **идентичными**.

### Проверка через API

```powershell
# Demo режим - прямой вызов
$demoResult = Invoke-RestMethod -Uri "http://localhost:8001/classify" -Method POST `
    -Body (@{text="Не могу войти в сетевой диск S:"; return_probabilities=$true} | ConvertTo-Json) `
    -ContentType "application/json"

# Production режим - через Dashboard, затем проверка в БД
# SELECT predicted_type, confidence, model_version 
# FROM ticket_events 
# WHERE text = 'Не могу войти в сетевой диск S:' 
# ORDER BY created_at DESC LIMIT 1;
```

**Ожидаемый результат:**
- `predicted_type` - одинаковый
- `confidence` - одинаковый (или очень близкий)
- `model_version` - `"v1.0"` в обоих случаях

## Заключение

✅ **Подтверждено:** В обоих режимах используется:
- **Один и тот же экземпляр** классификатора
- **Одна и та же версия** модели (v1.0)
- **Одни и те же файлы** модели (`classifier_smote_new.pkl`)
- **Один и тот же метод** классификации

**Единственная разница:** Способ вызова (прямой REST API vs через очередь), но модель используется одна и та же.

