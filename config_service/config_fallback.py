"""Модуль для работы с файлом конфигурации (fallback при недоступности PostgreSQL)"""

import os
import json
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from shared.logger import configure_service_logging

logger = configure_service_logging("config.fallback")

# Путь к файлу конфигурации
CONFIG_FILE_DIR = Path(os.getenv("CONFIG_FALLBACK_DIR", "./config_cache"))
CONFIG_FILE_PATH = CONFIG_FILE_DIR / "config_fallback.json"
CONFIG_LOCK = threading.Lock()


def ensure_config_dir():
    """Создание директории для файла конфигурации, если не существует"""
    try:
        CONFIG_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Ошибка при создании директории для fallback конфигурации: {e}")


def _parse_config_value(value: str) -> Any:
    """Парсинг значения конфигурации с преобразованием типов"""
    if isinstance(value, str):
        if value.lower() == 'true':
            return True
        elif value.lower() == 'false':
            return False
        try:
            if '.' in value:
                return float(value)
            else:
                return int(value)
        except ValueError:
            return value
    return value


def load_config_from_file() -> Dict[str, Any]:
    """
    Загрузка конфигурации из файла
    
    Returns:
        Словарь конфигурации или пустой словарь при ошибке
    """
    if not CONFIG_FILE_PATH.exists():
        logger.debug(f"Файл fallback конфигурации не найден: {CONFIG_FILE_PATH}")
        return {}
    
    try:
        with CONFIG_LOCK:
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                config = data.get('config', {})
                logger.info(f"Конфигурация загружена из файла fallback: {len(config)} ключей")
                return config
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON в файле fallback конфигурации: {e}")
        return {}
    except Exception as e:
        logger.error(f"Ошибка при загрузке fallback конфигурации из файла: {e}")
        return {}


def save_config_to_file(config: Dict[str, Any]) -> bool:
    """
    Сохранение конфигурации в файл
    
    Args:
        config: Словарь конфигурации для сохранения
        
    Returns:
        True если успешно, False иначе
    """
    try:
        ensure_config_dir()
        
        # Формируем структуру данных для сохранения
        data = {
            'config': config,
            'updated_at': datetime.utcnow().isoformat(),
            'source': 'postgresql'
        }
        
        with CONFIG_LOCK:
            # Создаем временный файл для атомарной записи
            temp_file = CONFIG_FILE_PATH.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Атомарная замена файла
            temp_file.replace(CONFIG_FILE_PATH)
            
        logger.info(f"Конфигурация сохранена в файл fallback: {len(config)} ключей")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении fallback конфигурации в файл: {e}")
        return False


def get_config_value_from_file(key: str, default: Any = None) -> Any:
    """
    Получение значения конфигурации из файла
    
    Args:
        key: Ключ конфигурации
        default: Значение по умолчанию
        
    Returns:
        Значение конфигурации или default
    """
    config = load_config_from_file()
    value = config.get(key, default)
    
    # Преобразование типов (если значение строка)
    if isinstance(value, str):
        return _parse_config_value(value)
    
    return value


def get_all_config_from_file() -> Dict[str, Any]:
    """
    Получение всей конфигурации из файла
    
    Returns:
        Словарь всей конфигурации
    """
    config = load_config_from_file()
    
    # Преобразование типов для всех значений
    parsed_config = {}
    for key, value in config.items():
        parsed_config[key] = _parse_config_value(value) if isinstance(value, str) else value
    
    return parsed_config


def update_config_in_file(key: str, value: Any) -> bool:
    """
    Обновление одного значения конфигурации в файле
    
    Args:
        key: Ключ конфигурации
        value: Новое значение
        
    Returns:
        True если успешно, False иначе
    """
    config = load_config_from_file()
    config[key] = str(value)  # Сохраняем как строку для консистентности с БД
    return save_config_to_file(config)


def sync_config_from_db() -> bool:
    """
    Синхронизация конфигурации из PostgreSQL в файл
    
    Эта функция вызывается при старте сервиса и периодически для актуализации файла.
    
    Returns:
        True если успешно, False иначе
    """
    try:
        from shared.database import get_db_cursor
        
        with get_db_cursor() as cursor:
            cursor.execute("SELECT key, value FROM configuration")
            results = cursor.fetchall()
            
            config = {}
            for row in results:
                config[row['key']] = row['value']
            
            if config:
                success = save_config_to_file(config)
                if success:
                    logger.info(f"Конфигурация синхронизирована из PostgreSQL в файл: {len(config)} ключей")
                return success
            else:
                logger.warning("Конфигурация в PostgreSQL пуста, файл не обновлен")
                return False
    except Exception as e:
        logger.warning(f"Не удалось синхронизировать конфигурацию из PostgreSQL: {e}")
        return False


def get_config_file_info() -> Dict[str, Any]:
    """
    Получение информации о файле конфигурации
    
    Returns:
        Словарь с информацией о файле
    """
    info = {
        'exists': CONFIG_FILE_PATH.exists(),
        'path': str(CONFIG_FILE_PATH),
        'updated_at': None,
        'keys_count': 0
    }
    
    if CONFIG_FILE_PATH.exists():
        try:
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                info['updated_at'] = data.get('updated_at')
                config = data.get('config', {})
                info['keys_count'] = len(config)
        except Exception as e:
            logger.warning(f"Ошибка при чтении информации о файле конфигурации: {e}")
    
    return info

