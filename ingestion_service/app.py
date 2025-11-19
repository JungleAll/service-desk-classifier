"""FastAPI приложение для Ingestion Service (Port 8000)"""

import logging
import uuid
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .models import (
    TicketRequest,
    TicketResponse,
    TicketStatusResponse,
    TicketDetailResponse,
    TicketListResponse,
    CancelRequest,
    CancelResponse,
    ReprocessRequest,
    ReprocessResponse,
    BatchTicketRequest,
    BatchTicketResponse,
    ErrorResponse
)
from .config import API_HOST, API_PORT, LOG_LEVEL, CONFIG_SERVICE_URL
from shared.redis_client import (
    push_to_queue,
    QUEUE_PENDING_TICKETS
)
from shared.database import (
    get_db_cursor,
    execute_query,
    execute_insert
)
import httpx

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def check_service_enabled() -> bool:
    """Проверка, включен ли сервис через Config Service"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{CONFIG_SERVICE_URL}/config")
            if response.status_code == 200:
                config = response.json()
                return config.get("service_enabled", True)
    except Exception as e:
        logger.warning(f"Не удалось проверить статус сервиса через Config Service: {e}")
        return True  # По умолчанию включен
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("Запуск Ingestion Service...")
    yield
    logger.info("Остановка Ingestion Service...")


# Создание FastAPI приложения
app = FastAPI(
    title="Service Desk Ingestion API",
    description="API для приема обращений Service Desk",
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
        "service": "Service Desk Ingestion API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.post(
    "/tickets",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Tickets"],
    summary="Создание нового обращения",
    description="Принимает обращение и ставит его в очередь на обработку"
)
async def create_ticket(request: TicketRequest) -> TicketResponse:
    """
    Создание нового обращения
    
    - **text**: Текст обращения (минимум 3 символа)
    - **source**: Источник ('email', 'chat', 'api')
    - **user_id**: ID пользователя (опционально)
    
    Возвращает:
    - **ticket_id**: Уникальный ID обращения
    - **status**: Статус обработки
    - **message**: Сообщение о результате
    """
    # Проверка, включен ли сервис
    if not await check_service_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис автоматической классификации отключен"
        )
    
    # Генерация уникального ID в формате tick_XXXXXXXX
    ticket_id = f"tick_{uuid.uuid4().hex[:8]}"
    created_at = datetime.utcnow()
    
    try:
        # Сохранение в БД
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO ticket_events (
                    ticket_id, text, source, user_id, email, priority, 
                    category_hint, metadata, status, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                ticket_id, request.text, request.source, request.user_id,
                request.email, request.priority, request.category_hint,
                json.dumps(request.metadata) if request.metadata else None,
                'queued', created_at
            ))
            result = cursor.fetchone()
        
        # Добавление в очередь Redis
        queue_data = {
            "ticket_id": ticket_id,
            "text": request.text,
            "source": request.source,
            "user_id": request.user_id,
            "created_at": created_at.isoformat()
        }
        
        if not push_to_queue(QUEUE_PENDING_TICKETS, queue_data):
            logger.error(f"Не удалось добавить ticket {ticket_id} в очередь Redis")
            # Обновляем статус на failed
            with get_db_cursor() as cursor:
                cursor.execute("""
                    UPDATE ticket_events
                    SET status = 'failed', error_message = 'Failed to add to queue'
                    WHERE ticket_id = %s
                """, (ticket_id,))
        
        logger.info(f"Обращение {ticket_id} создано и добавлено в очередь")
        
        return TicketResponse(
            ticket_id=ticket_id,
            status="queued",
            message="Обращение успешно создано и поставлено в очередь на обработку",
            created_at=created_at,
            estimated_processing_time=2000
        )
        
    except Exception as e:
        logger.error(f"Ошибка при создании обращения: {e}", exc_info=True)
        
        # Логирование ошибки
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO error_logs (service_name, error_type, error_message, ticket_id)
                    VALUES (%s, %s, %s, %s)
                """, ("ingestion", "TicketCreationError", str(e), ticket_id))
        except:
            pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при создании обращения: {str(e)}"
        )


