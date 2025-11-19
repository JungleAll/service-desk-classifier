# Service Desk Classifier ML Service

Production-ready ML Service для автоматической классификации обращений Service Desk на Python с использованием FastAPI.

## Описание

Сервис предоставляет REST API для классификации текстовых обращений в Service Desk на 17 категорий с использованием обученной модели LogisticRegression с SMOTE.

## Технологии

- **Python 3.11+**
- **FastAPI** - современный веб-фреймворк
- **scikit-learn** - ML библиотека
- **pymorphy3** - морфологический анализ русского языка
- **nltk** - обработка естественного языка (стоп-слова)

## Структура проекта

```
ml_service/
├── __init__.py
├── app.py              # FastAPI приложение с эндпоинтами
├── classifier.py       # Класс для загрузки и использования модели
├── config.py           # Конфигурация сервиса
├── models.py           # Pydantic модели для запросов/ответов
├── preprocessor.py     # Класс для предобработки текста
├── worker.py           # Worker для асинхронной обработки очереди Redis
├── requirements.txt    # Зависимости проекта
├── run.py              # Скрипт для запуска сервиса
└── README.md          # Документация
```

## Установка

1. Создайте виртуальное окружение (если еще не создано):
```bash
python -m venv venv
```

2. Активируйте виртуальное окружение:
```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

3. Установите зависимости:
```bash
cd ml_service
pip install -r requirements.txt
```

4. Убедитесь, что модели находятся в `models/v1.0/`:
   - `classifier_smote_new.pkl` (стабильная рабочая модель по умолчанию)
   - `vectorizer_smote.pkl` (стабильный векторизатор по умолчанию)
   - `label_encoder_smote.pkl` (стабильный энкодер по умолчанию)
   - `config.json` (опционально)

## Переключение между версиями моделей

По умолчанию используется стабильная модель `classifier_smote_new.pkl`. Для переключения на другую версию модели используйте переменные окружения:

### Через переменные окружения:

```bash
# Использование другой версии классификатора
export ML_CLASSIFIER_FILE="classifier_smote.pkl"
export ML_VECTORIZER_FILE="vectorizer.pkl"
export ML_LABEL_ENCODER_FILE="label_encoder.pkl"

# Или для другой версии модели (например, v1.1)
export ML_MODEL_VERSION="v1.1"
export ML_CLASSIFIER_FILE="classifier_v1.1.pkl"
```

### В Docker Compose:

Отредактируйте `docker-compose.yml` и установите переменные окружения:

```yaml
ml-service:
  environment:
    - ML_MODEL_VERSION=v1.1
    - ML_CLASSIFIER_FILE=classifier_v1.1.pkl
    - ML_VECTORIZER_FILE=vectorizer_v1.1.pkl
    - ML_LABEL_ENCODER_FILE=label_encoder_v1.1.pkl
```

**Важно:** Убедитесь, что все три файла (classifier, vectorizer, label_encoder) совместимы друг с другом и находятся в соответствующей директории `models/{ML_MODEL_VERSION}/`.

## Запуск сервиса

### Способ 1: Через uvicorn напрямую

```bash
cd ml_service
uvicorn app:app --host 0.0.0.0 --port 8001
```

### Способ 2: Через Python модуль

```bash
cd ml_service
python -m uvicorn app:app --host 0.0.0.0 --port 8001
```

### Способ 3: Из корня проекта

```bash
python -m uvicorn ml_service.app:app --host 0.0.0.0 --port 8001
```

### Способ 4: Через run.py

```bash
# Из корня проекта
python ml_service/run.py

