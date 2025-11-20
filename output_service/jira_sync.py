"""Сервис синхронизации данных из Jira в PostgreSQL для дообучения модели"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from shared.database import get_db_cursor
from .jira_client import JiraClient

logger = logging.getLogger(__name__)


class JiraSyncService:
    """Сервис для синхронизации данных из Jira в PostgreSQL"""
    
    def __init__(self, jira_client: Optional[JiraClient] = None):
        self.jira_client = jira_client or JiraClient()
        self.category_field = None  # Можно настроить через конфигурацию
    
    async def sync_ticket_from_jira(
        self,
        jira_ticket_id: str,
        ticket_id: Optional[str] = None,
        category_field: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Синхронизация одного тикета из Jira в PostgreSQL
        
        Args:
            jira_ticket_id: Ключ тикета в Jira (например, SD-123)
            ticket_id: ID тикета в нашей системе (если известен)
            category_field: Имя custom field для категории в Jira
        
        Returns:
            Словарь с результатом синхронизации
        """
        result = {
            "success": False,
            "jira_ticket_id": jira_ticket_id,
            "ticket_id": ticket_id,
            "updated_fields": [],
            "errors": []
        }
        
        if not self.jira_client.enabled:
            result["errors"].append("Jira клиент отключен")
            return result
        
        try:
            # Получение данных из Jira
            issue_data = await self.jira_client.get_issue(jira_ticket_id, expand="fields,changelog")
            
            if not issue_data:
                result["errors"].append(f"Не удалось получить тикет {jira_ticket_id} из Jira")
                return result
            
            # Извлечение категории из Jira
            category = self.jira_client.extract_category_from_issue(
                issue_data,
                category_field or self.category_field
            )
            
            # Поиск тикета в нашей БД по jira_ticket_id
            if not ticket_id:
                ticket_id = self._find_ticket_by_jira_id(jira_ticket_id)
            
            if not ticket_id:
                result["errors"].append(f"Тикет с jira_ticket_id={jira_ticket_id} не найден в БД")
                return result
            
            # Обновление данных в PostgreSQL
            update_result = await self._update_ticket_from_jira_data(
                ticket_id=ticket_id,
                issue_data=issue_data,
                category=category
            )
            
            result.update(update_result)
            result["success"] = len(result["errors"]) == 0
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при синхронизации тикета {jira_ticket_id}: {e}", exc_info=True)
            result["errors"].append(str(e))
            return result
    
    def _find_ticket_by_jira_id(self, jira_ticket_id: str) -> Optional[str]:
        """Поиск ticket_id в БД по jira_ticket_id"""
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    "SELECT ticket_id FROM ticket_events WHERE jira_ticket_id = %s LIMIT 1",
                    (jira_ticket_id,)
                )
                result = cursor.fetchone()
                if result:
                    return result['ticket_id']
                return None
        except Exception as e:
            logger.error(f"Ошибка при поиске тикета по jira_ticket_id: {e}")
            return None
    
    async def _update_ticket_from_jira_data(
        self,
        ticket_id: str,
        issue_data: Dict[str, Any],
        category: Optional[str]
    ) -> Dict[str, Any]:
        """
        Обновление тикета в PostgreSQL на основе данных из Jira
        
        Использует расширенную схему с отдельными таблицами:
        - category_corrections - для истории исправлений категорий
        - classification_feedback - для обратной связи
        
        Args:
            ticket_id: ID тикета в нашей системе
            issue_data: Данные тикета из Jira
            category: Извлеченная категория
        
        Returns:
            Словарь с результатом обновления
        """
        result = {
            "updated_fields": [],
            "errors": []
        }
        
        try:
            # Получение текущих данных тикета
            with get_db_cursor() as cursor:
                cursor.execute("""
                    SELECT predicted_type, actual_type, confidence, decision
                    FROM ticket_events
                    WHERE ticket_id = %s
                """, (ticket_id,))
                row = cursor.fetchone()
                
                if not row:
                    result["errors"].append(f"Тикет {ticket_id} не найден в БД")
                    return result
                
                predicted_type = row.get('predicted_type')
                current_actual_type = row.get('actual_type')
                confidence = row.get('confidence')
                decision = row.get('decision')
            
            # Определение, нужно ли обновлять категорию
            should_update_category = False
            if category and category != predicted_type:
                if current_actual_type != category:
                    should_update_category = True
            
            if not should_update_category:
                logger.debug(f"Нет изменений для тикета {ticket_id}")
                return result
            
            # Обновление в БД с использованием расширенной схемы
            with get_db_cursor() as cursor:
                # 1. Обновление actual_type в ticket_events
                cursor.execute("""
                    UPDATE ticket_events
                    SET actual_type = %s,
                        actual_type_set_at = %s,
                        actual_type_set_by = %s,
                        updated_at = %s
                    WHERE ticket_id = %s
                """, (
                    category,
                    datetime.utcnow(),
                    "jira_sync",
                    datetime.utcnow(),
                    ticket_id
                ))
                result["updated_fields"].append("actual_type")
                
                # 2. Добавление записи в category_corrections
                cursor.execute("""
                    INSERT INTO category_corrections (
                        ticket_id, original_type, corrected_type, 
                        correction_reason, corrected_by, confidence_at_correction
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    ticket_id,
                    predicted_type,
                    category,
                    "jira_sync",
                    "jira_sync",
                    confidence
                ))
                result["updated_fields"].append("category_corrections")
                
                # 3. Добавление обратной связи в classification_feedback
                cursor.execute("""
                    INSERT INTO classification_feedback (
                        ticket_id, feedback_type, original_predicted_type,
                        correct_type, confidence_at_feedback, provided_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    ticket_id,
                    "incorrect",
                    predicted_type,
                    category,
                    confidence,
                    "jira_sync"
                ))
                result["updated_fields"].append("classification_feedback")
                
                # 4. Если decision='manual-review', помечаем как готовый для обучения
                if decision == 'manual-review':
                    cursor.execute("""
                        UPDATE ticket_events
                        SET training_ready = TRUE,
                            training_ready_at = %s
                        WHERE ticket_id = %s
                          AND training_ready = FALSE
                    """, (datetime.utcnow(), ticket_id))
                    result["updated_fields"].append("training_ready")
                
                logger.info(f"Тикет {ticket_id} обновлен из Jira: {', '.join(result['updated_fields'])}")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении тикета {ticket_id}: {e}", exc_info=True)
            result["errors"].append(str(e))
        
        return result
    
    async def sync_multiple_tickets(
        self,
        jira_ticket_ids: List[str],
        category_field: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Синхронизация нескольких тикетов из Jira
        
        Args:
            jira_ticket_ids: Список ключей тикетов в Jira
            category_field: Имя custom field для категории
        
        Returns:
            Словарь с результатами синхронизации
        """
        results = {
            "total": len(jira_ticket_ids),
            "successful": 0,
            "failed": 0,
            "details": []
        }
        
        for jira_ticket_id in jira_ticket_ids:
            sync_result = await self.sync_ticket_from_jira(
                jira_ticket_id=jira_ticket_id,
                category_field=category_field
            )
            
            if sync_result["success"]:
                results["successful"] += 1
            else:
                results["failed"] += 1
            
            results["details"].append(sync_result)
        
        return results
    
    async def sync_tickets_by_jql(
        self,
        jql: str,
        category_field: Optional[str] = None,
        max_results: int = 100
    ) -> Dict[str, Any]:
        """
        Синхронизация тикетов по JQL запросу
        
        Args:
            jql: JQL запрос для поиска тикетов в Jira
            category_field: Имя custom field для категории
            max_results: Максимальное количество тикетов для синхронизации
        
        Returns:
            Словарь с результатами синхронизации
        """
        results = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "details": []
        }
        
        try:
            # Поиск тикетов в Jira
            search_result = await self.jira_client.search_issues(
                jql=jql,
                fields=["key", "summary", "status", "labels", "components", "issuetype"],
                max_results=max_results
            )
            
            if not search_result:
                results["errors"] = ["Не удалось выполнить поиск в Jira"]
                return results
            
            issues = search_result.get("issues", [])
            results["total"] = len(issues)
            
            # Синхронизация каждого тикета
            for issue in issues:
                jira_ticket_id = issue.get("key")
                if not jira_ticket_id:
                    continue
                
                sync_result = await self.sync_ticket_from_jira(
                    jira_ticket_id=jira_ticket_id,
                    category_field=category_field
                )
                
                if sync_result["success"]:
                    results["successful"] += 1
                else:
                    results["failed"] += 1
                
                results["details"].append(sync_result)
            
        except Exception as e:
            logger.error(f"Ошибка при синхронизации по JQL: {e}", exc_info=True)
            results["errors"] = [str(e)]
        
        return results
    
    async def sync_tickets_with_jira_ids(
        self,
        category_field: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Синхронизация всех тикетов из БД, у которых есть jira_ticket_id
        
        Args:
            category_field: Имя custom field для категории
            limit: Максимальное количество тикетов для синхронизации
        
        Returns:
            Словарь с результатами синхронизации
        """
        results = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "details": []
        }
        
        try:
            # Получение списка тикетов с jira_ticket_id
            with get_db_cursor() as cursor:
                cursor.execute("""
                    SELECT ticket_id, jira_ticket_id
                    FROM ticket_events
                    WHERE jira_ticket_id IS NOT NULL
                      AND jira_ticket_id != ''
                    ORDER BY sent_to_jira_at DESC NULLS LAST, created_at DESC
                    LIMIT %s
                """, (limit,))
                
                tickets = cursor.fetchall()
                results["total"] = len(tickets)
                
                # Синхронизация каждого тикета
                for ticket in tickets:
                    ticket_id = ticket['ticket_id']
                    jira_ticket_id = ticket['jira_ticket_id']
                    
                    sync_result = await self.sync_ticket_from_jira(
                        jira_ticket_id=jira_ticket_id,
                        ticket_id=ticket_id,
                        category_field=category_field
                    )
                    
                    if sync_result["success"]:
                        results["successful"] += 1
                    else:
                        results["failed"] += 1
                    
                    results["details"].append(sync_result)
        
        except Exception as e:
            logger.error(f"Ошибка при синхронизации тикетов с jira_ticket_id: {e}", exc_info=True)
            results["errors"] = [str(e)]
        
        return results

