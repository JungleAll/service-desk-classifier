# 📦 Управление версиями моделей

## 📍 Физическое размещение моделей

### Текущая структура

Модели хранятся в директории `models/` в корне проекта:

```
service-desk-classifier/
├── models/
│   └── v1.0/                    # Текущая версия модели
│       ├── classifier_smote_new.pkl
│       ├── vectorizer_smote.pkl
│       ├── label_encoder_smote.pkl
│       ├── config.json
│       ├── preprocessor.pkl
│       └── preprocessing_metadata.json
```

### Размещение новой модели v1.1

**Шаг 1: Создайте директорию для новой версии**

```bash
mkdir models/v1.1
```

**Шаг 2: Поместите файлы модели в директорию**

Скопируйте или создайте следующие файлы в `models/v1.1/`:

```
models/v1.1/
├── classifier_smote_new.pkl     # Основной классификатор (обязательно)
├── vectorizer_smote.pkl          # Векторизатор (обязательно)
├── label_encoder_smote.pkl       # Энкодер меток (обязательно)
├── config.json                   # Метаданные модели (рекомендуется)
├── preprocessor.pkl              # Препроцессор (опционально)
└── preprocessing_metadata.json   # Метаданные препроцессора (опционально)
```

**Важно:**
- Имена файлов могут отличаться от стандартных. В этом случае пути к файлам нужно будет указать в БД (см. раздел "Регистрация в БД").
- Пути к файлам указываются относительно корня проекта (`BASE_DIR`).

---

## 🗄️ Регистрация модели в базе данных

### Таблица `model_versions`

Информация о версиях моделей хранится в таблице `model_versions` в PostgreSQL:

```sql
CREATE TABLE model_versions (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) UNIQUE NOT NULL,           -- Версия модели (например, 'v1.1')
    model_path VARCHAR(500) NOT NULL,               -- Путь к classifier (относительно BASE_DIR)
    vectorizer_path VARCHAR(500) NOT NULL,          -- Путь к vectorizer
    label_encoder_path VARCHAR(500) NOT NULL,      -- Путь к label_encoder
    accuracy FLOAT,                                 -- Точность модели
    f1_score FLOAT,                                -- F1-score модели
    is_active BOOLEAN DEFAULT FALSE,               -- Активна ли версия
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP                          -- Когда была активирована
);
```

### Добавление записи для v1.1

**Вариант 1: Через SQL (рекомендуется)**

```sql
-- Добавление информации о модели v1.1
INSERT INTO model_versions (
    version, 
    model_path, 
    vectorizer_path, 
    label_encoder_path, 
    accuracy, 
    f1_score, 
    is_active
)
VALUES (
    'v1.1',
    'models/v1.1/classifier_smote_new.pkl',      -- Путь к классификатору
    'models/v1.1/vectorizer_smote.pkl',          -- Путь к векторизатору
    'models/v1.1/label_encoder_smote.pkl',      -- Путь к энкодеру
    0.9800,                                      -- Точность (accuracy)
    0.9750,                                      -- F1-score
    FALSE                                        -- Пока не активна
);
```

**Вариант 2: Через Python скрипт**

Создайте файл `add_model_version.py`:

```python
from shared.database import get_db_cursor

def add_model_version():
    """Добавление новой версии модели в БД"""
    with get_db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO model_versions (
                version, 
                model_path, 
                vectorizer_path, 
                label_encoder_path, 
                accuracy, 
                f1_score, 
                is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (version) DO UPDATE SET
                model_path = EXCLUDED.model_path,
                vectorizer_path = EXCLUDED.vectorizer_path,
                label_encoder_path = EXCLUDED.label_encoder_path,
                accuracy = EXCLUDED.accuracy,
                f1_score = EXCLUDED.f1_score
        """, (
            'v1.1',
            'models/v1.1/classifier_smote_new.pkl',
            'models/v1.1/vectorizer_smote.pkl',
            'models/v1.1/label_encoder_smote.pkl',
            0.9800,  # Замените на реальные метрики
            0.9750,  # Замените на реальные метрики
            False
        ))
        print("✅ Модель v1.1 успешно добавлена в БД")

if __name__ == "__main__":
    add_model_version()
```

Запустите:
```bash
python add_model_version.py
```

**Проверка регистрации:**

```sql
-- Проверка, что модель v1.1 добавлена
SELECT * FROM model_versions WHERE version = 'v1.1';
```