# Или из папки ml_service
cd ml_service
python run.py
```

## Переменные окружения

### Основные настройки:
- `ML_SERVICE_HOST` - хост для запуска сервиса (по умолчанию: `0.0.0.0`)
- `ML_SERVICE_PORT` - порт для запуска сервиса (по умолчанию: `8001`)
- `LOG_LEVEL` - уровень логирования (по умолчанию: `INFO`)

### Настройки модели:
- `ML_MODEL_VERSION` - версия модели (по умолчанию: `v1.0`)
- `ML_CLASSIFIER_FILE` - имя файла классификатора (по умолчанию: `classifier_smote_new.pkl`)
- `ML_VECTORIZER_FILE` - имя файла векторизатора (по умолчанию: `vectorizer_smote.pkl`)
- `ML_LABEL_ENCODER_FILE` - имя файла энкодера (по умолчанию: `label_encoder_smote.pkl`)

### Интеграции:
- `CONFIG_SERVICE_URL` - URL Config Service (по умолчанию: `http://localhost:8002`)
- `OUTPUT_SERVICE_URL` - URL Output Service (по умолчанию: `http://localhost:8003`)
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` - настройки PostgreSQL
- `REDIS_HOST`, `REDIS_PORT` - настройки Redis

### Настройки Worker (асинхронная обработка очереди):
- `WORKER_ENABLED` - включить/выключить worker (по умолчанию: `false`)
- `WORKER_QUEUE_TIMEOUT` - таймаут ожидания тикета из очереди в секундах (по умолчанию: `5`)
- `WORKER_DELAY` - задержка между итерациями цикла в секундах (по умолчанию: `0.1`)

Пример:
```bash
export API_HOST=0.0.0.0
export API_PORT=8080
export LOG_LEVEL=DEBUG
export WORKER_ENABLED=true
```

## Режимы работы

ML Service поддерживает два режима работы:

### 1. Режим REST API (без Worker) - По умолчанию

**Описание:** Сервис работает только как REST API. Классификация выполняется по запросу через HTTP.

**Когда использовать:**
- Для демонстрации и тестирования
- Для разработки и отладки
- Когда нужен полный контроль над процессом классификации
- Когда классификация выполняется по требованию (on-demand)

**Как включить:**
```bash
# Worker отключен по умолчанию
export WORKER_ENABLED=false
# или просто не устанавливайте переменную
```

**Поток работы:**
```
Клиент → POST /classify → ML Service → Результат
```

**Пример использования:**
```bash
# Создание тикета через Ingestion Service
curl -X POST "http://localhost:8000/tickets" \
  -H "Content-Type: application/json" \
  -d '{"text": "Не могу войти в систему", "source": "api"}'

# Ручная классификация через ML Service
curl -X POST "http://localhost:8001/classify" \
  -H "Content-Type: application/json" \
  -d '{"text": "Не могу войти в систему"}'

# Ручная отправка в Output Service
curl -X POST "http://localhost:8003/process_result" \
  -H "Content-Type: application/json" \
  -d '{...результат классификации...}'
```

**Преимущества:**
- ✅ Простота использования
- ✅ Полный контроль над процессом
- ✅ Легко отлаживать
- ✅ Не требует Redis для очереди

**Недостатки:**
- ❌ Нет автоматической обработки
- ❌ Требуется ручная интеграция между сервисами
- ❌ Не подходит для production с высокой нагрузкой

---

### 2. Режим с Worker (автоматическая обработка очереди)

**Описание:** Сервис автоматически обрабатывает тикеты из очереди Redis. Worker работает в фоновом режиме и обрабатывает тикеты по мере их поступления.

**Когда использовать:**
- Для production окружения
- Для автоматической обработки большого количества тикетов
- Когда нужна полная автоматизация потока данных
- Когда тикеты поступают из Ingestion Service в очередь Redis

**Как включить:**
```bash
export WORKER_ENABLED=true
export OUTPUT_SERVICE_URL=http://localhost:8003
export REDIS_HOST=localhost
export REDIS_PORT=6379
```

**Поток работы:**
```
Ingestion Service → Redis Queue → Worker → ML Service → Output Service → Jira/FileSystem
```

**Пример использования:**
```bash
# 1. Запустить все сервисы с включенным Worker
export WORKER_ENABLED=true
python ml_service/run.py

# 2. Создать тикет через Ingestion Service
curl -X POST "http://localhost:8000/tickets" \
  -H "Content-Type: application/json" \
  -d '{"text": "Не могу войти в систему", "source": "api"}'

