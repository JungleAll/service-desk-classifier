"""FastAPI приложение для Output Service (Port 8003)"""

import logging
import asyncio
import json
import os
from datetime import datetime
from typing import Optional, Any, Protocol, runtime_checkable, Dict, Tuple
from contextlib import asynccontextmanager
from pathlib import Path
import httpx

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .models import (
    ProcessResultRequest,
    ProcessResultResponse,
    ErrorResponse
)
from .config import (
    API_HOST, API_PORT, LOG_LEVEL, MAX_RETRY_ATTEMPTS, RETRY_DELAY,
    CONFIG_SERVICE_URL, CONFIG_SERVICE_TIMEOUT,
    JIRA_USER, JIRA_API_TOKEN
)
from .jira_client import JiraClient
from shared.database import get_db_cursor

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Клиент Jira
jira_client = JiraClient()

# ----------------------------
# Destination Connectors
# ----------------------------

@runtime_checkable
class ITicketDestination(Protocol):
    """Интерфейс назначения отправки результатов"""

    async def process_and_send(self, payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], int]:
        """Обработать результат и отправить в целевую систему. Возвращает (external_id, link, retry_count)"""
        ...

    async def validate_connection(self) -> bool:
        """Проверка доступности назначения"""
        ...

    def get_name(self) -> str:
        """Имя коннектора"""
        ...


class FileSystemConnector(ITicketDestination):
    """Коннектор для сохранения результатов в файловую систему (JSON)"""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or os.getenv("OUTPUT_DIR", "./out"))
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_name(self) -> str:
        return "filesystem"

    async def validate_connection(self) -> bool:
        try:
            test_path = self.base_dir / ".probe"
            test_path.write_text("ok", encoding="utf-8")
            test_path.unlink(missing_ok=True)
            return True
        except Exception as e:
            logger.error(f"FileSystemConnector validate failed: {e}")
            return False

    async def process_and_send(self, payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], int]:
        ticket_id = payload.get("ticket_id") or f"tick_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        file_name = f"{ticket_id}_{ts}.json"
        file_path = self.base_dir / file_name
        try:
            file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            external_id = f"FS-{ts}"
            link = str(file_path.resolve())
            return external_id, link, 0
        except Exception as e:
            logger.error(f"FileSystemConnector write error: {e}")
            return None, None, 0


class MockConnector(ITicketDestination):
    """Моковый коннектор - ничего не отправляет, генерирует фальшивый ID"""

    def get_name(self) -> str:
        return "mock"

    async def validate_connection(self) -> bool:
        return True

    async def process_and_send(self, payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], int]:
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        external_id = f"MOCK-{ts}"
        return external_id, None, 0


class JiraConnector(ITicketDestination):
    """Коннектор для отправки в Jira"""

    def get_name(self) -> str:
        return "jira"

    async def validate_connection(self) -> bool:
        """Проверка доступности Jira конфигурации"""
        try:
            # Получение конфигурации из Config Service с fallback на БД
            jira_enabled = await get_config_value("jira_enabled", False)
            jira_url = await get_config_value("jira_url", "")
            
            # Проверка базовых настроек
            if not jira_enabled or not jira_url:
                logger.debug(f"Jira отключен или URL не настроен: enabled={jira_enabled}, url={bool(jira_url)}")
                return False
            
            # Проверка переменных окружения (для обратной совместимости)
            if not jira_client.enabled:
                logger.debug("Jira клиент отключен через переменные окружения")
                return False
            
            # Опциональная проверка подключения к Jira (если включена)
            validate_connection = os.getenv("JIRA_VALIDATE_CONNECTION", "false").lower() == "true"
            if validate_connection:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        response = await client.get(
                            f"{jira_url}/rest/api/3/myself",
                            auth=(JIRA_USER, JIRA_API_TOKEN),
                            timeout=5.0
                        )
                        if response.status_code == 200:
                            logger.debug("Jira подключение проверено успешно")
                            return True
                        else:
                            logger.warning(f"Jira проверка вернула статус {response.status_code}")
                            return False
                except Exception as e:
                    logger.warning(f"Ошибка при проверке подключения к Jira: {e}")
                    return False
            
            # Если проверка подключения отключена, просто проверяем конфигурацию
            return True
        except Exception as e:
            logger.error(f"JiraConnector validate failed: {e}")
            return False

    async def process_and_send(self, payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], int]:
        summary = payload.get("summary") or ""
        description = payload.get("description") or ""
        priority = payload.get("priority")
        ticket_id = payload.get("ticket_id") or ""
        external_id, link, retry_count = await send_to_jira_with_retry(
            ticket_id=ticket_id,
            summary=summary,
            description=description,
            priority=priority,
            max_attempts=MAX_RETRY_ATTEMPTS
        )
        return external_id, link, retry_count


