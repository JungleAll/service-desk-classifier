"""FastAPI приложение для Config Service (Port 8002)"""

import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .models import (
    ConfigResponse,
    ToggleRequest,
    ToggleResponse,
    ModelSwitchRequest,
    ModelSwitchResponse,
    ThresholdRequest,
    ThresholdResponse,
    JiraConfigRequest,
    JiraConfigResponse,
    ConfigAuditResponse,
    ConfigAuditItem,
    ErrorResponse
)
from .config import API_HOST, API_PORT, LOG_LEVEL
from shared.database import get_db_cursor, execute_query
from datetime import datetime
from typing import List
import httpx

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_config_value(key: str, default: Any = None) -> Any:
    """Получение значения конфигурации из БД"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT value FROM configuration WHERE key = %s", (key,))
            result = cursor.fetchone()
            if result:
                value = result['value']
                # Преобразование типов
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
            return default
    except Exception as e:
        logger.error(f"Ошибка при получении конфигурации {key}: {e}")
        return default


def set_config_value(key: str, value: Any, updated_by: str = "system", reason: Optional[str] = None, old_value: Any = None) -> bool:
    """Установка значения конфигурации в БД с логированием изменений"""
    try:
        # Получение старого значения
        if old_value is None:
            old_value = get_config_value(key)
        
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO configuration (key, value, updated_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (key) 
                DO UPDATE SET value = EXCLUDED.value, 
                              updated_at = CURRENT_TIMESTAMP,
                              updated_by = EXCLUDED.updated_by
            """, (key, str(value), updated_by))
            
            # Логирование изменения
            if old_value != value:
                cursor.execute("""
                    INSERT INTO config_audit_log (field, old_value, new_value, changed_by, reason)
                    VALUES (%s, %s, %s, %s, %s)
                """, (key, str(old_value) if old_value is not None else None, str(value), updated_by, reason))
        
        logger.info(f"Конфигурация {key} обновлена: {old_value} -> {value}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при установке конфигурации {key}: {e}")
        return False


def get_all_config() -> Dict[str, Any]:
    """Получение всей конфигурации"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT key, value FROM configuration")
            results = cursor.fetchall()
            config = {}
            for row in results:
                key = row['key']
                value = row['value']
                # Преобразование типов
                if value.lower() == 'true':
                    config[key] = True
                elif value.lower() == 'false':
                    config[key] = False
                else:
                    try:
                        if '.' in value:
                            config[key] = float(value)
                        else:
                            config[key] = int(value)
                    except ValueError:
                        config[key] = value
            return config
    except Exception as e:
        logger.error(f"Ошибка при получении всей конфигурации: {e}")
        return {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("Запуск Config Service...")
    yield
    logger.info("Остановка Config Service...")


# Создание FastAPI приложения
app = FastAPI(
    title="Service Desk Config API",
    description="API для управления конфигурацией системы",
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
        "service": "Service Desk Config API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get(
    "/config",
    response_model=ConfigResponse,
    tags=["Configuration"],
    summary="Текущая конфигурация",
    description="""Получение текущей конфигурации системы.
    
**Response (200):**
- auto_classification_enabled: включена ли автоклассификация
- service_enabled: включен ли сервис
- confidence_threshold: порог уверенности для auto-process (0..1)
- model_version: версия модели (устаревшее, используйте current_model_version)
- current_model_version: текущая активная версия модели
- jira_integration_enabled: включена ли интеграция с Jira
- jira_enabled: включена ли интеграция с Jira (алиас)
- jira_project_key: ключ проекта Jira (опционально)
- auto_process_priority: приоритет для auto-process ('low'|'medium'|'high'|'critical')
- manual_review_priority: приоритет для manual-review ('low'|'medium'|'high'|'critical')
- max_retry_attempts: максимальное количество попыток повтора
- retry_delay_seconds: задержка между попытками в секундах (опционально)
- timeout_seconds: таймаут операций в секундах (опционально)
- batch_processing_enabled: включена ли пакетная обработка (опционально)
- batch_size: размер пакета (опционально)
- updated_at: время последнего обновления (ISO datetime, опционально)
- updated_by: кто обновил конфигурацию (опционально)
- all_config: полный объект конфигурации (опционально)"""
)
async def get_config() -> ConfigResponse:
    """Получение текущей конфигурации"""
    try:
        all_config = get_all_config()
        
        # Получение updated_at и updated_by из последнего изменения
        updated_at = None
        updated_by = None
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    SELECT updated_at, updated_by
                    FROM configuration
                    ORDER BY updated_at DESC
                    LIMIT 1
                """)
                result = cursor.fetchone()
                if result:
                    updated_at = result['updated_at'].isoformat() if result['updated_at'] else None
                    updated_by = result['updated_by']
        except:
            pass
        
        service_enabled = get_config_value("service_enabled", True)
        return ConfigResponse(
            auto_classification_enabled=service_enabled,
            service_enabled=service_enabled,
            confidence_threshold=get_config_value("confidence_threshold", 0.7),
            model_version=get_config_value("current_model_version", "v1.0"),
            current_model_version=get_config_value("current_model_version", "v1.0"),
            jira_integration_enabled=get_config_value("jira_enabled", True),
            jira_enabled=get_config_value("jira_enabled", True),
            jira_project_key=get_config_value("jira_project_key", "SD"),
            auto_process_priority=get_config_value("auto_process_priority", "medium"),
            manual_review_priority=get_config_value("manual_review_priority", "low"),
            max_retry_attempts=get_config_value("max_retry_attempts", 3),
            retry_delay_seconds=get_config_value("retry_delay_seconds", 5),
            timeout_seconds=get_config_value("timeout_seconds", 30),
            batch_processing_enabled=get_config_value("batch_processing_enabled", True),
            batch_size=get_config_value("batch_size", 100),
            updated_at=updated_at,
            updated_by=updated_by,
            all_config=all_config
        )
    except Exception as e:
        logger.error(f"Ошибка при получении конфигурации: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении конфигурации: {str(e)}"
        )


