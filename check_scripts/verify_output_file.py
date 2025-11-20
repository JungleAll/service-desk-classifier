import json
import subprocess

# Имя файла для проверки
filename = "tick_583b380d_20251119T063936.json"

print("=== Output File Verification ===\n")

# Чтение файла из контейнера с правильной кодировкой
result = subprocess.run(
    f"docker exec service-desk-output cat /app/output/{filename}",
    shell=True,
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='ignore'
)

if result.returncode != 0:
    print(f"Error reading file: {result.stderr}")
    exit(1)

if not result.stdout:
    print("Error: File is empty or could not be read")
    exit(1)

try:
    data = json.loads(result.stdout)
    print(f"File: {filename}")
    print(f"Status: Valid JSON\n")
    
    # Проверка обязательных полей
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
    
    print("=== Required Fields ===")
    all_required = True
    for field in required_fields:
        if field in data:
            value = data[field]
            if isinstance(value, str) and len(value) > 50:
                print(f"  [OK] {field}: {value[:50]}...")
            else:
                print(f"  [OK] {field}: {value}")
        else:
            print(f"  [MISSING] {field}")
            all_required = False
    
    print("\n=== Optional Fields ===")
    for field in optional_fields:
        if field in data:
            value = data[field]
            if isinstance(value, dict):
                print(f"  [OK] {field}: (object with {len(value)} fields)")
            elif isinstance(value, str) and len(value) > 50:
                print(f"  [OK] {field}: {value[:50]}...")
            else:
                print(f"  [OK] {field}: {value}")
        else:
            print(f"  [NOT SET] {field} (optional)")
    
    # Проверка формата ticket_id
    print("\n=== Format Checks ===")
    ticket_id = data.get("ticket_id", "")
    if ticket_id.startswith("tick_"):
        print(f"  [OK] ticket_id format: {ticket_id}")
    else:
        print(f"  [ERROR] Unexpected ticket_id format: {ticket_id}")
    
    # Проверка decision
    decision = data.get("decision")
    if decision in ["auto-process", "manual-review"]:
        print(f"  [OK] decision: {decision}")
    else:
        print(f"  [ERROR] Unexpected decision: {decision}")
    
    # Проверка confidence
    confidence = data.get("confidence")
    if confidence is not None and 0 <= confidence <= 1:
        print(f"  [OK] confidence: {confidence:.2%}")
    else:
        print(f"  [ERROR] Invalid confidence: {confidence}")
    
    # Проверка probabilities
    probabilities = data.get("probabilities")
    if probabilities:
        if isinstance(probabilities, dict):
            print(f"  [OK] probabilities: {len(probabilities)} categories")
            print("\n  Top 5 categories:")
            sorted_probs = sorted(probabilities.items(), key=lambda x: x[1], reverse=True)[:5]
            for cat, prob in sorted_probs:
                print(f"    - {cat}: {prob:.2%}")
        else:
            print(f"  [ERROR] probabilities is not a dict")
    
    # Проверка summary и description
    print("\n=== Content Checks ===")
    summary = data.get("summary", "")
    if summary.startswith("[") and "]" in summary:
        print(f"  [OK] summary format: starts with category in brackets")
    else:
        print(f"  [WARNING] summary format might be incorrect")
    
    description = data.get("description", "")
    if "Текст обращения:" in description or "Предсказанный тип:" in description:
        print(f"  [OK] description contains required sections")
    else:
        print(f"  [WARNING] description might be missing required sections")
    
    # Итоговая оценка
    print("\n=== Verification Result ===")
    if all_required:
        print("  [SUCCESS] All required fields are present")
        print("  [SUCCESS] File structure is valid")
        print("  [SUCCESS] File is ready for demonstration")
    else:
        print("  [FAILURE] Some required fields are missing")
    
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON - {e}")
    exit(1)
