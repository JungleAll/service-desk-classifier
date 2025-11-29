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
    summary="Создать обращение",
    description="""Создание нового обращения и постановка в очередь на обработку.
    
**Request:**
- text: текст обращения (минимум 3 символа)
- source: источник ('email' | 'chat' | 'api' | 'web')
- user_id: ID пользователя (опционально)
- email: email отправителя (опционально)
- priority: приоритет ('low' | 'medium' | 'high' | 'critical', default: 'medium')
- category_hint: подсказка о категории (опционально)
- metadata: дополнительные метаданные (опционально)

**Response (201 Created):**
- ticket_id: уникальный ID обращения (формат 'tick_XXXXXXXX')
- status: 'queued' - обращение поставлено в очередь
- message: сообщение о результате
- created_at: время создания (ISO datetime)
- estimated_processing_time: оценка времени обработки в мс (default: 2000)

**Поведение:**
- Проверяет, включен ли сервис через Config Service
- Сохраняет обращение в PostgreSQL
- Добавляет в очередь Redis для обработки Worker'ом

**Ошибки:**
- 400: некорректные параметры (неверный source, priority, слишком короткий text)
- 503: сервис отключен через Config Service
- 500: внутренняя ошибка"""
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
    summary="Список обращений",
    description="""Получение списка обращений с фильтрацией и пагинацией.
    
**Query параметры:**
- limit: количество результатов (default: 50, min: 1, max: 1000)
- offset: смещение для пагинации (default: 0, min: 0)
- status: фильтр по статусу ('queued' | 'processing' | 'classified' | 'completed' | 'failed' | 'cancelled')
- source: фильтр по источнику ('email' | 'chat' | 'api' | 'web')
- priority: фильтр по приоритету ('low' | 'medium' | 'high' | 'critical')
- date_from: фильтр с даты (YYYY-MM-DD)
- date_to: фильтр по дату (YYYY-MM-DD)
- sort: сортировка (default: "-created_at", префикс "-" для DESC, поля: created_at, updated_at, processed_at, status)

**Response (200):**
- tickets: массив объектов обращений
- total: общее количество
- page: текущая страница (вычисляется из offset/limit)
- pages: всего страниц"""
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
    summary="Детали обращения",
    description="""Получение полной информации об обращении.
    
**Response (200):**
- ticket_id: ID обращения
- text: текст обращения
- source: источник
- user_id: ID пользователя (опционально)
- email: email отправителя (опционально)
- priority: приоритет (опционально)
- status: статус ('queued' | 'processing' | 'classified' | 'completed' | 'failed' | 'cancelled')
- predicted_type: предсказанный тип (если классифицирован)
- confidence: уверенность модели (если классифицирован)
- probabilities: вероятности для всех классов в формате JSONB (если классифицирован)
- decision: решение ('auto-process' | 'manual-review', если классифицирован)
- model_version: версия модели, использованная для классификации
- jira_issue_id: ID тикета в Jira или external_id (если отправлен)
- jira_link: ссылка на тикет в Jira или путь к файлу (если отправлен)
- created_at: время создания (ISO datetime)
- processed_at: время завершения классификации (опционально)
- sent_to_jira_at: время отправки в destination (опционально)
- error_message: сообщение об ошибке (если есть)
- retry_count: количество попыток

**Ошибки:**
- 404: обращение не найдено
- 500: внутренняя ошибка"""
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
    summary="Статус обработки",
    description="""Получение текущего статуса и прогресса обработки обращения.
    
**Статусы:**
- 'queued': тикет создан и поставлен в очередь
- 'processing': тикет обрабатывается ML Service Worker
- 'classified': классификация завершена, ожидает обработки Output Service
- 'completed': полностью обработан (отправлен в destination)
- 'failed': ошибка при обработке
- 'cancelled': отменен пользователем

**Response (200):**
- ticket_id: ID обращения
- status: текущий статус
- progress: прогресс обработки в процентах (0..100)
- steps: объект с шагами обработки (received, validated, queued, processing, classified, sent_to_jira, completed)
- current_step: текущий шаг обработки (совпадает со status)
- errors: массив ошибок (если есть)
- retry_count: количество попыток
- text: текст обращения (опционально)
- source: источник (опционально)
- predicted_type: предсказанный тип (если классифицирован)
- confidence: уверенность модели (если классифицирован)
- decision: решение ('auto-process' | 'manual-review', если классифицирован)
- jira_ticket_id: ID тикета в Jira или external_id (если отправлен)
- created_at: время создания (опционально)
- processed_at: время завершения классификации (опционально)
- error_message: сообщение об ошибке (если есть)

**Ошибки:**
- 404: обращение не найдено
- 500: внутренняя ошибка"""
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
    summary="Отменить обработку",
    description="""Отмена обработки обращения.
    
**Request:**
- reason: причина отмены (обязательно)
- comment: дополнительный комментарий (опционально)

**Response (200):**
- ticket_id: ID обращения
- status: 'cancelled'
- cancelled_at: время отмены (ISO datetime)

**Поведение:**
- Проверяет текущий статус тикета
- Нельзя отменить, если статус 'completed' или 'cancelled'
- Обновляет статус на 'cancelled' в БД

**Ошибки:**
- 404: обращение не найдено
- 400: нельзя отменить (уже completed/cancelled)
- 500: внутренняя ошибка"""
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
    summary="Переотправить в очередь",
    description="""Переотправка обращения в очередь для повторной обработки.
    
**Request:**
- text: опционально заменить исходный текст
- force: принудительно переоформить даже если уже обработано (default: false)

**Response (202 Accepted):**
- ticket_id: ID обращения
- status: 'queued_for_reprocessing' (в БД устанавливается 'queued')
- previous_classification: предыдущая классификация predicted_type (если была)
- requeued_at: время переотправки (ISO datetime)

**Поведение:**
- Проверяет текущий статус тикета
- Если статус 'completed' и force=false → ошибка 400
- Обновляет статус на 'queued' в БД
- Опционально обновляет текст, если передан
- Тикет будет обработан Worker'ом заново

**Ошибки:**
- 404: обращение не найдено
- 400: нельзя переоформить без force (если уже completed)
- 500: внутренняя ошибка"""
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
    summary="Пакетная загрузка",
    description="""Пакетное создание обращений.
    
**Request:**
- tickets: массив запросов на создание обращений (TicketRequest[])

**Response (202 Accepted):**
- batch_id: уникальный ID пакета
- total: общее количество обращений в пакете
- queued: количество успешно поставленных в очередь
- failed: количество неудачных попыток
- estimated_time: оценка времени обработки в миллисекундах

**Поведение:**
- Проверяет, включен ли сервис через Config Service
- Обрабатывает каждое обращение из пакета
- Сохраняет в БД и добавляет в очередь Redis
- Возвращает статистику по успешным и неудачным попыткам"""
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


@app.get(
    "/health",
    tags=["Health"],
    summary="Healthcheck",
    description="""Проверка работоспособности сервиса (Ingestion).
    
**Response (200|503):**
- status: 'healthy' | 'unhealthy'
- redis: 'connected' | 'disconnected' - статус подключения к Redis (очередь)
- postgresql: 'connected' | 'disconnected' - статус подключения к PostgreSQL

**Статус 503:** возвращается, если Redis или PostgreSQL недоступны"""
)
async def health_check():
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

