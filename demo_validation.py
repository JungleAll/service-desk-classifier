#!/usr/bin/env python3
"""
Валидация сценария демонстрации Service Desk Classifier
Проверяет все ключевые пункты из DEMOSCRIPT.md
"""

import requests
import json
import time
from datetime import datetime

def log(message):
    """Логирование с временной меткой"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def check_service_health():
    """Проверка готовности всех сервисов"""
    log("=== ПРОВЕРКА ГОТОВНОСТИ СИСТЕМЫ ===")
    
    services = {
        "Ingestion Service": "http://localhost:8000/health",
        "ML Service": "http://localhost:8001/health", 
        "Config Service": "http://localhost:8002/health",
        "Output Service": "http://localhost:8003/health"
    }
    
    all_healthy = True
    for name, url in services.items():
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                log(f"✅ {name}: {status}")
            else:
                log(f"❌ {name}: HTTP {response.status_code}")
                all_healthy = False
        except Exception as e:
            log(f"❌ {name}: {e}")
            all_healthy = False
    
    return all_healthy

def episode1_magic_demo():
    """Эпизод 1: Магия - быстрая классификация"""
    log("\n=== ЭПИЗОД 1: МАГИЯ (БЫСТРАЯ КЛАССИФИКАЦИЯ) ===")
    
    test_text = "У меня не работает VPN, не могу подключиться к рабочей сети из дома"
    
    log(f"Действие: Классификация текста через ML API")
    log(f"Текст: '{test_text}'")
    
    try:
        start_time = time.time()
        response = requests.post(
            "http://localhost:8001/classify",
            json={"text": test_text, "return_probabilities": True},
            timeout=10
        )
        response_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            log(f"✅ Ожидаемый результат: Мгновенная классификация")
            log(f"   Предсказанный тип: {data.get('predicted_type')}")
            log(f"   Уверенность: {data.get('confidence', 0):.2%}")
            log(f"   Время обработки: {response_time*1000:.0f}мс")
            log(f"   Решение: {data.get('decision')}")
            
            # Проверяем ожидания
            if response_time < 1.0:  # Меньше секунды
                log("✅ Скорость: Мгновенная обработка достигнута")
            else:
                log("⚠️ Скорость: Обработка медленнее ожидаемой")
                
            if data.get('confidence', 0) > 0.8:
                log("✅ Качество: Высокая уверенность модели")
            else:
                log("⚠️ Качество: Низкая уверенность модели")
                
            return True, data
        else:
            log(f"❌ Ошибка: HTTP {response.status_code}")
            return False, None
            
    except Exception as e:
        log(f"❌ Исключение: {e}")
        return False, None

def episode2_full_pipeline():
    """Эпизод 2: Полный цикл обработки"""
    log("\n=== ЭПИЗОД 2: ПОЛНЫЙ ЦИКЛ ОБРАБОТКИ ===")
    
    ticket_data = {
        "text": "Принтер HP LaserJet не печатает, горит красная лампочка",
        "source": "email",
        "user_id": "demo_user",
        "email": "demo@company.com",
        "priority": "high"
    }
    
    log("Действие: Создание тикета через Ingestion API")
    log(f"Данные: {json.dumps(ticket_data, ensure_ascii=False)}")
    
    try:
        # Создание тикета
        response = requests.post(
            "http://localhost:8000/tickets",
            json=ticket_data,
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            ticket_response = response.json()
            ticket_id = ticket_response.get('ticket_id')
            
            log(f"✅ Тикет создан: {ticket_id}")
            log(f"   Статус: {ticket_response.get('status')}")
            log(f"   Сообщение: {ticket_response.get('message')}")
            
            # Отслеживание статуса
            log("\nДействие: Отслеживание обработки тикета")
            return track_ticket_processing(ticket_id)
            
        else:
            log(f"❌ Ошибка создания тикета: HTTP {response.status_code}")
            log(f"   Ответ: {response.text}")
            return False, None
            
    except Exception as e:
        log(f"❌ Исключение при создании тикета: {e}")
        return False, None

def track_ticket_processing(ticket_id, max_wait=30):
    """Отслеживание обработки тикета"""
    log(f"Ожидаемый результат: Переход статусов queued → processing → classified → completed")
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(f"http://localhost:8000/status/{ticket_id}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                current_status = data.get('status')
                
                if current_status != last_status:
                    log(f"   Статус: {current_status}")
                    last_status = current_status
                
                if current_status == "completed":
                    log("✅ Обработка завершена успешно")
                    log(f"   Предсказанный тип: {data.get('predicted_type')}")
                    log(f"   Уверенность: {data.get('confidence', 0):.2%}")
                    log(f"   Решение: {data.get('decision')}")
                    return True, data
                elif current_status == "failed":
                    log(f"❌ Обработка завершилась с ошибкой: {data.get('error_message')}")
                    return False, data
                    
            time.sleep(2)
            
        except Exception as e:
            log(f"⚠️ Ошибка при проверке статуса: {e}")
            time.sleep(2)
    
    log("⏱️ Таймаут ожидания обработки")
    return False, None

def episode3_config_management():
    """Эпизод 3: Управление конфигурацией"""
    log("\n=== ЭПИЗОД 3: УПРАВЛЕНИЕ КОНФИГУРАЦИЕЙ ===")
    
    # Получение текущей конфигурации
    log("Действие: Получение текущих настроек")
    try:
        response = requests.get("http://localhost:8002/config", timeout=5)
        if response.status_code == 200:
            config = response.json()
            current_threshold = config.get('threshold', 0.7)
            log(f"✅ Текущий порог уверенности: {current_threshold}")
            
            # Изменение порога
            log("Действие: Изменение порога уверенности на 0.99")
            new_threshold = 0.99
            
            update_response = requests.put(
                "http://localhost:8002/config/threshold",
                json={"threshold": new_threshold},
                timeout=5
            )
            
            if update_response.status_code == 200:
                log(f"✅ Порог изменен на {new_threshold}")
                
                # Тестирование с новым порогом
                log("Действие: Тестирование классификации с новым порогом")
                test_text = "У меня не работает VPN, не могу подключиться к рабочей сети из дома"
                
                classify_response = requests.post(
                    "http://localhost:8001/classify",
                    json={"text": test_text},
                    timeout=10
                )
                
                if classify_response.status_code == 200:
                    result = classify_response.json()
                    decision = result.get('decision')
                    confidence = result.get('confidence', 0)
                    
                    log(f"   Уверенность: {confidence:.2%}")
                    log(f"   Решение: {decision}")
                    
                    if decision == "manual-review":
                        log("✅ Ожидаемый результат: Тикет направлен на ручную проверку")
                    else:
                        log("⚠️ Неожиданный результат: Тикет не направлен на ручную проверку")
                
                # Возврат исходного порога
                log(f"Действие: Возврат исходного порога {current_threshold}")
                requests.put(
                    "http://localhost:8002/config/threshold",
                    json={"threshold": current_threshold},
                    timeout=5
                )
                
                return True
            else:
                log(f"❌ Ошибка изменения порога: HTTP {update_response.status_code}")
                return False
        else:
            log(f"❌ Ошибка получения конфигурации: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        log(f"❌ Исключение при работе с конфигурацией: {e}")
        return False

def episode4_batch_processing():
    """Эпизод 4: Пакетная обработка"""
    log("\n=== ЭПИЗОД 4: ПАКЕТНАЯ ОБРАБОТКА ===")
    
    # Создаем небольшой пакет тикетов для тестирования
    batch_tickets = [
        {"text": "Проблема с компьютером", "source": "email"},
        {"text": "Не работает принтер", "source": "chat"},
        {"text": "Нужна помощь с настройкой", "source": "api"},
        {"text": "Заказать новое оборудование", "source": "web"},
        {"text": "Восстановить пароль", "source": "email"}
    ]
    
    log(f"Действие: Отправка пакета из {len(batch_tickets)} тикетов")
    
    try:
        start_time = time.time()
        response = requests.post(
            "http://localhost:8000/tickets/batch",
            json={"tickets": batch_tickets},
            timeout=30
        )
        
        if response.status_code == 202:  # Accepted
            data = response.json()
            processing_time = time.time() - start_time
            
            log(f"✅ Пакет принят к обработке")
            log(f"   Batch ID: {data.get('batch_id')}")
            log(f"   Всего тикетов: {data.get('total')}")
            log(f"   Поставлено в очередь: {data.get('queued')}")
            log(f"   Время приема: {processing_time*1000:.0f}мс")
            
            # Ожидание обработки
            log("Ожидаемый результат: Быстрая обработка всех тикетов")
            time.sleep(10)  # Даем время на обработку
            
            # Проверка результатов
            tickets_response = requests.get(
                "http://localhost:8000/tickets?limit=10&status=completed",
                timeout=5
            )
            
            if tickets_response.status_code == 200:
                tickets_data = tickets_response.json()
                completed_count = len(tickets_data.get('tickets', []))
                log(f"✅ Обработано тикетов: {completed_count}")
                
                if completed_count >= len(batch_tickets):
                    log("✅ Ожидаемый результат: Все тикеты обработаны успешно")
                    return True
                else:
                    log("⚠️ Не все тикеты обработаны")
                    return False
            else:
                log("⚠️ Не удалось проверить результаты обработки")
                return False
        else:
            log(f"❌ Ошибка пакетной обработки: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        log(f"❌ Исключение при пакетной обработке: {e}")
        return False

def validate_output_files():
    """Проверка создания выходных файлов"""
    log("\n=== ПРОВЕРКА ВЫХОДНЫХ ФАЙЛОВ ===")
    
    log("Действие: Проверка создания JSON файлов в output")
    
    try:
        # Проверяем через Docker
        import subprocess
        result = subprocess.run(
            ["docker", "exec", "service-desk-output", "ls", "-la", "/app/output"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            files = result.stdout
            log("✅ Содержимое папки output:")
            for line in files.split('\n'):
                if '.json' in line:
                    log(f"   📄 {line.strip()}")
            
            # Попробуем прочитать один файл
            json_files = [line for line in files.split('\n') if '.json' in line]
            if json_files:
                filename = json_files[0].split()[-1]  # Последний элемент - имя файла
                
                cat_result = subprocess.run(
                    ["docker", "exec", "service-desk-output", "cat", f"/app/output/{filename}"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if cat_result.returncode == 0:
                    try:
                        file_content = json.loads(cat_result.stdout)
                        log(f"✅ Структура JSON файла корректна:")
                        log(f"   ticket_id: {file_content.get('ticket_id')}")
                        log(f"   predicted_type: {file_content.get('predicted_type')}")
                        log(f"   confidence: {file_content.get('confidence')}")
                        return True
                    except json.JSONDecodeError:
                        log("❌ Некорректный JSON в файле")
                        return False
            else:
                log("⚠️ JSON файлы не найдены")
                return False
        else:
            log(f"❌ Ошибка доступа к папке output: {result.stderr}")
            return False
            
    except Exception as e:
        log(f"❌ Исключение при проверке файлов: {e}")
        return False

def main():
    print("="*70)
    print("ВАЛИДАЦИЯ СЦЕНАРИЯ ДЕМОНСТРАЦИИ")
    print("="*70)
    
    results = {}
    
    # Проверка готовности системы
    if not check_service_health():
        log("❌ Система не готова к демонстрации")
        return
    
    # Эпизод 1: Магия
    success, _ = episode1_magic_demo()
    results["Эпизод 1: Магия"] = success
    
    # Эпизод 2: Полный цикл
    success, _ = episode2_full_pipeline()
    results["Эпизод 2: Полный цикл"] = success
    
    # Эпизод 3: Конфигурация
    success = episode3_config_management()
    results["Эпизод 3: Конфигурация"] = success
    
    # Эпизод 4: Пакетная обработка
    success = episode4_batch_processing()
    results["Эпизод 4: Пакетная обработка"] = success
    
    # Проверка выходных файлов
    success = validate_output_files()
    results["Выходные файлы"] = success
    
    # Итоговая сводка
    log("\n" + "="*70)
    log("РЕЗУЛЬТАТЫ ВАЛИДАЦИИ")
    log("="*70)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ ПРОЙДЕН" if result else "❌ НЕ ПРОЙДЕН"
        log(f"{status}: {test_name}")
        if result:
            passed += 1
    
    log(f"\nОбщий результат: {passed}/{total} тестов пройдено")
    
    if passed == total:
        log("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Система готова к демонстрации!")
    else:
        log("⚠️ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ. Требуется доработка.")
    
    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("❌ Валидация прервана пользователем")
    except Exception as e:
        log(f"❌ Критическая ошибка: {e}")
        input("Нажмите Enter для выхода...")