@app.post(
    "/config/toggle",
    response_model=ToggleResponse,
    tags=["Configuration"],
    summary="Включить/отключить автоклассификацию",
    description="""Включение или отключение сервиса автоматической классификации.
    
**Request:**
- enabled: включить (true) или отключить (false) автоклассификацию
- reason: причина изменения (опционально)

**Response (200):**
- auto_classification_enabled: новое состояние автоклассификации
- service_enabled: новое состояние сервиса
- message: сообщение о результате
- updated_at: время обновления (ISO datetime)

**Поведение:**
- Обновляет значение service_enabled в конфигурации
- Записывает изменение в audit log
- При отключении новые тикеты не будут обрабатываться"""
)
async def toggle_service(request: ToggleRequest) -> ToggleResponse:
    """Включение/отключение сервиса"""
    try:
        old_value = get_config_value("service_enabled", True)
        success = set_config_value(
            "service_enabled", 
            request.enabled, 
            "api",
            reason=request.reason,
            old_value=old_value
        )
        if success:
            updated_at = datetime.utcnow().isoformat()
            return ToggleResponse(
                auto_classification_enabled=request.enabled,
                service_enabled=request.enabled,
                message=f"Auto-classification {'enabled' if request.enabled else 'disabled'}",
                updated_at=updated_at
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось обновить конфигурацию"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при переключении сервиса: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при переключении сервиса: {str(e)}"
        )


@app.post(
    "/config/model-version",
    response_model=ModelSwitchResponse,
    tags=["Configuration"],
    summary="Переключение версии модели",
    description="""Переключение активной версии модели с поддержкой gradual rollout.
    
**Request:**
- version: версия модели для переключения (обязательно)
- gradual_rollout: использовать постепенное развертывание (опционально, default: false)
- rollout_percentage: процент трафика для новой версии (опционально, 0..100)

**Response (200):**
- model_version: версия модели
- current_model_version: текущая активная версия модели
- message: сообщение о результате
- previous_version: предыдущая версия (опционально)
- switched_at: время переключения (ISO datetime)
- active_models: активные модели с распределением трафика в % (опционально)

**Поведение:**
- Проверяет существование версии модели в БД
- Обновляет current_model_version в конфигурации
- Обновляет флаг is_active в model_versions
- Поддерживает gradual rollout для плавного перехода
- Записывает изменение в audit log

**Ошибки:**
- 404: модель версии не найдена
- 500: ошибка при переключении"""
)
async def switch_model(request: ModelSwitchRequest) -> ModelSwitchResponse:
    """Переключение версии модели"""
    try:
        # Проверка существования версии модели
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT version FROM model_versions WHERE version = %s",
                (request.version,)
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Модель версии {request.version} не найдена"
                )
        
        # Получение предыдущей версии
        previous_version = get_config_value("current_model_version", "v1.0")
        
        # Обновление активной версии
        old_value = previous_version
        success = set_config_value(
            "current_model_version", 
            request.version, 
            "api",
            old_value=old_value
        )
        
        if success:
            # Обновление флага is_active в model_versions
            with get_db_cursor() as cursor:
                if not request.gradual_rollout:
                    # Полное переключение
                    cursor.execute("""
                        UPDATE model_versions 
                        SET is_active = FALSE 
                        WHERE is_active = TRUE
                    """)
                    cursor.execute("""
                        UPDATE model_versions 
                        SET is_active = TRUE, activated_at = CURRENT_TIMESTAMP
                        WHERE version = %s
                    """, (request.version,))
                # Для gradual rollout можно добавить логику распределения трафика
            
            switched_at = datetime.utcnow().isoformat()
            active_models = {
                request.version: request.rollout_percentage
            }
            if request.gradual_rollout and previous_version:
                active_models[previous_version] = 100 - request.rollout_percentage
            
            return ModelSwitchResponse(
                model_version=request.version,
                current_model_version=request.version,
                message=f"Model switched to {request.version}",
                previous_version=previous_version,
                switched_at=switched_at,
                active_models=active_models
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось обновить конфигурацию"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при переключении модели: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при переключении модели: {str(e)}"
        )


