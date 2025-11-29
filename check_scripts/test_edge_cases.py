import requests
import json
import time

print("=== Testing Edge Cases ===\n")

# Тест 1: Очень короткий текст
print("=== Test 1: Very short text ===")
short_text = "Помощь"
try:
    r = requests.post(
        "http://localhost:8001/classify",
        json={"text": short_text, "return_probabilities": False},
        timeout=10
    )
    if r.status_code == 200:
        result = r.json()
        print(f"Status: OK")
        print(f"Text: '{short_text}'")
        print(f"Predicted: {result.get('predicted_type')}")
        print(f"Confidence: {result.get('confidence', 0):.2%}")
        print(f"Decision: {result.get('decision')}")
    else:
        print(f"Status: {r.status_code}")
        print(f"Error: {r.text}")
except Exception as e:
    print(f"Error: {e}")

# Тест 2: Очень длинный текст
print("\n=== Test 2: Very long text ===")
long_text = "У меня проблема с компьютером. " * 50  # ~1500 символов
try:
    r = requests.post(
        "http://localhost:8001/classify",
        json={"text": long_text, "return_probabilities": False},
        timeout=10
    )
    if r.status_code == 200:
        result = r.json()
        print(f"Status: OK")
        print(f"Text length: {len(long_text)} characters")
        print(f"Predicted: {result.get('predicted_type')}")
        print(f"Confidence: {result.get('confidence', 0):.2%}")
        print(f"Decision: {result.get('decision')}")
    else:
        print(f"Status: {r.status_code}")
except Exception as e:
    print(f"Error: {e}")

# Тест 3: Текст с необычными символами
print("\n=== Test 3: Text with special characters ===")
special_text = "Проблема!!! @#$%^&*() 123456789"
try:
    r = requests.post(
        "http://localhost:8001/classify",
        json={"text": special_text, "return_probabilities": False},
        timeout=10
    )
    if r.status_code == 200:
        result = r.json()
        print(f"Status: OK")
        print(f"Text: '{special_text[:30]}...'")
        print(f"Predicted: {result.get('predicted_type')}")
        print(f"Confidence: {result.get('confidence', 0):.2%}")
    else:
        print(f"Status: {r.status_code}")
except Exception as e:
    print(f"Error: {e}")

# Тест 4: Пустой текст (должен вернуть ошибку)
print("\n=== Test 4: Empty text (should fail) ===")
try:
    r = requests.post(
        "http://localhost:8001/classify",
        json={"text": "", "return_probabilities": False},
        timeout=10
    )
    if r.status_code == 400:
        print(f"Status: {r.status_code} (Expected error)")
        print("Empty text correctly rejected")
    else:
        print(f"Status: {r.status_code} (Unexpected)")
        print(f"Response: {r.text}")
except Exception as e:
    print(f"Error: {e}")

# Тест 5: Создание тикета с минимальными данными
print("\n=== Test 5: Ticket with minimal data ===")
try:
    r = requests.post(
        "http://localhost:8000/tickets",
        json={"text": "Нужна помощь", "source": "api"},
        timeout=10
    )
    if r.status_code == 201:
        result = r.json()
        ticket_id = result.get('ticket_id')
        print(f"Status: Created")
        print(f"Ticket ID: {ticket_id}")
        print(f"Status: {result.get('status')}")
        
        # Ждем обработки
        print("Waiting for processing...")
        for i in range(10):
            time.sleep(1)
            status_r = requests.get(f"http://localhost:8000/status/{ticket_id}", timeout=5)
            if status_r.status_code == 200:
                status_data = status_r.json()
                status = status_data.get('status')
                print(f"  Status: {status}")
                if status == 'completed':
                    print(f"  Predicted: {status_data.get('predicted_type')}")
                    print(f"  Confidence: {status_data.get('confidence', 0):.2%}")
                    print(f"  Decision: {status_data.get('decision')}")
                    break
    else:
        print(f"Status: {r.status_code}")
        print(f"Error: {r.text}")
except Exception as e:
    print(f"Error: {e}")

# Тест 6: Проверка различных источников
print("\n=== Test 6: Different sources ===")
sources = ['email', 'chat', 'api', 'web']
for source in sources:
    try:
        r = requests.post(
            "http://localhost:8000/tickets",
            json={"text": f"Тест из источника {source}", "source": source},
            timeout=10
        )
        if r.status_code == 201:
            result = r.json()
            print(f"  {source}: OK (ticket {result.get('ticket_id')})")
        else:
            print(f"  {source}: Failed ({r.status_code})")
    except Exception as e:
        print(f"  {source}: Error - {e}")

print("\n=== Edge Cases Test Complete ===")

