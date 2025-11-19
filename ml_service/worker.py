"""Worker для асинхронной обработки очереди тикетов из Redis"""

import asyncio
import hashlib
import logging
import os
import httpx
from typing import Optional, Dict, Any
from datetime import datetime

from .classifier import ServiceDeskClassifier
from .config import CONFIDENCE_THRESHOLD
from shared.redis_client import (
    pop_from_queue,
    push_to_queue,
    get_cache,
    set_cache,
    QUEUE_PENDING_TICKETS,
    QUEUE_FAILED_TICKETS,
    CACHE_PREDICTIONS
)
from shared.database import get_db_cursor

logger = logging.getLogger(__name__)

# Глобальные переменные для управления worker
_worker_task: Optional[asyncio.Task] = None
_worker_enabled = False
_worker_running = False


async def process_ticket_from_queue(
    ticket_data: Dict[str, Any],
    classifier: ServiceDeskClassifier,
    output_service_url: str
) -> bool:
    """
    Обработка одного тикета из очереди
    
    Args:
        ticket_data: Данные тикета из очереди
        classifier: Экземпляр классификатора
        output_service_url: URL Output Service
        
    Returns:
        True если обработка успешна, False иначе
    """
    ticket_id = ticket_data.get("ticket_id")
    text = ticket_data.get("text", "")
    
    if not ticket_id or not text:
        logger.warning(f"Некорректные данные тикета: {ticket_data}")
        return False
    
    try:
        # Проверяем существование тикета в БД и его текущий статус
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT status FROM ticket_events WHERE ticket_id = %s
            """, (ticket_id,))
            ticket_info = cursor.fetchone()
            
            if not ticket_info:
                logger.error(f"Тикет {ticket_id} не найден в БД, пропускаю обработку")
                return False
            
            current_status = ticket_info['status']
            
            # Если тикет уже обработан или обрабатывается, пропускаем
            if current_status in ['classified', 'completed', 'processing']:
                logger.warning(f"Тикет {ticket_id} уже в статусе {current_status}, пропускаю обработку")
                return False
            
            # Обновляем статус на "processing" только если статус был "queued"
            if current_status != 'queued':
                logger.warning(f"Тикет {ticket_id} в неожиданном статусе {current_status}, пропускаю обработку")
                return False
            
            # Обновляем статус на "processing"
            cursor.execute("""
                UPDATE ticket_events
                SET status = 'processing', updated_at = CURRENT_TIMESTAMP
                WHERE ticket_id = %s AND status = 'queued'
            """, (ticket_id,))
            
            # Проверяем, что обновление прошло успешно
            if cursor.rowcount == 0:
                logger.warning(f"Не удалось обновить статус тикета {ticket_id} на 'processing' (возможно, уже обработан)")
                return False
        
        logger.info(f"Обработка тикета {ticket_id}: {text[:50]}...")
        
        # Проверка версии модели перед классификацией (аналогично REST API)
        logger.info(f"Worker: Проверка версии модели перед классификацией тикета {ticket_id}. Текущая версия ML: {classifier.model_version}")
        try:
            config_url = os.getenv("CONFIG_SERVICE_URL", "http://localhost:8002")
            async with httpx.AsyncClient(timeout=1.5) as client:
                resp = await client.get(f"{config_url}/config")
                if resp.status_code == 200:
                    cfg = resp.json()
                    desired_version = cfg.get("current_model_version")
                    logger.info(f"Worker: Получена версия из Config Service: {desired_version}")
                    if desired_version:
                        if desired_version != classifier.model_version:
                            logger.warning(f"Worker: 🔄 Обнаружено несоответствие версии (ML={classifier.model_version}, Config={desired_version}). Перезагружаю модель...")
                            os.environ["ML_MODEL_VERSION"] = desired_version
                            if classifier.reload_model():
                                logger.info(f"Worker: ✅ Модель успешно перезагружена на версию {desired_version}. Текущая версия ML: {classifier.model_version}")
                            else:
                                logger.error(f"Worker: ❌ Перезагрузка модели на версию {desired_version} не удалась, продолжаю с текущей версией {classifier.model_version}")
                        else:
                            logger.info(f"Worker: ✅ Версии совпадают: ML={classifier.model_version}, Config={desired_version}")
                    else:
                        logger.warning(f"Worker: ⚠️ Config Service не вернул current_model_version, используем текущую версию ML: {classifier.model_version}")
                else:
                    logger.warning(f"Worker: ⚠️ Config Service вернул статус {resp.status_code}, используем текущую версию ML: {classifier.model_version}")
        except Exception as e:
            # Не блокируем классификацию, если Config недоступен
            logger.warning(f"Worker: ⚠️ Не удалось проверить версию модели в Config перед классификацией: {e}. Используем текущую версию ML: {classifier.model_version}")
        
        # Проверка кэша (аналогично REST API для консистентности)
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        cache_key = f"{CACHE_PREDICTIONS}:{classifier.model_version}:{text_hash}"
        cached_result = get_cache(cache_key)
        
        if cached_result:
            logger.info(f"Worker: Результат получен из кэша для тикета {ticket_id}")
            result = {
                'predicted_type': cached_result['predicted_type'],
                'confidence': cached_result['confidence'],
                'probabilities': cached_result.get('probabilities', {}),
                'model_version': cached_result['model_version'],
                'decision': cached_result['decision']
            }
        else:
            # Классификация
            if not classifier.is_loaded:
                raise Exception("Модель не загружена")
            
            result = classifier.predict(text)
            
            # Сохранение в кэш (аналогично REST API)
            cache_data = {
                'predicted_type': result['predicted_type'],
                'confidence': result['confidence'],
                'probabilities': result.get('probabilities', {}),
                'model_version': result['model_version'],
                'decision': result['decision']
            }
            set_cache(cache_key, cache_data, ttl=3600)
            logger.debug(f"Worker: Результат классификации сохранен в кэш для тикета {ticket_id}")
        
        # Получение порога уверенности из Config Service (опционально)
        confidence_threshold = CONFIDENCE_THRESHOLD
        try:
            config_url = os.getenv("CONFIG_SERVICE_URL", "http://localhost:8002")
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{config_url}/config")
                if resp.status_code == 200:
                    cfg = resp.json()
                    threshold = cfg.get("confidence_threshold")
                    if threshold is not None:
                        confidence_threshold = float(threshold)
        except Exception as e:
            logger.debug(f"Не удалось получить порог из Config Service, используем дефолтный: {e}")
        
        # Определение решения
        decision = "auto-process" if result['confidence'] >= confidence_threshold else "manual-review"
        
        # Обновление статуса в БД с результатами классификации
        # Преобразуем probabilities в JSON строку для БД
        import json as json_lib
        probabilities_json = json_lib.dumps(result.get('probabilities', {}), ensure_ascii=False)
        
        with get_db_cursor() as cursor:
            cursor.execute("""
                UPDATE ticket_events
                SET status = 'classified',
                    predicted_type = %s,
                    confidence = %s,
                    probabilities = %s,
                    decision = %s,
                    model_version = %s,
                    processed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ticket_id = %s
            """, (
                result['predicted_type'],
                result['confidence'],
                probabilities_json,
                decision,
                result['model_version'],
                ticket_id
            ))
        
        logger.info(
            f"Тикет {ticket_id} классифицирован: {result['predicted_type']} "
            f"(confidence={result['confidence']:.2f}, decision={decision}, model_version={result['model_version']})"
        )
        
        # Отправка в Output Service
        try:
            payload = {
                "ticket_id": ticket_id,
                "text": text,
                "predicted_type": result['predicted_type'],
                "confidence": result['confidence'],
                "probabilities": result.get('probabilities', {}),
                "decision": decision,
                "model_version": result['model_version'],
                "source": ticket_data.get("source", "unknown"),
                "user_id": ticket_data.get("user_id"),
                "email": ticket_data.get("email"),
                "priority": ticket_data.get("priority", "medium")
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{output_service_url}/process_result",
                    json=payload
                )
                
                if resp.status_code == 200:
                    output_result = resp.json()
                    jira_ticket_id = output_result.get("jira_ticket_id")
                    jira_link = output_result.get("jira_link")
                    
                    # Обновление статуса с информацией о Jira
                    with get_db_cursor() as cursor:
                        cursor.execute("""
                            UPDATE ticket_events
                            SET status = 'completed',
                                jira_ticket_id = %s,
                                jira_link = %s,
                                sent_to_jira_at = CURRENT_TIMESTAMP,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE ticket_id = %s
                        """, (jira_ticket_id, jira_link, ticket_id))
                    
                    logger.info(f"Тикет {ticket_id} успешно отправлен в Output Service")
                    return True
                else:
                    raise Exception(f"Output Service вернул статус {resp.status_code}: {resp.text}")
                    
        except Exception as e:
            logger.error(f"Ошибка при отправке тикета {ticket_id} в Output Service: {e}")
            # НЕ помечаем тикет как failed, так как классификация была успешной
            # Тикет остается в статусе 'classified' и может быть обработан позже
            # Только логируем ошибку в error_message для информации
            try:
                with get_db_cursor() as cursor:
                    cursor.execute("""
                        UPDATE ticket_events
                        SET error_message = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE ticket_id = %s AND status = 'classified'
                    """, (f"Output Service error: {str(e)}", ticket_id))
                logger.warning(f"Тикет {ticket_id} остается в статусе 'classified' после ошибки Output Service. Классификация успешна.")
            except Exception as db_error:
                logger.error(f"Не удалось обновить error_message для тикета {ticket_id}: {db_error}")
            # Возвращаем True, так как классификация была успешной
            # Ошибка в Output Service не должна влиять на статус классификации
            return True
        
    except Exception as e:
        logger.error(f"Ошибка при обработке тикета {ticket_id}: {e}", exc_info=True)
        
        # Обновление статуса на failed
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    UPDATE ticket_events
                    SET status = 'failed',
                        error_message = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE ticket_id = %s
                """, (str(e), ticket_id))
        except Exception as db_error:
            logger.error(f"Ошибка при обновлении статуса тикета {ticket_id} в БД: {db_error}")
        
        # Отправка в очередь failed_tickets для последующей обработки
        try:
            push_to_queue(QUEUE_FAILED_TICKETS, {
                **ticket_data,
                "error": str(e),
                "failed_at": datetime.utcnow().isoformat()
            })
        except Exception as queue_error:
            logger.error(f"Ошибка при добавлении тикета {ticket_id} в очередь failed: {queue_error}")
        
        return False


