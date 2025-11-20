"""Скрипт для применения миграций к базе данных PostgreSQL"""

import os
import sys
import psycopg2
from pathlib import Path
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Параметры подключения к БД
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "service_desk_db")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")


def apply_migration(migration_file: str):
    """
    Применение миграции к базе данных
    
    Args:
        migration_file: Путь к файлу миграции
    """
    migration_path = Path(__file__).parent / "migrations" / migration_file
    
    if not migration_path.exists():
        print(f"[ERROR] File migration not found: {migration_path}")
        sys.exit(1)
    
    try:
        # Подключение к БД
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        print(f"[INFO] Reading migration: {migration_path.name}")
        
        # Чтение SQL миграции
        with open(migration_path, 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        print(f"[INFO] Applying migration...")
        
        # Выполнение миграции
        cursor.execute(migration_sql)
        
        print(f"[SUCCESS] Migration {migration_path.name} applied successfully")
        
        # Проверка созданных объектов
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('classification_feedback', 'category_corrections', 'training_data_usage')
            ORDER BY table_name
        """)
        tables = cursor.fetchall()
        
        if tables:
            print("\n[INFO] Created tables:")
            for table in tables:
                print(f"   + {table[0]}")
        
        cursor.execute("""
            SELECT viewname 
            FROM pg_views 
            WHERE schemaname = 'public' 
            AND viewname IN ('training_ready_tickets', 'tickets_with_feedback', 'manual_review_pending')
            ORDER BY viewname
        """)
        views = cursor.fetchall()
        
        if views:
            print("\n[INFO] Created views:")
            for view in views:
                print(f"   + {view[0]}")
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f"[ERROR] Error applying migration: {e}")
        print(f"   Details: {e.pgcode} - {e.pgerror}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        migration_file = sys.argv[1]
    else:
        # По умолчанию применяем расширенную миграцию
        migration_file = "001_add_retraining_fields_extended.sql"
    
    print(f"[INFO] Applying migration to database: {DB_NAME}")
    print(f"   Host: {DB_HOST}:{DB_PORT}")
    print(f"   User: {DB_USER}")
    print()
    
    apply_migration(migration_file)
    
    print("\n[SUCCESS] Done!")

