"""Конфигурация ML Service для классификации обращений Service Desk"""

import os
from pathlib import Path
from typing import Optional

# Базовые пути
BASE_DIR = Path(__file__).parent.parent
MODELS_DIR = BASE_DIR / "models" / "v1.0"

# Версия модели
MODEL_VERSION = "v1.0"

# Пути к файлам модели
# По умолчанию используем стабильную версию classifier_smote_new.pkl
# Можно переключиться на другую версию через переменные окружения:
# ML_CLASSIFIER_FILE, ML_VECTORIZER_FILE, ML_LABEL_ENCODER_FILE
CLASSIFIER_FILE = os.getenv("ML_CLASSIFIER_FILE", "classifier_smote_new.pkl")
VECTORIZER_FILE = os.getenv("ML_VECTORIZER_FILE", "vectorizer_smote.pkl")
LABEL_ENCODER_FILE = os.getenv("ML_LABEL_ENCODER_FILE", "label_encoder_smote.pkl")

CLASSIFIER_PATH = MODELS_DIR / CLASSIFIER_FILE
VECTORIZER_PATH = MODELS_DIR / VECTORIZER_FILE
LABEL_ENCODER_PATH = MODELS_DIR / LABEL_ENCODER_FILE
CONFIG_JSON_PATH = MODELS_DIR / "config.json"

# Настройки API
API_HOST = os.getenv("ML_SERVICE_HOST", "0.0.0.0")
API_PORT = int(os.getenv("ML_SERVICE_PORT", "8001"))
API_RELOAD = os.getenv("API_RELOAD", "false").lower() == "true"

# Настройки классификации
CONFIDENCE_THRESHOLD = 0.7  # Порог для auto-process

# Настройки логирования
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Минимальная длина текста для классификации
MIN_TEXT_LENGTH = 3

# Настройки Worker (асинхронная обработка очереди Redis)
WORKER_ENABLED = os.getenv("WORKER_ENABLED", "false").lower() == "true"  # Включить/выключить worker
WORKER_QUEUE_TIMEOUT = int(os.getenv("WORKER_QUEUE_TIMEOUT", "5"))  # Таймаут ожидания тикета из очереди (секунды)
WORKER_DELAY = float(os.getenv("WORKER_DELAY", "0.1"))  # Задержка между итерациями цикла (секунды)

