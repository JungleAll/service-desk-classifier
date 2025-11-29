"""
Проверка данных в PostgreSQL
Использует прямые SQL запросы через psycopg2
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

# Параметры подключения (из docker-compose)
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "service_desk_db"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres")
}


def print_section(title):
    """Печать заголовка секции"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def connect_db():
    """Подключение к базе данных"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        print(f"   Проверьте параметры: {DB_CONFIG}")
        return None


def check_ticket_events(conn, ticket_id=None):
    """Проверка таблицы ticket_events"""
    print_section("ПРОВЕРКА ТАБЛИЦЫ ticket_events")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    if ticket_id:
        # Проверка конкретного тикета
        cursor.execute("""
            SELECT 
                ticket_id, text, source, status, email, user_id,
                predicted_type, confidence, decision, model_version,
                jira_ticket_id, jira_link, priority,
                created_at, processed_at, sent_to_jira_at,
                probabilities
            FROM ticket_events
            WHERE ticket_id = %s
        """, (ticket_id,))
        
        result = cursor.fetchone()
        if result:
            print(f"\n✅ Тикет найден: {ticket_id}")
            print(f"\nОсновные данные:")
            print(f"   Текст: {result['text'][:100]}...")
            print(f"   Источник: {result['source']}")
            print(f"   Email: {result['email']}")
            print(f"   User ID: {result['user_id']}")
            
            print(f"\nСтатус обработки:")
            print(f"   Статус: {result['status']}")
            print(f"   Создан: {result['created_at']}")
            print(f"   Обработан: {result['processed_at']}")
            
            if result['status'] == 'completed':
                print(f"\nРезультаты классификации:")
                print(f"   Категория: {result['predicted_type']}")
                print(f"   Уверенность: {result['confidence']:.2%}" if result['confidence'] else "   Уверенность: N/A")
                print(f"   Решение: {result['decision']}")
                print(f"   Версия модели: {result['model_version']}")
                print(f"   Приоритет: {result['priority']}")
                
                if result['jira_ticket_id']:
                    print(f"\nВыходные данные:")
                    print(f"   ID файла: {result['jira_ticket_id']}")
                    print(f"   Путь: {result['jira_link']}")
                    print(f"   Отправлен: {result['sent_to_jira_at']}")
                
                if result['probabilities']:
                    print(f"\nВероятности (топ-5):")
                    probs = result['probabilities']
                    if isinstance(probs, dict):
                        sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:5]
                        for cat, prob in sorted_probs:
                            print(f"   - {cat}: {prob:.2%}")
            else:
                print(f"\n⚠️  Тикет еще не обработан (статус: {result['status']})")
            
            return True
        else:
            print(f"❌ Тикет {ticket_id} не найден")
            return False
    else:
        # Статистика по всем тикетам
        cursor.execute("""
            SELECT 
                status,
                COUNT(*) as count,
                AVG(confidence) as avg_confidence,
                COUNT(CASE WHEN decision = 'auto-process' THEN 1 END) as auto_processed,
                COUNT(CASE WHEN decision = 'manual-review' THEN 1 END) as manual_review
            FROM ticket_events
            GROUP BY status
            ORDER BY count DESC
        """)
        
        results = cursor.fetchall()
        print("\nСтатистика по статусам:")
        for row in results:
            print(f"   {row['status']}: {row['count']} тикетов")
            if row['avg_confidence']:
                print(f"      Средняя уверенность: {row['avg_confidence']:.2%}")
            if row['auto_processed']:
                print(f"      Автообработано: {row['auto_processed']}")
            if row['manual_review']:
                print(f"      Требует проверки: {row['manual_review']}")
        
        return True


def check_audit_logs(conn, ticket_id=None):
    """Проверка таблицы audit_logs"""
    print_section("ПРОВЕРКА ТАБЛИЦЫ audit_logs")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    if ticket_id:
        cursor.execute("""
            SELECT 
                ticket_id, action, service_name, status, details, retry_count, created_at
            FROM audit_logs
            WHERE ticket_id = %s
            ORDER BY created_at DESC
        """, (ticket_id,))
        
        results = cursor.fetchall()
        if results:
            print(f"\n✅ Найдено {len(results)} записей для тикета {ticket_id}")
            for i, row in enumerate(results, 1):
                print(f"\n   Запись {i}:")
                print(f"      Действие: {row['action']}")
                print(f"      Сервис: {row['service_name']}")
                print(f"      Статус: {row['status']}")
                print(f"      Время: {row['created_at']}")
                if row['retry_count']:
                    print(f"      Попыток: {row['retry_count']}")
                if row['details']:
                    print(f"      Детали: {json.dumps(row['details'], ensure_ascii=False, indent=8)}")
            return True
        else:
            print(f"⚠️  Записи для тикета {ticket_id} не найдены")
            return False
    else:
        cursor.execute("""
            SELECT 
                action, service_name, status, COUNT(*) as count
            FROM audit_logs
            GROUP BY action, service_name, status
            ORDER BY count DESC
            LIMIT 10
        """)
        
        results = cursor.fetchall()
        print("\nСтатистика по действиям:")
        for row in results:
            print(f"   {row['action']} ({row['service_name']}): {row['status']} - {row['count']} раз")
        
        return True


def check_metrics(conn):
    """Проверка таблицы metrics"""
    print_section("ПРОВЕРКА ТАБЛИЦЫ metrics")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT 
            model_version, metric_name, metric_value, calculated_at
        FROM metrics
        WHERE model_version = 'v1.0'
        ORDER BY calculated_at DESC
        LIMIT 20
    """)
    
    results = cursor.fetchall()
    if results:
        print(f"\n✅ Найдено {len(results)} записей метрик")
        
        # Группировка по типу метрики
        metrics_dict = {}
        for row in results:
            name = row['metric_name']
            if name not in metrics_dict:
                metrics_dict[name] = []
            metrics_dict[name].append(row)
        
        for metric_name, rows in metrics_dict.items():
            print(f"\n   {metric_name}:")
            for row in rows[:5]:  # Показываем последние 5
                print(f"      {row['calculated_at']}: {row['metric_value']}")
        
        return True
    else:
        print("⚠️  Записи метрик не найдены")
        return False


def main():
    """Главная функция"""
    print_section("ПРОВЕРКА POSTGRESQL")
    print(f"Время начала: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Подключение
    conn = connect_db()
    if not conn:
        sys.exit(1)
    
    try:
        # Получение ticket_id из аргументов или проверка всех
        ticket_id = sys.argv[1] if len(sys.argv) > 1 else None
        
        results = {}
        
        # Проверки
        results["ticket_events"] = check_ticket_events(conn, ticket_id)
        results["audit_logs"] = check_audit_logs(conn, ticket_id)
        results["metrics"] = check_metrics(conn)
        
        # Итог
        print_section("ИТОГ")
        passed = sum(1 for r in results.values() if r)
        total = len(results)
        
        for check_name, result in results.items():
            status = "✅" if result else "❌"
            print(f"   {status} {check_name}")
        
        print(f"\nПройдено: {passed}/{total}")
        
    finally:
        conn.close()
    
    print(f"\nВремя завершения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    import json
    main()

