"""FastAPI приложение для Output Service (Port 8003)"""

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
    ErrorResponse,
    SyncTicketRequest,
    SyncBatchRequest,
    SyncJQLRequest,
    SyncAllRequest,
    SyncResultResponse,
    SyncBatchResponse
)
from .config import (
    API_HOST, API_PORT, MAX_RETRY_ATTEMPTS, RETRY_DELAY,
    CONFIG_SERVICE_URL, CONFIG_SERVICE_TIMEOUT,
    JIRA_USER, JIRA_API_TOKEN
)
from .jira_client import JiraClient
from .jira_sync import JiraSyncService
from shared.database import get_db_cursor
from shared.logger import configure_service_logging

# Настройка логирования
logger = configure_service_logging("output")

# Клиент Jira
jira_client = JiraClient()

# Сервис синхронизации с Jira
jira_sync_service = JiraSyncService(jira_client)

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

    def _normalize_text(self, text: Any) -> str:
        """Нормализация текста для правильной кодировки UTF-8
        
        Исправляет проблему, когда UTF-8 текст был прочитан как Windows-1251
        (например, "РЈ РјРµРЅСЏ" вместо "У меня")
        
        Алгоритм исправления:
        1. Если текст содержит искаженные русские символы (типа "РЈ" вместо "У")
        2. Это значит, что UTF-8 байты были интерпретированы как Windows-1251
        3. Исправление: text.encode('latin1').decode('utf-8')
           (latin1 сохраняет байты как есть, затем декодируем как UTF-8)
        """
        if text is None:
            return ""
        if not isinstance(text, str):
            text = str(text)
        
        # Если текст пустой, возвращаем как есть
        if not text:
            return text
        
        # Проверяем, что текст может быть закодирован в UTF-8
        try:
            text.encode('utf-8')
        except UnicodeEncodeError:
            # Если не может быть закодирован, пытаемся исправить
            try:
                if isinstance(text, bytes):
                    return text.decode('utf-8', errors='replace')
                return text.encode('latin1').decode('utf-8', errors='replace')
            except:
                return text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        
        # Проверяем на признаки двойного кодирования (UTF-8 прочитан как Windows-1251)
        # Характерные признаки: последовательности типа "РЈ", "РјРµ", "РЅСЏ" и т.д.
        # Это байты UTF-8 русских букв, интерпретированные как Windows-1251
        try:
            # Если текст содержит символы вне ASCII, проверяем на искажение
            if any(ord(c) > 127 for c in text):
                # Пробуем исправить: encode('latin1') сохраняет байты как есть,
                # затем decode('utf-8') правильно декодирует UTF-8
                fixed = text.encode('latin1').decode('utf-8', errors='replace')
                
                # Проверяем, что исправленный текст содержит нормальные русские буквы
                # (кириллица в диапазоне 0x0400-0x04FF)
                has_cyrillic = any('\u0400' <= c <= '\u04FF' for c in fixed)
                original_has_cyrillic = any('\u0400' <= c <= '\u04FF' for c in text)
                
                # Если исправленный текст содержит кириллицу, а оригинальный нет,
                # значит исправление помогло
                if has_cyrillic and not original_has_cyrillic:
                    return fixed
                # Если оба содержат кириллицу, но исправленный выглядит лучше
                # (меньше искаженных символов), используем исправленный
                elif has_cyrillic and original_has_cyrillic:
                    # Подсчитываем количество нормальных русских букв
                    fixed_cyrillic_count = sum(1 for c in fixed if '\u0400' <= c <= '\u04FF')
                    original_cyrillic_count = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
                    if fixed_cyrillic_count > original_cyrillic_count:
                        return fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        
        return text

    def _normalize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Нормализация всех строковых полей в payload для правильной кодировки"""
        normalized = {}
        for key, value in payload.items():
            if isinstance(value, str):
                normalized[key] = self._normalize_text(value)
            elif isinstance(value, dict):
                normalized[key] = self._normalize_payload(value)
            elif isinstance(value, list):
                normalized[key] = [
                    self._normalize_text(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                normalized[key] = value
        return normalized

    async def process_and_send(self, payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], int]:
        ticket_id = payload.get("ticket_id") or f"tick_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        file_name = f"{ticket_id}_{ts}.json"
        file_path = self.base_dir / file_name
        try:
            # Нормализуем payload перед записью
            normalized_payload = self._normalize_payload(payload)
            # Записываем JSON с правильной кодировкой UTF-8
            json_str = json.dumps(normalized_payload, ensure_ascii=False, indent=2)
            file_path.write_text(json_str, encoding="utf-8")
            external_id = f"FS-{ts}"
            link = str(file_path.resolve())
            return external_id, link, 0
        except Exception as e:
            logger.error(f"FileSystemConnector write error: {e}", exc_info=True)
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
    summary="Обработка результата классификации",
    description="""Обработка результата классификации и отправка в destination (Jira/FileSystem/Mock).
    
