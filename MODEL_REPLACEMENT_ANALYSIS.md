# Анализ возможности замены модели на OpenSource версию

**Дата анализа:** 2025-11-19  
**Версия системы:** 1.0  
**Цель:** Оценка возможности замены собственной модели обучения на готовую OpenSource модель без изменения кода

---

## Текущая архитектура модели

### Используемые технологии

1. **Фреймворк ML:** scikit-learn 1.7.2
2. **Тип модели:** LogisticRegression (линейная классификация)
3. **Векторизация:** TfidfVectorizer (TF-IDF)
4. **Препроцессор:** 
   - pymorphy3 (морфологический анализ для русского языка)
   - nltk (стоп-слова)
   - Кастомная очистка текста
5. **Формат хранения:** joblib (pickle файлы)
6. **Классы:** 17 категорий обращений Service Desk

### Структура модели

```
models/v1.0/
├── classifier_smote_new.pkl      # Обученный классификатор
├── vectorizer_smote.pkl           # TF-IDF векторизатор
├── label_encoder_smote.pkl        # Кодировщик меток классов
├── config.json                    # Метаданные модели
└── preprocessing_metadata.json    # Метаданные препроцессора
```

### Интерфейс модели

Класс `ServiceDeskClassifier` предоставляет:
- `load_model()` - загрузка модели из файлов
- `predict(text)` - классификация текста
- `get_model_info()` - информация о модели
- `reload_model()` - hot reload модели

---

## Анализ возможности замены

### ✅ ПЛЮСЫ текущей архитектуры для замены

1. **Абстракция через класс**
   - Модель инкапсулирована в класс `ServiceDeskClassifier`
   - Интерфейс `predict()` не зависит от внутренней реализации
   - Можно заменить внутреннюю логику без изменения API

2. **Версионирование моделей**
   - Поддержка через переменные окружения (`ML_MODEL_VERSION`)
   - Хранение путей в БД (`model_versions` таблица)
   - Hot reload без перезапуска сервиса

3. **Разделение компонентов**
   - Препроцессор отделен (`TextPreprocessor`)
   - Векторизатор отделен
   - Классификатор отделен
   - Можно заменить любой компонент независимо

4. **Стандартные форматы**
   - Использование joblib (стандарт для sklearn)
   - JSON для конфигурации
   - Совместимость с экосистемой Python ML

---

## Варианты замены на OpenSource модели

### Вариант 1: Замена на другую sklearn модель

**Подходит для:**
- Другие алгоритмы sklearn (SVM, RandomForest, XGBoost)
- Предобученные sklearn модели из библиотек

**Требования:**
1. ✅ **Минимальные изменения** - только замена файла классификатора
2. ✅ **Совместимость** - sklearn модели используют тот же интерфейс
3. ✅ **Формат** - joblib поддерживается напрямую

**Что нужно:**
- Обученная модель в формате joblib
- Совместимый векторизатор (или переобучение)
- Обновление `label_encoder` если изменились классы

**Пример интеграции:**
```python
# В classifier.py - минимальные изменения
# Вместо:
self.classifier = joblib.load(classifier_path)

# Можно использовать любую sklearn модель:
from sklearn.ensemble import RandomForestClassifier
self.classifier = joblib.load(classifier_path)  # Работает без изменений!
```

**Оценка сложности:** ⭐ (Очень легко)

---

### Вариант 2: Замена на Transformer модели (BERT, RoBERTa)

**Подходит для:**
- Предобученные модели для русского языка:
  - `rubert-base` (DeepPavlov)
  - `cointegrated/rubert-tiny`
  - `sberbank-ai/ruBert-base`
  - `ai-forever/ruBert-base`

**Требования:**
1. ⚠️ **Средние изменения** - нужен адаптер для интерфейса
2. ⚠️ **Дополнительные зависимости** - transformers, torch/tensorflow
3. ⚠️ **Препроцессор** - токенизация через tokenizer модели
4. ⚠️ **Векторизация** - эмбеддинги вместо TF-IDF

**Что нужно:**

1. **Установка зависимостей:**
```python
# requirements.txt
transformers==4.35.0
torch==2.1.0  # или tensorflow
sentencepiece==0.1.99  # для некоторых моделей
```

2. **Адаптер для интерфейса:**
```python
# Новый класс-обертка для transformer модели
class TransformerClassifier:
    def __init__(self, model_name="cointegrated/rubert-tiny"):
        from transformers import AutoTokenizer, AutoModel
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.classifier_head = None  # Нужен fine-tuned классификатор
    
    def predict(self, text):
        # Токенизация
        inputs = self.tokenizer(text, return_tensors="pt", padding=True, truncation=True)
        # Получение эмбеддингов
        outputs = self.model(**inputs)
        # Классификация через head
        logits = self.classifier_head(outputs.pooler_output)
        return logits
```

