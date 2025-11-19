"""Модуль для загрузки и использования ML модели классификации"""

import logging
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder

from .config import (
    CONFIDENCE_THRESHOLD,
    BASE_DIR
)
import os
from .preprocessor import TextPreprocessor

logger = logging.getLogger(__name__)


class ServiceDeskClassifier:
    """Класс для классификации обращений Service Desk"""
    
    def __init__(self):
        """Инициализация классификатора"""
        self.classifier: Optional[LogisticRegression] = None
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.label_encoder: Optional[LabelEncoder] = None
        self.preprocessor: Optional[TextPreprocessor] = None
        self.model_version: str = os.getenv("ML_MODEL_VERSION", "v1.0")
        self.model_config: Optional[Dict] = None
        self.is_loaded: bool = False
        self._paths: Dict[str, str] = {}
        
    def load_model(self) -> bool:
        """
        Загрузка модели из pickle файлов
        
        Returns:
            True если загрузка успешна, False иначе
        """
        try:
            logger.info("Начало загрузки модели...")

            # Определяем директорию по версии - всегда берем из окружения, если доступно
            version = os.getenv("ML_MODEL_VERSION", "v1.0") or "v1.0"
            # Обновляем self.model_version актуальной версией
            self.model_version = version
            models_dir = BASE_DIR / "models" / version

            # Определяем имена файлов модели через переменные окружения
            # По умолчанию используем стабильную версию classifier_smote_new.pkl
            # Можно переключиться на другую версию через переменные окружения:
            # ML_CLASSIFIER_FILE, ML_VECTORIZER_FILE, ML_LABEL_ENCODER_FILE
            classifier_file = os.getenv("ML_CLASSIFIER_FILE", "classifier_smote_new.pkl")
            vectorizer_file = os.getenv("ML_VECTORIZER_FILE", "vectorizer_smote.pkl")
            label_encoder_file = os.getenv("ML_LABEL_ENCODER_FILE", "label_encoder_smote.pkl")
            
            classifier_path = models_dir / classifier_file
            vectorizer_path = models_dir / vectorizer_file
            label_encoder_path = models_dir / label_encoder_file
            config_json_path = models_dir / "config.json"

            # Сначала пытаемся получить пути из БД (особенно важно для v1.1, которая использует файлы из v1.0)
            # Это позволяет использовать файлы из других директорий, если они указаны в БД
            try:
                from shared.database import get_db_cursor
                with get_db_cursor() as cursor:
                    cursor.execute(
                        "SELECT model_path, vectorizer_path, label_encoder_path FROM model_versions WHERE version = %s",
                        (version,)
                    )
                    result = cursor.fetchone()
                    if result:
                        # Используем пути из БД (относительные от BASE_DIR)
                        db_classifier_path = BASE_DIR / result['model_path']
                        db_vectorizer_path = BASE_DIR / result['vectorizer_path']
                        db_label_encoder_path = BASE_DIR / result['label_encoder_path']
                        
                        logger.info(f"Получены пути из БД для версии {version}:")
                        logger.info(f"  classifier: {db_classifier_path}")
                        logger.info(f"  vectorizer: {db_vectorizer_path}")
                        logger.info(f"  label_encoder: {db_label_encoder_path}")
                        
                        if db_classifier_path.exists() and db_vectorizer_path.exists() and db_label_encoder_path.exists():
                            logger.info(f"✅ Использую пути из БД для версии {version}")
                            classifier_path = db_classifier_path
                            vectorizer_path = db_vectorizer_path
                            label_encoder_path = db_label_encoder_path
                            # config.json ищем в той же директории, что и classifier
                            config_json_path = classifier_path.parent / "config.json"
                        else:
                            logger.warning(f"⚠️ Пути из БД не существуют, использую стандартные пути:")
                            logger.warning(f"  classifier: {db_classifier_path} (exists: {db_classifier_path.exists()})")
                            logger.warning(f"  vectorizer: {db_vectorizer_path} (exists: {db_vectorizer_path.exists()})")
                            logger.warning(f"  label_encoder: {db_label_encoder_path} (exists: {db_label_encoder_path.exists()})")
                    else:
                        logger.info(f"Версия {version} не найдена в БД, использую стандартные пути")
            except Exception as e:
                logger.warning(f"Не удалось получить пути из БД, использую стандартные пути: {e}")


            # Проверка существования файлов
            if not classifier_path.exists():
                raise FileNotFoundError(
                    f"Файл модели не найден: {classifier_path}. "
                    f"Проверьте, что файл существует. "
                    f"Проверена стандартная директория: {models_dir}. "
                    f"Также проверена таблица model_versions в БД для версии {version}. "
                    f"По умолчанию используется classifier_smote_new.pkl (стабильная версия). "
                    f"Для использования другой версии установите переменную окружения ML_CLASSIFIER_FILE."
                )
            if not vectorizer_path.exists():
                raise FileNotFoundError(
                    f"Файл векторизатора не найден: {vectorizer_path}. "
                    f"Проверьте, что файл существует. "
                    f"Проверена стандартная директория: {models_dir}. "
                    f"Также проверена таблица model_versions в БД для версии {version}. "
                    f"По умолчанию используется vectorizer_smote.pkl. "
                    f"Для использования другой версии установите переменную окружения ML_VECTORIZER_FILE."
                )
            if not label_encoder_path.exists():
                raise FileNotFoundError(
                    f"Файл энкодера не найден: {label_encoder_path}. "
                    f"Проверьте, что файл существует. "
                    f"Проверена стандартная директория: {models_dir}. "
                    f"Также проверена таблица model_versions в БД для версии {version}. "
                    f"По умолчанию используется label_encoder_smote.pkl. "
                    f"Для использования другой версии установите переменную окружения ML_LABEL_ENCODER_FILE."
                )

            # Загрузка компонентов модели
            logger.info(f"Загрузка модели классификатора: {classifier_path.name}")
            self.classifier = joblib.load(classifier_path)
            
            logger.info(f"Загрузка векторизатора: {vectorizer_path.name}")
            self.vectorizer = joblib.load(vectorizer_path)
            
            logger.info(f"Загрузка энкодера: {label_encoder_path.name}")
            self.label_encoder = joblib.load(label_encoder_path)
            
            # Загрузка конфигурации модели
            if config_json_path.exists():
                with open(config_json_path, 'r', encoding='utf-8') as f:
                    self.model_config = json.load(f)
                    # Версия из окружения имеет приоритет над версией из config.json
                    # self.model_version уже установлен выше из переменной окружения
                    if 'model_version' in self.model_config and not os.getenv("ML_MODEL_VERSION"):
                        # Используем версию из config.json только если не задана в окружении
                        self.model_version = self.model_config['model_version']
            # self.model_version уже установлен из переменной окружения выше

            # Сохраняем используемые пути
            self._paths = {
                "classifier_path": str(classifier_path),
                "vectorizer_path": str(vectorizer_path),
                "label_encoder_path": str(label_encoder_path)
            }
            
            # Инициализация препроцессора
            self.preprocessor = TextPreprocessor()
            
            self.is_loaded = True
            logger.info("Модель успешно загружена")
            
            # Логируем информацию о модели
            if self.label_encoder:
                num_classes = len(self.label_encoder.classes_)
                logger.info(
                    f"✅ Модель загружена: версия {self.model_version}, "
                    f"классификатор: {classifier_file}, векторизатор: {vectorizer_file}, "
                    f"энкодер: {label_encoder_file}, классов: {num_classes}"
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка загрузки модели: {e}", exc_info=True)
            self.is_loaded = False
            return False
    
    def predict(self, text: str, top_n: Optional[int] = None) -> Dict:
        """
        Классификация текста
        
        Args:
            text: Текст для классификации
            
        Returns:
            Словарь с результатами классификации:
            - predicted_type: предсказанный класс
            - confidence: уверенность (максимальная вероятность)
            - probabilities: словарь {класс: вероятность}
            - model_version: версия модели
            - decision: "auto-process" или "manual-review"
        """
        if not self.is_loaded:
            raise RuntimeError("Модель не загружена. Вызовите load_model() сначала.")
        
        if not text or len(text.strip()) < 3:
            raise ValueError("Текст должен содержать минимум 3 символа")
        
        try:
            # Предобработка текста
            processed_text = self.preprocessor.preprocess(text)
            
            if not processed_text or len(processed_text.strip()) == 0:
                raise ValueError("После предобработки текст стал пустым")
            
            # Векторизация
            text_vector = self.vectorizer.transform([processed_text])
            
            # Предсказание вероятностей
            probabilities = self.classifier.predict_proba(text_vector)[0]
            
            # Получение индекса класса с максимальной вероятностью
            predicted_idx = np.argmax(probabilities)
            confidence = float(probabilities[predicted_idx])
            
            # Декодирование класса
            predicted_type = self.label_encoder.inverse_transform([predicted_idx])[0]
            
            # Создание словаря вероятностей для всех классов
            class_names = self.label_encoder.classes_
            probabilities_dict = {
                str(class_name): float(prob) 
                for class_name, prob in zip(class_names, probabilities)
            }
            
            # Определение решения на основе порога уверенности
            decision = "auto-process" if confidence >= CONFIDENCE_THRESHOLD else "manual-review"
            
            result = {
                "predicted_type": str(predicted_type),
                "confidence": confidence,
                "probabilities": probabilities_dict,
                "model_version": self.model_version,
                "decision": decision
            }
            
            logger.info(f"Классификация выполнена: {predicted_type} (confidence: {confidence:.3f})")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при классификации: {e}", exc_info=True)
            raise
    
    def get_model_info(self) -> Dict:
        """
        Получение информации о модели
        
        Returns:
            Словарь с информацией о модели
        """
        info = {
            "model_version": self.model_version,
            "is_loaded": self.is_loaded,
            "classifier_path": self._paths.get("classifier_path"),
            "vectorizer_path": self._paths.get("vectorizer_path"),
            "label_encoder_path": self._paths.get("label_encoder_path"),
        }
        
        if self.label_encoder:
            info["num_classes"] = len(self.label_encoder.classes_)
            info["classes"] = [str(cls) for cls in self.label_encoder.classes_]
        
        if self.model_config:
            info["config"] = self.model_config
        
        return info
    
    def reload_model(self) -> bool:
        """
        Перезагрузка модели (hot reload)
        
        Returns:
            True если перезагрузка успешна, False иначе
        """
        logger.info("Начало перезагрузки модели...")
        # Обновляем версию модели из окружения перед перезагрузкой
        version_from_env = os.getenv("ML_MODEL_VERSION", "v1.0") or "v1.0"
        self.model_version = version_from_env
        logger.info(f"Перезагрузка модели версии: {version_from_env}")
        
        self.is_loaded = False
        self.classifier = None
        self.vectorizer = None
        self.label_encoder = None
        self.preprocessor = None
        
        return self.load_model()

