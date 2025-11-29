"""
Проверка работы Redis (очереди и кэш)
"""

import redis
import json
import sys
import hashlib
from datetime import datetime

# Параметры подключения
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB_QUEUES = 0  # Очереди
REDIS_DB_CACHE = 1   # Кэш


def print_section(title):
    """Печать заголовка секции"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def connect_redis(db):
    """Подключение к Redis"""
    try:
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=db,
            decode_responses=True,
            socket_connect_timeout=5
        )
        client.ping()
        return client
    except Exception as e:
        print(f"❌ Ошибка подключения к Redis (DB {db}): {e}")
        return None


def check_queues():
    """Проверка очередей (DB 0)"""
    print_section("ПРОВЕРКА ОЧЕРЕДЕЙ (Redis DB 0)")
    
    client = connect_redis(REDIS_DB_QUEUES)
    if not client:
        return False
    
    try:
        # Проверка pending_tickets
        pending_len = client.llen("pending_tickets")
        print(f"\n📦 Очередь pending_tickets: {pending_len} задач")
        
        if pending_len > 0:
            print("\n   Последние 5 задач:")
            items = client.lrange("pending_tickets", -5, -1)
            for i, item in enumerate(items, 1):
                try:
                    data = json.loads(item)
                    ticket_id = data.get("ticket_id", "N/A")
                    print(f"      {i}. ticket_id: {ticket_id}")
                except:
                    print(f"      {i}. (невалидный JSON)")
        
        # Проверка failed_tickets
        failed_len = client.llen("failed_tickets")
        print(f"\n❌ Очередь failed_tickets: {failed_len} задач")
        
        if failed_len > 0:
            print("\n   Последние 3 задачи:")
            items = client.lrange("failed_tickets", -3, -1)
            for i, item in enumerate(items, 1):
                try:
                    data = json.loads(item)
                    ticket_id = data.get("ticket_id", "N/A")
                    print(f"      {i}. ticket_id: {ticket_id}")
                except:
                    print(f"      {i}. (невалидный JSON)")
        
        # Информация о базе данных
        info = client.info()
        print(f"\n📊 Информация о Redis (DB 0):")
        print(f"   Использовано памяти: {info.get('used_memory_human', 'N/A')}")
        print(f"   Подключений: {info.get('connected_clients', 0)}")
        print(f"   Всего ключей: {client.dbsize()}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при проверке очередей: {e}")
        return False


def check_cache():
    """Проверка кэша (DB 1)"""
    print_section("ПРОВЕРКА КЭША (Redis DB 1)")
    
    client = connect_redis(REDIS_DB_CACHE)
    if not client:
        return False
    
    try:
        # Поиск всех ключей кэша
        pattern = "cache_predictions:*"
        keys = client.keys(pattern)
        
        print(f"\n💾 Найдено ключей кэша: {len(keys)}")
        
        if keys:
            print("\n   Примеры ключей (первые 5):")
            for i, key in enumerate(keys[:5], 1):
                # Извлечение версии модели и хэша из ключа
                parts = key.split(":")
                if len(parts) >= 3:
                    version = parts[1]
                    text_hash = parts[2][:8] + "..."
                    print(f"      {i}. Версия: {version}, Хэш: {text_hash}")
                
                # Проверка TTL
                ttl = client.ttl(key)
                if ttl > 0:
                    minutes = ttl // 60
                    seconds = ttl % 60
                    print(f"         TTL: {minutes}м {seconds}с")
                elif ttl == -1:
                    print(f"         TTL: без ограничения")
                else:
                    print(f"         TTL: истек")
            
            # Просмотр одного значения для примера
            if keys:
                example_key = keys[0]
                value = client.get(example_key)
                if value:
                    try:
                        data = json.loads(value)
                        print(f"\n   Пример значения (ключ: {example_key}):")
                        print(f"      predicted_type: {data.get('predicted_type')}")
                        print(f"      confidence: {data.get('confidence', 0):.2%}")
                        print(f"      model_version: {data.get('model_version')}")
                        print(f"      decision: {data.get('decision')}")
                    except:
                        print(f"      (невалидный JSON)")
        
        # Информация о базе данных
        info = client.info()
        print(f"\n📊 Информация о Redis (DB 1):")
        print(f"   Использовано памяти: {info.get('used_memory_human', 'N/A')}")
        print(f"   Подключений: {info.get('connected_clients', 0)}")
        print(f"   Всего ключей: {client.dbsize()}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при проверке кэша: {e}")
        return False


def check_cache_for_text(text, model_version="v1.0"):
    """Проверка кэша для конкретного текста"""
    print_section(f"ПРОВЕРКА КЭША ДЛЯ ТЕКСТА")
    
    client = connect_redis(REDIS_DB_CACHE)
    if not client:
        return False
    
    try:
        # Вычисление хэша (как в ML Service)
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        cache_key = f"cache_predictions:{model_version}:{text_hash}"
        
        print(f"\n   Текст: {text[:50]}...")
        print(f"   Хэш: {text_hash}")
        print(f"   Ключ кэша: {cache_key}")
        
        value = client.get(cache_key)
        if value:
            print(f"\n   ✅ Ключ найден в кэше")
            data = json.loads(value)
            print(f"      predicted_type: {data.get('predicted_type')}")
            print(f"      confidence: {data.get('confidence', 0):.2%}")
            
            ttl = client.ttl(cache_key)
            if ttl > 0:
                minutes = ttl // 60
                seconds = ttl % 60
                print(f"      TTL: {minutes}м {seconds}с")
            
            return True
        else:
            print(f"\n   ⚠️  Ключ не найден в кэше")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def main():
    """Главная функция"""
    print_section("ПРОВЕРКА REDIS")
    print(f"Время начала: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    # Проверки
    results["Очереди (DB 0)"] = check_queues()
    results["Кэш (DB 1)"] = check_cache()
    
    # Проверка кэша для конкретного текста (если указан)
    if len(sys.argv) > 1:
        text = sys.argv[1]
        model_version = sys.argv[2] if len(sys.argv) > 2 else "v1.0"
        results["Кэш для текста"] = check_cache_for_text(text, model_version)
    
    # Итог
    print_section("ИТОГ")
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for check_name, result in results.items():
        status = "✅" if result else "❌"
        print(f"   {status} {check_name}")
    
    print(f"\nПройдено: {passed}/{total}")
    
    print(f"\nВремя завершения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()