**Request:**
- ticket_id: ID тикета (обязательно)
- predicted_type: предсказанный тип (обязательно)
- confidence: уверенность модели (0..1, обязательно)
- decision: решение ('auto-process' | 'manual-review', обязательно)
- model_version: версия модели (обязательно)
- text: текст обращения (обязательно)
- source: источник (опционально)
- user_id: ID пользователя (опционально)
- email: email отправителя (опционально)
- priority: приоритет ('low'|'medium'|'high'|'critical', опционально)
- probabilities: вероятности для всех классов (опционально, Record<string, number>)
- metadata: дополнительные метаданные (опционально)

**Response (200):**
- success: успешно ли обработано
- message: сообщение о результате
- ticket_id: ID тикета
- jira_ticket_id: external_id для всех коннекторов (Jira issue key, FileSystem filename, Mock ID)
- jira_link: ссылка для Jira, путь к файлу для FileSystem, null для Mock
- status: 'completed'
- processed_at: время обработки (ISO datetime, опционально)
- retry_count: количество попыток (опционально)

**Поведение:**
- Получает конфигурацию из Config Service API (GET /config) с fallback на БД
- Определяет приоритет на основе decision:
  - decision='auto-process' → auto_process_priority (default: 'medium')
  - decision='manual-review' → manual_review_priority (default: 'low')
- При decision='auto-process' — публикация в целевую систему через выбранный коннектор:
  - DESTINATION_TYPE=jira → JiraConnector (создает тикет через Jira REST API или Service Desk API)
  - DESTINATION_TYPE=filesystem → FileSystemConnector (сохраняет JSON в OUTPUT_DIR)
  - DESTINATION_TYPE=mock → MockConnector (генерирует MOCK-{timestamp})
- При decision='manual-review' — только обновление БД, без отправки
- Обновляет запись в ticket_events (status='completed', external_id, link, priority, sent_to_jira_at)
- Записывает в audit_logs (action, status, details, retry_count)"""
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
            # Нормализуем текст для правильной кодировки
            # (FileSystemConnector будет дополнительно нормализовать, но лучше сделать это заранее)
            normalized_text = request.text
            normalized_predicted_type = request.predicted_type
            
            summary = f"[{normalized_predicted_type}] {normalized_text[:100]}"
            description = f"""
Текст обращения: {normalized_text}

Предсказанный тип: {normalized_predicted_type}
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
                "predicted_type": normalized_predicted_type,
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


@app.get(
    "/health",
    tags=["Health"],
    summary="Healthcheck",
    description="""Проверка работоспособности сервиса (Output).
    
**Response (200|503):**
- status: 'healthy' | 'unhealthy'
- postgresql: 'connected' | 'disconnected' - статус подключения к PostgreSQL
- jira_enabled: включена ли интеграция с Jira (boolean)

**Статус 503:** возвращается, если PostgreSQL недоступен"""
)
async def health_check():
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


# ============================================================================
# Endpoints для синхронизации данных из Jira
# ============================================================================

@app.post(
    "/sync/jira/ticket",
    response_model=SyncResultResponse,
    tags=["Jira Sync"],
    summary="Синхронизация одного тикета из Jira",
    description="""Синхронизация одного тикета из Jira с PostgreSQL.
    
**Request:**
- jira_ticket_id: ключ тикета в Jira (например, SD-123, обязательно)
- ticket_id: ID тикета в нашей системе (опционально, будет найден автоматически)
- category_field: имя custom field для категории в Jira (опционально, например, "customfield_10001")

**Response (200):**
- success: успешно ли выполнена синхронизация
- jira_ticket_id: ключ тикета в Jira
- ticket_id: ID тикета в нашей системе (опционально)
- updated_fields: список обновленных полей (actual_type, feedback_status, training_ready и т.д.)
- errors: список ошибок при синхронизации

**Поведение:**
- Получает данные тикета из Jira по jira_ticket_id
- Извлекает категорию из Jira (custom field, labels, components, issue type)
- Если категория отличается от predicted_type, обновляет actual_type в PostgreSQL
- Помечает тикет как training_ready, если decision='manual-review' и actual_type установлена
- Обновляет feedback_status='incorrect' и feedback_correct_type, если категория отличается

**Ошибки:**
- 500: ошибка синхронизации
- 404: тикет не найден в БД"""
)
async def sync_ticket_from_jira(request: SyncTicketRequest) -> SyncResultResponse:
    """
    Синхронизация одного тикета из Jira
    
    - Получает данные тикета из Jira по jira_ticket_id
    - Извлекает категорию из Jira (custom field, labels, components и т.д.)
    - Обновляет actual_type в PostgreSQL, если категория отличается от predicted_type
    - Помечает тикет как training_ready, если decision='manual-review'
    """
    try:
        result = await jira_sync_service.sync_ticket_from_jira(
            jira_ticket_id=request.jira_ticket_id,
            ticket_id=request.ticket_id,
            category_field=request.category_field
        )
        
        return SyncResultResponse(**result)
        
    except Exception as e:
        logger.error(f"Ошибка при синхронизации тикета: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при синхронизации тикета: {str(e)}"
        )


