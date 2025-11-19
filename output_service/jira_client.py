"""Клиент для работы с Jira REST API"""

import logging
import httpx
from typing import Optional, Dict, Any
from .config import JIRA_URL, JIRA_USER, JIRA_API_TOKEN, JIRA_PROJECT_KEY, JIRA_ENABLED

logger = logging.getLogger(__name__)


class JiraClient:
    """Клиент для работы с Jira"""
    
    def __init__(self):
        self.base_url = JIRA_URL
        self.auth = (JIRA_USER, JIRA_API_TOKEN) if JIRA_USER and JIRA_API_TOKEN else None
        self.enabled = JIRA_ENABLED and self.auth is not None
    
    async def create_ticket(
        self,
        summary: str,
        description: str,
        issue_type: str = "Task",
        priority: Optional[str] = None
    ) -> Optional[str]:
        """
        Создание тикета в Jira
        
        Args:
            summary: Краткое описание
            description: Полное описание
            issue_type: Тип задачи (Task, Bug, Story)
            priority: Приоритет (Highest, High, Medium, Low, Lowest)
        
        Returns:
            ID созданного тикета или None при ошибке
        """
        if not self.enabled:
            logger.warning("Jira отключен или не настроен")
            return None
        
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
                    logger.info(f"Тикет Jira создан: {ticket_key}")
                    return ticket_key
                else:
                    logger.error(f"Ошибка при создании тикета в Jira: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Исключение при создании тикета в Jira: {e}", exc_info=True)
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

