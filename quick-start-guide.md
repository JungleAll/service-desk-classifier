# Быстрый старт: обучение модели (15 минут)

Если нужно быстро обучить модель с минимумом теории, используйте этот скрипт.

> **Примечание:** обучающие данные (`data/service_desk_train.csv`) не включены в репозиторий. Подготовьте CSV с колонками `Тема`, `Тип задачи` и при необходимости `Пользовательское поле (Активность)`.

## Шаг 1: Скопируйте готовый скрипт обучения

Создайте файл `train_quick.py` в корне проекта:

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Быстрый скрипт для обучения модели Service Desk Classifier
Использует все в одном файле для простоты
"""

import pandas as pd
import numpy as np
import re
import pymorphy2
from nltk.corpus import stopwords
import nltk
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.preprocessing import LabelEncoder
import joblib
import json
import os
from datetime import datetime

# === ЗАГРУЗКА ДАННЫХ ===
print("\n" + "="*80)
print("ЗАГРУЗКА ДАННЫХ")
print("="*80)

train_df = pd.read_csv('data/service_desk_train.csv', sep=';', encoding='utf-8')
print(f"Загружено {len(train_df)} записей")
print(f"  Категории: {train_df['Тип задачи'].nunique()}")

# === ЗАГРУЗКА СТОП-СЛОВ ===
try:
    stopwords.words('russian')
except:
    nltk.download('stopwords', quiet=True)

russian_stopwords = set(stopwords.words('russian'))
morph = pymorphy2.MorphAnalyzer()

# === ФУНКЦИЯ ДЛЯ ОЧИСТКИ ТЕКСТА ===
def clean_and_lemmatize(text):
    """Быстрая очистка и лемматизация текста"""
    if pd.isna(text):
        return ""
    
    text = str(text).lower()
    text = re.sub(r'[^а-яёa-z\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    words = []
    for word in text.split():
        if word not in russian_stopwords and len(word) > 2:
            lemma = morph.parse(word)[0].normal_form
            words.append(lemma)
    
    return ' '.join(words)

# === ПРЕДОБРАБОТКА ===
print("\n" + "="*80)
print("ПРЕДОБРАБОТКА ТЕКСТОВ")
print("="*80)

train_df['text'] = (
    train_df['Тема'].fillna('') + ' ' + 
    train_df.get('Пользовательское поле (Активность)', '').fillna('')
)

print("Обработка текстов...")
train_df['text_clean'] = train_df['text'].apply(clean_and_lemmatize)
print("Готово")

# === КОДИРОВАНИЕ ЦЕЛЕВОЙ ПЕРЕМЕННОЙ ===
print("\n" + "="*80)
print("КОДИРОВАНИЕ КАТЕГОРИЙ")
print("="*80)

le = LabelEncoder()
train_df['target'] = le.fit_transform(train_df['Тип задачи'])

print(f"Обнаружено {len(le.classes_)} категорий:")
for i, cls in enumerate(le.classes_):
    count = (train_df['target'] == i).sum()
    print(f"  {i}: {cls} ({count} записей)")

# === TF-IDF ВЕКТОРИЗАЦИЯ ===
print("\n" + "="*80)
print("TF-IDF ВЕКТОРИЗАЦИЯ")
print("="*80)

vectorizer = TfidfVectorizer(
    max_features=8000,
    ngram_range=(1, 2),
    min_df=2,
    max_df=0.9,
    sublinear_tf=True
)

X = vectorizer.fit_transform(train_df['text_clean'])
y = train_df['target'].values

print(f"Матрица признаков: {X.shape}")

# === РАЗДЕЛЕНИЕ НА TRAIN/VAL ===
print("\n" + "="*80)
print("РАЗДЕЛЕНИЕ ДАННЫХ")
print("="*80)

X_train, X_val, y_train, y_val = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

print(f"Train: {X_train.shape[0]} примеров")
print(f"Validation: {X_val.shape[0]} примеров")

# === ОБУЧЕНИЕ МОДЕЛИ ===
print("\n" + "="*80)
print("ОБУЧЕНИЕ МОДЕЛИ")
print("="*80)
print("Обучение (может занять 1-2 минуты)...")

clf = LogisticRegression(
    C=1.0,
    max_iter=1000,
    multi_class='multinomial',
    solver='lbfgs',
    random_state=42,
    n_jobs=-1,
    verbose=0
)

clf.fit(X_train, y_train)
print("Готово")

# === ОЦЕНКА ===
print("\n" + "="*80)
print("РЕЗУЛЬТАТЫ")
print("="*80)

y_train_pred = clf.predict(X_train)
y_val_pred = clf.predict(X_val)

train_acc = accuracy_score(y_train, y_train_pred)
val_acc = accuracy_score(y_val, y_val_pred)
val_f1 = f1_score(y_val, y_val_pred, average='weighted', zero_division=0)

print(f"\nACCURACY:")
print(f"  Train: {train_acc:.4f} ({train_acc*100:.2f}%)")
print(f"  Validation: {val_acc:.4f} ({val_acc*100:.2f}%)")

print(f"\nF1-SCORE: {val_f1:.4f}")

print(f"\nДЕТАЛЬНЫЙ ОТЧЕТ:")
print(classification_report(
    y_val, y_val_pred,
    target_names=le.classes_,
    zero_division=0
))

# === СОХРАНЕНИЕ ===
print("\n" + "="*80)
print("СОХРАНЕНИЕ МОДЕЛИ")
print("="*80)

os.makedirs('models/v1.0', exist_ok=True)

joblib.dump(clf, 'models/v1.0/classifier.pkl')
joblib.dump(vectorizer, 'models/v1.0/vectorizer.pkl')
joblib.dump(le, 'models/v1.0/label_encoder.pkl')

config = {
    'model_type': 'LogisticRegression',
    'train_accuracy': float(train_acc),
    'val_accuracy': float(val_acc),
    'val_f1_score': float(val_f1),
    'num_classes': len(le.classes_),
    'num_features': X.shape[1],
    'classes': le.classes_.tolist(),
    'trained_at': datetime.now().isoformat()
}

with open('models/v1.0/config.json', 'w', encoding='utf-8') as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print("classifier.pkl")
print("vectorizer.pkl")
print("label_encoder.pkl")
print("config.json")

print("\n" + "="*80)
print("УСПЕШНО")
print("="*80)
print("\nМодель готова к использованию.\n")
```

## Шаг 2: Запустите скрипт

```bash
# Убедитесь, что активировано виртуальное окружение
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows

# Запустите скрипт
python train_quick.py
```

## Что произойдет

1. Загрузятся ваши данные
2. Очистятся и обработаются тексты (~1 минута)
3. Обучится модель (~1-2 минуты)
4. Выведутся результаты (Accuracy, F1)
5. Сохранятся все файлы в `models/v1.0/`

## Ожидаемый результат

```
================================================================================
ЗАГРУЗКА ДАННЫХ
================================================================================
Загружено 10000 записей
  Категории: 12

================================================================================
РЕЗУЛЬТАТЫ
================================================================================

ACCURACY:
  Train: 0.8945 (89.45%)
  Validation: 0.8723 (87.23%)

F1-SCORE: 0.8701

================================================================================
УСПЕШНО
================================================================================

Модель готова к использованию.
```

## Если accuracy низкий (< 80%)

Попробуйте:

1. **Увеличить max_features**
   ```python
   TfidfVectorizer(max_features=15000, ...)
   ```

2. **Использовать другой solver**
   ```python
   LogisticRegression(solver='saga', ...)
   ```

3. **Увеличить max_iter**
   ```python
   LogisticRegression(max_iter=2000, ...)
   ```

## Что дальше?

Когда модель обучена:

1. Запустите платформу через `docker compose up -d` (см. [startup-guide.md](startup-guide.md))
2. Проверьте классификацию через Dashboard или `POST /classify`
3. Для production-пайплайна включите Worker: `WORKER_ENABLED=true`
