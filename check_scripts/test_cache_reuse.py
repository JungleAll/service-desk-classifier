import requests
import time
import hashlib
import json

# Текст для тестирования (тот же, что использовался ранее)
TEST_TEXT = "У меня не работает принтер, пишет ошибку замятия бумаги. Помогите решить проблему."

print("=== Testing Cache Reuse ===\n")

# Вычисление хэша текста (как в ML Service)
text_hash = hashlib.md5(TEST_TEXT.encode('utf-8')).hexdigest()
cache_key = f"cache_predictions:v1.0:{text_hash}"

print(f"Test Text: {TEST_TEXT[:50]}...")
print(f"Text Hash: {text_hash}")
print(f"Expected Cache Key: {cache_key}\n")

# Первая классификация (должна создать кэш)
print("=== First Classification (should create cache) ===")
start_time = time.time()
response1 = requests.post(
    "http://localhost:8001/classify",
    json={"text": TEST_TEXT, "return_probabilities": True},
    timeout=10
)
elapsed1 = time.time() - start_time

if response1.status_code == 200:
    result1 = response1.json()
    print(f"Status: OK")
    print(f"Time: {elapsed1*1000:.1f}ms")
    print(f"Predicted Type: {result1.get('predicted_type')}")
    print(f"Confidence: {result1.get('confidence', 0):.2%}")
    print(f"Processing Time: {result1.get('processing_time_ms', 0)}ms")
else:
    print(f"Error: {response1.status_code}")
    print(response1.text)
    exit(1)

# Небольшая пауза
time.sleep(0.5)

# Вторая классификация (должна использовать кэш)
print("\n=== Second Classification (should use cache) ===")
start_time = time.time()
response2 = requests.post(
    "http://localhost:8001/classify",
    json={"text": TEST_TEXT, "return_probabilities": True},
    timeout=10
)
elapsed2 = time.time() - start_time

if response2.status_code == 200:
    result2 = response2.json()
    print(f"Status: OK")
    print(f"Time: {elapsed2*1000:.1f}ms")
    print(f"Predicted Type: {result2.get('predicted_type')}")
    print(f"Confidence: {result2.get('confidence', 0):.2%}")
    print(f"Processing Time: {result2.get('processing_time_ms', 0)}ms")
else:
    print(f"Error: {response2.status_code}")
    print(response2.text)
    exit(1)

# Сравнение результатов
print("\n=== Comparison ===")
print(f"First time:  {elapsed1*1000:.1f}ms (processing: {result1.get('processing_time_ms', 0)}ms)")
print(f"Second time: {elapsed2*1000:.1f}ms (processing: {result2.get('processing_time_ms', 0)}ms)")

if elapsed2 < elapsed1 * 0.5:  # Второй запрос должен быть значительно быстрее
    print("\n✅ Cache is working! Second request was faster.")
else:
    print("\n⚠️  Cache might not be working. Times are similar.")

# Проверка совпадения результатов
if result1.get('predicted_type') == result2.get('predicted_type'):
    print("✅ Results match (cache is correct)")
else:
    print("❌ Results don't match (cache might be incorrect)")

# Проверка кэша в Redis
print("\n=== Checking Redis Cache ===")
import redis
client = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
cached_value = client.get(cache_key)

if cached_value:
    print(f"✅ Cache key found in Redis")
    cache_data = json.loads(cached_value)
    print(f"   Predicted Type: {cache_data.get('predicted_type')}")
    print(f"   Confidence: {cache_data.get('confidence', 0):.2%}")
    
    ttl = client.ttl(cache_key)
    if ttl > 0:
        minutes = ttl // 60
        seconds = ttl % 60
        print(f"   TTL: {minutes}m {seconds}s ({ttl} seconds)")
    else:
        print(f"   TTL: expired or no TTL")
else:
    print(f"❌ Cache key not found in Redis")

