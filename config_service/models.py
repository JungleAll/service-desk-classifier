"""Pydantic модели для Config Service"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ConfigResponse(BaseModel):
    """Модель ответа с текущей конфигурацией"""
    
    auto_classification_enabled: bool = Field(..., description="Включена ли автоклассификация")
    service_enabled: bool = Field(..., description="Включен ли сервис (алиас)")
    confidence_threshold: float = Field(..., description="Порог уверенности")
    model_version: str = Field(..., description="Текущая версия модели")
    current_model_version: str = Field(..., description="Текущая версия модели (алиас)")
    jira_integration_enabled: bool = Field(..., description="Включена ли интеграция с Jira")
    jira_enabled: bool = Field(..., description="Включена ли отправка в Jira (алиас)")
    jira_project_key: Optional[str] = Field(None, description="Ключ проекта Jira")
    auto_process_priority: Optional[str] = Field("medium", description="Приоритет для auto-process")
    manual_review_priority: Optional[str] = Field("low", description="Приоритет для manual-review")
    max_retry_attempts: int = Field(..., description="Максимальное количество попыток")
    retry_delay_seconds: Optional[int] = Field(5, description="Задержка между попытками в секундах")
    timeout_seconds: Optional[int] = Field(30, description="Таймаут в секундах")
    batch_processing_enabled: Optional[bool] = Field(True, description="Включена ли пакетная обработка")
    batch_size: Optional[int] = Field(100, description="Размер пакета")
    updated_at: Optional[str] = Field(None, description="Время последнего обновления")
    updated_by: Optional[str] = Field(None, description="Кто обновил")
    all_config: Optional[Dict[str, Any]] = Field(None, description="Вся конфигурация")


class ToggleRequest(BaseModel):
    """Модель запроса для включения/отключения сервиса"""
    
    enabled: bool = Field(..., description="Включить или отключить сервис")
    reason: Optional[str] = Field(None, description="Причина изменения (опционально)")


class ToggleResponse(BaseModel):
    """Модель ответа при переключении"""
    
    auto_classification_enabled: bool = Field(..., description="Текущее состояние")
    service_enabled: bool = Field(..., description="Текущее состояние (алиас)")
    message: str = Field(..., description="Сообщение")
    updated_at: str = Field(..., description="Время обновления")


class ModelSwitchRequest(BaseModel):
    """Модель запроса для переключения модели"""
    
    version: str = Field(..., description="Версия модели для переключения")
    gradual_rollout: bool = Field(False, description="Постепенный переход?")
    rollout_percentage: int = Field(100, ge=0, le=100, description="% трафика на новую версию")


class ModelSwitchResponse(BaseModel):
    """Модель ответа при переключении модели"""
    
    model_version: str = Field(..., description="Текущая версия модели")
    current_model_version: str = Field(..., description="Текущая версия модели (алиас)")
    message: str = Field(..., description="Сообщение")
    previous_version: Optional[str] = Field(None, description="Предыдущая версия")
    switched_at: str = Field(..., description="Время переключения")
    active_models: Optional[Dict[str, int]] = Field(None, description="Активные модели и их % трафика")


class ThresholdRequest(BaseModel):
    """Модель запроса для изменения порога уверенности"""
    
    threshold: float = Field(..., ge=0.0, le=1.0, description="Порог уверенности (0-1)")
    apply_retroactive: bool = Field(False, description="Переклассифицировать старые обращения?")


class ThresholdResponse(BaseModel):
    """Модель ответа при изменении порога"""
    
    confidence_threshold: float = Field(..., description="Текущий порог уверенности")
    previous_threshold: Optional[float] = Field(None, description="Предыдущий порог")
    message: str = Field(..., description="Сообщение")
    affected_tickets: Optional[int] = Field(0, description="Количество затронутых обращений")
    updated_at: str = Field(..., description="Время обновления")


class JiraConfigRequest(BaseModel):
    """Модель запроса для настройки Jira"""
    
    jira_url: str = Field(..., description="URL Jira")
    jira_user: str = Field(..., description="Пользователь Jira")
    jira_api_token: str = Field(..., description="API токен Jira")
    jira_project_key: str = Field(..., description="Ключ проекта")
    custom_field_mapping: Optional[Dict[str, str]] = Field(None, description="Маппинг кастомных полей")


class JiraConfigResponse(BaseModel):
    """Модель ответа при настройке Jira"""
    
    status: str = Field(..., description="Статус: configured")
    connection_test: str = Field(..., description="Результат теста подключения")
    project_key: str = Field(..., description="Ключ проекта")
    available_issue_types: Optional[List[str]] = Field(None, description="Доступные типы задач")


class ConfigAuditItem(BaseModel):
    """Элемент истории изменений конфигурации"""
    
    id: int = Field(..., description="ID изменения")
    field: str = Field(..., description="Измененное поле")
    old_value: Optional[Any] = Field(None, description="Старое значение")
    new_value: Optional[Any] = Field(None, description="Новое значение")
    changed_by: str = Field(..., description="Кто изменил")
    reason: Optional[str] = Field(None, description="Причина изменения")
    changed_at: str = Field(..., description="Время изменения")


class ConfigAuditResponse(BaseModel):
    """Модель ответа для истории изменений"""
    
    changes: List[ConfigAuditItem] = Field(..., description="Список изменений")
    total: int = Field(..., description="Общее количество изменений")


class ErrorResponse(BaseModel):
    """Модель ответа для ошибок"""
    
    error: str = Field(..., description="Описание ошибки")
    detail: Optional[str] = Field(None, description="Детали ошибки")

