"""Pydantic модели для Output Service"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class ProcessResultRequest(BaseModel):
    """Модель запроса для обработки результата классификации"""
    
    ticket_id: str = Field(..., description="ID обращения")
    predicted_type: str = Field(..., description="Предсказанный тип")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность модели")
    decision: str = Field(..., description="Решение: 'auto-process' или 'manual-review'")
    model_version: str = Field(..., description="Версия модели")
    text: str = Field(..., description="Текст обращения")
    source: Optional[str] = Field(None, description="Источник обращения")
    user_id: Optional[str] = Field(None, description="ID пользователя")
    email: Optional[str] = Field(None, description="Email отправителя")
    priority: Optional[str] = Field(None, description="Приоритет обращения")
    probabilities: Optional[Dict[str, float]] = Field(None, description="Вероятности для всех классов")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Дополнительные метаданные")


class ProcessResultResponse(BaseModel):
    """Модель ответа при обработке результата"""
    
    success: bool = Field(..., description="Успешно ли обработано")
    message: str = Field(..., description="Сообщение о результате")
    ticket_id: str = Field(..., description="ID обращения")
    jira_ticket_id: Optional[str] = Field(None, description="ID тикета в Jira, если создан")
    jira_link: Optional[str] = Field(None, description="Ссылка на тикет в Jira")
    status: str = Field(..., description="Статус обработки")
    processed_at: Optional[str] = Field(None, description="Время обработки")
    retry_count: Optional[int] = Field(0, description="Количество попыток")


class ErrorResponse(BaseModel):
    """Модель ответа для ошибок"""
    
    error: str = Field(..., description="Описание ошибки")
    detail: Optional[str] = Field(None, description="Детали ошибки")


class SyncTicketRequest(BaseModel):
    """Модель запроса для синхронизации тикета из Jira"""
    
    jira_ticket_id: str = Field(..., description="Ключ тикета в Jira (например, SD-123)")
    ticket_id: Optional[str] = Field(None, description="ID тикета в нашей системе (опционально)")
    category_field: Optional[str] = Field(None, description="Имя custom field для категории в Jira")


class SyncBatchRequest(BaseModel):
    """Модель запроса для пакетной синхронизации"""
    
    jira_ticket_ids: list[str] = Field(..., description="Список ключей тикетов в Jira")
    category_field: Optional[str] = Field(None, description="Имя custom field для категории в Jira")


class SyncJQLRequest(BaseModel):
    """Модель запроса для синхронизации по JQL"""
    
    jql: str = Field(..., description="JQL запрос для поиска тикетов в Jira")
    category_field: Optional[str] = Field(None, description="Имя custom field для категории в Jira")
    max_results: int = Field(100, ge=1, le=1000, description="Максимальное количество тикетов")


class SyncAllRequest(BaseModel):
    """Модель запроса для синхронизации всех тикетов"""
    
    category_field: Optional[str] = Field(None, description="Имя custom field для категории в Jira")
    limit: int = Field(100, ge=1, le=1000, description="Максимальное количество тикетов")


class SyncResultResponse(BaseModel):
    """Модель ответа при синхронизации"""
    
    success: bool = Field(..., description="Успешно ли выполнена синхронизация")
    jira_ticket_id: str = Field(..., description="Ключ тикета в Jira")
    ticket_id: Optional[str] = Field(None, description="ID тикета в нашей системе")
    updated_fields: list[str] = Field(default_factory=list, description="Обновленные поля")
    errors: list[str] = Field(default_factory=list, description="Ошибки при синхронизации")


class SyncBatchResponse(BaseModel):
    """Модель ответа при пакетной синхронизации"""
    
    total: int = Field(..., description="Общее количество тикетов")
    successful: int = Field(..., description="Успешно синхронизировано")
    failed: int = Field(..., description="Не удалось синхронизировать")
    details: list[SyncResultResponse] = Field(default_factory=list, description="Детали по каждому тикету")