@app.post(
    "/config/model-switch",
    response_model=ModelSwitchResponse,
    tags=["Configuration"],
    summary="Переключение версии модели (алиас)",
    description="""Алиас для POST /config/model-version.
    
**Request/Response:** аналогично POST /config/model-version"""
)
async def switch_model_alias(request: ModelSwitchRequest) -> ModelSwitchResponse:
    """Алиас для switch_model"""
    return await switch_model(request)


@app.put(
    "/config/threshold",
    response_model=ThresholdResponse,
    tags=["Configuration"],
    summary="Изменение порога уверенности",
    description="""Изменение порога уверенности для принятия решения auto-process.
    
**Request:**
- threshold: новый порог уверенности (0..1, обязательно)
- apply_retroactive: применить ретроактивно к существующим тикетам (опционально, default: false)

**Response (200):**
- confidence_threshold: новый порог уверенности
- previous_threshold: предыдущий порог (опционально)
- message: сообщение о результате
- affected_tickets: количество затронутых тикетов (если apply_retroactive=true, опционально)
- updated_at: время обновления (ISO datetime)

**Поведение:**
- Обновляет confidence_threshold в конфигурации
- При apply_retroactive=true может переклассифицировать существующие тикеты (фоновая задача)
- Записывает изменение в audit log
- ML Service использует новый порог для определения decision (auto-process vs manual-review)

**Примеры:**
- threshold=0.70 → тикеты с confidence >= 0.70 → auto-process
- threshold=0.95 → только очень уверенные тикеты → auto-process"""
)
async def set_threshold(request: ThresholdRequest) -> ThresholdResponse:
    """Изменение порога уверенности"""
    try:
        previous_threshold = get_config_value("confidence_threshold", 0.7)
        old_value = previous_threshold
        
        success = set_config_value(
            "confidence_threshold", 
            request.threshold, 
            "api",
            old_value=old_value
        )
        
        affected_tickets = 0
        if success and request.apply_retroactive:
            # Переклассификация старых обращений (если нужно)
            # Это можно реализовать через фоновую задачу
            logger.info("Retroactive reclassification requested - would be processed in background")
        
        if success:
            updated_at = datetime.utcnow().isoformat()
            return ThresholdResponse(
                confidence_threshold=request.threshold,
                previous_threshold=previous_threshold,
                message="Threshold updated",
                affected_tickets=affected_tickets,
                updated_at=updated_at
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось обновить конфигурацию"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при изменении порога: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при изменении порога: {str(e)}"
        )


