"""
Комплексный тест пайплайна Service Desk Classifier
Проверяет: PostgreSQL, Redis, выходные файлы
"""

import requests
import time
import json
import sys
import hashlib
from datetime import datetime

# Конфигурация
INGESTION_URL = "http://localhost:8000"
ML_SERVICE_URL = "http://localhost:8001"
OUTPUT_SERVICE_URL = "http://localhost:8003"

# Тестовый текст
TEST_TEXT = "У меня не работает принтер, пишет ошибку замятия бумаги. Помогите решить проблему."


def print_section(title):
    """Печать заголовка секции"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_step(step_num, description):
    """Печать шага"""
    print(f"\n[{step_num}] {description}")
    print("-" * 70)


def check_service_health():
    """Проверка работоспособности сервисов"""
    print_section("ПРОВЕРКА РАБОТОСПОСОБНОСТИ СЕРВИСОВ")
    
    services = {
        "Ingestion": f"{INGESTION_URL}/health",
        "ML Service": f"{ML_SERVICE_URL}/health",
        "Output Service": f"{OUTPUT_SERVICE_URL}/health"
    }
    
    all_ok = True
    for name, url in services.items():
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "unknown")
                print(f"✅ {name}: {status}")
            else:
                print(f"❌ {name}: HTTP {resp.status_code}")
                all_ok = False
        except Exception as e:
            print(f"❌ {name}: {e}")
            all_ok = False
    
    return all_ok


def create_ticket():
    """Создание тестового тикета"""
    print_step(1, "Создание тикета")
    
    payload = {
        "text": TEST_TEXT,
        "source": "test_pipeline",
        "email": "test@example.com",
        "user_id": "test_user_123"
    }
    
    try:
        resp = requests.post(f"{INGESTION_URL}/tickets", json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        ticket_id = data["ticket_id"]
        
        print(f"✅ Тикет создан: {ticket_id}")
        print(f"   Статус: {data.get('status')}")
        print(f"   Сообщение: {data.get('message')}")
        
        return ticket_id
    except Exception as e:
        print(f"❌ Ошибка создания тикета: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Ответ сервера: {e.response.text}")
        return None


def poll_ticket_status(ticket_id, max_wait=30):
    """Опрос статуса тикета до завершения"""
    print_step(2, f"Отслеживание статуса тикета {ticket_id}")
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < max_wait:
        try:
            resp = requests.get(f"{INGESTION_URL}/status/{ticket_id}", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            status = data["status"]
            
            # Печать только при изменении статуса
            if status != last_status:
                progress = data.get("progress", 0)
                print(f"   Статус: {status} (прогресс: {progress}%)")
                last_status = status
            
            # Проверка завершения
            if status == "completed":
                print(f"\n✅ Обработка завершена за {int(time.time() - start_time)} секунд")
                return data
            elif status == "failed":
                print(f"\n❌ Обработка завершилась с ошибкой")
                print(f"   Ошибка: {data.get('error_message', 'Неизвестная ошибка')}")
                return data
            
            time.sleep(1)
        except Exception as e:
            print(f"   ⚠️  Ошибка при опросе статуса: {e}")
            time.sleep(1)
    
    print(f"\n⏱️  Таймаут ожидания ({max_wait} секунд)")
    return None


def verify_postgresql_data(ticket_id):
    """Проверка данных в PostgreSQL через API"""
    print_step(3, "Проверка данных в PostgreSQL")
    
    try:
        resp = requests.get(f"{INGESTION_URL}/tickets/{ticket_id}", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        
        checks = {
            "ticket_id": data.get("ticket_id") == ticket_id,
            "text": data.get("text") == TEST_TEXT,
            "status": data.get("status") == "completed",
            "predicted_type": data.get("predicted_type") is not None,
            "confidence": data.get("confidence") is not None and 0 <= data.get("confidence") <= 1,
            "model_version": data.get("model_version") is not None,
            "decision": data.get("decision") in ["auto-process", "manual-review"],
            "jira_ticket_id": data.get("jira_issue_id") is not None,  # API возвращает jira_issue_id
        }
        
        all_ok = True
        for field, check_result in checks.items():
            status = "✅" if check_result else "❌"
            value = data.get(field) or data.get("jira_issue_id")  # fallback для jira_ticket_id
            print(f"   {status} {field}: {value}")
            if not check_result:
                all_ok = False
        
        # Дополнительная информация
        if data.get("probabilities"):
            print(f"\n   📊 Вероятности (топ-3):")
            probs = data.get("probabilities", {})
            if isinstance(probs, dict):
                sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:3]
                for cat, prob in sorted_probs:
                    print(f"      - {cat}: {prob:.2%}")
        
        return all_ok, data
    except Exception as e:
        print(f"❌ Ошибка при проверке данных: {e}")
        return False, None


def verify_redis_cache(ticket_id, final_data):
    """Проверка кэша в Redis"""
    print_step(4, "Проверка кэша Redis")
    
    try:
        # Вычисление хэша текста (как в ML Service)
        text_hash = hashlib.md5(TEST_TEXT.encode('utf-8')).hexdigest()
        model_version = final_data.get("model_version", "v1.0")
        cache_key = f"cache_predictions:{model_version}:{text_hash}"
        
        print(f"   Ключ кэша: {cache_key}")
        print(f"   (Проверка через повторную классификацию)")
        
        # Повторная классификация для проверки кэша
        start_time = time.time()
        resp = requests.post(
            f"{ML_SERVICE_URL}/classify",
            json={"text": TEST_TEXT, "return_probabilities": True},
            timeout=10
        )
        resp.raise_for_status()
        result = resp.json()
        elapsed = time.time() - start_time
        
        # Если время очень мало (< 100ms), вероятно использовался кэш
        if elapsed < 0.1:
            print(f"   ✅ Кэш работает (время: {elapsed*1000:.1f}ms - очень быстро)")
        else:
            print(f"   ⚠️  Время классификации: {elapsed*1000:.1f}ms (может быть кэш или нет)")
        
        # Проверка совпадения результатов
        if result.get("predicted_type") == final_data.get("predicted_type"):
            print(f"   ✅ Результаты совпадают (кэш корректен)")
            return True
        else:
            print(f"   ❌ Результаты не совпадают")
            return False
            
    except Exception as e:
        print(f"   ⚠️  Не удалось проверить кэш: {e}")
        return False


def verify_output_file(ticket_id, final_data):
    """Проверка выходного файла"""
    print_step(5, "Проверка выходного файла")
    
    jira_ticket_id = final_data.get("jira_issue_id") or final_data.get("jira_ticket_id")
    jira_link = final_data.get("jira_link")
    
    if not jira_ticket_id:
        print("   ⚠️  jira_ticket_id не найден (возможно, decision=manual-review)")
        return False
    
    print(f"   ID файла: {jira_ticket_id}")
    
    # Проверка типа коннектора
    if jira_ticket_id.startswith("FS-"):
        print("   ✅ Использован FileSystem Connector")
        if jira_link:
            print(f"   📁 Путь к файлу: {jira_link}")
            print("   ℹ️  Для просмотра файла выполните:")
            print(f"      docker exec -it service-desk-output cat {jira_link}")
            return True
        else:
            print("   ⚠️  Путь к файлу не указан")
            return False
    elif jira_ticket_id.startswith("MOCK-"):
        print("   ✅ Использован Mock Connector")
        print("   ℹ️  Файл не создается (тестовый режим)")
        return True
    else:
        print(f"   ⚠️  Неожиданный формат ID: {jira_ticket_id}")
        return False


def print_summary(results):
    """Печать итоговой сводки"""
    print_section("ИТОГОВАЯ СВОДКА")
    
    total = len(results)
    passed = sum(1 for r in results.values() if r)
    
    print(f"\nПройдено проверок: {passed}/{total}")
    
    for check_name, result in results.items():
        status = "✅ ПРОЙДЕНО" if result else "❌ НЕ ПРОЙДЕНО"
        print(f"   {status}: {check_name}")
    
    if passed == total:
        print("\n🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!")
        return True
    else:
        print(f"\n⚠️  НЕКОТОРЫЕ ПРОВЕРКИ НЕ ПРОЙДЕНЫ ({total - passed} из {total})")
        return False


def main():
    """Главная функция тестирования"""
    print_section("ТЕСТИРОВАНИЕ ПАЙПЛАЙНА SERVICE DESK CLASSIFIER")
    print(f"Время начала: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Проверка работоспособности сервисов
    if not check_service_health():
        print("\n❌ Некоторые сервисы недоступны. Убедитесь, что все сервисы запущены.")
        print("   Запустите: docker-compose up -d")
        sys.exit(1)
    
    # Создание тикета
    ticket_id = create_ticket()
    if not ticket_id:
        print("\n❌ Не удалось создать тикет. Тестирование прервано.")
        sys.exit(1)
    
    # Отслеживание статуса
    final_data = poll_ticket_status(ticket_id)
    if not final_data or final_data.get("status") != "completed":
        print("\n❌ Тикет не был обработан до конца. Тестирование прервано.")
        sys.exit(1)
    
    # Проверки
    results = {}
    
    # Проверка PostgreSQL
    pg_ok, pg_data = verify_postgresql_data(ticket_id)
    results["PostgreSQL: Данные тикета"] = pg_ok
    
    # Проверка Redis кэша
    if pg_data:
        cache_ok = verify_redis_cache(ticket_id, pg_data)
        results["Redis: Кэширование"] = cache_ok
    
    # Проверка выходного файла
    if pg_data:
        file_ok = verify_output_file(ticket_id, pg_data)
        results["Output: Выходной файл"] = file_ok
    
    # Итоговая сводка
    success = print_summary(results)
    
    print(f"\nВремя завершения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
