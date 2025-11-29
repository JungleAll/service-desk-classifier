"""Конфигурация для Streamlit Dashboard"""

import os
from pathlib import Path

# Путь к корню проекта
BASE_DIR = Path(__file__).parent.parent.parent

# URL ML Service API
ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8001")

# URL Ingestion Service API
INGESTION_SERVICE_URL = os.getenv("INGESTION_SERVICE_URL", "http://localhost:8000")

# URL Config Service API
CONFIG_SERVICE_URL = os.getenv("CONFIG_SERVICE_URL", "http://localhost:8002")

# Режим работы Dashboard
# 'demo' - прямой вызов ML Service (быстро, без логирования в БД)
# 'production' - через Ingestion Service (с полным логированием в ticket_events)
DASHBOARD_MODE = os.getenv("DASHBOARD_MODE", "demo")  # demo | production

# Таймауты
API_TIMEOUT = 10  # секунды

# Настройки истории
MAX_HISTORY_SIZE = 20

# Цветовая схема
COLORS = {
    "primary": "#4A90E2",
    "success": "#2ECC71",
    "warning": "#F39C12",
    "error": "#E74C3C",
    "background": "#F8F9FA",
    "text": "#2C3E50",
    "border": "#E0E0E0"
}

# Mock данные для демонстрации
MOCK_CLASSIFICATION_RESULT = {
    "predicted_type": "Запрос на обслуживание",
    "confidence": 0.95,
    "probabilities": {
        "Запрос на обслуживание": 0.95,
        "Подзадача": 0.02,
        "HR: Увольнение": 0.01,
        "Заказ визиток": 0.01,
        "Изменение персональных данных": 0.01
    },
    "model_version": "v1.0",
    "decision": "auto-process"
}

MOCK_HISTORY = [
    {
        "id": "ticket_001",
        "text": "Не могу войти в корпоративную систему",
        "predicted_type": "Запрос на обслуживание",
        "confidence": 0.95,
        "decision": "auto-process",
        "timestamp": "2025-01-15 10:30:00"
    },
    {
        "id": "ticket_002",
        "text": "Увольнение Иванова И.И. с должности менеджера",
        "predicted_type": "HR: Увольнение",
        "confidence": 0.88,
        "decision": "auto-process",
        "timestamp": "2025-01-15 10:25:00"
    },
    {
        "id": "ticket_003",
        "text": "Заказать визитки для отдела продаж, 500 шт, белые",
        "predicted_type": "Заказ визиток",
        "confidence": 0.92,
        "decision": "auto-process",
        "timestamp": "2025-01-15 10:20:00"
    },
    {
        "id": "ticket_004",
        "text": "Согласование запроса на новую виртуальную машину",
        "predicted_type": "Заявка на согласование ВМ",
        "confidence": 0.65,
        "decision": "manual-review",
        "timestamp": "2025-01-15 10:15:00"
    },
    {
        "id": "ticket_005",
        "text": "Падает соединение с ВМ, статус недоступна",
        "predicted_type": "Запрос на обслуживание",
        "confidence": 0.78,
        "decision": "auto-process",
        "timestamp": "2025-01-15 10:10:00"
    },
    {
        "id": "ticket_006",
        "text": "Изменение персональных данных сотрудника",
        "predicted_type": "Изменение персональных данных",
        "confidence": 0.85,
        "decision": "auto-process",
        "timestamp": "2025-01-15 10:05:00"
    },
    {
        "id": "ticket_007",
        "text": "Заказ гостевого пропуска для посетителя",
        "predicted_type": "Заказ гостевого пропуска",
        "confidence": 0.91,
        "decision": "auto-process",
        "timestamp": "2025-01-15 10:00:00"
    },
    {
        "id": "ticket_008",
        "text": "Заявка на билет и проживание в командировку",
        "predicted_type": "Заявка на билет и проживание",
        "confidence": 0.73,
        "decision": "auto-process",
        "timestamp": "2025-01-15 09:55:00"
    },
    {
        "id": "ticket_009",
        "text": "Согласование VDI для нового сотрудника",
        "predicted_type": "Согласование VDI",
        "confidence": 0.68,
        "decision": "manual-review",
        "timestamp": "2025-01-15 09:50:00"
    },
    {
        "id": "ticket_010",
        "text": "Уведомление о плановых работах на сервере",
        "predicted_type": "Уведомление о работах",
        "confidence": 0.89,
        "decision": "auto-process",
        "timestamp": "2025-01-15 09:45:00"
    }
]

MOCK_METRICS = {
    "processed_today": 156,
    "auto_processed": 132,
    "auto_processed_percent": 84.6,
    "manual_review": 24,
    "manual_review_percent": 15.4,
    "avg_confidence": 0.82
}

