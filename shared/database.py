"""Общий модуль для работы с PostgreSQL"""

import os
import logging
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool

logger = logging.getLogger(__name__)

# Параметры подключения
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "service_desk_db")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# Пул соединений
_pool: Optional[SimpleConnectionPool] = None


def init_pool(minconn: int = 1, maxconn: int = 10):
    """Инициализация пула соединений"""
    global _pool
    if _pool is None:
        try:
            _pool = SimpleConnectionPool(
                minconn=minconn,
                maxconn=maxconn,
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            logger.info("Пул соединений PostgreSQL инициализирован")
        except Exception as e:
            logger.error(f"Ошибка при создании пула соединений: {e}")
            raise
    return _pool


@contextmanager
def get_db_connection():
    """Контекстный менеджер для получения соединения с БД"""
    pool = init_pool()
    conn = None
    try:
        conn = pool.getconn()
        # Проверяем, что соединение действительно открыто
        if conn.closed:
            # Соединение закрыто - получаем новое
            pool.putconn(conn, close=True)
            conn = pool.getconn()
        yield conn
        if conn and not conn.closed:
            conn.commit()
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        # Ошибка соединения - соединение закрыто сервером
        logger.error(f"Ошибка соединения с БД: {e}")
        # Закрываем соединение и возвращаем в пул с флагом close=True
        if conn:
            try:
                if not conn.closed:
                    try:
                        conn.rollback()
                    except:
                        pass  # Игнорируем ошибки при rollback
                pool.putconn(conn, close=True)  # Закрываем поврежденное соединение
            except Exception as put_error:
                logger.warning(f"Ошибка при возврате соединения в пул: {put_error}")
        conn = None
        raise
    except Exception as e:
        # Другие ошибки - пытаемся rollback только если соединение открыто
        if conn and not conn.closed:
            try:
                conn.rollback()
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                # Соединение закрыто во время rollback - закрываем его
                logger.warning("Соединение закрыто во время rollback")
                try:
                    pool.putconn(conn, close=True)
                except:
                    pass
                conn = None
        logger.error(f"Ошибка при работе с БД: {e}")
        raise
    finally:
        # Возвращаем соединение в пул только если оно еще открыто
        if conn:
            try:
                if not conn.closed:
                    pool.putconn(conn)
                else:
                    # Соединение закрыто - закрываем его явно
                    pool.putconn(conn, close=True)
            except Exception as put_error:
                logger.warning(f"Ошибка при возврате соединения в пул в finally: {put_error}")


@contextmanager
def get_db_cursor(dict_cursor: bool = True):
    """Контекстный менеджер для получения курсора"""
    with get_db_connection() as conn:
        if dict_cursor:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()


def execute_query(query: str, params: tuple = None) -> List[Dict[str, Any]]:
    """Выполнение SELECT запроса"""
    with get_db_cursor() as cursor:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def execute_insert(query: str, params: tuple = None) -> int:
    """Выполнение INSERT запроса, возвращает ID вставленной записи"""
    with get_db_cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchone()['id'] if cursor.rowcount > 0 else None


def execute_update(query: str, params: tuple = None) -> int:
    """Выполнение UPDATE запроса, возвращает количество обновленных строк"""
    with get_db_cursor() as cursor:
        cursor.execute(query, params)
        return cursor.rowcount


def execute_delete(query: str, params: tuple = None) -> int:
    """Выполнение DELETE запроса, возвращает количество удаленных строк"""
    with get_db_cursor() as cursor:
        cursor.execute(query, params)
        return cursor.rowcount

