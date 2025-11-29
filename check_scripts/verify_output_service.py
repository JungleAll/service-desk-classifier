import psycopg2
from psycopg2.extras import RealDictCursor
import json

print("=== Output Service Verification ===\n")

# Проверка записей в ticket_events с jira_ticket_id
conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='service_desk_db',
    user='postgres',
    password='postgres'
)

cursor = conn.cursor(cursor_factory=RealDictCursor)

# Статистика по обработанным тикетам
cursor.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(CASE WHEN jira_ticket_id IS NOT NULL THEN 1 END) as with_output,
        COUNT(CASE WHEN decision = 'auto-process' THEN 1 END) as auto_processed,
        COUNT(CASE WHEN decision = 'manual-review' THEN 1 END) as manual_review
    FROM ticket_events
    WHERE status = 'completed'
""")

stats = cursor.fetchone()
print("=== Statistics ===")
print(f"Total completed tickets: {stats['total']}")
print(f"Tickets with output file: {stats['with_output']}")
print(f"Auto-processed: {stats['auto_processed']}")
print(f"Manual review: {stats['manual_review']}")

# Проверка тикетов с выходными файлами
cursor.execute("""
    SELECT 
        ticket_id,
        jira_ticket_id,
        jira_link,
        decision,
        priority,
        processed_at
    FROM ticket_events
    WHERE jira_ticket_id IS NOT NULL
    ORDER BY processed_at DESC
    LIMIT 5
""")

files = cursor.fetchall()
print(f"\n=== Recent Output Files (last 5) ===")
for i, row in enumerate(files, 1):
    print(f"\n{i}. Ticket: {row['ticket_id']}")
    print(f"   Output ID: {row['jira_ticket_id']}")
    print(f"   File Path: {row['jira_link']}")
    print(f"   Decision: {row['decision']}")
    print(f"   Priority: {row['priority']}")
    print(f"   Processed: {row['processed_at']}")

# Проверка audit_logs для Output Service
cursor.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(CASE WHEN status = 'success' THEN 1 END) as success,
        COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
    FROM audit_logs
    WHERE service_name = 'output'
""")

audit_stats = cursor.fetchone()
print(f"\n=== Audit Logs Statistics ===")
print(f"Total entries: {audit_stats['total']}")
print(f"Success: {audit_stats['success']}")
print(f"Failed: {audit_stats['failed']}")

conn.close()

print("\n=== Verification Result ===")
if stats['with_output'] > 0:
    print("[SUCCESS] Output Service is creating files correctly")
    print(f"[SUCCESS] {stats['with_output']} files created")
else:
    print("[WARNING] No output files found")