3. **Изменения в ServiceDeskClassifier:**
   - Заменить загрузку классификатора
   - Адаптировать метод `predict()` для работы с эмбеддингами
   - Обновить препроцессор (возможно не нужен для BERT)

**Оценка сложности:** ⭐⭐⭐ (Средняя сложность)

**Преимущества:**
- Лучшее качество на русском языке
- Контекстное понимание текста
- Предобученные на больших корпусах

**Недостатки:**
- Больше зависимостей
- Больше памяти (модели 100-500MB)
- Медленнее инференс (но можно оптимизировать)

---

### Вариант 3: Замена на готовые библиотеки классификации

**Подходит для:**
- `fasttext` (Facebook) - быстрая классификация текста
- `spacy` с обученными моделями
- `flair` (NLP библиотека)

**Пример с FastText:**

**Требования:**
1. ⚠️ **Средние изменения** - другой формат модели
2. ✅ **Простота** - FastText очень прост в использовании
3. ✅ **Скорость** - очень быстрый инференс

**Что нужно:**

1. **Установка:**
```python
# requirements.txt
fasttext==0.9.2
```

2. **Адаптер:**
```python
import fasttext

class FastTextClassifier:
    def __init__(self, model_path):
        self.model = fasttext.load_model(model_path)
    
    def predict(self, text, k=1):
        labels, scores = self.model.predict(text, k=k)
        return labels[0].replace('__label__', ''), scores[0]
```

3. **Изменения:**
   - Заменить загрузку в `load_model()`
   - Адаптировать `predict()` для формата FastText
   - Возможно убрать препроцессор (FastText работает с сырым текстом)

**Оценка сложности:** ⭐⭐ (Легко)

---

### Вариант 4: Использование предобученных моделей из HuggingFace

**Подходит для:**
- Fine-tuned модели для классификации текста на русском
- Модели из HuggingFace Model Hub

**Примеры моделей:**

1. **Для русского языка (HuggingFace):**
   - `cointegrated/rubert-tiny2-classifier` - легкая модель (29MB)
   - `ai-forever/ruBert-base-classifier` - базовая модель (700MB)
   - `DeepPavlov/rubert-base-cased` - популярная модель
   - `sberbank-ai/ruBert-base` - модель от Сбербанка
   - `cointegrated/rubert-tiny` - очень легкая (29MB)

2. **FastText предобученные:**
   - `cc.ru.300.bin` - векторы для русского языка
   - Можно обучить свою модель на данных

3. **Sklearn совместимые:**
   - Любые модели из scikit-learn
   - XGBoost, LightGBM (через sklearn интерфейс)
   - Можно использовать предобученные модели из MLflow

**Требования:**
1. ⚠️ **Средние изменения** - нужен адаптер
2. ⚠️ **Зависимости** - transformers, torch
3. ✅ **Готовые решения** - модели уже обучены

**Что нужно:**

1. **Установка:**
```python
# requirements.txt
transformers==4.35.0
torch==2.1.0
```

2. **Интеграция:**
```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification

class HuggingFaceClassifier:
    def __init__(self, model_name):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.id2label = self.model.config.id2label
    
    def predict(self, text):
        inputs = self.tokenizer(text, return_tensors="pt", padding=True, truncation=True)
        outputs = self.model(**inputs)
        probs = torch.softmax(outputs.logits, dim=-1)
        predicted_id = torch.argmax(probs, dim=-1).item()
        confidence = probs[0][predicted_id].item()
        label = self.id2label[predicted_id]
        return label, confidence
```

**Оценка сложности:** ⭐⭐⭐ (Средняя сложность)

---

## Сравнительная таблица вариантов

| Вариант | Сложность | Качество | Скорость | Память | Зависимости |
|---------|-----------|----------|----------|--------|-------------|
| **Sklearn (текущий)** | ⭐ | Хорошее | ⚡⚡⚡ | Низкая | Минимальные |
| **Другая sklearn модель** | ⭐ | Хорошее | ⚡⚡⚡ | Низкая | Минимальные |
| **FastText** | ⭐⭐ | Среднее | ⚡⚡⚡⚡ | Низкая | Минимальные |
| **Transformer (BERT)** | ⭐⭐⭐ | Отличное | ⚡⚡ | Высокая | Большие |
| **HuggingFace готовые** | ⭐⭐⭐ | Отличное | ⚡⚡ | Высокая | Большие |

---

## Что потребуется для замены

### Минимальный вариант (sklearn модель)

**Изменения в коде:** Минимальные (только замена файла)

1. ✅ **Обучение новой модели** в формате sklearn
2. ✅ **Сохранение через joblib** в тот же формат
3. ✅ **Замена файлов** в `models/v1.0/`
4. ✅ **Обновление config.json** (если нужно)