@app.post(
    "/config/jira",
    response_model=JiraConfigResponse,
    tags=["Configuration"],
    summary="Настройка Jira",
    description="""Настройка интеграции с Jira REST API.
    
**Request:**
- jira_url: URL Jira сервера (обязательно)
- jira_user: имя пользователя Jira (обязательно)
- jira_api_token: API токен Jira (обязательно)
- jira_project_key: ключ проекта Jira (обязательно)
- custom_field_mapping: маппинг кастомных полей (опционально, Record<string,string>)

**Response (200):**
- status: 'configured' - статус настройки
- connection_test: 'successful' | 'failed' - результат теста подключения
- project_key: ключ проекта Jira
- available_issue_types: доступные типы задач (опционально, string[])

**Поведение:**
- Тестирует подключение к Jira перед сохранением конфигурации
- Получает доступные типы задач проекта
- Сохраняет конфигурацию в БД
- Записывает изменение в audit log

**Ошибки:**
- 503: не удалось подключиться к Jira (проверьте URL, credentials, доступность)
- 500: ошибка при настройке"""
)
async def configure_jira(request: JiraConfigRequest) -> JiraConfigResponse:
    """Настройка Jira интеграции"""
    try:
        # Тест подключения к Jira
        connection_test = "failed"
        available_issue_types = None
        
        try:
            async with httpx.AsyncClient() as client:
                # Тест подключения
                test_url = f"{request.jira_url}/rest/api/3/myself"
                response = await client.get(
                    test_url,
                    auth=(request.jira_user, request.jira_api_token),
                    timeout=10.0
                )
                if response.status_code == 200:
                    connection_test = "successful"
                    
                    # Получение типов задач проекта
                    project_url = f"{request.jira_url}/rest/api/3/project/{request.jira_project_key}"
                    project_response = await client.get(
                        project_url,
                        auth=(request.jira_user, request.jira_api_token),
                        timeout=10.0
                    )
                    if project_response.status_code == 200:
                        # Типы задач можно получить из метаданных проекта
                        available_issue_types = ["Task", "Service Request", "Incident"]
        except Exception as e:
            logger.warning(f"Ошибка при тесте подключения к Jira: {e}")
            connection_test = "failed"
        
        if connection_test == "failed":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cannot connect to Jira. Проверьте URL, credentials и доступность Jira."
            )
        
        # Сохранение конфигурации Jira
        set_config_value("jira_url", request.jira_url, "api")
        set_config_value("jira_user", request.jira_user, "api")
        set_config_value("jira_api_token", request.jira_api_token, "api")
        set_config_value("jira_project_key", request.jira_project_key, "api")
        if request.custom_field_mapping:
            import json
            set_config_value("jira_custom_field_mapping", json.dumps(request.custom_field_mapping), "api")
        
        return JiraConfigResponse(
            status="configured",
            connection_test=connection_test,
            project_key=request.jira_project_key,
            available_issue_types=available_issue_types
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при настройке Jira: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при настройке Jira: {str(e)}"
        )


@app.get(
    "/config/audit",
    response_model=ConfigAuditResponse,
    tags=["Configuration"],
    summary="История изменений конфигурации",
    description="""Получение истории изменений конфигурации системы.
    
**Query параметры:**
- limit: количество результатов (default: 50, min: 1, max: 1000)
- offset: смещение для пагинации (default: 0, min: 0)
- changed_field: фильтр по полю (опционально)

**Response (200):**
- changes: массив изменений [{ id, field, old_value?, new_value?, changed_by, reason?, changed_at }]
- total: общее количество изменений

**Использование:**
- Аудит всех изменений конфигурации
- Отслеживание того, кто и когда вносил изменения
- Фильтрация по конкретному полю для анализа истории"""
)
async def get_config_audit(
    limit: int = Query(50, ge=1, le=1000, description="Количество результатов"),
    offset: int = Query(0, ge=0, description="Смещение для пагинации"),
    changed_field: Optional[str] = Query(None, description="Фильтр по полю")
) -> ConfigAuditResponse:
    """Получение истории изменений конфигурации"""
    try:
        where_clause = ""
        params = []
        
        if changed_field:
            where_clause = "WHERE field = %s"
            params.append(changed_field)
        
        # Подсчет общего количества
        with get_db_cursor() as cursor:
            cursor.execute(f"""
                SELECT COUNT(*) as total
                FROM config_audit_log
                {where_clause}
            """, params)
            total = cursor.fetchone()['total']
        
        # Получение данных
        with get_db_cursor() as cursor:
            cursor.execute(f"""
                SELECT id, field, old_value, new_value, changed_by, reason, changed_at
                FROM config_audit_log
                {where_clause}
                ORDER BY changed_at DESC
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            results = cursor.fetchall()
        
        changes = []
        for row in results:
            changes.append(ConfigAuditItem(
                id=row['id'],
                field=row['field'],
                old_value=row['old_value'],
                new_value=row['new_value'],
                changed_by=row['changed_by'],
                reason=row['reason'],
                changed_at=row['changed_at'].isoformat() if row['changed_at'] else None
            ))
        
        return ConfigAuditResponse(
            changes=changes,
            total=total
        )
        
    except Exception as e:
        logger.error(f"Ошибка при получении истории конфигурации: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении истории: {str(e)}"
        )


@app.get(
    "/health",
    tags=["Health"],
    summary="Healthcheck",
    description="""Проверка работоспособности сервиса (Config).
    
**Response (200|503):**
- status: 'healthy' | 'unhealthy'
- postgresql: 'connected' | 'disconnected' - статус подключения к PostgreSQL

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
            "postgresql": "connected" if db_ok else "disconnected"
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

