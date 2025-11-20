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
print(f"=== Redis Cache Analysis (DB 1) ===")
print(f"Total cache keys: {len(keys)}\n")

if keys:
    print("=== Cache Keys ===")
    for i, key in enumerate(keys[:5], 1):  # Показываем первые 5
        parts = key.split(":")
        if len(parts) >= 3:
            version = parts[1]
            text_hash = parts[2][:8] + "..."
            print(f"{i}. Version: {version}, Hash: {text_hash}")
            
            # TTL
            ttl = client.ttl(key)
            if ttl > 0:
                minutes = ttl // 60
                seconds = ttl % 60
                print(f"   TTL: {minutes}m {seconds}s")
            elif ttl == -1:
                print(f"   TTL: no expiration")
            else:
                print(f"   TTL: expired")
    
    # Детальный анализ первого ключа
    if keys:
        key = keys[0]
        print(f"\n=== Detailed Analysis: {key} ===")
        
        value = client.get(key)
        if value:
            data = json.loads(value)
            print(f"Predicted Type: {data.get('predicted_type')}")
            print(f"Confidence: {data.get('confidence', 0):.2%}")
            print(f"Model Version: {data.get('model_version')}")
            print(f"Decision: {data.get('decision')}")
            
            # Probabilities
            if 'probabilities' in data:
                probs = data['probabilities']
                if isinstance(probs, dict):
                    print(f"\nProbabilities ({len(probs)} categories):")
                    sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:5]
                    for cat, prob in sorted_probs:
                        print(f"  {cat}: {prob:.2%}")

# Статистика Redis
info = client.info()
print(f"\n=== Redis Statistics (DB 1) ===")
print(f"Used Memory: {info.get('used_memory_human', 'N/A')}")
print(f"Connected Clients: {info.get('connected_clients', 0)}")
print(f"Total Keys: {client.dbsize()}")

