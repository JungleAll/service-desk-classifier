"""Модуль для отслеживания метрик недоступности соседних сервисов"""

import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from collections import deque
from threading import Lock
from shared.logger import configure_service_logging

logger = configure_service_logging("ingestion.metrics")

# Глобальные метрики
_metrics_lock = Lock()

# Счетчики недоступности
_unavailability_counts = {
    "config_service": 0,
    "postgresql": 0,
    "redis": 0
}

# Время последней недоступности
_last_unavailability = {
    "config_service": None,
    "postgresql": None,
    "redis": None
}

# История недоступности (последние 100 событий)
_unavailability_history = {
    "config_service": deque(maxlen=100),
    "postgresql": deque(maxlen=100),
    "redis": deque(maxlen=100)
}

# Время последней успешной проверки
_last_successful_check = {
    "config_service": None,
    "postgresql": None,
    "redis": None
}


def record_unavailability(service: str, error_message: Optional[str] = None):
    """
    Запись события недоступности сервиса
    
    Args:
        service: Имя сервиса ('config_service', 'postgresql', 'redis')
        error_message: Сообщение об ошибке (опционально)
    """
    with _metrics_lock:
        _unavailability_counts[service] = _unavailability_counts.get(service, 0) + 1
        _last_unavailability[service] = datetime.utcnow()
        
        # Добавление в историю
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": service,
            "error": error_message
        }
        if service not in _unavailability_history:
            _unavailability_history[service] = deque(maxlen=100)
        _unavailability_history[service].append(event)
        
        logger.warning(f"Зафиксирована недоступность {service}: {error_message or 'Unknown error'}")


def record_success(service: str):
    """
    Запись успешного подключения к сервису
    
    Args:
        service: Имя сервиса ('config_service', 'postgresql', 'redis')
    """
    with _metrics_lock:
        _last_successful_check[service] = datetime.utcnow()
        
        # Если сервис был недоступен, логируем восстановление
        if _last_unavailability.get(service):
            duration = (datetime.utcnow() - _last_unavailability[service]).total_seconds()
            logger.info(f"Сервис {service} восстановлен после {duration:.1f} секунд недоступности")
            _last_unavailability[service] = None


def get_metrics() -> Dict[str, Any]:
    """
    Получение всех метрик недоступности
    
    Returns:
        Словарь с метриками для каждого сервиса
    """
    with _metrics_lock:
        metrics = {}
        
        for service in ["config_service", "postgresql", "redis"]:
            count = _unavailability_counts.get(service, 0)
            last_unavailable = _last_unavailability.get(service)
            last_successful = _last_successful_check.get(service)
            history = list(_unavailability_history.get(service, []))
            
            # Вычисление времени с последней недоступности
            time_since_unavailable = None
            if last_unavailable:
                time_since_unavailable = (datetime.utcnow() - last_unavailable).total_seconds()
            
            # Вычисление времени с последней успешной проверки
            time_since_successful = None
            if last_successful:
                time_since_successful = (datetime.utcnow() - last_successful).total_seconds()
            
            # Статус доступности
            is_available = last_unavailable is None or (
                last_successful and 
                last_successful > last_unavailable
            )
            
            metrics[service] = {
                "total_unavailability_count": count,
                "is_available": is_available,
                "last_unavailable_at": last_unavailable.isoformat() if last_unavailable else None,
                "last_successful_check_at": last_successful.isoformat() if last_successful else None,
                "time_since_unavailable_seconds": time_since_unavailable,
                "time_since_successful_seconds": time_since_successful,
                "recent_events_count": len(history),
                "recent_events": history[-10:] if history else []  # Последние 10 событий
            }
        
        return metrics


def get_service_status(service: str) -> Dict[str, Any]:
    """
    Получение статуса конкретного сервиса
    
    Args:
        service: Имя сервиса ('config_service', 'postgresql', 'redis')
        
    Returns:
        Словарь со статусом сервиса
    """
    metrics = get_metrics()
    return metrics.get(service, {})


def reset_metrics():
    """Сброс всех метрик (для тестирования)"""
    global _unavailability_counts, _last_unavailability, _unavailability_history, _last_successful_check
    
    with _metrics_lock:
        _unavailability_counts = {
            "config_service": 0,
            "postgresql": 0,
            "redis": 0
        }
        _last_unavailability = {
            "config_service": None,
            "postgresql": None,
            "redis": None
        }
        _unavailability_history = {
            "config_service": deque(maxlen=100),
            "postgresql": deque(maxlen=100),
            "redis": deque(maxlen=100)
        }
        _last_successful_check = {
            "config_service": None,
            "postgresql": None,
            "redis": None
        }
        
        logger.info("Метрики недоступности сброшены")

