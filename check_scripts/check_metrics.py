import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='service_desk_db',
    user='postgres',
    password='postgres'
)

cursor = conn.cursor(cursor_factory=RealDictCursor)

# Проверка метрик для модели v1.0
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
    print(f"=== Found {len(results)} metric entries ===\n")
    
    # Группировка по типу метрики
    metrics_dict = {}
    for row in results:
        name = row['metric_name']
        if name not in metrics_dict:
            metrics_dict[name] = []
        metrics_dict[name].append(row)
    
    for metric_name, rows in metrics_dict.items():
        print(f"=== {metric_name} ===")
        for row in rows[:5]:  # Показываем последние 5
            print(f"  Value: {row['metric_value']}")
            print(f"  Calculated At: {row['calculated_at']}")
            print()
        
        # Статистика
        if metric_name == 'classification_count':
            total = sum(float(r['metric_value']) for r in rows)
            print(f"  Total Classifications: {int(total)}")
            print()
else:
    print("No metrics found")

# Проверка метрик модели (accuracy, precision, recall, f1_score)
cursor.execute("""
    SELECT 
        metric_name, metric_value, calculated_at
    FROM metrics
    WHERE model_version = 'v1.0'
        AND metric_name IN ('accuracy', 'precision', 'recall', 'f1_score')
    ORDER BY calculated_at DESC
""")

model_metrics = cursor.fetchall()
if model_metrics:
    print("=== Model Performance Metrics ===")
    for row in model_metrics:
        print(f"{row['metric_name']}: {float(row['metric_value']):.4f}")
        print(f"  Calculated At: {row['calculated_at']}")
        print()

conn.close()

