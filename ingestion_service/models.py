"""Pydantic модели для Ingestion API"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class TicketRequest(BaseModel):
    """Модель запроса для создания обращения"""
    
    text: str = Field(
        ...,
        min_length=3,
        description="Текст обращения (минимум 3 символа)"
    )
    source: str = Field(
        ...,
        description="Источник обращения: 'email', 'chat', 'api', 'web'"
    )
    user_id: Optional[str] = Field(
        None,
        description="ID пользователя, отправившего обращение"
    )
    email: Optional[str] = Field(
        None,
        description="Email отправителя"
    )
    priority: Optional[str] = Field(
        "medium",
        description="Приоритет: 'low', 'medium', 'high', 'critical'"
    )
    category_hint: Optional[str] = Field(
        None,
        description="Подсказка о категории (опционально)"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Дополнительные метаданные"
    )
    
    @field_validator('source')
    @classmethod
    def validate_source(cls, v: str) -> str:
        """Валидация источника"""
        allowed_sources = ['email', 'chat', 'api', 'web']
        if v.lower() not in allowed_sources:
            raise ValueError(f"Источник должен быть одним из: {', '.join(allowed_sources)}")
        return v.lower()
    
    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v: Optional[str]) -> str:
        """Валидация приоритета"""
        if v:
            allowed_priorities = ['low', 'medium', 'high', 'critical']
            if v.lower() not in allowed_priorities:
                raise ValueError(f"Приоритет должен быть одним из: {', '.join(allowed_priorities)}")
            return v.lower()
        return "medium"
    
    @field_validator('text')
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Валидация текста"""
        if not v or len(v.strip()) < 3:
            raise ValueError("Текст должен содержать минимум 3 символа")
        return v.strip()


class TicketResponse(BaseModel):
    """Модель ответа при создании обращения"""
    
    ticket_id: str = Field(..., description="Уникальный ID обращения")
    status: str = Field(..., description="Статус: 'queued', 'pending', 'processing', 'completed', 'failed'")
    message: str = Field(..., description="Сообщение о результате")
    created_at: datetime = Field(..., description="Время создания")
    estimated_processing_time: Optional[int] = Field(2000, description="Оценка времени обработки в мс")


class TicketStatusResponse(BaseModel):
    """Модель ответа для статуса обращения"""
    
    ticket_id: str = Field(..., description="ID обращения")
    status: str = Field(..., description="Текущий статус")
    progress: Optional[int] = Field(None, ge=0, le=100, description="Прогресс обработки в %")
    steps: Optional[Dict[str, bool]] = Field(None, description="Шаги обработки")
    current_step: Optional[str] = Field(None, description="Текущий шаг")
    errors: Optional[List[str]] = Field(None, description="Список ошибок")
    retry_count: Optional[int] = Field(0, description="Количество попыток")
    text: Optional[str] = Field(None, description="Текст обращения")
    source: Optional[str] = Field(None, description="Источник")
    predicted_type: Optional[str] = Field(None, description="Предсказанный тип")
    confidence: Optional[float] = Field(None, description="Уверенность модели")
    decision: Optional[str] = Field(None, description="Решение: 'auto-process' или 'manual-review'")
    jira_ticket_id: Optional[str] = Field(None, description="ID тикета в Jira")
    created_at: Optional[datetime] = Field(None, description="Время создания")
    processed_at: Optional[datetime] = Field(None, description="Время обработки")
    error_message: Optional[str] = Field(None, description="Сообщение об ошибке, если есть")


class TicketDetailResponse(BaseModel):
    """Модель ответа для деталей обращения"""
    
    ticket_id: str = Field(..., description="ID обращения")
    text: str = Field(..., description="Текст обращения")
    source: str = Field(..., description="Источник")
    user_id: Optional[str] = Field(None, description="ID пользователя")
    email: Optional[str] = Field(None, description="Email отправителя")
    priority: Optional[str] = Field(None, description="Приоритет")
    status: str = Field(..., description="Статус")
    predicted_type: Optional[str] = Field(None, description="Предсказанный тип")
    confidence: Optional[float] = Field(None, description="Уверенность модели")
    probabilities: Optional[Dict[str, float]] = Field(None, description="Вероятности для всех классов")
    decision: Optional[str] = Field(None, description="Решение")
    jira_issue_id: Optional[str] = Field(None, description="ID тикета в Jira")
    jira_link: Optional[str] = Field(None, description="Ссылка на тикет в Jira")
    created_at: datetime = Field(..., description="Время создания")
    processed_at: Optional[datetime] = Field(None, description="Время обработки")
    sent_to_jira_at: Optional[datetime] = Field(None, description="Время отправки в Jira")


class TicketListResponse(BaseModel):
    """Модель ответа для списка обращений"""
    
    tickets: List[Dict[str, Any]] = Field(..., description="Список обращений")
    total: int = Field(..., description="Общее количество")
    page: int = Field(..., description="Текущая страница")
    pages: int = Field(..., description="Всего страниц")


class CancelRequest(BaseModel):
    """Модель запроса для отмены обращения"""
    
    reason: str = Field(..., description="Причина отмены")
    comment: Optional[str] = Field(None, description="Комментарий")


class CancelResponse(BaseModel):
    """Модель ответа при отмене обращения"""
    
    ticket_id: str = Field(..., description="ID обращения")
    status: str = Field(..., description="Статус")
    cancelled_at: datetime = Field(..., description="Время отмены")


class ReprocessRequest(BaseModel):
    """Модель запроса для переоформления обращения"""
    
    text: Optional[str] = Field(None, description="Новое содержание обращения")
    force: bool = Field(False, description="Переоформить даже если уже отправлено")


class ReprocessResponse(BaseModel):
    """Модель ответа при переоформлении"""
    
    ticket_id: str = Field(..., description="ID обращения")
    status: str = Field(..., description="Статус")
    previous_classification: Optional[str] = Field(None, description="Предыдущая классификация")
    requeued_at: datetime = Field(..., description="Время повторной постановки в очередь")


class BatchTicketRequest(BaseModel):
    """Модель запроса для пакетной загрузки"""
    
    tickets: List[TicketRequest] = Field(..., description="Список обращений")


class BatchTicketResponse(BaseModel):
    """Модель ответа при пакетной загрузке"""
    
    batch_id: str = Field(..., description="ID пакета")
    total: int = Field(..., description="Всего обращений")
    queued: int = Field(..., description="Поставлено в очередь")
    failed: int = Field(..., description="Не удалось обработать")
    estimated_time: int = Field(..., description="Оценка времени обработки в мс")


class ErrorResponse(BaseModel):
    """Модель ответа для ошибок"""
    
    error: str = Field(..., description="Описание ошибки")
    detail: Optional[str] = Field(None, description="Детали ошибки")

