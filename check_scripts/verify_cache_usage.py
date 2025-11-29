import requests
import time
import redis
import json
import hashlib

# Текст для тестирования
TEST_TEXT = "Нужна помощь с настройкой компьютера"

print("=== Verifying Cache Usage ===\n")

# Вычисление хэша
text_hash = hashlib.md5(TEST_TEXT.encode('utf-8')).hexdigest()
cache_key = f"cache_predictions:v1.0:{text_hash}"

print(f"Test Text: {TEST_TEXT}")
print(f"Cache Key: {cache_key}\n")

# Подключение к Redis
client = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)

# Проверка наличия кэша до запроса
cached_before = client.get(cache_key)
print(f"Cache before request: {'EXISTS' if cached_before else 'NOT FOUND'}")

# Первый запрос
print("\n=== First Request ===")
start = time.time()
r1 = requests.post(
    "http://localhost:8001/classify",
    json={"text": TEST_TEXT, "return_probabilities": False},
    timeout=10
)
elapsed1 = time.time() - start

if r1.status_code == 200:
    result1 = r1.json()
    print(f"Time: {elapsed1*1000:.1f}ms")
    print(f"Processing Time: {result1.get('processing_time_ms', 0)}ms")
    print(f"Predicted: {result1.get('predicted_type')}")
    
    # Проверка кэша после запроса
    cached_after = client.get(cache_key)
    print(f"Cache after request: {'EXISTS' if cached_after else 'NOT FOUND'}")
    
    if cached_after:
        cache_data = json.loads(cached_after)
        print(f"Cache TTL: {client.ttl(cache_key)} seconds")
        print(f"Cache matches: {cache_data.get('predicted_type') == result1.get('predicted_type')}")

# Второй запрос (должен использовать кэш)
print("\n=== Second Request (should use cache) ===")
start = time.time()
r2 = requests.post(
    "http://localhost:8001/classify",
    json={"text": TEST_TEXT, "return_probabilities": False},
    timeout=10
)
elapsed2 = time.time() - start

if r2.status_code == 200:
    result2 = r2.json()
    print(f"Time: {elapsed2*1000:.1f}ms")
    print(f"Processing Time: {result2.get('processing_time_ms', 0)}ms")
    print(f"Predicted: {result2.get('predicted_type')}")
    
    # Сравнение времени
    if result2.get('processing_time_ms', 0) < result1.get('processing_time_ms', 0) * 0.7:
        print("\n[SUCCESS] Cache is being used! Second request was faster.")
    else:
        print("\n[INFO] Processing times are similar (cache might be used or request is very fast)")