@app.get(
    "/tickets",
    response_model=TicketListResponse,
    tags=["Tickets"],
    summary="Получить список обращений",
    description="Возвращает список обращений с фильтрацией и пагинацией"
)
async def get_tickets(
    limit: int = Query(50, ge=1, le=1000, description="Количество результатов"),
    offset: int = Query(0, ge=0, description="Смещение для пагинации"),
    status_filter: Optional[str] = Query(None, alias="status", description="Фильтр по статусу"),
    source: Optional[str] = Query(None, description="Фильтр по источнику"),
    priority: Optional[str] = Query(None, description="Фильтр по приоритету"),
    date_from: Optional[str] = Query(None, description="С какой даты (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="По какую дату (YYYY-MM-DD)"),
    sort: str = Query("-created_at", description="Сортировка")
) -> TicketListResponse:
    """Получение списка обращений с фильтрацией"""
    try:
        where_clauses = []
        params = []
        
        if status_filter:
            where_clauses.append("status = %s")
            params.append(status_filter)
        if source:
            where_clauses.append("source = %s")
            params.append(source)
        if priority:
            where_clauses.append("priority = %s")
            params.append(priority)
        if date_from:
            where_clauses.append("created_at >= %s")
            params.append(date_from)
        if date_to:
            where_clauses.append("created_at <= %s")
            params.append(f"{date_to} 23:59:59")
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        sort_field = sort.lstrip('-')
        sort_dir = "DESC" if sort.startswith('-') else "ASC"
        if sort_field not in ['created_at', 'updated_at', 'processed_at', 'status']:
            sort_field = 'created_at'
        
        with get_db_cursor() as cursor:
            cursor.execute(f"""
                SELECT COUNT(*) as total
                FROM ticket_events
                WHERE {where_sql}
            """, params)
            total = cursor.fetchone()['total']
        
        with get_db_cursor() as cursor:
            cursor.execute(f"""
                SELECT ticket_id, text, source, status, predicted_type, 
                       confidence, created_at, processed_at
                FROM ticket_events
                WHERE {where_sql}
                ORDER BY {sort_field} {sort_dir}
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            results = cursor.fetchall()
        
        tickets = [dict(row) for row in results]
        pages = (total + limit - 1) // limit
        page = (offset // limit) + 1
        
        return TicketListResponse(
            tickets=tickets,
            total=total,
            page=page,
            pages=pages
        )
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка обращений: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении списка: {str(e)}"
        )


@app.get(
    "/tickets/{ticket_id}",
    response_model=TicketDetailResponse,
    tags=["Tickets"],
    summary="Получить детали обращения",
    description="Возвращает полную информацию об обращении"
)
async def get_ticket_detail(ticket_id: str) -> TicketDetailResponse:
    """Получение деталей обращения"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT ticket_id, text, source, user_id, email, priority, status,
                       predicted_type, confidence, probabilities, decision,
                       jira_ticket_id, jira_link, created_at, processed_at,
                       sent_to_jira_at
                FROM ticket_events
                WHERE ticket_id = %s
            """, (ticket_id,))
            result = cursor.fetchone()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Обращение с ID {ticket_id} не найдено"
            )
        
        data = dict(result)
        if data.get('probabilities') and isinstance(data['probabilities'], str):
            data['probabilities'] = json.loads(data['probabilities'])
        
        # Маппинг jira_ticket_id из БД в jira_issue_id для модели
        if 'jira_ticket_id' in data:
            data['jira_issue_id'] = data.pop('jira_ticket_id')
        
        return TicketDetailResponse(**data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении деталей обращения {ticket_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении деталей: {str(e)}"
        )


@app.get(
    "/status/{ticket_id}",
    response_model=TicketStatusResponse,
    tags=["Tickets"],
    summary="Получить статус обработки",
    description="Возвращает текущий статус и прогресс обработки обращения"
)
async def get_ticket_status(ticket_id: str) -> TicketStatusResponse:
    """Получение статуса обработки с прогрессом"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT ticket_id, status, text, source, predicted_type, 
                       confidence, decision, jira_ticket_id, created_at, 
                       processed_at, error_message, retry_count
                FROM ticket_events
                WHERE ticket_id = %s
            """, (ticket_id,))
            result = cursor.fetchone()
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Обращение с ID {ticket_id} не найдено"
            )
        
        data = dict(result)
        status_val = data['status']
        
        # Вычисление прогресса
        steps_map = {
            'queued': {'received': True, 'validated': True, 'queued': True},
            'processing': {'received': True, 'validated': True, 'queued': True, 'processing': True},
            'classified': {'received': True, 'validated': True, 'queued': True, 'processing': True, 'classified': True},
            'completed': {'received': True, 'validated': True, 'queued': True, 'processing': True, 'classified': True, 'sent_to_jira': True, 'completed': True}
        }
        
        steps = steps_map.get(status_val, {})
        progress = int((len(steps) / 7) * 100) if steps else 0
        
        return TicketStatusResponse(
            **data,
            progress=progress,
            steps=steps,
            current_step=status_val,
            errors=[data['error_message']] if data.get('error_message') else []
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении статуса обращения {ticket_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении статуса: {str(e)}"
        )


@app.post(
    "/tickets/{ticket_id}/cancel",
    response_model=CancelResponse,
    tags=["Tickets"],
    summary="Отменить обработку обращения",
    description="Отменяет обработку обращения, если оно еще не обработано"
)
async def cancel_ticket(ticket_id: str, request: CancelRequest) -> CancelResponse:
    """Отмена обработки обращения"""
    try:
        with get_db_cursor() as cursor:
            # Проверка текущего статуса
            cursor.execute("""
                SELECT status FROM ticket_events WHERE ticket_id = %s
            """, (ticket_id,))
            result = cursor.fetchone()
            
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Обращение с ID {ticket_id} не найдено"
                )
            
            current_status = result['status']
            if current_status in ['completed', 'cancelled']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot cancel - ticket already {current_status}"
                )
            
            # Обновление статуса
            cancelled_at = datetime.utcnow()
            cursor.execute("""
                UPDATE ticket_events
                SET status = 'cancelled', cancelled_at = %s, updated_at = %s,
                    error_message = %s
                WHERE ticket_id = %s
            """, (cancelled_at, cancelled_at, f"Cancelled: {request.reason}", ticket_id))
            
            logger.info(f"Обращение {ticket_id} отменено: {request.reason}")
            
            return CancelResponse(
                ticket_id=ticket_id,
                status="cancelled",
                cancelled_at=cancelled_at
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при отмене обращения {ticket_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при отмене обращения: {str(e)}"
        )


@app.post(
    "/tickets/{ticket_id}/reprocess",
    response_model=ReprocessResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Tickets"],
    summary="Переоформить обращение",
    description="Переоформляет обращение для повторной обработки"
)
async def reprocess_ticket(ticket_id: str, request: ReprocessRequest) -> ReprocessResponse:
    """Переоформление обращения"""
    try:
        with get_db_cursor() as cursor:
            # Получение текущих данных
            cursor.execute("""
                SELECT status, predicted_type, text, source FROM ticket_events WHERE ticket_id = %s
            """, (ticket_id,))
            result = cursor.fetchone()
            
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Обращение с ID {ticket_id} не найдено"
                )
            
            current_status = result['status']
            previous_classification = result['predicted_type']
            
            if current_status == 'completed' and not request.force:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot reprocess - ticket already processed. Use force=true to override"
                )
            
            # Обновление текста, если указан
            new_text = request.text if request.text else result['text']
            requeued_at = datetime.utcnow()
            
            cursor.execute("""
                UPDATE ticket_events
                SET status = 'queued', text = %s, updated_at = %s,
                    predicted_type = NULL, confidence = NULL, decision = NULL,
                    processed_at = NULL, error_message = NULL
                WHERE ticket_id = %s
            """, (new_text, requeued_at, ticket_id))
            
            # Добавление в очередь Redis
            queue_data = {
                "ticket_id": ticket_id,
                "text": new_text,
                "source": result['source'],
                "created_at": requeued_at.isoformat(),
                "reprocess": True
            }
            push_to_queue(QUEUE_PENDING_TICKETS, queue_data)
            
            logger.info(f"Обращение {ticket_id} переоформлено для повторной обработки")
            
            return ReprocessResponse(
                ticket_id=ticket_id,
                status="queued_for_reprocessing",
                previous_classification=previous_classification,
                requeued_at=requeued_at
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при переоформлении обращения {ticket_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при переоформлении: {str(e)}"
        )


@app.post(
    "/tickets/batch",
    response_model=BatchTicketResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Tickets"],
    summary="Загрузить пакет обращений",
    description="Создает несколько обращений за один запрос"
)
async def create_batch_tickets(request: BatchTicketRequest) -> BatchTicketResponse:
    """Пакетное создание обращений"""
    if not await check_service_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис автоматической классификации отключен"
        )
    
    batch_id = f"batch_{uuid.uuid4().hex[:8]}"
    total = len(request.tickets)
    queued = 0
    failed = 0
    
    try:
        for ticket_req in request.tickets:
            try:
                ticket_id = f"tick_{uuid.uuid4().hex[:8]}"
                created_at = datetime.utcnow()
                
                # Сохранение в БД
                with get_db_cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO ticket_events (
                            ticket_id, text, source, user_id, email, priority, 
                            category_hint, metadata, status, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        ticket_id, ticket_req.text, ticket_req.source, ticket_req.user_id,
                        ticket_req.email, ticket_req.priority, ticket_req.category_hint,
                        json.dumps(ticket_req.metadata) if ticket_req.metadata else None,
                        'queued', created_at
                    ))
                
                # Добавление в очередь
                queue_data = {
                    "ticket_id": ticket_id,
                    "text": ticket_req.text,
                    "source": ticket_req.source,
                    "user_id": ticket_req.user_id,
                    "email": ticket_req.email,
                    "priority": ticket_req.priority,
                    "created_at": created_at.isoformat(),
                    "batch_id": batch_id
                }
                
                if push_to_queue(QUEUE_PENDING_TICKETS, queue_data):
                    queued += 1
                else:
                    failed += 1
                    logger.warning(f"Не удалось добавить ticket {ticket_id} в очередь")
                    
            except Exception as e:
                failed += 1
                logger.error(f"Ошибка при создании обращения в пакете: {e}")
        
        # Оценка времени обработки (примерно 2 секунды на обращение)
        estimated_time = queued * 2000
        
        logger.info(f"Пакет {batch_id}: {queued} обращений поставлено в очередь, {failed} ошибок")
        
        return BatchTicketResponse(
            batch_id=batch_id,
            total=total,
            queued=queued,
            failed=failed,
            estimated_time=estimated_time
        )
        
    except Exception as e:
        logger.error(f"Ошибка при пакетном создании обращений: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при пакетном создании: {str(e)}"
        )


@app.get("/health", tags=["Health"])
async def health_check():
    """Проверка работоспособности сервиса"""
    try:
        # Проверка подключения к Redis (очереди)
        from shared.redis_client import get_redis_queue_client
        redis_client = get_redis_queue_client()
        redis_client.ping()
        redis_ok = True
    except:
        redis_ok = False
    
    try:
        # Проверка подключения к PostgreSQL
        from shared.database import get_db_connection
        with get_db_connection():
            db_ok = True
    except:
        db_ok = False
    
    status_code = status.HTTP_200_OK if (redis_ok and db_ok) else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if (redis_ok and db_ok) else "unhealthy",
            "redis": "connected" if redis_ok else "disconnected",
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

