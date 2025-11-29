"""Скрипт для инициализации базы данных PostgreSQL"""

import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from pathlib import Path

# Параметры подключения к БД
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "service_desk_db")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

def init_database():
    """Инициализация базы данных"""
    try:
        # Подключение к PostgreSQL (к базе postgres для создания БД)
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database="postgres",
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Проверка существования БД
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (DB_NAME,)
        )
        exists = cursor.fetchone()
        
        if not exists:
            # Создание БД
            cursor.execute(f'CREATE DATABASE {DB_NAME}')
            print(f"✅ База данных {DB_NAME} создана")
        else:
            print(f"ℹ️  База данных {DB_NAME} уже существует")
        
        cursor.close()
        conn.close()
        
        # Подключение к созданной БД и выполнение схемы
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = conn.cursor()
        
        # Чтение и выполнение SQL схемы
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        cursor.execute(schema_sql)
        conn.commit()
        
        print("✅ Схема базы данных применена успешно")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации базы данных: {e}")
        raise

if __name__ == "__main__":
    init_database()

