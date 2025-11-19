"""Общие модули для микросервисов"""

from .database import (
    get_db_connection,
    get_db_cursor,
    execute_query,
    execute_insert,
    execute_update,
    execute_delete
)
from .redis_client import (
    get_redis_client,
    push_to_queue,
    pop_from_queue,
    get_cache,
    set_cache,
    delete_cache,
    get_queue_length,
    QUEUE_PENDING_TICKETS,
    QUEUE_FAILED_TICKETS,
    CACHE_PREDICTIONS
)

__all__ = [
    "get_db_connection",
    "get_db_cursor",
    "execute_query",
    "execute_insert",
    "execute_update",
    "execute_delete",
    "get_redis_client",
    "push_to_queue",
    "pop_from_queue",
    "get_cache",
    "set_cache",
    "delete_cache",
    "get_queue_length",
    "QUEUE_PENDING_TICKETS",
    "QUEUE_FAILED_TICKETS",
    "CACHE_PREDICTIONS",
]

