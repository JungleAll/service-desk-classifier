"""HTTP клиент для взаимодействия с ML и Config Service API"""

import logging
import requests
from typing import Dict, Optional, Any
from datetime import datetime

from .config import (
    ML_SERVICE_URL, 
    CONFIG_SERVICE_URL, 
    INGESTION_SERVICE_URL,
    DASHBOARD_MODE,
    API_TIMEOUT, 
    MOCK_CLASSIFICATION_RESULT, 
    MOCK_HISTORY
)

logger = logging.getLogger(__name__)


class APIClient:
    """Клиент для работы с ML и Config Service API"""
    
    def __init__(self, base_url: str = ML_SERVICE_URL, config_url: str = CONFIG_SERVICE_URL, ingestion_url: str = INGESTION_SERVICE_URL):
        """
        Инициализация клиента
        
        Args:
            base_url: Базовый URL ML Service
            config_url: Базовый URL Config Service
            ingestion_url: Базовый URL Ingestion Service
        """
        self.base_url = base_url.rstrip('/')
        self.config_url = config_url.rstrip('/')
        self.ingestion_url = ingestion_url.rstrip('/')
        self.session = requests.Session()
        self.session.timeout = API_TIMEOUT
        self.mode = DASHBOARD_MODE  # 'demo' или 'production'
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        use_mock: bool = False,
        service: str = "ml"  # "ml" | "config" | "ingestion"
    ) -> Optional[Dict[str, Any]]:
        """
        Выполнение HTTP запроса
        
        Args:
            method: HTTP метод (GET, POST)
            endpoint: Endpoint API
            data: Данные для POST запроса
            use_mock: Использовать mock данные при ошибке
            service: Сервис для запроса ("ml", "config" или "ingestion")
            
        Returns:
            Ответ API или None при ошибке
        """
        if service == "ml":
            base = self.base_url
        elif service == "config":
            base = self.config_url
        elif service == "ingestion":
            base = self.ingestion_url
        else:
            base = self.base_url
        url = f"{base}{endpoint}"
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url, timeout=API_TIMEOUT)
            elif method.upper() == "POST":
                response = self.session.post(
                    url, 
                    json=data, 
                    headers={"Content-Type": "application/json"},
                    timeout=API_TIMEOUT
                )
            else:
                raise ValueError(f"Неподдерживаемый метод: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.ConnectionError:
            logger.error(f"Не удалось подключиться к {url}")
            if use_mock:
                return None
            svc = "ML Service" if service == "ml" else "Config Service"
            raise ConnectionError(f"{svc} недоступен по адресу {url}. Проверьте, что сервис запущен.")
        
        except requests.exceptions.Timeout:
            logger.error(f"Таймаут при запросе к {url}")
            if use_mock:
                return None
            svc = "ML Service" if service == "ml" else "Config Service"
            raise TimeoutError(f"{svc} не отвечает. Повторите попытку позже.")
        
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP ошибка {e.response.status_code}: {e}")
            if use_mock:
                return None
            error_detail = "Неизвестная ошибка"
            try:
                error_data = e.response.json()
                # Обработка разных форматов ошибок
                if isinstance(error_data, dict):
                    error_detail = error_data.get("detail", error_data.get("error", str(e)))
                    # Если detail - это список (Pydantic validation errors)
                    if isinstance(error_detail, list) and len(error_detail) > 0:
                        first_error = error_detail[0]
                        if isinstance(first_error, dict):
                            error_detail = first_error.get("msg", str(first_error))
                else:
                    error_detail = str(error_data)
            except Exception as parse_error:
                logger.warning(f"Не удалось распарсить ошибку: {parse_error}")
                error_detail = str(e)
            raise ValueError(f"Ошибка API ({e.response.status_code}): {error_detail}")
        
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            if use_mock:
                return None
            raise
    
    def classify_text(self, text: str, use_mock: bool = True, mode: Optional[str] = None) -> Dict[str, Any]:
        """
        Классификация текста
        
        Args:
            text: Текст для классификации
            use_mock: Использовать mock данные при ошибке
            mode: Режим работы ('demo' или 'production'). Если None, используется self.mode
            
        Returns:
            Результат классификации
        """
        # Определяем режим работы
        work_mode = mode if mode else self.mode
        
        # Production режим: через Ingestion Service (с логированием в ticket_events)
        if work_mode == "production":
            return self._classify_via_ingestion(text, use_mock)
        
        # Demo режим: прямой вызов ML Service (быстро, без логирования)
        return self._classify_direct(text, use_mock)
    
    def _classify_direct(self, text: str, use_mock: bool = True) -> Dict[str, Any]:
        """
        Прямая классификация через ML Service (demo режим)
        Не создает запись в ticket_events
        """
        try:
            payload = {
                "text": text,
                "return_probabilities": True,
                "top_n": 5
            }
            result = self._make_request("POST", "/classify", payload, use_mock=False, service="ml")
            if result:
                return result
        except Exception as e:
            logger.warning(f"Ошибка при классификации: {e}")
            if use_mock:
                logger.info("Используются mock данные для демонстрации")
                return MOCK_CLASSIFICATION_RESULT.copy()
            raise
        
        # Fallback на mock
        if use_mock:
            return MOCK_CLASSIFICATION_RESULT.copy()
        raise ConnectionError("Не удалось выполнить классификацию")
    
    def _classify_via_ingestion(self, text: str, use_mock: bool = True) -> Dict[str, Any]:
        """
        Классификация через Ingestion Service (production режим)
        Создает запись в ticket_events и обрабатывает через полный pipeline
        """
        try:
            # Шаг 1: Создание тикета через Ingestion Service
            ticket_payload = {
                "text": text,
                "source": "web",  # Допустимые значения: email, chat, api, web
                "user_id": None,
                "email": None,
                "priority": None,
                "category_hint": None,
                "metadata": {"source": "dashboard", "mode": "production"}
            }
            
            ticket_response = self._make_request(
                "POST", 
                "/tickets", 
                ticket_payload, 
                use_mock=False, 
                service="ingestion"
            )
            
            if not ticket_response:
                error_msg = "Не удалось создать тикет через Ingestion Service (пустой ответ)"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            ticket_id = ticket_response.get("ticket_id")
            if not ticket_id:
                raise ValueError("Ingestion Service не вернул ticket_id")
            
            logger.info(f"Тикет {ticket_id} создан через Ingestion Service")
            
            # Шаг 2: Ожидание обработки тикета (polling)
            import time
            max_wait_time = 60  # секунд (увеличено с 30 для сложных случаев)
            poll_interval = 0.5  # секунд
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                status_response = self._make_request(
                    "GET",
                    f"/status/{ticket_id}",
                    use_mock=False,
                    service="ingestion"
                )
                
                if not status_response:
                    time.sleep(poll_interval)
                    continue
                
                status = status_response.get("status")
                predicted_type = status_response.get("predicted_type")
                
                # Если тикет обработан:
                # - "classified" - классификация завершена (worker установил этот статус)
                # - "completed" - полностью обработан (включая отправку в Output Service)
                # Также проверяем наличие predicted_type, что означает завершение классификации
                if status in ["classified", "completed"] or (status == "processing" and predicted_type):
                    # Получаем детали тикета
                    detail_response = self._make_request(
                        "GET",
                        f"/tickets/{ticket_id}",
                        use_mock=False,
                        service="ingestion"
                    )
                    
                    if detail_response:
                        # Преобразуем ответ Ingestion Service в формат ML Service
                        probabilities = detail_response.get("probabilities", {})
                        if isinstance(probabilities, str):
                            import json
                            probabilities = json.loads(probabilities)
                        
                        # Преобразуем probabilities в список для совместимости
                        probabilities_list = [
                            {"category": k, "score": v}
                            for k, v in sorted(probabilities.items(), key=lambda x: x[1], reverse=True)[:5]
                        ]
                        
                        return {
                            "predicted_type": detail_response.get("predicted_type", "Неизвестно"),
                            "confidence": detail_response.get("confidence", 0.0),
                            "probabilities": probabilities_list,
                            "model_version": detail_response.get("model_version", "unknown"),
                            "decision": detail_response.get("decision", "manual-review"),
                            "ticket_id": ticket_id,  # Дополнительное поле для production режима
                            "processing_time_ms": None  # Можно вычислить из created_at и processed_at
                        }
                
                # Если ошибка
                if status == "failed":
                    error_msg = status_response.get("error_message", "Ошибка обработки")
                    raise ValueError(f"Обработка тикета завершилась ошибкой: {error_msg}")
                
                # Ждем перед следующей проверкой
                time.sleep(poll_interval)
            
            # Таймаут ожидания
            raise TimeoutError(f"Таймаут ожидания обработки тикета {ticket_id}")
            
        except Exception as e:
            logger.warning(f"Ошибка при классификации через Ingestion Service: {e}")
            if use_mock:
                logger.info("Используются mock данные для демонстрации")
                return MOCK_CLASSIFICATION_RESULT.copy()
            raise
    
    def get_health(self, use_mock: bool = True) -> Dict[str, Any]:
        """
        Проверка здоровья сервиса
        
        Args:
            use_mock: Использовать mock данные при ошибке
            
        Returns:
            Статус сервиса
        """
        try:
            result = self._make_request("GET", "/health", use_mock=False, service="ml")
            if result:
                return result
        except Exception as e:
            logger.warning(f"Ошибка при проверке здоровья: {e}")
            if use_mock:
                return {
                    "status": "unhealthy",
                    "model_loaded": False,
                    "model_version": None,
                    "message": "ML Service недоступен (используются mock данные)"
                }
            raise
        
        if use_mock:
            return {
                "status": "unhealthy",
                "model_loaded": False,
                "model_version": None,
                "message": "ML Service недоступен"
            }
        return {"status": "unknown", "model_loaded": False}
    
    def get_model_status(self, use_mock: bool = True) -> Dict[str, Any]:
        """
        Получение статуса модели
        
        Args:
            use_mock: Использовать mock данные при ошибке
            
        Returns:
            Информация о модели
        """
        try:
            result = self._make_request("GET", "/model/status", use_mock=False, service="ml")
            if result:
                return result
        except Exception as e:
            logger.warning(f"Ошибка при получении статуса модели: {e}")
            if use_mock:
                return {
                    "model_version": "v1.0",
                    "is_loaded": False,
                    "num_classes": 17,
                    "classes": [
                        "HR: Перевод через увольнение",
                        "HR: Приём",
                        "HR: Техническое увольнение",
                        "HR: Увольнение",
                        "Заказ визиток",
                        "Заказ гостевого пропуска",
                        "Запрос на обслуживание",
                        "Заявка на билет и проживание",
                        "Заявка на выход сотрудника",
                        "Заявка на согласование ВМ",
                        "Изменение персональных данных",
                        "Изменение условий работы",
                        "Подзадача",
                        "Подзадача основные средства",
                        "Подзадача увольнение",
                        "Согласование VDI",
                        "Уведомление о работах"
                    ]
                }
            raise
        
        if use_mock:
            return {
                "model_version": "v1.0",
                "is_loaded": False,
                "num_classes": 17
            }
        return {"model_version": "unknown", "is_loaded": False}
    
    def reload_model(self, use_mock: bool = True) -> Dict[str, Any]:
        """
        Перезагрузка модели (hot reload)
        
        Args:
            use_mock: Использовать mock данные при ошибке
            
        Returns:
            Результат перезагрузки
        """
        try:
            result = self._make_request("POST", "/reload_model", use_mock=False, service="ml")
            if result:
                return result
        except Exception as e:
            logger.warning(f"Ошибка при перезагрузке модели: {e}")
            if use_mock:
                return {
                    "success": False,
                    "message": f"Ошибка при перезагрузке: {str(e)}",
                    "model_version": None
                }
            raise
        
        if use_mock:
            return {
                "success": False,
                "message": "Не удалось перезагрузить модель",
                "model_version": None
            }
        return {"success": False, "message": "Unknown error"}
    
    def is_available(self) -> bool:
        """
        Проверка доступности API
        
        Returns:
            True если API доступен
        """
        try:
            result = self.get_health(use_mock=False)
            return result.get("status") == "healthy"
        except:
            return False

    # -------- Config Service --------
    def get_config(self, use_mock: bool = True) -> Dict[str, Any]:
        """Получить текущую конфигурацию"""
        try:
            result = self._make_request("GET", "/config", use_mock=False, service="config")
            if result:
                return result
        except Exception as e:
            logger.warning(f"Ошибка при получении конфигурации: {e}")
            if use_mock:
                return {
                    "current_model_version": "v1.0",
                    "confidence_threshold": 0.7,
                    "service_enabled": True
                }
            raise
        if use_mock:
            return {
                "current_model_version": "v1.0",
                "confidence_threshold": 0.7,
                "service_enabled": True
            }
        return {}

    def switch_model_version(self, version: str) -> Dict[str, Any]:
        """Переключить активную версию модели через Config Service"""
        payload = {"version": version, "gradual_rollout": False, "rollout_percentage": 100}
        return self._make_request("POST", "/config/model-version", data=payload, use_mock=False, service="config") or {}

