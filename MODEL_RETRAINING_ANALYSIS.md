# Анализ готовности данных для дообучения модели

**Дата анализа:** 2025-11-19  
**Цель:** Оценка достаточности данных в PostgreSQL для дообучения модели и рекомендации по расширению схемы БД

---

## Текущее состояние данных

### Что уже хранится в `ticket_events`

✅ **Достаточно для базового обучения:**
- `text` - текст обращения (TEXT)
- `source` - источник обращения ('email', 'chat', 'api', 'web')
- `user_id`, `email` - информация о пользователе
- `priority` - приоритет обращения
- `created_at`, `processed_at` - временные метки
- `metadata` (JSONB) - дополнительные метаданные

✅ **Достаточно для анализа качества:**
- `predicted_type` - предсказанная моделью категория
- `confidence` - уверенность модели (0-1)
- `probabilities` (JSONB) - вероятности для всех классов
- `decision` - решение ('auto-process' | 'manual-review')
- `model_version` - версия модели, использованная для классификации

✅ **Достаточно для фильтрации:**
- `status` - статус обработки
- `created_at` - дата создания (для временных фильтров)

---

## Что отсутствует для дообучения

### ❌ Критически необходимо

#### 1. Правильная категория (Ground Truth)
**Проблема:** Нет поля для хранения фактической категории тикета после ручной обработки.

**Требуется:**
- `actual_type` VARCHAR(255) - фактическая категория после ручной обработки
- `actual_type_set_at` TIMESTAMP - когда была установлена фактическая категория
- `actual_type_set_by` VARCHAR(255) - кто установил категорию (оператор, система)

**Использование:**
- Обучение на тикетах с `decision='manual-review'` после их ручной обработки
- Сравнение `predicted_type` vs `actual_type` для выявления ошибок

#### 2. Обратная связь по классификации
**Проблема:** Нет механизма для получения и хранения обратной связи от пользователей/операторов.

**Требуется:**
- `feedback_status` VARCHAR(50) - статус обратной связи ('none', 'correct', 'incorrect', 'pending')
- `feedback_correct_type` VARCHAR(255) - правильная категория по обратной связи
- `feedback_comment` TEXT - комментарий к обратной связи
- `feedback_provided_at` TIMESTAMP - когда была предоставлена обратная связь
- `feedback_provided_by` VARCHAR(255) - кто предоставил обратную связь

**Использование:**
- Обучение на тикетах, где пользователь указал неправильную классификацию
- Анализ паттернов ошибок модели

#### 3. Флаг готовности для обучения
**Проблема:** Нет способа пометить тикеты, которые готовы для использования в обучении.

**Требуется:**
- `training_ready` BOOLEAN DEFAULT FALSE - готов ли тикет для обучения
- `training_ready_at` TIMESTAMP - когда тикет был помечен как готовый
- `training_used_in_version` VARCHAR(50) - в какой версии модели был использован

**Использование:**
- Фильтрация тикетов для обучения
- Отслеживание, какие тикеты уже использовались в обучении
- Предотвращение дублирования данных

---

## Рекомендуемые расширения схемы

### Вариант 1: Минимальное расширение (для быстрого старта)

Добавить только критически необходимые поля в `ticket_events`:

```sql
-- Добавление полей для дообучения
ALTER TABLE ticket_events
ADD COLUMN IF NOT EXISTS actual_type VARCHAR(255),
ADD COLUMN IF NOT EXISTS actual_type_set_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS actual_type_set_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS feedback_status VARCHAR(50) DEFAULT 'none',
ADD COLUMN IF NOT EXISTS feedback_correct_type VARCHAR(255),
ADD COLUMN IF NOT EXISTS feedback_comment TEXT,
ADD COLUMN IF NOT EXISTS feedback_provided_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS feedback_provided_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS training_ready BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS training_ready_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS training_used_in_version VARCHAR(50);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_ticket_events_actual_type ON ticket_events(actual_type);
CREATE INDEX IF NOT EXISTS idx_ticket_events_feedback_status ON ticket_events(feedback_status);
CREATE INDEX IF NOT EXISTS idx_ticket_events_training_ready ON ticket_events(training_ready);
CREATE INDEX IF NOT EXISTS idx_ticket_events_training_used_in_version ON ticket_events(training_used_in_version);
```

