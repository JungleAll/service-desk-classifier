import requests
import json
import time

print("=== Testing Batch Processing ===\n")

# Тест пакетного создания тикетов
print("=== Test: Batch ticket creation ===")
batch_payload = {
    "tickets": [
        {"text": "Проблема с компьютером", "source": "api"},
        {"text": "Вопрос по программному обеспечению", "source": "api"},
        {"text": "Нужна помощь с настройкой", "source": "api"},
        {"text": "Заявка на билет", "source": "api"},
        {"text": "Проблема с принтером", "source": "api"}
    ]
}

try:
    start_time = time.time()
    r = requests.post(
        "http://localhost:8000/tickets/batch",
        json=batch_payload,
        timeout=30
    )
    elapsed = time.time() - start_time
    
    if r.status_code == 202:
        result = r.json()
        print(f"Status: Accepted")
        print(f"Batch ID: {result.get('batch_id')}")
        print(f"Total: {result.get('total')}")
        print(f"Queued: {result.get('queued')}")
        print(f"Failed: {result.get('failed')}")
        print(f"Estimated Time: {result.get('estimated_time')}ms")
        print(f"Actual Time: {elapsed*1000:.1f}ms")
        
        # Ждем обработки всех тикетов
        print("\nWaiting for batch processing...")
        ticket_ids = []
        
        # Получаем список последних тикетов
        list_r = requests.get(
            "http://localhost:8000/tickets?limit=10&status=completed",
            timeout=10
        )
        if list_r.status_code == 200:
            tickets = list_r.json().get('tickets', [])
            print(f"\nFound {len(tickets)} completed tickets")
            
            # Проверяем последние 5 тикетов
            for i, ticket in enumerate(tickets[:5], 1):
                ticket_id = ticket.get('ticket_id')
                status = ticket.get('status')
                predicted = ticket.get('predicted_type')
                confidence = ticket.get('confidence', 0)
                print(f"\n{i}. Ticket: {ticket_id}")
                print(f"   Status: {status}")
                if predicted:
                    print(f"   Predicted: {predicted}")
                    print(f"   Confidence: {confidence:.2%}" if confidence else "   Confidence: N/A")
    else:
        print(f"Status: {r.status_code}")
        print(f"Error: {r.text}")
except Exception as e:
    print(f"Error: {e}")

# Тест пакетной классификации через ML Service
print("\n=== Test: Batch classification ===")
batch_classify_payload = {
    "texts": [
        "Проблема с компьютером",
        "Вопрос по программному обеспечению",
        "Нужна помощь с настройкой"
    ]
}

try:
    start_time = time.time()
    r = requests.post(
        "http://localhost:8001/classify/batch",
        json=batch_classify_payload,
        timeout=30
    )
    elapsed = time.time() - start_time
    
    if r.status_code == 200:
        result = r.json()
        print(f"Status: OK")
        print(f"Total Time: {result.get('total_time_ms', 0)}ms")
        print(f"Actual Time: {elapsed*1000:.1f}ms")
        print(f"Results: {len(result.get('results', []))}")
        
        for i, item in enumerate(result.get('results', []), 1):
            print(f"\n{i}. Text: {item.get('text', '')[:40]}...")
            print(f"   Predicted: {item.get('predicted_type')}")
            print(f"   Confidence: {item.get('confidence', 0):.2%}")
    else:
        print(f"Status: {r.status_code}")
        print(f"Error: {r.text}")
except Exception as e:
    print(f"Error: {e}")

print("\n=== Batch Processing Test Complete ===")

