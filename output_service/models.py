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

