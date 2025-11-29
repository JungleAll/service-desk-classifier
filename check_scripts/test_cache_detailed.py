import requests
import time
import redis
import json
import hashlib

print("=== Detailed Cache Testing ===\n")

# Тестовый текст (тот же, что использовался ранее)
TEST_TEXT = "У меня не работает принтер, пишет ошибку замятия бумаги. Помогите решить проблему."

# Вычисление хэша
text_hash = hashlib.md5(TEST_TEXT.encode('utf-8')).hexdigest()
cache_key = f"cache_predictions:v1.0:{text_hash}"

print(f"Test Text: {TEST_TEXT[:50]}...")
print(f"Cache Key: {cache_key}\n")

# Подключение к Redis
client = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)

# Проверка кэша ДО запроса
print("=== Step 1: Check cache before request ===")
cached_before = client.get(cache_key)
if cached_before:
    print(f"Cache EXISTS (from previous test)")
    cache_data = json.loads(cached_before)
    print(f"  Predicted Type: {cache_data.get('predicted_type')}")
    print(f"  Confidence: {cache_data.get('confidence', 0):.2%}")
    ttl_before = client.ttl(cache_key)
    print(f"  TTL: {ttl_before} seconds ({ttl_before//60}m {ttl_before%60}s)")
else:
    print("Cache NOT FOUND")

# Первая классификация
print("\n=== Step 2: First classification request ===")
start = time.time()
r1 = requests.post(
    "http://localhost:8001/classify",
    json={"text": TEST_TEXT, "return_probabilities": True},
    timeout=10
)
elapsed1 = time.time() - start

if r1.status_code == 200:
    result1 = r1.json()
    print(f"Status: OK")
    print(f"Total Time: {elapsed1*1000:.1f}ms")
    print(f"Processing Time: {result1.get('processing_time_ms', 0)}ms")
    print(f"Predicted: {result1.get('predicted_type')}")
    print(f"Confidence: {result1.get('confidence', 0):.2%}")
    
    # Проверка кэша после запроса
    cached_after = client.get(cache_key)
    if cached_after:
        print(f"\nCache after request: EXISTS")
        ttl_after = client.ttl(cache_key)
        print(f"TTL: {ttl_after} seconds ({ttl_after//60}m {ttl_after%60}s)")
        if ttl_after == 3600:
            print("TTL is correct (3600 seconds = 1 hour)")
        else:
            print(f"TTL is {ttl_after}, expected 3600")
    else:
        print("Cache after request: NOT FOUND (ERROR!)")
else:
    print(f"Error: {r1.status_code}")

# Небольшая пауза
time.sleep(0.5)

# Вторая классификация (должна использовать кэш)
print("\n=== Step 3: Second classification (should use cache) ===")
start = time.time()
r2 = requests.post(
    "http://localhost:8001/classify",
    json={"text": TEST_TEXT, "return_probabilities": True},
    timeout=10
)
elapsed2 = time.time() - start

if r2.status_code == 200:
    result2 = r2.json()
    print(f"Status: OK")
    print(f"Total Time: {elapsed2*1000:.1f}ms")
    print(f"Processing Time: {result2.get('processing_time_ms', 0)}ms")
    print(f"Predicted: {result2.get('predicted_type')}")
    print(f"Confidence: {result2.get('confidence', 0):.2%}")
    
    # Сравнение
    print("\n=== Comparison ===")
    time_diff = elapsed1 - elapsed2
    time_percent = (time_diff / elapsed1) * 100 if elapsed1 > 0 else 0
    print(f"Time difference: {time_diff*1000:.1f}ms ({time_percent:.1f}% faster)")
    
    proc_diff = result1.get('processing_time_ms', 0) - result2.get('processing_time_ms', 0)
    proc_percent = (proc_diff / result1.get('processing_time_ms', 1)) * 100 if result1.get('processing_time_ms', 0) > 0 else 0
    print(f"Processing time difference: {proc_diff:.1f}ms ({proc_percent:.1f}% faster)")
    
    # Проверка совпадения результатов
    if result1.get('predicted_type') == result2.get('predicted_type'):
        print("Results match: OK")
    else:
        print("Results don't match: ERROR")
    
    if result1.get('confidence') == result2.get('confidence'):
        print("Confidence matches: OK")
    else:
        print("Confidence doesn't match: ERROR")

# Третья классификация (для подтверждения стабильности кэша)
print("\n=== Step 4: Third classification (cache stability) ===")
start = time.time()
r3 = requests.post(
    "http://localhost:8001/classify",
    json={"text": TEST_TEXT, "return_probabilities": False},
    timeout=10
)
elapsed3 = time.time() - start

if r3.status_code == 200:
    result3 = r3.json()
    print(f"Status: OK")
    print(f"Total Time: {elapsed3*1000:.1f}ms")
    print(f"Processing Time: {result3.get('processing_time_ms', 0)}ms")
    
    # Проверка, что результаты одинаковые
    if (result3.get('predicted_type') == result1.get('predicted_type') and
        result3.get('confidence') == result1.get('confidence')):
        print("Results consistent across all requests: OK")
    else:
        print("Results inconsistent: ERROR")

# Итоговая проверка TTL
print("\n=== Step 5: Final TTL check ===")
ttl_final = client.ttl(cache_key)
if ttl_final > 0:
    minutes = ttl_final // 60
    seconds = ttl_final % 60
    print(f"TTL: {minutes}m {seconds}s ({ttl_final} seconds)")
    print(f"Expected: 3600 seconds (1 hour)")
    if 3590 <= ttl_final <= 3600:
        print("TTL is correct")
    else:
        print(f"TTL is {ttl_final}, should be close to 3600")
else:
    print("TTL expired or not set")

print("\n=== Test Summary ===")
print("Cache is working correctly if:")
print("  1. Second request is faster than first")
print("  2. Results match across all requests")
print("  3. TTL is set to 3600 seconds")