**Преимущества:**
- Минимальные изменения в схеме
- Быстрое внедрение
- Все данные в одной таблице

**Недостатки:**
- Таблица `ticket_events` становится перегруженной
- Нет истории изменений категорий
- Нет детальной истории обратной связи

---

### Вариант 2: Расширенное решение (рекомендуется)

Создать отдельные таблицы для обратной связи и истории изменений:

#### 2.1. Таблица для обратной связи

```sql
CREATE TABLE IF NOT EXISTS classification_feedback (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(255) NOT NULL,
    feedback_type VARCHAR(50) NOT NULL,  -- 'correct', 'incorrect', 'partial'
    original_predicted_type VARCHAR(255),  -- что предсказала модель
    correct_type VARCHAR(255),  -- правильная категория
    confidence_at_feedback FLOAT,  -- уверенность модели на момент обратной связи
    comment TEXT,  -- комментарий пользователя/оператора
    provided_by VARCHAR(255),  -- кто предоставил обратную связь
    provided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE,  -- обработана ли обратная связь для обучения
    processed_at TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES ticket_events(ticket_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_classification_feedback_ticket_id ON classification_feedback(ticket_id);
CREATE INDEX IF NOT EXISTS idx_classification_feedback_type ON classification_feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_classification_feedback_processed ON classification_feedback(processed);
CREATE INDEX IF NOT EXISTS idx_classification_feedback_provided_at ON classification_feedback(provided_at);
```

#### 2.2. Таблица для истории изменений категорий

```sql
CREATE TABLE IF NOT EXISTS category_corrections (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(255) NOT NULL,
    original_type VARCHAR(255),  -- исходная категория (predicted_type)
    corrected_type VARCHAR(255) NOT NULL,  -- исправленная категория
    correction_reason VARCHAR(255),  -- причина исправления ('manual_review', 'feedback', 'admin_correction')
    corrected_by VARCHAR(255) NOT NULL,  -- кто исправил
    corrected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confidence_at_correction FLOAT,  -- уверенность модели на момент исправления
    used_in_training BOOLEAN DEFAULT FALSE,  -- использовано ли в обучении
    used_in_version VARCHAR(50),  -- в какой версии модели использовано
    FOREIGN KEY (ticket_id) REFERENCES ticket_events(ticket_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_category_corrections_ticket_id ON category_corrections(ticket_id);
CREATE INDEX IF NOT EXISTS idx_category_corrections_corrected_type ON category_corrections(corrected_type);
CREATE INDEX IF NOT EXISTS idx_category_corrections_used_in_training ON category_corrections(used_in_training);
CREATE INDEX IF NOT EXISTS idx_category_corrections_corrected_at ON category_corrections(corrected_at);
```

#### 2.3. Таблица для отслеживания использования данных в обучении

```sql
CREATE TABLE IF NOT EXISTS training_data_usage (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(255) NOT NULL,
    model_version VARCHAR(50) NOT NULL,  -- версия модели, в которой использованы данные
    training_type VARCHAR(50) NOT NULL,  -- 'initial', 'retraining', 'incremental'
    data_type VARCHAR(50) NOT NULL,  -- 'manual_review', 'feedback', 'correction'
    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES ticket_events(ticket_id) ON DELETE CASCADE,
    FOREIGN KEY (model_version) REFERENCES model_versions(version) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_training_data_usage_ticket_id ON training_data_usage(ticket_id);
CREATE INDEX IF NOT EXISTS idx_training_data_usage_model_version ON training_data_usage(model_version);
CREATE INDEX IF NOT EXISTS idx_training_data_usage_training_type ON training_data_usage(training_type);
```

