"""Общий модуль для работы с Redis

Архитектура Redis:
- DB 0: Очереди (pending_tickets, failed_tickets) - для очередей задач
- DB 1: Кэш (cache_predictions) - для кэширования результатов классификации

Разделение на разные базы данных позволяет:
- Изолировать данные очередей и кэша
- Настроить разные политики управления (TTL, persistence)
- Упростить мониторинг и отладку
- Оптимизировать производительность
"""

import os
import json
import logging
from typing import Optional, Any, Dict
import redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# Параметры подключения
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Номера баз данных для разных типов данных
REDIS_DB_QUEUES = int(os.getenv("REDIS_DB_QUEUES", "0"))  # Очереди
REDIS_DB_CACHE = int(os.getenv("REDIS_DB_CACHE", "1"))   # Кэш

# Глобальные клиенты Redis (singleton для каждой базы данных)
_redis_queue_client: Optional[redis.Redis] = None
_redis_cache_client: Optional[redis.Redis] = None


def _create_redis_client(db: int) -> redis.Redis:
    """Создание клиента Redis для указанной базы данных"""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=db,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5
    )


def get_redis_queue_client() -> redis.Redis:
    """Получение клиента Redis для очередей (DB 0)"""
    global _redis_queue_client
    if _redis_queue_client is None:
        try:
            _redis_queue_client = _create_redis_client(REDIS_DB_QUEUES)
            _redis_queue_client.ping()
            logger.info(f"Подключение к Redis (очереди, DB {REDIS_DB_QUEUES}) установлено")
        except RedisError as e:
            logger.error(f"Ошибка подключения к Redis (очереди): {e}")
            raise
    return _redis_queue_client


def get_redis_cache_client() -> redis.Redis:
    """Получение клиента Redis для кэша (DB 1)"""
    global _redis_cache_client
    if _redis_cache_client is None:
        try:
            _redis_cache_client = _create_redis_client(REDIS_DB_CACHE)
            _redis_cache_client.ping()
            logger.info(f"Подключение к Redis (кэш, DB {REDIS_DB_CACHE}) установлено")
        except RedisError as e:
            logger.error(f"Ошибка подключения к Redis (кэш): {e}")
            raise
    return _redis_cache_client


def get_redis_client() -> redis.Redis:
    """
    Получение клиента Redis (обратная совместимость)
    
    ВНИМАНИЕ: Эта функция возвращает клиент для очередей (DB 0) для обратной совместимости.
    Для новых проектов рекомендуется использовать get_redis_queue_client() или get_redis_cache_client()
    """
    logger.warning("Использование устаревшей функции get_redis_client(). Используйте get_redis_queue_client() или get_redis_cache_client()")
    return get_redis_queue_client()


# Ключи для очередей
QUEUE_PENDING_TICKETS = "pending_tickets"
QUEUE_FAILED_TICKETS = "failed_tickets"
CACHE_PREDICTIONS = "cache_predictions"


def push_to_queue(queue_name: str, data: Dict[str, Any]) -> bool:
    """Добавление задачи в очередь (использует DB 0)"""
    try:
        client = get_redis_queue_client()
        client.rpush(queue_name, json.dumps(data, ensure_ascii=False))
        logger.debug(f"Задача добавлена в очередь {queue_name} (DB {REDIS_DB_QUEUES})")
        return True
    except RedisError as e:
        logger.error(f"Ошибка при добавлении в очередь {queue_name}: {e}")
        return False


def pop_from_queue(queue_name: str, timeout: int = 0) -> Optional[Dict[str, Any]]:
    """Извлечение задачи из очереди (использует DB 0)"""
    try:
        client = get_redis_queue_client()
        if timeout > 0:
            result = client.blpop(queue_name, timeout=timeout)
            if result:
                return json.loads(result[1])
        else:
            result = client.lpop(queue_name)
            if result:
                return json.loads(result)
        return None
    except redis.exceptions.TimeoutError:
        # Таймаут при blpop - это нормально, если очередь пуста
        # Не логируем как ошибку, так как это ожидаемое поведение
        return None
    except RedisError as e:
        # Логируем только реальные ошибки (не таймауты)
        error_str = str(e).lower()
        if "timeout" not in error_str:
            logger.error(f"Ошибка при извлечении из очереди {queue_name}: {e}")
        return None