# 3. Worker автоматически:
#    - Получит тикет из очереди Redis
#    - Классифицирует его
#    - Отправит результат в Output Service
#    - Обновит статус в БД

# 4. Проверить статус тикета
curl "http://localhost:8000/status/{ticket_id}"
```

**Преимущества:**
- ✅ Полная автоматизация обработки
- ✅ Масштабируемость (можно запустить несколько worker'ов)
- ✅ Асинхронная обработка (не блокирует API)
- ✅ Подходит для production

**Недостатки:**
- ❌ Требует Redis для очереди
- ❌ Сложнее отлаживать (нужно проверять логи)
- ❌ Требует настройки всех сервисов

---

### Переключение между режимами

#### Переключение с REST API на Worker:

1. **Остановите ML Service** (если запущен):
   ```bash
   # Нажмите Ctrl+C в терминале с запущенным сервисом
   ```

2. **Установите переменные окружения:**
   ```bash
   export WORKER_ENABLED=true
   export OUTPUT_SERVICE_URL=http://localhost:8003
   export REDIS_HOST=localhost
   export REDIS_PORT=6379
   ```

3. **Убедитесь, что Redis запущен:**
   ```bash
   # Проверьте подключение к Redis
   redis-cli ping
   # Должно вернуть: PONG
   ```

4. **Запустите ML Service:**
   ```bash
   python ml_service/run.py
   ```

5. **Проверьте логи:**
   ```
   ✅ Worker для обработки очереди запущен
   ```

#### Переключение с Worker на REST API:

1. **Остановите ML Service:**
   ```bash
   # Нажмите Ctrl+C
   ```

2. **Отключите Worker:**
   ```bash
   export WORKER_ENABLED=false
   # или удалите переменную
   unset WORKER_ENABLED
   ```

3. **Запустите ML Service:**
   ```bash
   python ml_service/run.py
   ```

4. **Проверьте логи:**
   ```
   ℹ️ Worker отключен. Используйте REST API для классификации.
   ```

#### Проверка текущего режима:

```bash
# Проверка через health endpoint
curl http://localhost:8001/health

# В ответе будет указан статус worker:
# "message": "Сервис работает нормально (Worker: running)"  # Worker включен
# "message": "Сервис работает нормально"                     # Worker отключен
```

---

### Рекомендации по выбору режима

| Сценарий | Рекомендуемый режим |
|----------|-------------------|
| Демонстрация/презентация | REST API (без Worker) |
| Разработка и тестирование | REST API (без Worker) |
| Production с высокой нагрузкой | Worker (автоматическая обработка) |
| Интеграция с внешними системами | Worker (автоматическая обработка) |
| Отладка отдельных компонентов | REST API (без Worker) |

---

## API Endpoints

### 1. POST /classify

Классификация текста обращения.

**Запрос:**
```json
{
  "text": "Не могу войти в корпоративную систему"
}
```

**Ответ:**
```json
{
  "predicted_type": "Запрос на обслуживание",
  "confidence": 0.95,
  "probabilities": {
    "Запрос на обслуживание": 0.95,
    "HR: Приём": 0.02,
    ...
  },
  "model_version": "v1.0",
  "decision": "auto-process"
}
```

**Поля ответа:**
- `predicted_type` - предсказанный класс обращения
- `confidence` - уверенность модели (0-1)
- `probabilities` - вероятности для всех 17 классов (массив объектов `{category, score}`)
- `model_version` - версия используемой модели
- `decision` - решение: `"auto-process"` (confidence >= 0.7) или `"manual-review"` (confidence < 0.7)
- `processing_time_ms` - время обработки в миллисекундах

**Дополнительные параметры запроса:**
- `return_probabilities?: boolean` (default: true) - возвращать ли вероятности
- `top_n?: number` (0..20) - ограничить количество возвращаемых вероятностей

### 2. POST /classify/batch

Пакетная классификация нескольких текстов за один запрос.

**Запрос:**
```json
{
  "texts": [
    "Не могу войти в систему",
    "Увольнение Иванова И.И.",
    "Заказать визитки"
  ]
}
```

**Ответ:**
```json
{
  "results": [
    {
      "text": "Не могу войти в систему",
      "predicted_type": "Запрос на обслуживание",
      "confidence": 0.95
    },
    {
      "text": "Увольнение Иванова И.И.",
      "predicted_type": "HR: Увольнение",
      "confidence": 0.98
    },
    {
      "text": "Заказать визитки",
      "predicted_type": "Заказ визиток",
      "confidence": 0.97
    }
  ],
  "total_time_ms": 150
}
```

### 3. GET /model/status

Получение информации о загруженной модели.

**Ответ:**
```json
{
  "model_version": "v1.0",
  "is_loaded": true,
  "num_classes": 17,
  "classes": ["Запрос на обслуживание", ...],
  "classifier_path": "models/v1.0/classifier_smote_new.pkl",
  "vectorizer_path": "models/v1.0/vectorizer_smote.pkl",
  "label_encoder_path": "models/v1.0/label_encoder_smote.pkl"
}
```

### 4. GET /model/list

Получение списка доступных версий моделей из БД.

**Ответ:**
```json
{
  "models": [
    {
      "version": "v1.0",
      "name": "classifier_smote_new",
      "accuracy": 0.985,
      "is_active": true,
      "created_at": "2025-01-15T10:00:00"
    }
  ]
}
```

### 5. GET /health

Проверка работоспособности сервиса.

**Ответ:**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "model_version": "v1.0",
  "message": "Сервис работает нормально"
}
```

