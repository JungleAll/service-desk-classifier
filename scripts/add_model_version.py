#!/usr/bin/env python3
"""
Скрипт для добавления новой версии модели в базу данных

Использование:
    python scripts/add_model_version.py --version v1.1 \
        --classifier models/v1.1/classifier.pkl \
        --vectorizer models/v1.1/vectorizer.pkl \
        --encoder models/v1.1/label_encoder.pkl \
        --accuracy 0.98 \
        --f1_score 0.975
"""

import argparse
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.database import get_db_cursor


def add_model_version(
    version: str,
    classifier_path: str,
    vectorizer_path: str,
    label_encoder_path: str,
    accuracy: float = None,
    f1_score: float = None,
    is_active: bool = False
):
    """
    Добавление новой версии модели в БД
    
    Args:
        version: Версия модели (например, 'v1.1')
        classifier_path: Путь к файлу классификатора (относительно корня проекта)
        vectorizer_path: Путь к файлу векторизатора
        label_encoder_path: Путь к файлу энкодера меток
        accuracy: Точность модели (опционально)
        f1_score: F1-score модели (опционально)
        is_active: Активировать ли версию сразу (по умолчанию False)
    """
    # Проверка существования файлов
    base_dir = project_root
    classifier_full_path = base_dir / classifier_path
    vectorizer_full_path = base_dir / vectorizer_path
    encoder_full_path = base_dir / label_encoder_path
    
    missing_files = []
    if not classifier_full_path.exists():
        missing_files.append(f"  - {classifier_path}")
    if not vectorizer_full_path.exists():
        missing_files.append(f"  - {vectorizer_path}")
    if not encoder_full_path.exists():
        missing_files.append(f"  - {label_encoder_path}")
    
    if missing_files:
        print("❌ Ошибка: Следующие файлы не найдены:")
        for file in missing_files:
            print(file)
        print(f"\nПроверьте пути относительно корня проекта: {base_dir}")
        return False
    
    # Добавление записи в БД
    try:
        with get_db_cursor() as cursor:
            # Проверка существования версии
            cursor.execute(
                "SELECT version FROM model_versions WHERE version = %s",
                (version,)
            )
            existing = cursor.fetchone()
            
            if existing:
                print(f"⚠️  Версия {version} уже существует в БД.")
                response = input("Обновить существующую запись? (y/n): ")
                if response.lower() != 'y':
                    print("Отменено.")
                    return False
                
                # Обновление существующей записи
                cursor.execute("""
                    UPDATE model_versions 
                    SET 
                        model_path = %s,
                        vectorizer_path = %s,
                        label_encoder_path = %s,
                        accuracy = %s,
                        f1_score = %s,
                        is_active = %s
                    WHERE version = %s
                """, (
                    classifier_path,
                    vectorizer_path,
                    label_encoder_path,
                    accuracy,
                    f1_score,
                    is_active,
                    version
                ))
                print(f"✅ Запись для версии {version} обновлена.")
            else:
                # Вставка новой записи
                cursor.execute("""
                    INSERT INTO model_versions (
                        version, 
                        model_path, 
                        vectorizer_path, 
                        label_encoder_path, 
                        accuracy, 
                        f1_score, 
                        is_active
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    version,
                    classifier_path,
                    vectorizer_path,
                    label_encoder_path,
                    accuracy,
                    f1_score,
                    is_active
                ))
                print(f"✅ Модель {version} успешно добавлена в БД.")
            
            # Если версия активирована, обновляем флаги других версий
            if is_active:
                cursor.execute("""
                    UPDATE model_versions 
                    SET is_active = FALSE 
                    WHERE version != %s AND is_active = TRUE
                """, (version,))
                cursor.execute("""
                    UPDATE model_versions 
                    SET activated_at = CURRENT_TIMESTAMP
                    WHERE version = %s
                """, (version,))
                print(f"✅ Версия {version} активирована (другие версии деактивированы).")
            
            # Вывод информации о добавленной версии
            cursor.execute("""
                SELECT * FROM model_versions WHERE version = %s
            """, (version,))
            result = cursor.fetchone()
            
            print("\n📋 Информация о версии:")
            print(f"  Версия: {result['version']}")
            print(f"  Классификатор: {result['model_path']}")
            print(f"  Векторизатор: {result['vectorizer_path']}")
            print(f"  Энкодер: {result['label_encoder_path']}")
            if result['accuracy']:
                print(f"  Accuracy: {result['accuracy']:.4f}")
            if result['f1_score']:
                print(f"  F1-score: {result['f1_score']:.4f}")
            print(f"  Активна: {'Да' if result['is_active'] else 'Нет'}")
            
            return True
            
    except Exception as e:
        print(f"❌ Ошибка при добавлении версии в БД: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Добавление новой версии модели в базу данных",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Добавление версии v1.1 с метриками
  python scripts/add_model_version.py --version v1.1 \\
      --classifier models/v1.1/classifier_smote_new.pkl \\
      --vectorizer models/v1.1/vectorizer_smote.pkl \\
      --encoder models/v1.1/label_encoder_smote.pkl \\
      --accuracy 0.98 --f1_score 0.975

  # Добавление и активация версии
  python scripts/add_model_version.py --version v1.1 \\
      --classifier models/v1.1/classifier.pkl \\
      --vectorizer models/v1.1/vectorizer.pkl \\
      --encoder models/v1.1/encoder.pkl \\
      --activate

  # Обновление существующей версии
  python scripts/add_model_version.py --version v1.1 \\
      --classifier models/v1.1/new_classifier.pkl \\
      --vectorizer models/v1.1/vectorizer.pkl \\
      --encoder models/v1.1/encoder.pkl
        """
    )
    
    parser.add_argument(
        '--version',
        required=True,
        help='Версия модели (например, v1.1)'
    )
    parser.add_argument(
        '--classifier',
        required=True,
        help='Путь к файлу классификатора (относительно корня проекта)'
    )
    parser.add_argument(
        '--vectorizer',
        required=True,
        help='Путь к файлу векторизатора (относительно корня проекта)'
    )
    parser.add_argument(
        '--encoder',
        required=True,
        help='Путь к файлу энкодера меток (относительно корня проекта)'
    )
    parser.add_argument(
        '--accuracy',
        type=float,
        help='Точность модели (accuracy)'
    )
    parser.add_argument(
        '--f1-score',
        dest='f1_score',
        type=float,
        help='F1-score модели'
    )
    parser.add_argument(
        '--activate',
        action='store_true',
        help='Активировать версию сразу (деактивирует другие версии)'
    )
    
    args = parser.parse_args()
    
    # Нормализация путей (убираем лишние слеши)
    classifier_path = args.classifier.replace('\\', '/').strip('/')
    vectorizer_path = args.vectorizer.replace('\\', '/').strip('/')
    encoder_path = args.encoder.replace('\\', '/').strip('/')
    
    success = add_model_version(
        version=args.version,
        classifier_path=classifier_path,
        vectorizer_path=vectorizer_path,
        label_encoder_path=encoder_path,
        accuracy=args.accuracy,
        f1_score=args.f1_score,
        is_active=args.activate
    )
    
    if success:
        print("\n✅ Готово!")
        if not args.activate:
            print("\n💡 Для активации версии используйте:")
            print(f"   curl -X POST http://localhost:8002/config/model-version \\")
            print(f"     -H 'Content-Type: application/json' \\")
            print(f"     -d '{{\"version\": \"{args.version}\"}}'")
        sys.exit(0)
    else:
        print("\n❌ Не удалось добавить версию модели.")
        sys.exit(1)


if __name__ == "__main__":
    main()