#### 2.4. Обновление ticket_events

```sql
-- Добавить только необходимые поля для связи
ALTER TABLE ticket_events
ADD COLUMN IF NOT EXISTS actual_type VARCHAR(255),  -- текущая фактическая категория
ADD COLUMN IF NOT EXISTS actual_type_set_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS actual_type_set_by VARCHAR(255),
ADD COLUMN IF NOT EXISTS has_feedback BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS has_correction BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS training_ready BOOLEAN DEFAULT FALSE;

-- Индексы
CREATE INDEX IF NOT EXISTS idx_ticket_events_actual_type ON ticket_events(actual_type);
CREATE INDEX IF NOT EXISTS idx_ticket_events_has_feedback ON ticket_events(has_feedback);
CREATE INDEX IF NOT EXISTS idx_ticket_events_has_correction ON ticket_events(has_correction);
CREATE INDEX IF NOT EXISTS idx_ticket_events_training_ready ON ticket_events(training_ready);
```

**Преимущества:**
- Четкое разделение ответственности
- Полная история изменений
- Возможность анализировать паттерны ошибок
- Отслеживание использования данных в обучении
- Масштабируемость

**Недостатки:**
- Более сложная схема
- Требует больше времени на внедрение
- Более сложные запросы для получения данных

---

## Сценарии использования для дообучения

### Сценарий 1: Обучение на тикетах с manual-review

**Текущее состояние:**
- ✅ Есть: `text`, `predicted_type`, `confidence`, `decision='manual-review'`
- ❌ Нет: `actual_type` (правильная категория после ручной обработки)

**Что нужно:**
1. После ручной обработки оператор должен установить `actual_type`
2. Тикет помечается как `training_ready=TRUE`
3. При дообучении выбираются тикеты:
   ```sql
   SELECT text, actual_type 
   FROM ticket_events 
   WHERE decision = 'manual-review' 
     AND actual_type IS NOT NULL 
     AND training_ready = TRUE
     AND training_used_in_version IS NULL;  -- еще не использованы
   ```

**Рекомендация:** Добавить API endpoint для установки `actual_type` оператором.

---

### Сценарий 2: Обучение на тикетах с обратной связью

**Текущее состояние:**
- ✅ Есть: `text`, `predicted_type`, `confidence`
- ❌ Нет: механизм получения и хранения обратной связи

**Что нужно:**
1. API endpoint для получения обратной связи от пользователей/операторов
2. Хранение обратной связи в `classification_feedback`
3. При дообучении выбираются тикеты:
   ```sql
   SELECT t.text, f.correct_type as actual_type
   FROM ticket_events t
   JOIN classification_feedback f ON t.ticket_id = f.ticket_id
   WHERE f.feedback_type = 'incorrect'
     AND f.processed = FALSE
     AND f.correct_type IS NOT NULL;
   ```

**Рекомендация:** 
- Добавить API endpoint `POST /tickets/{ticket_id}/feedback`
- Интеграция с Jira для получения обратной связи через комментарии
- Dashboard для операторов для быстрой обратной связи

---

### Сценарий 3: Инкрементальное обучение

**Текущее состояние:**
- ✅ Есть: `model_version` - можно отслеживать, какая модель использовалась
- ❌ Нет: отслеживание использования данных в обучении

**Что нужно:**
1. При обучении новой версии модели:
   - Помечать использованные тикеты в `training_data_usage`
   - Обновлять `training_used_in_version` в `ticket_events`
2. При следующем обучении исключать уже использованные тикеты:
   ```sql
   SELECT text, actual_type
   FROM ticket_events
   WHERE training_ready = TRUE
     AND actual_type IS NOT NULL
     AND (training_used_in_version IS NULL 
          OR training_used_in_version != 'v2.0')  -- новая версия
   ```