async def queue_worker_loop(classifier: ServiceDeskClassifier):
    """
    Основной цикл worker для обработки очереди
    
    Args:
        classifier: Экземпляр классификатора
    """
    global _worker_running
    
    output_service_url = os.getenv("OUTPUT_SERVICE_URL", "http://localhost:8003")
    queue_poll_timeout = int(os.getenv("WORKER_QUEUE_TIMEOUT", "5"))  # секунды
    worker_delay = float(os.getenv("WORKER_DELAY", "0.1"))  # секунды между итерациями
    
    logger.info(
        f"Worker запущен. Ожидание тикетов из очереди {QUEUE_PENDING_TICKETS} "
        f"(timeout={queue_poll_timeout}s, delay={worker_delay}s)"
    )
    
    _worker_running = True
    
    while _worker_running:
        try:
            # Получение тикета из очереди (блокирующий вызов с таймаутом)
            # Используем run_in_executor чтобы не блокировать event loop
            loop = asyncio.get_event_loop()
            def get_ticket():
                return pop_from_queue(QUEUE_PENDING_TICKETS, timeout=queue_poll_timeout)
            ticket_data = await loop.run_in_executor(None, get_ticket)
            
            if ticket_data:
                ticket_id = ticket_data.get("ticket_id", "unknown")
                logger.info(f"Worker: Получен тикет {ticket_id} из очереди, начинаю обработку...")
                # Обработка тикета
                success = await process_ticket_from_queue(
                    ticket_data,
                    classifier,
                    output_service_url
                )
                
                if success:
                    logger.debug(f"Тикет {ticket_data.get('ticket_id')} успешно обработан")
                else:
                    logger.warning(f"Тикет {ticket_data.get('ticket_id')} обработан с ошибкой")
            else:
                # Очередь пуста, небольшая задержка перед следующей проверкой
                await asyncio.sleep(worker_delay)
                
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки worker")
            _worker_running = False
            break
        except Exception as e:
            logger.error(f"Ошибка в цикле worker: {e}", exc_info=True)
            # Небольшая задержка перед повторной попыткой
            await asyncio.sleep(1.0)
    
    logger.info("Worker остановлен")
    _worker_running = False