---

## 🔄 Механизм автоматического переключения версий

### Архитектура переключения

Система использует **централизованное управление версиями** через Config Service:

```
┌─────────────────┐
│ Config Service  │  ← Хранит current_model_version в таблице configuration
│   (Port 8002)   │
└────────┬────────┘
         │
         │ Проверка версии при каждом запросе
         │
┌────────▼────────┐
│  ML Service     │  ← Читает версию из Config Service
│   (Port 8001)   │     Автоматически перезагружает модель при несоответствии
└─────────────────┘
```

### Как работает автоматическое переключение

**1. При старте ML Service:**

- ML Service запрашивает `current_model_version` из Config Service
- Загружает модель указанной версии из таблицы `model_versions`
- Если версия не найдена, использует значение по умолчанию (`v1.0`)

**2. При каждом запросе классификации:**

- ML Service проверяет версию из Config Service
- Если версия отличается от загруженной, **автоматически перезагружает модель**
- Логирует переключение в консоль

**3. При использовании Worker (асинхронная обработка):**

- Worker проверяет версию перед обработкой каждого тикета
- Автоматически перезагружает модель при несоответствии

### Код автоматического переключения

**В `ml_service/app.py` (строки 217-232):**

```python
# Перед классификацией: быстрая проверка версии модели из Config Service
try:
    config_url = os.getenv("CONFIG_SERVICE_URL", "http://localhost:8002")
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{config_url}/config")
        if resp.status_code == 200:
            cfg = resp.json()
            desired_version = cfg.get("current_model_version")
            if desired_version and desired_version != classifier.model_version:
                logger.info(f"Обнаружено несоответствие версии (ML={classifier.model_version}, Config={desired_version}). Перезагружаю модель...")
                os.environ["ML_MODEL_VERSION"] = desired_version
                if classifier.reload_model():
                    logger.info(f"Модель успешно перезагружена на версию {desired_version}. Текущая версия ML: {classifier.model_version}")
                else:
                    logger.warning(f"Перезагрузка модели на версию {desired_version} не удалась, продолжаю с текущей версией {classifier.model_version}")
```

**В `ml_service/classifier.py` (строки 48-103):**

```python
def load_model(self) -> bool:
    """Загрузка модели из pickle файлов"""
    # Определяем директорию по версии - всегда берем из окружения
    version = os.getenv("ML_MODEL_VERSION", "v1.0") or "v1.0"
    self.model_version = version
    models_dir = BASE_DIR / "models" / version
    
    # Сначала пытаемся получить пути из БД (особенно важно для v1.1)
    try:
        from shared.database import get_db_cursor
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT model_path, vectorizer_path, label_encoder_path FROM model_versions WHERE version = %s",
                (version,)
            )
            result = cursor.fetchone()
            if result:
                # Используем пути из БД (относительные от BASE_DIR)
                db_classifier_path = BASE_DIR / result['model_path']
                db_vectorizer_path = BASE_DIR / result['vectorizer_path']
                db_label_encoder_path = BASE_DIR / result['label_encoder_path']
                
                if db_classifier_path.exists() and db_vectorizer_path.exists() and db_label_encoder_path.exists():
                    logger.info(f"✅ Использую пути из БД для версии {version}")
                    classifier_path = db_classifier_path
                    vectorizer_path = db_vectorizer_path
                    label_encoder_path = db_label_encoder_path
```

---

## 🎯 Переключение на новую версию модели

### Способ 1: Через Config Service API (рекомендуется)

**1. Проверьте, что модель v1.1 зарегистрирована в БД:**

```bash
curl http://localhost:8002/config
```

**2. Переключите версию через API:**

```bash
curl -X POST http://localhost:8002/config/model-version \
  -H "Content-Type: application/json" \
  -d '{
    "version": "v1.1",
    "gradual_rollout": false,
    "rollout_percentage": 100
  }'
```

**Ответ:**
```json
{
  "model_version": "v1.1",
  "current_model_version": "v1.1",
  "message": "Model switched to v1.1",
  "previous_version": "v1.0",
  "switched_at": "2024-01-15T10:30:00",
  "active_models": {
    "v1.1": 100
  }
}
```

**3. ML Service автоматически перезагрузит модель при следующем запросе**

### Способ 2: Через Dashboard

