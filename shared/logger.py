"""
Централизованный модуль логирования для всех сервисов

Поддерживает:
- JSON формат для интеграции с ElasticSearch
- Файловый вывод с ротацией
- Стандартный stdout вывод для совместимости
- Структурированное логирование с метаданными
"""

import logging
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler
import sys


class JSONFormatter(logging.Formatter):
    """Форматтер для вывода логов в JSON формате (для ElasticSearch)"""
    
    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name
    
    def format(self, record: logging.LogRecord) -> str:
        """Форматирование записи лога в JSON"""
        log_data = {
            "@timestamp": datetime.utcnow().isoformat() + "Z",
            "service": self.service_name,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Добавление дополнительных полей, если они есть
        if hasattr(record, "ticket_id"):
            log_data["ticket_id"] = record.ticket_id
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        
        # Добавление exception info, если есть
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            log_data["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        
        # Добавление stack trace для DEBUG уровня
        if record.levelno == logging.DEBUG and hasattr(record, "stack_info") and record.stack_info:
            log_data["stack_trace"] = record.stack_info
        
        return json.dumps(log_data, ensure_ascii=False)


class StandardFormatter(logging.Formatter):
    """Стандартный форматтер для вывода в stdout (человекочитаемый формат)"""
    
    def __init__(self):
        super().__init__(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )


def setup_logging(
    service_name: str,
    log_level: Optional[str] = None,
    log_dir: Optional[str] = None,
    enable_file_logging: bool = True,
    enable_json_logging: bool = True,
    enable_stdout_logging: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Настройка логирования для сервиса
    
    Args:
        service_name: Имя сервиса (например, 'ingestion', 'ml', 'config', 'output')
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Директория для сохранения логов (по умолчанию ./logs)
        enable_file_logging: Включить сохранение логов в файлы
        enable_json_logging: Включить JSON формат для файлов (для ElasticSearch)
        enable_stdout_logging: Включить вывод в stdout (стандартный формат)
        max_bytes: Максимальный размер файла лога перед ротацией
        backup_count: Количество резервных файлов логов
        
    Returns:
        Настроенный logger
    """
    # Определение уровня логирования
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    level = getattr(logging, log_level, logging.INFO)
    
    # Создание logger
    logger = logging.getLogger(service_name)
    logger.setLevel(level)
    
    # Очистка существующих handlers
    logger.handlers.clear()
    
    # Настройка stdout handler (стандартный формат)
    if enable_stdout_logging:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(level)
        stdout_handler.setFormatter(StandardFormatter())
        logger.addHandler(stdout_handler)
    
    # Настройка файлового логирования
    if enable_file_logging:
        try:
            # Определение директории для логов
            if log_dir is None:
                log_dir = os.getenv("LOG_DIR", "./logs")
            
            log_path = Path(log_dir)
            # Создание директории с обработкой ошибок
            try:
                log_path.mkdir(parents=True, exist_ok=True)
            except PermissionError as e:
                # Если нет прав на создание директории, логируем в stdout и продолжаем без файлового логирования
                print(f"WARNING: Не удалось создать директорию для логов {log_path}: {e}. Файловое логирование отключено.", file=sys.stderr)
                enable_file_logging = False
            except Exception as e:
                print(f"WARNING: Ошибка при создании директории для логов {log_path}: {e}. Файловое логирование отключено.", file=sys.stderr)
                enable_file_logging = False
            
            if enable_file_logging:
                # Путь к файлу лога
                log_file = log_path / f"{service_name}.log"
                
                try:
                    # Создание rotating file handler
                    file_handler = RotatingFileHandler(
                        log_file,
                        maxBytes=max_bytes,
                        backupCount=backup_count,
                        encoding='utf-8'
                    )
                    file_handler.setLevel(level)
                    
                    # Выбор формата для файла
                    if enable_json_logging:
                        file_handler.setFormatter(JSONFormatter(service_name))
                    else:
                        file_handler.setFormatter(StandardFormatter())
                    
                    logger.addHandler(file_handler)
                    # Логируем успешное создание файлового handler (только в stdout, чтобы не было циклической зависимости)
                    print(f"INFO: Файловое логирование включено для {service_name}: {log_file}", file=sys.stdout)
                except PermissionError as e:
                    print(f"WARNING: Не удалось создать файл лога {log_file}: {e}. Файловое логирование отключено.", file=sys.stderr)
                except Exception as e:
                    print(f"WARNING: Ошибка при создании файла лога {log_file}: {e}. Файловое логирование отключено.", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: Критическая ошибка при настройке файлового логирования: {e}. Продолжаем только с stdout логированием.", file=sys.stderr)
    
    # Предотвращение распространения логов на root logger
    logger.propagate = False
    
    return logger


def get_logger(service_name: Optional[str] = None) -> logging.Logger:
    """
    Получение logger для сервиса
    
    Args:
        service_name: Имя сервиса. Если не указано, используется имя модуля
        
    Returns:
        Logger
    """
    if service_name:
        return logging.getLogger(service_name)
    else:
        # Используем имя вызывающего модуля
        import inspect
        frame = inspect.currentframe().f_back
        module_name = frame.f_globals.get('__name__', 'root')
        return logging.getLogger(module_name)


# Глобальная настройка для всех сервисов
def configure_service_logging(service_name: str) -> logging.Logger:
    """
    Удобная функция для настройки логирования сервиса
    
    Использует переменные окружения:
    - LOG_LEVEL: уровень логирования (default: INFO)
    - LOG_DIR: директория для логов (default: ./logs)
    - LOG_ENABLE_FILE: включить файловое логирование (default: true)
    - LOG_ENABLE_JSON: включить JSON формат (default: true)
    - LOG_ENABLE_STDOUT: включить stdout вывод (default: true)
    - LOG_MAX_BYTES: максимальный размер файла (default: 10485760 = 10MB)
    - LOG_BACKUP_COUNT: количество резервных файлов (default: 5)
    
    Args:
        service_name: Имя сервиса
        
    Returns:
        Настроенный logger
    """
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_dir = os.getenv("LOG_DIR", "./logs")
    enable_file = os.getenv("LOG_ENABLE_FILE", "true").lower() == "true"
    enable_json = os.getenv("LOG_ENABLE_JSON", "true").lower() == "true"
    enable_stdout = os.getenv("LOG_ENABLE_STDOUT", "true").lower() == "true"
    
    try:
        max_bytes = int(os.getenv("LOG_MAX_BYTES", "10485760"))
    except ValueError:
        max_bytes = 10 * 1024 * 1024
    
    try:
        backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    except ValueError:
        backup_count = 5
    
    return setup_logging(
        service_name=service_name,
        log_level=log_level,
        log_dir=log_dir,
        enable_file_logging=enable_file,
        enable_json_logging=enable_json,
        enable_stdout_logging=enable_stdout,
        max_bytes=max_bytes,
        backup_count=backup_count
    )