def start_worker(classifier: ServiceDeskClassifier) -> Optional[asyncio.Task]:
    """
    Запуск worker в фоновом режиме
    
    Args:
        classifier: Экземпляр классификатора
        
    Returns:
        Task объект или None если worker не включен
    """
    global _worker_task, _worker_enabled
    
    worker_enabled = os.getenv("WORKER_ENABLED", "false").lower() == "true"
    
    if not worker_enabled:
        logger.info("Worker отключен (WORKER_ENABLED=false). Используйте REST API для классификации.")
        return None
    
    if _worker_task and not _worker_task.done():
        logger.warning("Worker уже запущен")
        return _worker_task
    
    logger.info("Запуск worker для обработки очереди Redis...")
    _worker_enabled = True
    _worker_task = asyncio.create_task(queue_worker_loop(classifier))
    
    return _worker_task


def stop_worker():
    """Остановка worker"""
    global _worker_task, _worker_running, _worker_enabled
    
    if not _worker_enabled:
        return
    
    logger.info("Остановка worker...")
    _worker_running = False
    
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        # Не ждем завершения синхронно, так как мы уже в event loop
        # Задача будет отменена асинхронно
        logger.debug("Задача worker отменена")
    
    _worker_task = None
    _worker_enabled = False
    logger.info("Worker остановлен")


def is_worker_running() -> bool:
    """Проверка, запущен ли worker"""
    return _worker_running and _worker_enabled