**Время:** 1-2 часа

---

### Средний вариант (FastText или другая библиотека)

**Изменения в коде:** Умеренные (адаптер для интерфейса)

1. ⚠️ **Добавление зависимостей** в `requirements.txt`
2. ⚠️ **Создание адаптера** в `classifier.py`
3. ⚠️ **Обновление метода `predict()`**
4. ⚠️ **Тестирование совместимости**
5. ✅ **Обновление Dockerfile** (если нужно)

**Время:** 4-8 часов

---

### Сложный вариант (Transformer модели)

**Изменения в коде:** Значительные (рефакторинг компонентов)

1. ⚠️ **Добавление зависимостей** (transformers, torch)
2. ⚠️ **Создание нового класса** для transformer модели
3. ⚠️ **Рефакторинг `ServiceDeskClassifier`** для поддержки разных типов
4. ⚠️ **Обновление препроцессора** (токенизация вместо лемматизации)
5. ⚠️ **Обновление векторизации** (эмбеддинги вместо TF-IDF)
6. ⚠️ **Обновление Dockerfile** (больше памяти, GPU опционально)
7. ⚠️ **Тестирование производительности**
8. ⚠️ **Оптимизация** (квантизация, ONNX конвертация)

**Время:** 2-5 дней

---

## Рекомендации по интеграции

### Подход 1: Плагинная архитектура (рекомендуется)

Создать абстракцию для разных типов моделей:

```python
# ml_service/model_adapters/base.py
class BaseModelAdapter:
    def load(self, model_path: str) -> bool:
        raise NotImplementedError
    
    def predict(self, text: str) -> Dict:
        raise NotImplementedError

# ml_service/model_adapters/sklearn_adapter.py
class SklearnAdapter(BaseModelAdapter):
    # Текущая реализация

# ml_service/model_adapters/transformer_adapter.py
class TransformerAdapter(BaseModelAdapter):
    # Новая реализация для BERT

# ml_service/classifier.py
class ServiceDeskClassifier:
    def __init__(self):
        model_type = os.getenv("ML_MODEL_TYPE", "sklearn")
        if model_type == "sklearn":
            self.adapter = SklearnAdapter()
        elif model_type == "transformer":
            self.adapter = TransformerAdapter()
        # ...
```

**Преимущества:**
- ✅ Легко добавлять новые типы моделей
- ✅ Не ломает существующий код
- ✅ Можно переключаться через переменные окружения

---

### Подход 2: Обертка (wrapper)

Создать обертку для любой модели, которая предоставляет единый интерфейс:

```python
class ModelWrapper:
    def __init__(self, model, vectorizer=None, preprocessor=None):
        self.model = model
        self.vectorizer = vectorizer
        self.preprocessor = preprocessor
    
    def predict(self, text):
        # Универсальная логика для любой модели
        if self.preprocessor:
            text = self.preprocessor(text)
        if self.vectorizer:
            text = self.vectorizer(text)
        return self.model.predict(text)
```

---

## Специфические требования для русского языка

### Текущий препроцессор

Использует:
- `pymorphy3` - морфологический анализ
- `nltk` - стоп-слова
- Кастомная очистка (email, URL, числа)

### Для OpenSource моделей

1. **Transformer модели (BERT):**
   - ✅ Уже обучены на русском языке
   - ✅ Не требуют лемматизации (работают с токенами)
   - ⚠️ Нужен tokenizer для русского языка

2. **FastText:**
   - ✅ Поддерживает русский язык
   - ✅ Работает с сырым текстом
   - ✅ Может использовать предобученные векторы

3. **Sklearn модели:**
   - ⚠️ Требуют препроцессор (можно использовать текущий)
   - ⚠️ Нужны обучающие данные на русском

---

## Оценка совместимости

### ✅ Что работает без изменений

1. **API интерфейс** - `predict(text)` остается тем же
2. **Версионирование** - механизм через переменные окружения
3. **Hot reload** - `reload_model()` работает для любой модели
4. **Кэширование** - Redis кэш не зависит от типа модели
5. **Метрики** - логирование в БД работает одинаково

### ⚠️ Что может потребовать изменений

1. **Препроцессор** - разные модели требуют разной обработки
2. **Векторизация** - TF-IDF vs эмбеддинги
3. **Формат файлов** - joblib vs другие форматы
4. **Память** - transformer модели требуют больше RAM
5. **Производительность** - разная скорость инференса

---

## Практические шаги для замены

### Шаг 1: Выбор модели

1. Определить требования:
   - Качество классификации
   - Скорость инференса
   - Доступные ресурсы (память, CPU/GPU)
   - Бюджет на зависимости

2. Исследовать доступные модели:
   - HuggingFace Model Hub
   - GitHub репозитории
   - Научные статьи