### 6. POST /reload_model

Hot reload модели без остановки сервиса.

**Ответ:**
```json
{
  "success": true,
  "message": "Модель успешно перезагружена",
  "model_version": "v1.0"
}
```

## Документация API

После запуска сервиса доступна автоматическая документация:

- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

## Обработка ошибок

Все ошибки возвращаются в формате JSON с соответствующими HTTP статус-кодами:

- `400` - Неверный запрос (например, текст короче 3 символов)
- `503` - Сервис недоступен (модель не загружена, ошибка при классификации)

Пример ответа с ошибкой:
```json
{
  "error": "Service Unavailable",
  "detail": "Модель не загружена. Сервис недоступен."
}
```

## Особенности

1. **Асинхронная обработка** - FastAPI поддерживает асинхронные запросы
2. **Hot reload модели** - возможность перезагрузить модель через endpoint без остановки сервиса
3. **Логирование** - подробные логи на уровне INFO и ERROR
4. **CORS** - разрешен для всех источников (настраивается в `app.py`)
5. **Валидация данных** - использование Pydantic для валидации запросов
6. **Автодокументация** - автоматическая генерация OpenAPI/Swagger документации

## Предобработка текста

Сервис выполняет следующую предобработку текста:

1. **Очистка:**
   - Удаление email адресов
   - Удаление URL
   - Удаление дат
   - Замена чисел на токен `NUM`
   - Удаление специальных символов
   - Приведение к нижнему регистру

2. **Лемматизация:**
   - Преобразование слов в начальную форму (pymorphy3)
   - Удаление стоп-слов (nltk russian stopwords)
   - Удаление слов короче 3 символов

## Классы классификации

Модель классифицирует обращения на 17 категорий:

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

## Примеры использования

### cURL

```bash
# Классификация текста
curl -X POST "http://localhost:8001/classify" \
  -H "Content-Type: application/json" \
  -d '{"text": "Не могу войти в корпоративную систему"}'

# Проверка здоровья
curl -X GET "http://localhost:8001/health"

# Статус модели
curl -X GET "http://localhost:8001/model/status"

# Перезагрузка модели
curl -X POST "http://localhost:8001/reload_model"
```

### Python

```python
import requests

# Классификация
response = requests.post(
    "http://localhost:8001/classify",
    json={"text": "Не могу войти в корпоративную систему"}
)
result = response.json()
print(f"Класс: {result['predicted_type']}")
print(f"Уверенность: {result['confidence']}")
print(f"Решение: {result['decision']}")
```

## Разработка

Для разработки с автоперезагрузкой:

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8001
```

## Лицензия

Проект создан для хакатона AI.