class DestinationFactory:
    """Фабрика для создания коннекторов назначения"""

    @staticmethod
    def create() -> ITicketDestination:
        dest_type = os.getenv("DESTINATION_TYPE", "filesystem").strip().lower()
        if dest_type == "jira":
            return JiraConnector()
        if dest_type in ("fs", "filesystem", "file"):
            return FileSystemConnector()
        if dest_type == "mock":
            return MockConnector()
        logger.warning(f"Unknown DESTINATION_TYPE '{dest_type}', fallback to FileSystemConnector")
        return FileSystemConnector()

# Глобальный выбранный коннектор
_destination: ITicketDestination = DestinationFactory.create()


def _parse_config_value(value: str) -> Any:
    """Парсинг значения конфигурации с преобразованием типов"""
    if isinstance(value, str):
        if value.lower() == 'true':
            return True
        elif value.lower() == 'false':
            return False
        try:
            if '.' in value:
                return float(value)
            else:
                return int(value)
        except ValueError:
            return value
    return value


def get_config_value_from_db(key: str, default: Any = None) -> Any:
    """Получение значения конфигурации из БД (fallback метод)"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT value FROM configuration WHERE key = %s", (key,))
            result = cursor.fetchone()
            if result:
                return _parse_config_value(result['value'])
            return default
    except Exception as e:
        logger.error(f"Ошибка при получении конфигурации {key} из БД: {e}")
        return default


async def get_config_from_service() -> Optional[Dict[str, Any]]:
    """
    Получение конфигурации из Config Service API
    
    Returns:
        Словарь конфигурации или None при ошибке
    """
    try:
        async with httpx.AsyncClient(timeout=CONFIG_SERVICE_TIMEOUT) as client:
            response = await client.get(f"{CONFIG_SERVICE_URL}/config")
            if response.status_code == 200:
                config = response.json()
                logger.debug(f"Конфигурация получена из Config Service: {list(config.keys())}")
                return config
            else:
                logger.warning(f"Config Service вернул статус {response.status_code}")
                return None
    except httpx.TimeoutException:
        logger.warning(f"Таймаут при запросе к Config Service ({CONFIG_SERVICE_URL})")
        return None
    except httpx.ConnectError:
        logger.warning(f"Не удалось подключиться к Config Service ({CONFIG_SERVICE_URL})")
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении конфигурации из Config Service: {e}")
        return None


async def get_config_value(key: str, default: Any = None) -> Any:
    """
    Получение значения конфигурации с приоритетом Config Service API
    
    Сначала пытается получить из Config Service, при недоступности использует БД как fallback.
    
    Args:
        key: Ключ конфигурации
        default: Значение по умолчанию
        
    Returns:
        Значение конфигурации
    """
    # Попытка получить из Config Service
    config = await get_config_from_service()
    if config is not None:
        value = config.get(key, default)
        if value is not None:
            logger.debug(f"Конфигурация {key} получена из Config Service: {value}")
            return value
    
    # Fallback на БД
    logger.debug(f"Используется fallback на БД для конфигурации {key}")
    return get_config_value_from_db(key, default)


async def send_to_jira_with_retry(
    ticket_id: str,
    summary: str,
    description: str,
    priority: Optional[str] = None,
    max_attempts: int = MAX_RETRY_ATTEMPTS
) -> tuple[Optional[str], Optional[str], int]:
    """
    Отправка в Jira с повторными попытками
    
    Returns:
        (jira_ticket_id, jira_link, retry_count)
    """
    # Получение конфигурации Jira из Config Service с fallback на БД
    jira_url = await get_config_value("jira_url", "")
    
    for attempt in range(1, max_attempts + 1):
        try:
            jira_ticket_id = await jira_client.create_ticket(
                summary=summary,
                description=description,
                priority=priority
            )
            
            if jira_ticket_id:
                # Формирование ссылки на Jira
                jira_link = f"{jira_url}/browse/{jira_ticket_id}" if jira_url else None
                
                # Логирование успешной отправки
                with get_db_cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO audit_logs (ticket_id, action, service_name, status, details)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        ticket_id,
                        "jira_created",
                        "output",
                        "success",
                        json.dumps({"jira_ticket_id": jira_ticket_id, "attempt": attempt})
                    ))
                return (jira_ticket_id, jira_link, attempt)
            else:
                # Логирование неудачной попытки
                with get_db_cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO audit_logs (ticket_id, action, service_name, status, details, retry_count)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        ticket_id,
                        "jira_created",
                        "output",
                        "retry",
                        json.dumps({"attempt": attempt}),
                        attempt
                    ))
                
                if attempt < max_attempts:
                    await asyncio.sleep(RETRY_DELAY)
                    logger.warning(f"Попытка {attempt} не удалась, повтор через {RETRY_DELAY} сек...")
        except Exception as e:
            logger.error(f"Ошибка при попытке {attempt} отправки в Jira: {e}")
            if attempt < max_attempts:
                await asyncio.sleep(RETRY_DELAY)
    
    # Все попытки исчерпаны
    with get_db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO audit_logs (ticket_id, action, service_name, status, details, retry_count)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            ticket_id,
            "jira_created",
            "output",
            "failed",
            json.dumps({"max_attempts": max_attempts}),
            max_attempts
        ))
    
    return (None, None, max_attempts)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("Запуск Output Service...")
    # Инициализация и валидация назначения
    global _destination
    dest_ok = await _destination.validate_connection()
    logger.info(f"Destination selected: '{_destination.get_name()}', valid={dest_ok}")
    yield
    logger.info("Остановка Output Service...")


# Создание FastAPI приложения
app = FastAPI(
    title="Service Desk Output API",
    description="API для обработки результатов классификации и отправки в Jira",
    version="1.0.0",
    lifespan=lifespan
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """Глобальный обработчик ошибок"""
    logger.error(f"Необработанная ошибка: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "detail": str(exc)
        }
    )


@app.get("/", tags=["Root"])
async def root():
    """Корневой endpoint"""
    return {
        "service": "Service Desk Output API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.post(
    "/process_result",
    response_model=ProcessResultResponse,
    tags=["Processing"],
    summary="Обработать результат классификации",
    description="Обрабатывает результат классификации и отправляет в Jira"
)
async def process_result(request: ProcessResultRequest) -> ProcessResultResponse:
    """
    Обработка результата классификации
    
    - Обновляет запись в ticket_events
    - Отправляет в назначение (Jira/FileSystem/Mock)
    - Логирует в audit_logs
    """
    try:
        jira_ticket_id = None
        jira_link = None
        retry_count = 0
        
        # Определение приоритета
        priority = request.priority
        if not priority:
            # Получение приоритета из Config Service на основе решения
            if request.decision == "auto-process":
                priority = await get_config_value("auto_process_priority", "medium")
            else:
                priority = await get_config_value("manual_review_priority", "low")
        
        # Отправка в выбранное назначение при auto-process
        if request.decision == "auto-process":
            summary = f"[{request.predicted_type}] {request.text[:100]}"
            description = f"""
