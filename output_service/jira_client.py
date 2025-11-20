"""Клиент для работы с Jira REST API и Jira Service Desk API"""

import logging
import httpx
from typing import Optional, Dict, Any
from .config import (
    JIRA_URL, JIRA_USER, JIRA_API_TOKEN, JIRA_PROJECT_KEY, JIRA_ENABLED,
    JIRA_USE_SERVICEDESK_API, JIRA_SERVICE_DESK_ID, JIRA_REQUEST_TYPE_ID
)

logger = logging.getLogger(__name__)


class JiraClient:
    """Клиент для работы с Jira (стандартный API и Service Desk API)"""
    
    def __init__(self):
        self.base_url = JIRA_URL
        self.auth = (JIRA_USER, JIRA_API_TOKEN) if JIRA_USER and JIRA_API_TOKEN else None
        self.enabled = JIRA_ENABLED and self.auth is not None
        self.use_servicedesk_api = JIRA_USE_SERVICEDESK_API
        self.service_desk_id = JIRA_SERVICE_DESK_ID
        self.request_type_id = JIRA_REQUEST_TYPE_ID
    
    async def create_ticket(
        self,
        summary: str,
        description: str,
        issue_type: str = "Task",
        priority: Optional[str] = None
    ) -> Optional[str]:
        """
        Создание тикета в Jira
        
        Поддерживает два режима:
        - Стандартный Jira REST API (/rest/api/3/issue)
        - Jira Service Desk API (/rest/servicedeskapi/request)
        
        Args:
            summary: Краткое описание
            description: Полное описание
            issue_type: Тип задачи (Task, Bug, Story) - используется только для стандартного API
            priority: Приоритет (Highest, High, Medium, Low, Lowest)
        
        Returns:
            ID созданного тикета (issue key) или None при ошибке
        """
        if not self.enabled:
            logger.warning("Jira отключен или не настроен")
            return None
        
        # Выбор API в зависимости от конфигурации
        if self.use_servicedesk_api:
            return await self._create_ticket_servicedesk_api(summary, description, priority)
        else:
            return await self._create_ticket_standard_api(summary, description, issue_type, priority)
    
    async def _create_ticket_standard_api(
        self,
        summary: str,
        description: str,
        issue_type: str,
        priority: Optional[str]
    ) -> Optional[str]:
        """Создание тикета через стандартный Jira REST API"""
        try:
            url = f"{self.base_url}/rest/api/3/issue"
            
            # Маппинг приоритетов
            priority_map = {
                "low": "Lowest",
                "medium": "Medium",
                "high": "High",
                "critical": "Highest"
            }
            jira_priority = priority_map.get(priority.lower() if priority else "medium", "Medium")
            
            payload = {
                "fields": {
                    "project": {
                        "key": JIRA_PROJECT_KEY
                    },
                    "summary": summary,
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": description
                                    }
                                ]
                            }
                        ]
                    },
                    "issuetype": {
                        "name": issue_type
                    },
                    "priority": {
                        "name": jira_priority
                    }
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    auth=self.auth,
                    timeout=30.0
                )
                
                if response.status_code == 201:
                    ticket_data = response.json()
                    ticket_key = ticket_data.get("key")
                    logger.info(f"Тикет Jira создан через стандартный API: {ticket_key}")
                    return ticket_key
                else:
                    logger.error(f"Ошибка при создании тикета в Jira: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Исключение при создании тикета в Jira: {e}", exc_info=True)
            return None
    
    async def _create_ticket_servicedesk_api(
        self,
        summary: str,
        description: str,
        priority: Optional[str]
    ) -> Optional[str]:
        """Создание тикета через Jira Service Desk API"""
        try:
            # Проверка обязательных параметров для Service Desk API
            if not self.service_desk_id:
                logger.error("JIRA_SERVICE_DESK_ID не настроен для использования Service Desk API")
                return None
            
            if not self.request_type_id:
                logger.error("JIRA_REQUEST_TYPE_ID не настроен для использования Service Desk API")
                return None
            
            url = f"{self.base_url}/rest/servicedeskapi/request"
            
            # Маппинг приоритетов для Service Desk API
            priority_map = {
                "low": "Lowest",
                "medium": "Medium",
                "high": "High",
                "critical": "Highest"
            }
            jira_priority = priority_map.get(priority.lower() if priority else "medium", "Medium")
            
            # Формат запроса для Service Desk API
            # Согласно документации: https://docs.atlassian.com/jira-servicedesk/REST/5.17.2/
            payload = {
                "serviceDeskId": self.service_desk_id,
                "requestTypeId": self.request_type_id,
                "requestFieldValues": {
                    "summary": summary,
                    "description": description,
                    "priority": {
                        "name": jira_priority
                    }
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    auth=self.auth,
                    headers={
                        "Content-Type": "application/json",
                        "X-ExperimentalApi": "true"  # Может потребоваться для некоторых версий
                    },
                    timeout=30.0
                )
                
                if response.status_code == 201:
                    ticket_data = response.json()
                    # Service Desk API возвращает issueKey в поле issueKey или key
                    ticket_key = ticket_data.get("issueKey") or ticket_data.get("key")
                    if not ticket_key:
                        # Если ключ не в корне, ищем в _links или других полях
                        links = ticket_data.get("_links", {})
                        if "jiraRest" in links:
                            # Извлекаем ключ из URL типа /rest/api/2/issue/{key}
                            jira_rest_url = links["jiraRest"]
                            ticket_key = jira_rest_url.split("/")[-1] if jira_rest_url else None
                    
                    logger.info(f"Тикет Jira создан через Service Desk API: {ticket_key}")
                    return ticket_key
                else:
                    logger.error(f"Ошибка при создании тикета через Service Desk API: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Исключение при создании тикета через Service Desk API: {e}", exc_info=True)
            return None
    
    async def update_ticket(
        self,
        ticket_key: str,
        fields: Dict[str, Any]
    ) -> bool:
        """
        Обновление тикета в Jira
        
        Args:
            ticket_key: Ключ тикета (например, SD-123)
            fields: Словарь полей для обновления
        
        Returns:
            True если успешно, False иначе
        """
        if not self.enabled:
            return False
        
        try:
            url = f"{self.base_url}/rest/api/3/issue/{ticket_key}"
            
            payload = {"fields": fields}
            
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    url,
                    json=payload,
                    auth=self.auth,
                    timeout=30.0
                )
                
                if response.status_code == 204:
                    logger.info(f"Тикет Jira обновлен: {ticket_key}")
                    return True
                else:
                    logger.error(f"Ошибка при обновлении тикета в Jira: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Исключение при обновлении тикета в Jira: {e}", exc_info=True)
            return False
    
    async def get_issue(self, ticket_key: str, expand: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Получение тикета из Jira через стандартный REST API
        
        Args:
            ticket_key: Ключ тикета (например, SD-123)
            expand: Список полей для расширения (например, "fields,changelog")
        
        Returns:
            Словарь с данными тикета или None при ошибке
        """
        if not self.enabled:
            logger.warning("Jira отключен или не настроен")
            return None
        
        try:
            url = f"{self.base_url}/rest/api/3/issue/{ticket_key}"
            params = {}
            if expand:
                params["expand"] = expand
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    auth=self.auth,
                    params=params,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    issue_data = response.json()
                    logger.debug(f"Тикет Jira получен: {ticket_key}")
                    return issue_data
                else:
                    logger.error(f"Ошибка при получении тикета из Jira: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Исключение при получении тикета из Jira: {e}", exc_info=True)
            return None
    
    async def get_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        Получение request из Jira через Service Desk API
        
        Args:
            request_id: ID или ключ request (например, SD-123)
        
        Returns:
            Словарь с данными request или None при ошибке
        """
        if not self.enabled:
            logger.warning("Jira отключен или не настроен")
            return None
        
        try:
            # Service Desk API использует issueKey для получения request
            url = f"{self.base_url}/rest/servicedeskapi/request/{request_id}"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    auth=self.auth,
                    headers={
                        "Content-Type": "application/json",
                        "X-ExperimentalApi": "true"
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    request_data = response.json()
                    logger.debug(f"Request Jira получен: {request_id}")
                    return request_data
                else:
                    logger.error(f"Ошибка при получении request из Jira: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Исключение при получении request из Jira: {e}", exc_info=True)
            return None
    
    async def search_issues(
        self,
        jql: str,
        fields: Optional[list] = None,
        max_results: int = 50,
        start_at: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Поиск тикетов в Jira по JQL запросу
        
        Args:
            jql: JQL запрос (например, "project = SD AND status = Resolved")
            fields: Список полей для возврата (по умолчанию основные поля)
            max_results: Максимальное количество результатов
            start_at: Смещение для пагинации
        
        Returns:
            Словарь с результатами поиска или None при ошибке
        """
        if not self.enabled:
            logger.warning("Jira отключен или не настроен")
            return None
        
        try:
            url = f"{self.base_url}/rest/api/3/search"
            
            payload = {
                "jql": jql,
                "maxResults": max_results,
                "startAt": start_at
            }
            
            if fields:
                payload["fields"] = fields
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    auth=self.auth,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    search_data = response.json()
                    logger.debug(f"Найдено тикетов в Jira: {search_data.get('total', 0)}")
                    return search_data
                else:
                    logger.error(f"Ошибка при поиске тикетов в Jira: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Исключение при поиске тикетов в Jira: {e}", exc_info=True)
            return None
    
    def extract_category_from_issue(self, issue_data: Dict[str, Any], category_field: Optional[str] = None) -> Optional[str]:
        """
        Извлечение категории из данных тикета Jira
        
        Ищет категорию в следующих местах (в порядке приоритета):
        1. Custom field (если указан category_field)
        2. Labels (первый label, если есть)
        3. Issue type name
        4. Component name (первый компонент)
        
        Args:
            issue_data: Данные тикета из Jira API
            category_field: Имя custom field для категории (например, "customfield_10001")
        
        Returns:
            Категория или None если не найдена
        """
        if not issue_data:
            return None
        
        fields = issue_data.get("fields", {})
        
        # 1. Проверка custom field
        if category_field and category_field in fields:
            field_value = fields[category_field]
            if isinstance(field_value, dict):
                # Для select fields
                return field_value.get("value") or field_value.get("name")
            elif isinstance(field_value, list) and len(field_value) > 0:
                # Для multi-select fields
                first_item = field_value[0]
                if isinstance(first_item, dict):
                    return first_item.get("value") or first_item.get("name")
                return str(first_item)
            elif field_value:
                return str(field_value)
        
        # 2. Проверка labels (первый label)
        labels = fields.get("labels", [])
        if labels and len(labels) > 0:
            return labels[0]
        
        # 3. Проверка issue type
        issue_type = fields.get("issuetype", {})
        if isinstance(issue_type, dict):
            issue_type_name = issue_type.get("name")
            if issue_type_name and issue_type_name not in ["Task", "Bug", "Story", "Epic"]:
                return issue_type_name
        
        # 4. Проверка components (первый компонент)
        components = fields.get("components", [])
        if components and len(components) > 0:
            first_component = components[0]
            if isinstance(first_component, dict):
                return first_component.get("name")
        
        return None