1. Откройте Dashboard: http://localhost:8501
2. Перейдите на страницу **Settings**
3. В разделе **"Версия модели"** выберите `v1.1`
4. Нажмите **"Переключить версию"**
5. Система автоматически переключится на новую версию

### Способ 3: Напрямую в БД (не рекомендуется для production)

```sql
-- Обновление активной версии в таблице configuration
UPDATE configuration 
SET value = 'v1.1', 
    updated_at = CURRENT_TIMESTAMP,
    updated_by = 'admin'
WHERE key = 'current_model_version';

-- Обновление флагов is_active в model_versions
UPDATE model_versions SET is_active = FALSE WHERE is_active = TRUE;
UPDATE model_versions SET is_active = TRUE, activated_at = CURRENT_TIMESTAMP WHERE version = 'v1.1';
```

**После изменения в БД:**
- ML Service автоматически обнаружит изменение при следующем запросе
- Или вызовите endpoint `/reload` для принудительной перезагрузки

### Способ 4: Принудительная перезагрузка через ML Service API

```bash
curl -X POST http://localhost:8001/reload
```

Этот endpoint:
1. Запрашивает текущую версию из Config Service
2. Перезагружает модель указанной версии
3. Возвращает статус перезагрузки

---

## ✅ Проверка корректности работы модели

### 1. Проверка статуса модели

**Через ML Service API:**

```bash
curl http://localhost:8001/status
```

**Ответ:**
```json
{
  "model_version": "v1.1",
  "is_loaded": true,
  "classifier_path": "/path/to/models/v1.1/classifier_smote_new.pkl",
  "vectorizer_path": "/path/to/models/v1.1/vectorizer_smote.pkl",
  "label_encoder_path": "/path/to/models/v1.1/label_encoder_smote.pkl",
  "num_classes": 15,
  "classes": ["Hardware", "Software", "Network", ...]
}
```

**Через Dashboard:**

1. Откройте http://localhost:8501
2. Перейдите на страницу **Settings**
3. Проверьте раздел **"Статус модели"**

### 2. Тестовая классификация

**Через API:**

```bash
curl -X POST http://localhost:8001/classify \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Не работает принтер в кабинете 205",
    "return_probabilities": true
  }'
```

**Проверьте в ответе:**
- `model_version` должно быть `"v1.1"`
- `predicted_type` - предсказанная категория
- `confidence` - уверенность модели (0-1)
- `decision` - "auto-process" или "manual-review"

**Через Dashboard:**

1. Откройте http://localhost:8501
2. Перейдите на страницу **Demo**
3. Введите тестовый текст
4. Проверьте, что в результате указана версия `v1.1`

### 3. Проверка логов

**ML Service логи:**

Проверьте логи ML Service на наличие сообщений:
```
✅ Модель успешно загружена: версия v1.1
✅ Использую пути из БД для версии v1.1
```

**При переключении версии:**
```
Обнаружено несоответствие версии (ML=v1.0, Config=v1.1). Перезагружаю модель...
Модель успешно перезагружена на версию v1.1. Текущая версия ML: v1.1
```

### 4. Проверка в базе данных

**Проверка активной версии:**

```sql
SELECT key, value FROM configuration WHERE key = 'current_model_version';
-- Должно вернуть: v1.1
```

**Проверка записей классификации:**

```sql
SELECT 
    ticket_id, 
    predicted_type, 
    confidence, 
    model_version,
    created_at
FROM ticket_events 
WHERE model_version = 'v1.1'
ORDER BY created_at DESC
LIMIT 10;
```

**Проверка метрик:**

```sql
SELECT 
    model_version,
    metric_name,
    SUM(metric_value) as total
FROM metrics
WHERE model_version = 'v1.1'
GROUP BY model_version, metric_name;
```

### 5. Мониторинг через Dashboard

1. Откройте http://localhost:8501
2. Перейдите на страницу **Monitoring**
3. Проверьте:
   - График использования версий моделей
   - Метрики производительности для v1.1
   - Количество классификаций по версиям

---

## 🔍 Откат на предыдущую версию

Если новая модель работает некорректно, можно быстро откатиться:

### Через API:

```bash
curl -X POST http://localhost:8002/config/model-version \
  -H "Content-Type: application/json" \
  -d '{
    "version": "v1.0",
    "gradual_rollout": false,
    "rollout_percentage": 100
  }'
```

### Через Dashboard:

1. Откройте Settings
2. Выберите версию `v1.0`
3. Нажмите "Переключить версию"