### Шаг 2: Подготовка адаптера

1. Создать класс-адаптер для новой модели
2. Реализовать интерфейс `predict(text) -> Dict`
3. Обеспечить совместимость формата ответа

### Шаг 3: Интеграция

1. Добавить зависимость в `requirements.txt`
2. Обновить `ServiceDeskClassifier` для поддержки нового типа
3. Добавить переменную окружения для выбора типа модели

### Шаг 4: Тестирование

1. Unit тесты для нового адаптера
2. Интеграционные тесты
3. Тесты производительности
4. A/B тестирование (старая vs новая модель)

### Шаг 5: Развертывание

1. Обновить Dockerfile (если нужно)
2. Обновить docker-compose.yml
3. Развернуть новую версию
4. Мониторинг метрик

---

## Выводы

### ✅ Замена возможна

Текущая архитектура **хорошо подходит** для замены модели:
- Абстракция через класс
- Версионирование моделей
- Разделение компонентов
- Стандартные интерфейсы

### 📊 Рекомендации

1. **Для быстрой замены:** Использовать другую sklearn модель (сложность ⭐)
2. **Для улучшения качества:** Transformer модель (BERT) (сложность ⭐⭐⭐)
3. **Для баланса:** FastText (сложность ⭐⭐)

### 🎯 Оптимальный подход

**Плагинная архитектура** с адаптерами:
- Минимальные изменения в существующем коде
- Легко добавлять новые типы моделей
- Можно переключаться через конфигурацию
- Не ломает обратную совместимость

---

## Конкретные примеры OpenSource моделей для русского языка

### 1. Transformer модели (BERT-based)

#### cointegrated/rubert-tiny2-classifier
- **Размер:** ~29MB
- **Скорость:** Быстрая
- **Качество:** Хорошее для легкой модели
- **Использование:**
```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification

model_name = "cointegrated/rubert-tiny2-classifier"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name)
```

#### ai-forever/ruBert-base
- **Размер:** ~700MB
- **Скорость:** Средняя
- **Качество:** Отличное
- **Особенность:** Обучена на больших корпусах русского языка

#### DeepPavlov/rubert-base-cased
- **Размер:** ~700MB
- **Скорость:** Средняя
- **Качество:** Отличное
- **Особенность:** Популярная модель от DeepPavlov

### 2. FastText

#### Предобученные векторы
- **cc.ru.300.bin** - 300-мерные векторы для русского языка
- **Размер:** ~2GB
- **Использование:** Для получения эмбеддингов слов

#### Обучение своей модели
```python
import fasttext

# Обучение на данных
model = fasttext.train_supervised(
    input="train.txt",
    lr=0.1,
    epoch=25,
    wordNgrams=2
)

# Сохранение
model.save_model("model.bin")
```

### 3. Sklearn совместимые модели

#### XGBoost
```python
from xgboost import XGBClassifier
import joblib

# Обучение
model = XGBClassifier()
model.fit(X_train, y_train)

# Сохранение (совместимо с joblib)
joblib.dump(model, "xgb_classifier.pkl")
```

#### LightGBM
```python
from lightgbm import LGBMClassifier
import joblib

# Обучение
model = LGBMClassifier()
model.fit(X_train, y_train)

# Сохранение
joblib.dump(model, "lgbm_classifier.pkl")
```

### 4. Готовые решения для классификации текста

#### Flair (NLP библиотека)
```python
from flair.models import TextClassifier
from flair.data import Sentence

# Загрузка предобученной модели
classifier = TextClassifier.load('sentiment')

# Классификация
sentence = Sentence('Текст для классификации')
classifier.predict(sentence)
```

#### spaCy с обученными моделями
```python
import spacy

# Загрузка русской модели
nlp = spacy.load("ru_core_news_lg")

# Можно добавить кастомный классификатор
```

---

## Сравнение конкретных моделей

| Модель | Размер | Скорость | Качество | Сложность интеграции |
|--------|--------|----------|----------|----------------------|
| **LogisticRegression (текущая)** | ~1MB | ⚡⚡⚡ | 97.49% | ⭐ |
| **rubert-tiny2** | 29MB | ⚡⚡⚡ | ~95-97% | ⭐⭐⭐ |
| **ruBert-base** | 700MB | ⚡⚡ | ~98-99% | ⭐⭐⭐ |
| **FastText** | 2-50MB | ⚡⚡⚡⚡ | ~90-95% | ⭐⭐ |
| **XGBoost** | ~5MB | ⚡⚡⚡ | ~96-98% | ⭐ |
| **LightGBM** | ~3MB | ⚡⚡⚡ | ~96-98% | ⭐ |

---

**Дата создания:** 2025-11-19  
**Версия документа:** 1.0

