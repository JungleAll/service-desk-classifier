"""Расширенное FastAPI приложение для Ingestion Service с полной API спецификацией"""

import logging
import uuid
import json
from datetime import datetime, timedelta
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
        return True
    return True


def calculate_progress(status: str) -> Dict[str, Any]:
    """Вычисление прогресса обработки"""
    steps_map = {
        'pending': {'received': True, 'validated': True, 'queued': True},
        'processing': {'received': True, 'validated': True, 'queued': True, 'processing': True},
        'classified': {'received': True, 'validated': True, 'queued': True, 'processing': True, 'classified': True},
        'completed': {'received': True, 'validated': True, 'queued': True, 'processing': True, 'classified': True, 'sent_to_jira': True, 'completed': True}
    }
    
    steps = steps_map.get(status, {})
    progress = int((len(steps) / 7) * 100) if steps else 0
    
    return {
        'progress': progress,
        'steps': steps,
        'current_step': status
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("Запуск Ingestion Service...")
    yield
    logger.info("Остановка Ingestion Service...")


# Создание FastAPI приложения
app = FastAPI(
    title="Service Desk Ingestion API",
    description="API для приема обращений Service Desk - Полная спецификация",
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
    summary="Создать новое обращение",
    description="Принимает обращение и ставит его в очередь на обработку"
)
async def create_ticket(request: TicketRequest) -> TicketResponse:
    """Создание нового обращения с расширенными полями"""
    if not await check_service_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис автоматической классификации отключен"
        )
    
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
            "email": request.email,
            "priority": request.priority,
            "created_at": created_at.isoformat()
        }
        
        if not push_to_queue(QUEUE_PENDING_TICKETS, queue_data):
            logger.error(f"Не удалось добавить ticket {ticket_id} в очередь Redis")
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
        # Построение запроса
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
        
        # Определение сортировки
        sort_field = sort.lstrip('-')
        sort_dir = "DESC" if sort.startswith('-') else "ASC"
        if sort_field not in ['created_at', 'updated_at', 'processed_at', 'status']:
            sort_field = 'created_at'
        
        # Подсчет общего количества
        with get_db_cursor() as cursor:
            cursor.execute(f"""
                SELECT COUNT(*) as total
                FROM ticket_events
                WHERE {where_sql}
            """, params)
            total = cursor.fetchone()['total']
        
        # Получение данных
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
        # Парсинг JSON полей
        if data.get('probabilities'):
            if isinstance(data['probabilities'], str):
                data['probabilities'] = json.loads(data['probabilities'])
        
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
        progress_info = calculate_progress(data['status'])
        
        return TicketStatusResponse(
            **data,
            **progress_info,
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


# Продолжение в следующем файле из-за ограничения размера...