**ML Service автоматически перезагрузит модель v1.0 при следующем запросе.**

---

## 📝 Важные замечания

### 1. Имена файлов модели

Если файлы модели имеют другие имена (не стандартные), укажите их в таблице `model_versions`:

```sql
UPDATE model_versions 
SET 
    model_path = 'models/v1.1/my_custom_classifier.pkl',
    vectorizer_path = 'models/v1.1/my_custom_vectorizer.pkl',
    label_encoder_path = 'models/v1.1/my_custom_encoder.pkl'
WHERE version = 'v1.1';
```

### 2. Использование файлов из другой версии

Модель v1.1 может использовать файлы из v1.0 (например, если векторizer не изменился):

```sql
UPDATE model_versions 
SET 
    model_path = 'models/v1.1/classifier_v1.1.pkl',
    vectorizer_path = 'models/v1.0/vectorizer_smote.pkl',  -- Используем из v1.0
    label_encoder_path = 'models/v1.0/label_encoder_smote.pkl'  -- Используем из v1.0
WHERE version = 'v1.1';
```

### 3. Переменные окружения

При запуске через Docker Compose версия модели может быть задана через переменную окружения:

```yaml
# docker-compose.yml
ml_service:
  environment:
    - ML_MODEL_VERSION=v1.1  # По умолчанию используется из Config Service
```

**Важно:** Версия из Config Service имеет приоритет над переменной окружения.

### 4. Кэширование предсказаний

Предсказания кэшируются в Redis с ключом, включающим версию модели:

```
cache:prediction:v1.1:<hash_text>
```

При переключении версии старые предсказания из кэша не используются (так как ключ содержит версию).

### 5. Worker (асинхронная обработка)

Если используется Worker для обработки очереди Redis, он также автоматически проверяет версию модели перед обработкой каждого тикета (см. `ml_service/worker.py`, строки 94-119).

---

## 🚀 Полный процесс добавления новой модели

### Пошаговая инструкция:

1. **Подготовка файлов модели:**
   ```bash
   mkdir models/v1.1
   # Скопируйте файлы модели в models/v1.1/
   ```

2. **Регистрация в БД:**
   ```sql
   INSERT INTO model_versions (...) VALUES (...);
   ```

3. **Проверка регистрации:**
   ```sql
   SELECT * FROM model_versions WHERE version = 'v1.1';
   ```

4. **Тестовая загрузка (опционально):**
   ```bash
   # Установите переменную окружения для теста
   export ML_MODEL_VERSION=v1.1
   # Перезапустите ML Service
   ```

5. **Переключение через Config Service:**
   ```bash
   curl -X POST http://localhost:8002/config/model-version -d '{"version": "v1.1"}'
   ```

6. **Проверка работы:**
   ```bash
   curl http://localhost:8001/status
   curl -X POST http://localhost:8001/classify -d '{"text": "тест"}'
   ```

7. **Мониторинг:**
   - Проверьте логи ML Service
   - Проверьте Dashboard → Monitoring
   - Проверьте записи в БД

---

## 📚 Дополнительные ресурсы

- **API Reference:** `API_REFERENCE.md` - документация по всем API endpoints
- **Architecture:** `ARCHITECTURE.md` - архитектура системы
- **Database Schema:** `database/schema.sql` - схема базы данных
- **Config Service:** `config_service/README.md` - документация Config Service
- **ML Service:** `ml_service/README.md` - документация ML Service

---

## ❓ Часто задаваемые вопросы

**Q: Можно ли иметь несколько активных версий одновременно?**  
A: Нет, в текущей реализации только одна версия может быть активной (`is_active = TRUE`). Однако можно реализовать gradual rollout через Config Service API.

**Q: Что произойдет, если файлы модели не найдены?**  
A: ML Service выдаст ошибку при загрузке и вернет статус `is_loaded = false`. Проверьте логи для деталей.

**Q: Нужно ли перезапускать ML Service при переключении версии?**  
A: Нет, переключение происходит автоматически при следующем запросе. Можно также вызвать `/reload` для немедленной перезагрузки.

**Q: Как проверить, какая версия используется сейчас?**  
A: Вызовите `GET /status` на ML Service или проверьте `current_model_version` в Config Service.

**Q: Можно ли использовать разные имена файлов для разных версий?**  
A: Да, пути к файлам указываются в таблице `model_versions` в БД, поэтому можно использовать любые имена файлов.

