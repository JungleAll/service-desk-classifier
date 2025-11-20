import redis
import json
import hashlib

# Подключение к Redis кэшу (DB 1)
client = redis.Redis(
    host='localhost',
    port=6379,
    db=1,
    decode_responses=True
)

# Поиск всех ключей кэша
keys = client.keys("cache_predictions:*")
print(f"Found {len(keys)} cache keys")

if keys:
    # Проверка первого ключа
    key = keys[0]
    print(f"\nCache Key: {key}")
    
    # Получение значения
    value = client.get(key)
    if value:
        data = json.loads(value)
        print(f"\n=== Cached Data ===")
        print(f"Predicted Type: {data.get('predicted_type')}")
        print(f"Confidence: {data.get('confidence', 0):.2%}")
        print(f"Model Version: {data.get('model_version')}")
        print(f"Decision: {data.get('decision')}")
        
        # Проверка TTL
        ttl = client.ttl(key)
        if ttl > 0:
            minutes = ttl // 60
            seconds = ttl % 60
            print(f"\nTTL: {minutes}m {seconds}s ({ttl} seconds)")
        else:
            print(f"\nTTL: expired or no TTL")
        
        # Проверка probabilities
        if 'probabilities' in data:
            probs = data['probabilities']
            if isinstance(probs, dict):
                print(f"\nTop 3 Probabilities:")
                sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:3]
                for cat, prob in sorted_probs:
                    print(f"  {cat}: {prob:.2%}")

