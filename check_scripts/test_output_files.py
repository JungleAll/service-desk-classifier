"""
Проверка выходных файлов, созданных Output Service
"""

import subprocess
import json
import sys
import os
from datetime import datetime
from pathlib import Path


def print_section(title):
    """Печать заголовка секции"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def run_docker_command(cmd):
    """Выполнение команды в Docker контейнере"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Таймаут выполнения команды"
    except Exception as e:
        return False, "", str(e)


def list_output_files():
    """Список всех файлов в директории output"""
    print_section("СПИСОК ВЫХОДНЫХ ФАЙЛОВ")
    
    # Проверка наличия контейнера
    success, _, _ = run_docker_command("docker ps --filter name=service-desk-output --format '{{.Names}}'")
    if not success:
        print("❌ Контейнер service-desk-output не запущен")
        return []
    
    # Получение списка файлов
    success, stdout, stderr = run_docker_command(
        "docker exec service-desk-output ls -lh /app/output 2>/dev/null || echo 'Directory not found'"
    )
    
    if not success or "Directory not found" in stdout:
        print("⚠️  Директория /app/output не найдена или пуста")
        print("   Убедитесь, что DESTINATION_TYPE=filesystem")
        return []
    
    lines = stdout.strip().split('\n')
    if len(lines) <= 1:  # Только заголовок
        print("⚠️  Директория пуста")
        return []
    
    files = []
    print("\n📁 Файлы в /app/output:")
    for line in lines[1:]:  # Пропускаем заголовок
        if line.strip():
            parts = line.split()
            if len(parts) >= 9:
                size = parts[4]
                filename = parts[-1]
                files.append(filename)
                print(f"   - {filename} ({size})")
    
    return files


def read_output_file(filename):
    """Чтение и проверка содержимого файла"""
    print_section(f"ПРОВЕРКА ФАЙЛА: {filename}")
    
    # Чтение файла из контейнера
    success, stdout, stderr = run_docker_command(
        f"docker exec service-desk-output cat /app/output/{filename}"
    )
    
    if not success:
        print(f"❌ Не удалось прочитать файл: {stderr}")
        return None
    
    try:
        data = json.loads(stdout)
        print("✅ Файл содержит валидный JSON")
        return data
    except json.JSONDecodeError as e:
        print(f"❌ Файл не является валидным JSON: {e}")
        return None


def verify_file_structure(data, filename):
    """Проверка структуры файла"""
    print_section("ПРОВЕРКА СТРУКТУРЫ ФАЙЛА")
    
    required_fields = [
        "ticket_id",
        "summary",
        "description",
        "priority",
        "predicted_type",
        "confidence",
        "model_version",
        "decision"
    ]
    
    optional_fields = [
        "email",
        "user_id",
        "probabilities",
        "metadata"
    ]
    
    all_ok = True
    
    print("\nОбязательные поля:")
    for field in required_fields:
        if field in data:
            value = data[field]
            if isinstance(value, str) and len(value) > 50:
                print(f"   ✅ {field}: {value[:50]}...")
            else:
                print(f"   ✅ {field}: {value}")
        else:
            print(f"   ❌ {field}: ОТСУТСТВУЕТ")
            all_ok = False
    
    print("\nОпциональные поля:")
    for field in optional_fields:
        if field in data:
            value = data[field]
            if isinstance(value, dict):
                print(f"   ✅ {field}: (объект с {len(value)} полями)")
            elif isinstance(value, str) and len(value) > 50:
                print(f"   ✅ {field}: {value[:50]}...")
            else:
                print(f"   ✅ {field}: {value}")
        else:
            print(f"   ⚠️  {field}: отсутствует (не критично)")
    
    # Проверка формата ticket_id
    ticket_id = data.get("ticket_id", "")
    if ticket_id.startswith("tick_"):
        print(f"\n✅ Формат ticket_id корректен: {ticket_id}")
    else:
        print(f"\n⚠️  Неожиданный формат ticket_id: {ticket_id}")
    
    # Проверка decision
    decision = data.get("decision")
    if decision in ["auto-process", "manual-review"]:
        print(f"✅ Decision корректен: {decision}")
    else:
        print(f"❌ Неожиданный decision: {decision}")
        all_ok = False
    
    # Проверка confidence
    confidence = data.get("confidence")
    if confidence is not None and 0 <= confidence <= 1:
        print(f"✅ Confidence корректен: {confidence:.2%}")
    else:
        print(f"❌ Неожиданный confidence: {confidence}")
        all_ok = False
    
    # Проверка probabilities
    probabilities = data.get("probabilities")
    if probabilities:
        if isinstance(probabilities, dict):
            print(f"✅ Probabilities: {len(probabilities)} категорий")
            print("   Топ-5 категорий:")
            sorted_probs = sorted(probabilities.items(), key=lambda x: x[1], reverse=True)[:5]
            for cat, prob in sorted_probs:
                print(f"      - {cat}: {prob:.2%}")
        else:
            print(f"⚠️  Probabilities не является словарем")
    
    return all_ok


def save_file_locally(filename, data):
    """Сохранение файла локально для демонстрации"""
    output_dir = Path("test_outputs")
    output_dir.mkdir(exist_ok=True)
    
    local_path = output_dir / filename
    with open(local_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Файл сохранен локально: {local_path.absolute()}")
    return local_path


def main():
    """Главная функция"""
    print_section("ПРОВЕРКА ВЫХОДНЫХ ФАЙЛОВ")
    print(f"Время начала: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Получение списка файлов
    files = list_output_files()
    
    if not files:
        print("\n⚠️  Файлы не найдены. Убедитесь, что:")
        print("   1. DESTINATION_TYPE=filesystem в docker-compose.yml")
        print("   2. Тикеты были успешно обработаны")
        print("   3. Output Service работает корректно")
        sys.exit(1)
    
    # Проверка последнего файла (или указанного)
    filename = sys.argv[1] if len(sys.argv) > 1 else files[-1]
    
    if filename not in files:
        print(f"❌ Файл {filename} не найден в списке")
        sys.exit(1)
    
    # Чтение и проверка файла
    data = read_output_file(filename)
    if not data:
        sys.exit(1)
    
    # Проверка структуры
    structure_ok = verify_file_structure(data, filename)
    
    # Сохранение локально
    local_path = save_file_locally(filename, data)
    
    # Итог
    print_section("ИТОГ")
    if structure_ok:
        print("✅ Все проверки пройдены успешно")
        print(f"\n📄 Файл для демонстрации: {local_path.absolute()}")
    else:
        print("⚠️  Некоторые проверки не пройдены")
    
    print(f"\nВремя завершения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()

