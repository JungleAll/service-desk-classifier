import psycopg2
from psycopg2.extras import RealDictCursor
import json

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='service_desk_db',
    user='postgres',
    password='postgres'
)

cursor = conn.cursor(cursor_factory=RealDictCursor)
cursor.execute("""
    SELECT 
        ticket_id, action, service_name, status, details, retry_count, created_at
    FROM audit_logs
    WHERE ticket_id = %s
    ORDER BY created_at DESC
""", ('tick_583b380d',))

results = cursor.fetchall()
if results:
    print(f"Found {len(results)} audit log entries")
    for i, row in enumerate(results, 1):
        print(f"\n=== Entry {i} ===")
        print(f"Action: {row['action']}")
        print(f"Service: {row['service_name']}")
        print(f"Status: {row['status']}")
        print(f"Created At: {row['created_at']}")
        if row['retry_count']:
            print(f"Retry Count: {row['retry_count']}")
        if row['details']:
            print(f"Details: {json.dumps(row['details'], ensure_ascii=False, indent=2)}")
else:
    print("No audit log entries found")

conn.close()