@app.post(
    "/sync/jira/batch",
    response_model=SyncBatchResponse,
    tags=["Jira Sync"],
    summary="Пакетная синхронизация тикетов из Jira",
    description="""Пакетная синхронизация тикетов из Jira с PostgreSQL.
    
**Request:**
- jira_ticket_ids: список ключей тикетов в Jira (обязательно, string[])
- category_field: имя custom field для категории (опционально)

**Response (200):**
- total: общее количество тикетов
- successful: успешно синхронизировано
- failed: не удалось синхронизировать
- details: детали по каждому тикету (SyncResultResponse[])

**Поведение:**
- Синхронизирует каждый тикет из списка
- Возвращает статистику по успешным и неудачным синхронизациям
- Детали по каждому тикету содержат информацию об обновленных полях"""
)
async def sync_batch_from_jira(request: SyncBatchRequest) -> SyncBatchResponse:
    """Пакетная синхронизация тикетов из Jira"""
    try:
        result = await jira_sync_service.sync_multiple_tickets(
            jira_ticket_ids=request.jira_ticket_ids,
            category_field=request.category_field
        )
        
        return SyncBatchResponse(**result)
        
    except Exception as e:
        logger.error(f"Ошибка при пакетной синхронизации: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при пакетной синхронизации: {str(e)}"
        )


@app.post(
    "/sync/jira/jql",
    response_model=SyncBatchResponse,
    tags=["Jira Sync"],
    summary="Синхронизация тикетов по JQL запросу",
    description="""Синхронизация тикетов из Jira по JQL запросу.
    
**Request:**
- jql: JQL запрос для поиска тикетов в Jira (обязательно)
- category_field: имя custom field для категории (опционально)
- max_results: максимальное количество тикетов (default: 100, max: 1000)

**Response (200):** аналогично POST /sync/jira/batch

**Примеры JQL:**
- "project = SD AND status = Resolved"
- "project = SD AND updated >= -7d"
- "project = SD AND labels = 'training-ready'"

**Поведение:**
- Выполняет поиск тикетов в Jira по JQL запросу
- Синхронизирует найденные тикеты с PostgreSQL
- Возвращает статистику синхронизации"""
)
async def sync_jql_from_jira(request: SyncJQLRequest) -> SyncBatchResponse:
    """
    Синхронизация тикетов по JQL запросу
    
    Примеры JQL:
    - "project = SD AND status = Resolved"
    - "project = SD AND updated >= -7d"
    - "project = SD AND labels = 'training-ready'"
    """
    try:
        result = await jira_sync_service.sync_tickets_by_jql(
            jql=request.jql,
            category_field=request.category_field,
            max_results=request.max_results
        )
        
        return SyncBatchResponse(**result)
        
    except Exception as e:
        logger.error(f"Ошибка при синхронизации по JQL: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при синхронизации по JQL: {str(e)}"
        )


@app.post(
    "/sync/jira/all",
    response_model=SyncBatchResponse,
    tags=["Jira Sync"],
    summary="Синхронизация всех тикетов с jira_ticket_id",
    description="""Синхронизация всех тикетов из БД, у которых есть jira_ticket_id.
    
**Request:**
- category_field: имя custom field для категории (опционально)
- limit: максимальное количество тикетов (default: 100, max: 1000)

**Response (200):** аналогично POST /sync/jira/batch

**Поведение:**
- Находит все тикеты в БД, у которых есть jira_ticket_id
- Синхронизирует их с данными из Jira
- Сортирует по sent_to_jira_at DESC, затем по created_at DESC"""
)
async def sync_all_from_jira(request: SyncAllRequest) -> SyncBatchResponse:
    """Синхронизация всех тикетов с jira_ticket_id"""
    try:
        result = await jira_sync_service.sync_tickets_with_jira_ids(
            category_field=request.category_field,
            limit=request.limit
        )
        
        return SyncBatchResponse(**result)
        
    except Exception as e:
        logger.error(f"Ошибка при синхронизации всех тикетов: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при синхронизации всех тикетов: {str(e)}"
        )