def get_cache(key: str) -> Optional[Dict[str, Any]]:
    """Получение значения из кэша (использует DB 1)"""
    try:
        client = get_redis_cache_client()
        value = client.get(key)
        if value:
            return json.loads(value)
        return None
    except RedisError as e:
        logger.error(f"Ошибка при получении из кэша: {e}")
        return None


def set_cache(key: str, value: Dict[str, Any], ttl: int = 3600) -> bool:
    """Установка значения в кэш с TTL (использует DB 1)"""
    try:
        client = get_redis_cache_client()
        client.setex(
            key,
            ttl,
            json.dumps(value, ensure_ascii=False)
        )
        logger.debug(f"Значение установлено в кэш с ключом {key} (DB {REDIS_DB_CACHE}, TTL={ttl}s)")
        return True
    except RedisError as e:
        logger.error(f"Ошибка при установке в кэш: {e}")
        return False


def delete_cache(key: str) -> bool:
    """Удаление значения из кэша (использует DB 1)"""
    try:
        client = get_redis_cache_client()
        client.delete(key)
        logger.debug(f"Значение удалено из кэша с ключом {key} (DB {REDIS_DB_CACHE})")
        return True
    except RedisError as e:
        logger.error(f"Ошибка при удалении из кэша: {e}")
        return False


def get_queue_length(queue_name: str) -> int:
    """Получение длины очереди (использует DB 0)"""
    try:
        client = get_redis_queue_client()
        length = client.llen(queue_name)
        logger.debug(f"Длина очереди {queue_name}: {length} (DB {REDIS_DB_QUEUES})")
        return length
    except RedisError as e:
        logger.error(f"Ошибка при получении длины очереди {queue_name}: {e}")
        return 0


def clear_queue(queue_name: str) -> bool:
    """Очистка очереди (использует DB 0)"""
    try:
        client = get_redis_queue_client()
        client.delete(queue_name)
        logger.info(f"Очередь {queue_name} очищена (DB {REDIS_DB_QUEUES})")
        return True
    except RedisError as e:
        logger.error(f"Ошибка при очистке очереди {queue_name}: {e}")
        return False


def clear_cache(pattern: str = "*") -> int:
    """
    Очистка кэша по паттерну (использует DB 1)
    
    Args:
        pattern: Паттерн для поиска ключей (по умолчанию "*" - все ключи)
        
    Returns:
        Количество удаленных ключей
    """
    try:
        client = get_redis_cache_client()
        keys = client.keys(pattern)
        if keys:
            deleted = client.delete(*keys)
            logger.info(f"Удалено {deleted} ключей из кэша по паттерну '{pattern}' (DB {REDIS_DB_CACHE})")
            return deleted
        return 0
    except RedisError as e:
        logger.error(f"Ошибка при очистке кэша: {e}")
        return 0


def get_cache_info() -> Dict[str, Any]:
    """Получение информации о кэше (использует DB 1)"""
    try:
        client = get_redis_cache_client()
        info = client.info()
        keys = client.dbsize()
        return {
            "db": REDIS_DB_CACHE,
            "keys": keys,
            "used_memory": info.get("used_memory_human", "N/A"),
            "connected_clients": info.get("connected_clients", 0)
        }
    except RedisError as e:
        logger.error(f"Ошибка при получении информации о кэше: {e}")
        return {"error": str(e)}


def get_queue_info() -> Dict[str, Any]:
    """Получение информации об очередях (использует DB 0)"""
    try:
        client = get_redis_queue_client()
        info = client.info()
        pending_length = get_queue_length(QUEUE_PENDING_TICKETS)
        failed_length = get_queue_length(QUEUE_FAILED_TICKETS)
        return {
            "db": REDIS_DB_QUEUES,
            "pending_tickets": pending_length,
            "failed_tickets": failed_length,
            "used_memory": info.get("used_memory_human", "N/A"),
            "connected_clients": info.get("connected_clients", 0)
        }
    except RedisError as e:
        logger.error(f"Ошибка при получении информации об очередях: {e}")
        return {"error": str(e)}
