"""Pydantic модели для запросов и ответов API"""

from typing import Dict, Optional, List
from pydantic import BaseModel, Field, field_validator


class ClassifyRequest(BaseModel):
    """Модель запроса для классификации текста"""
    
    text: str = Field(
        ...,
        min_length=3,
        description="Текст обращения для классификации (минимум 3 символа)"
    )
    return_probabilities: bool = Field(
        True,
        description="Возвращать ли вероятности для всех классов"
    )
    top_n: Optional[int] = Field(
        None,
        ge=0,
        le=20,
        description="Топ-N вероятностей для возврата (0 или None - вернуть все, 1-20 - ограничить количество)"
    )
    
    @field_validator('text')
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Валидация текста"""
        if not v or len(v.strip()) < 3:
            raise ValueError("Текст должен содержать минимум 3 символа")
        return v.strip()


class ProbabilityItem(BaseModel):
    """Элемент вероятности"""
    
    category: str = Field(..., description="Категория")
    score: float = Field(..., ge=0.0, le=1.0, description="Вероятность")


class ClassifyResponse(BaseModel):
    """Модель ответа для классификации"""
    
    predicted_type: str = Field(..., description="Предсказанный класс обращения")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность модели (0-1)")
    probabilities: List[ProbabilityItem] = Field(..., description="Вероятности для классов")
    model_version: str = Field(..., description="Версия используемой модели")
    decision: str = Field(..., description="Решение: auto-process или manual-review")
    processing_time_ms: int = Field(..., description="Время обработки в миллисекундах")


class ModelStatusResponse(BaseModel):
    """Модель ответа для статуса модели"""
    
    model_version: str = Field(..., description="Версия модели")
    model_name: Optional[str] = Field(None, description="Название модели")
    status: Optional[str] = Field(None, description="Статус: loaded, not_loaded")
    is_loaded: bool = Field(..., description="Загружена ли модель")
    num_classes: Optional[int] = Field(None, description="Количество классов")
    classes: Optional[list] = Field(None, description="Список классов")
    accuracy: Optional[float] = Field(None, description="Точность модели")
    precision: Optional[float] = Field(None, description="Precision модели")
    recall: Optional[float] = Field(None, description="Recall модели")
    f1_score: Optional[float] = Field(None, description="F1-score модели")
    loaded_at: Optional[str] = Field(None, description="Время загрузки модели")
    memory_usage_mb: Optional[int] = Field(None, description="Использование памяти в МБ")
    classifier_path: str = Field(..., description="Путь к файлу классификатора")
    vectorizer_path: str = Field(..., description="Путь к файлу векторизатора")
    label_encoder_path: str = Field(..., description="Путь к файлу энкодера")


class HealthResponse(BaseModel):
    """Модель ответа для health check"""
    
    status: str = Field(..., description="Статус сервиса: healthy или unhealthy")
    model_loaded: bool = Field(..., description="Загружена ли модель")
    model_version: Optional[str] = Field(None, description="Версия модели")
    uptime_seconds: Optional[int] = Field(None, description="Время работы сервиса в секундах")
    requests_total: Optional[int] = Field(None, description="Общее количество запросов")
    errors_total: Optional[int] = Field(None, description="Общее количество ошибок")
    avg_latency_ms: Optional[float] = Field(None, description="Средняя задержка в мс")
    message: Optional[str] = Field(None, description="Дополнительное сообщение")
    reason: Optional[str] = Field(None, description="Причина, если unhealthy")


class BatchClassifyRequest(BaseModel):
    """Модель запроса для пакетной классификации"""
    
    texts: List[str] = Field(..., min_length=1, description="Список текстов для классификации")


class BatchClassifyItem(BaseModel):
    """Элемент результата пакетной классификации"""
    
    text: str = Field(..., description="Исходный текст")
    predicted_type: str = Field(..., description="Предсказанный класс")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность")


class BatchClassifyResponse(BaseModel):
    """Модель ответа для пакетной классификации"""
    
    results: List[BatchClassifyItem] = Field(..., description="Результаты классификации")
    total_time_ms: int = Field(..., description="Общее время обработки в мс")


class ModelListItem(BaseModel):
    """Элемент списка моделей"""
    
    version: str = Field(..., description="Версия модели")
    name: str = Field(..., description="Название модели")
    accuracy: Optional[float] = Field(None, description="Точность модели")
    is_active: bool = Field(..., description="Активна ли модель")
    created_at: Optional[str] = Field(None, description="Дата создания")


class ModelListResponse(BaseModel):
    """Модель ответа для списка моделей"""
    
    models: List[ModelListItem] = Field(..., description="Список доступных моделей")


class ErrorResponse(BaseModel):
    """Модель ответа для ошибок"""
    
    error: str = Field(..., description="Описание ошибки")
    detail: Optional[str] = Field(None, description="Детали ошибки")


class ReloadResponse(BaseModel):
    """Модель ответа для перезагрузки модели"""
    
    success: bool = Field(..., description="Успешна ли перезагрузка")
    message: str = Field(..., description="Сообщение о результате")
    model_version: Optional[str] = Field(None, description="Версия модели после перезагрузки")


class WorkerDiagnosticsResponse(BaseModel):
    """Модель ответа для диагностики Worker и очереди"""
    
    worker_enabled: bool = Field(..., description="Включен ли Worker")
    worker_running: bool = Field(..., description="Запущен ли Worker")
    model_loaded: bool = Field(..., description="Загружена ли модель")
    queue_pending_length: int = Field(..., description="Количество тикетов в очереди pending_tickets")
    queue_failed_length: int = Field(..., description="Количество тикетов в очереди failed_tickets")
    redis_connected: bool = Field(..., description="Подключен ли Redis")
    message: str = Field(..., description="Сообщение о статусе")