# ============================================================================
# Endpoints для получения данных из Jira (без синхронизации)
# ============================================================================

@app.get(
    "/jira/ticket/{jira_ticket_id}",
    tags=["Jira"],
    summary="Получить данные тикета из Jira",
    description="""Получение данных тикета из Jira без синхронизации с PostgreSQL.
    
**Path parameters:**
- jira_ticket_id: ключ тикета в Jira (например, SD-123)

**Query parameters:**
- expand: список полей для расширения через запятую (опционально, например, "fields,changelog")

**Response (200):**
- Данные тикета из Jira REST API (полный объект issue)
- Содержит fields, key, id, self и другие стандартные поля Jira API
- Формат ответа соответствует Jira REST API v3

**Поведение:**
- Получает данные тикета из Jira через REST API
- Не выполняет синхронизацию с PostgreSQL
- Используется для просмотра данных тикета без обновления БД

**Ошибки:**
- 404: тикет не найден в Jira или нет доступа
- 503: Jira клиент отключен или не настроен
- 500: ошибка запроса к Jira"""
)
async def get_jira_ticket(
    jira_ticket_id: str,
    expand: Optional[str] = None
) -> Dict[str, Any]:
    """
    Получение данных тикета из Jira
    
    Args:
        jira_ticket_id: Ключ тикета в Jira (например, SD-123)
        expand: Список полей для расширения (например, "fields,changelog")
    
    Returns:
        Данные тикета из Jira API
    """
    if not jira_client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jira клиент отключен или не настроен"
        )
    
    try:
        issue_data = await jira_client.get_issue(jira_ticket_id, expand=expand)
        
        if not issue_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Тикет {jira_ticket_id} не найден в Jira или нет доступа"
            )
        
        return issue_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении тикета из Jira: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении тикета из Jira: {str(e)}"
        )


@app.get(
    "/jira/search",
    tags=["Jira"],
    summary="Поиск тикетов в Jira по JQL",
    description="""Поиск тикетов в Jira по JQL запросу без синхронизации с PostgreSQL.
    
**Query parameters:**
- jql: JQL запрос (обязательный, например, "project = SD AND status = Resolved")
- fields: список полей через запятую (опционально, например, "key,summary,status"). Если не указан, возвращаются все поля
- max_results: максимальное количество результатов (default: 50, max: 1000)
- start_at: смещение для пагинации (default: 0)

**Response (200):**
- expand: расширенные поля
- startAt: смещение
- maxResults: максимальное количество результатов
- total: общее количество найденных тикетов
- issues: массив тикетов из Jira (формат соответствует Jira REST API v3)

**Поведение:**
- Выполняет поиск тикетов в Jira по JQL запросу
- Не выполняет синхронизацию с PostgreSQL
- Используется для просмотра и фильтрации тикетов в Jira

**Примеры JQL:**
- "project = SD AND status = Resolved"
- "project = SD AND updated >= -7d"
- "project = SD AND assignee = currentUser()"
- "project = SD AND labels = 'training-ready'"

**Ошибки:**
- 503: Jira клиент отключен или не настроен
- 500: ошибка запроса к Jira или не удалось выполнить поиск"""
)
async def search_jira_tickets(
    jql: str,
    fields: Optional[str] = None,
    max_results: int = 50,
    start_at: int = 0
) -> Dict[str, Any]:
    """
    Поиск тикетов в Jira по JQL запросу
    
    Args:
        jql: JQL запрос (например, "project = SD AND status = Resolved")
        fields: Список полей через запятую (например, "key,summary,status")
        max_results: Максимальное количество результатов (default: 50, max: 1000)
        start_at: Смещение для пагинации (default: 0)
    
    Returns:
        Результаты поиска из Jira API
    """
    if not jira_client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jira клиент отключен или не настроен"
        )
    
    if max_results > 1000:
        max_results = 1000
    
    try:
        fields_list = fields.split(",") if fields else None
        search_result = await jira_client.search_issues(
            jql=jql,
            fields=fields_list,
            max_results=max_results,
            start_at=start_at
        )
        
        if not search_result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось выполнить поиск в Jira"
            )
        
        return search_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при поиске тикетов в Jira: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при поиске тикетов в Jira: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    log_level = os.getenv("LOG_LEVEL", "INFO").lower()
    uvicorn.run(
        "app:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level=log_level
    )