Текст обращения: {request.text}

Предсказанный тип: {request.predicted_type}
Уверенность: {request.confidence:.2%}
Версия модели: {request.model_version}
Решение: {request.decision}
            """.strip()
            
            if request.email:
                description += f"\nEmail отправителя: {request.email}"
            if request.user_id:
                description += f"\nID пользователя: {request.user_id}"
            
            # Общий payload для destination
            destination_payload = {
                "ticket_id": request.ticket_id,
                "summary": summary,
                "description": description,
                "priority": priority,
                "predicted_type": request.predicted_type,
                "confidence": request.confidence,
                "model_version": request.model_version,
                "decision": request.decision,
                "email": request.email,
                "user_id": request.user_id,
                "probabilities": request.probabilities,
                "metadata": request.metadata
            }

            external_id, link, retry_count = await _destination.process_and_send(destination_payload)
            jira_ticket_id = external_id
            jira_link = link
        
        # Обновление записи в ticket_events
        processed_at = datetime.utcnow()
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    UPDATE ticket_events
                    SET status = 'completed',
                        predicted_type = %s,
                        confidence = %s,
                        decision = %s,
                        model_version = %s,
                        probabilities = %s,
                        priority = %s,
                        email = %s,
                        metadata = %s,
                        jira_ticket_id = %s,
                        jira_link = %s,
                        processed_at = %s,
                        sent_to_jira_at = CASE WHEN %s IS NOT NULL THEN %s ELSE sent_to_jira_at END,
                        retry_count = %s,
                        updated_at = %s
                        WHERE ticket_id = %s
                """, (
                    request.predicted_type,
                    request.confidence,
                    request.decision,
                    request.model_version,
                    json.dumps(request.probabilities) if request.probabilities else None,
                    priority,
                    request.email,
                    json.dumps(request.metadata) if request.metadata else None,
                    jira_ticket_id,
                    jira_link,
                    processed_at,
                    jira_ticket_id,
                    processed_at if jira_ticket_id else None,
                    retry_count,
                    processed_at,
                    request.ticket_id
                ))
        except Exception as db_error:
            logger.error(f"Ошибка при обновлении ticket_events для {request.ticket_id}: {db_error}")
            # Пытаемся повторно с новым подключением
            try:
                from shared.database import init_pool
                init_pool()  # Переинициализация пула
                with get_db_cursor() as cursor:
                    cursor.execute("""
                        UPDATE ticket_events
                        SET status = 'completed',
                            predicted_type = %s,
                            confidence = %s,
                            decision = %s,
                            model_version = %s,
                            probabilities = %s,
                            priority = %s,
                            email = %s,
                            metadata = %s,
                            jira_ticket_id = %s,
                            jira_link = %s,
                            processed_at = %s,
                            sent_to_jira_at = CASE WHEN %s IS NOT NULL THEN %s ELSE sent_to_jira_at END,
                            retry_count = %s,
                            updated_at = %s
                            WHERE ticket_id = %s
                    """, (
                        request.predicted_type,
                        request.confidence,
                        request.decision,
                        request.model_version,
                        json.dumps(request.probabilities) if request.probabilities else None,
                        priority,
                        request.email,
                        json.dumps(request.metadata) if request.metadata else None,
                        jira_ticket_id,
                        jira_link,
                        processed_at,
                        jira_ticket_id,
                        processed_at if jira_ticket_id else None,
                        retry_count,
                        processed_at,
                        request.ticket_id
                    ))
                logger.info(f"Успешно обновлено ticket_events для {request.ticket_id} после повторной попытки")
            except Exception as retry_error:
                logger.error(f"Повторная попытка обновления ticket_events также не удалась: {retry_error}")
                raise
        
        # Логирование в audit_logs (не критично, если не удастся)
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO audit_logs (ticket_id, action, service_name, status, details)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    request.ticket_id,
                    "classification_completed",
                    "output",
                    "success",
                    json.dumps({
                        "predicted_type": request.predicted_type,
                        "confidence": request.confidence,
                        "decision": request.decision,
                        "jira_ticket_id": jira_ticket_id
                    })
                ))
        except Exception as audit_error:
            logger.warning(f"Не удалось записать в audit_logs для {request.ticket_id}: {audit_error}")
        
        logger.info(f"Результат классификации обработан для ticket {request.ticket_id}")
        
        # Формирование ответа
        processed_at_str = processed_at.isoformat()
        
        if jira_ticket_id:
            return ProcessResultResponse(
                success=True,
                message="Result processed and sent to Jira",
                ticket_id=request.ticket_id,
                jira_ticket_id=jira_ticket_id,
                jira_link=jira_link,
                status="completed",
                processed_at=processed_at_str,
                retry_count=retry_count
            )
        else:
            return ProcessResultResponse(
                success=True,
                message="Result processed",
                ticket_id=request.ticket_id,
                jira_ticket_id=None,
                jira_link=None,
                status="completed",
                processed_at=processed_at_str,
                retry_count=retry_count
            )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке результата: {e}", exc_info=True)
        
        # Логирование ошибки
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO error_logs (service_name, error_type, error_message, ticket_id)
                    VALUES (%s, %s, %s, %s)
                """, ("output", "ProcessResultError", str(e), request.ticket_id))
        except:
            pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обработке результата: {str(e)}"
        )


@app.get("/health", tags=["Health"])
async def health_check():
    """Проверка работоспособности сервиса"""
    try:
        from shared.database import get_db_connection
        with get_db_connection():
            db_ok = True
    except:
        db_ok = False
    
    status_code = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if db_ok else "unhealthy",
            "postgresql": "connected" if db_ok else "disconnected",
            "jira_enabled": jira_client.enabled
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level=LOG_LEVEL.lower()
    )