**Рекомендация:** Создать скрипт для подготовки данных для обучения из БД.

---

## Дополнительные рекомендации

### 1. API для работы с обратной связью

```python
# POST /tickets/{ticket_id}/feedback
{
    "feedback_type": "incorrect",  # 'correct', 'incorrect', 'partial'
    "correct_type": "Запрос на обслуживание",
    "comment": "Модель неправильно классифицировала",
    "provided_by": "operator_123"
}

# POST /tickets/{ticket_id}/correct
{
    "correct_type": "Запрос на обслуживание",
    "reason": "manual_review",
    "corrected_by": "operator_123"
}
```

### 2. Интеграция с Jira

Если используется Jira, можно получать обратную связь через:
- Комментарии к тикетам (если оператор указывает правильную категорию)
- Кастомные поля Jira для обратной связи
- Webhook от Jira при изменении категории тикета

### 3. Dashboard для операторов

Создать интерфейс для:
- Просмотра тикетов с `decision='manual-review'`
- Быстрого указания правильной категории
- Просмотра тикетов с неправильной классификацией
- Статистики по качеству классификации

### 4. Автоматическое определение готовности для обучения

Логика для автоматической установки `training_ready=TRUE`:
- Если `decision='manual-review'` и `actual_type` установлен → `training_ready=TRUE`
- Если получена обратная связь `feedback_type='incorrect'` и `correct_type` указан → `training_ready=TRUE`
- Если категория была исправлена через `category_corrections` → `training_ready=TRUE`

---

## Миграция данных

### Для существующих тикетов

Если уже есть тикеты в системе, можно:

1. **Импортировать данные из Jira:**
   - Если в Jira есть правильные категории, можно синхронизировать их в `actual_type`
   - Использовать API Jira для получения категорий тикетов

2. **Ручная разметка:**
   - Создать интерфейс для операторов для разметки старых тикетов
   - Приоритизировать тикеты с низким `confidence` или `decision='manual-review'`

3. **Постепенное накопление:**
   - Начать собирать данные с текущего момента
   - Постепенно накапливать достаточный объем для дообучения

---

## Выводы и рекомендации

### ✅ Что уже есть (достаточно для начала):

1. **Базовые данные для обучения:**
   - Текст обращений (`text`)
   - Метаданные (источник, приоритет, дата)
   - Результаты классификации (predicted_type, confidence, probabilities)

2. **Данные для анализа:**
   - Версия модели (`model_version`)
   - Решение системы (`decision`)
   - Временные метки

### ❌ Что критически необходимо добавить:

1. **Правильная категория (Ground Truth):**
   - `actual_type` - фактическая категория после обработки
   - Механизм установки категории оператором

2. **Обратная связь:**
   - Таблица `classification_feedback` или поля в `ticket_events`
   - API для получения обратной связи

3. **Отслеживание использования в обучении:**
   - `training_ready` - флаг готовности
   - `training_used_in_version` - в какой версии использован

### 📊 Рекомендуемый план действий:

**Фаза 1 (Быстрый старт - 1-2 недели):**
1. Добавить минимальные поля в `ticket_events` (Вариант 1)
2. Создать API endpoint для установки `actual_type`
3. Создать простой интерфейс для операторов

**Фаза 2 (Расширенное решение - 1 месяц):**
1. Создать таблицы `classification_feedback` и `category_corrections`
2. Интегрировать с Jira для получения обратной связи
3. Создать Dashboard для операторов
4. Автоматизировать установку `training_ready`

**Фаза 3 (Оптимизация - 2-3 месяца):**
1. Создать скрипты для подготовки данных для обучения
2. Настроить автоматическое дообучение модели
3. Мониторинг качества модели на новых данных

---

**Дата создания:** 2025-11-19  
**Версия документа:** 1.0

