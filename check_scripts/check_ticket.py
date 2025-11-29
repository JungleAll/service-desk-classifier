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
        ticket_id, status, text, source, email, user_id,
        predicted_type, confidence, decision, model_version,
        jira_ticket_id, jira_link, priority,
        created_at, processed_at, sent_to_jira_at,
        probabilities
    FROM ticket_events
    WHERE ticket_id = %s
""", ('tick_583b380d',))

result = cursor.fetchone()
if result:
    print("=== Ticket Data ===")
    print(f"Ticket ID: {result['ticket_id']}")
    print(f"Status: {result['status']}")
    print(f"Source: {result['source']}")
    print(f"Email: {result['email']}")
    print(f"User ID: {result['user_id']}")
    print(f"\n=== Classification Results ===")
    print(f"Predicted Type: {result['predicted_type']}")
    print(f"Confidence: {result['confidence']:.2%}" if result['confidence'] else "Confidence: N/A")
    print(f"Decision: {result['decision']}")
    print(f"Model Version: {result['model_version']}")
    print(f"Priority: {result['priority']}")
    print(f"\n=== Output Data ===")
    print(f"Jira Ticket ID: {result['jira_ticket_id']}")
    print(f"Jira Link: {result['jira_link']}")
    print(f"\n=== Timestamps ===")
    print(f"Created At: {result['created_at']}")
    print(f"Processed At: {result['processed_at']}")
    print(f"Sent To Jira At: {result['sent_to_jira_at']}")
    
    if result['probabilities']:
        print(f"\n=== Top 5 Probabilities ===")
        probs = result['probabilities']
        if isinstance(probs, dict):
            sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:5]
            for cat, prob in sorted_probs:
                print(f"  {cat}: {prob:.2%}")
else:
    print("Ticket not found")

conn.close()

