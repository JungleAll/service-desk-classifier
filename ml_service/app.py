"""FastAPI приложение для классификации обращений Service Desk"""

import time
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, List
from datetime import datetime
import os
import httpx

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .classifier import ServiceDeskClassifier
from .models import (
    ClassifyRequest,
    ClassifyResponse,
    ProbabilityItem,
    BatchClassifyRequest,
    BatchClassifyResponse,
    BatchClassifyItem,
    ModelStatusResponse,
    ModelListResponse,
    ModelListItem,
    HealthResponse,
    ErrorResponse,
    ReloadResponse,
    WorkerDiagnosticsResponse
)
from .config import API_HOST, API_PORT, WORKER_ENABLED, CONFIDENCE_THRESHOLD
from .worker import start_worker, stop_worker, is_worker_running
from shared.redis_client import (
    get_cache, 
    set_cache, 
    CACHE_PREDICTIONS,
    get_queue_length,
    QUEUE_PENDING_TICKETS,
    QUEUE_FAILED_TICKETS,
    get_redis_queue_client
)
from shared.database import get_db_cursor
from shared.logger import configure_service_logging

# Настройка логирования
logger = configure_service_logging("ml")

# Глобальный экземпляр классификатора
classifier = ServiceDeskClassifier()

# Метрики сервиса
_service_start_time = None
_request_count = 0
_error_count = 0
_total_latency_ms = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    global _service_start_time
    # Startup: загрузка модели
    logger.info("Запуск приложения...")
    _service_start_time = datetime.utcnow()
    # Попытка получить текущую версию модели из Config Service
    # Делаем несколько попыток, так как Config Service может быть еще не готов
    config_url = os.getenv("CONFIG_SERVICE_URL", "http://localhost:8002")
    current_version = None
    max_retries = 5
    retry_delay = 2.0
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{config_url}/config")
                if resp.status_code == 200:
                    cfg = resp.json()
                    current_version = cfg.get("current_model_version")
                    if current_version:
                        os.environ["ML_MODEL_VERSION"] = current_version
                        logger.info(f"✅ Установлена версия модели из Config: {current_version}")
                        break
                    else:
                        logger.warning(f"Config Service не вернул current_model_version (попытка {attempt + 1}/{max_retries})")
                else:
                    logger.warning(f"Config Service вернул статус {resp.status_code} (попытка {attempt + 1}/{max_retries})")
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Не удалось получить конфигурацию из {config_url} (попытка {attempt + 1}/{max_retries}): {e}. Повтор через {retry_delay}с...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"Не удалось получить конфигурацию из {config_url} после {max_retries} попыток: {e}")
                logger.warning("Использую версию модели по умолчанию из переменной окружения ML_MODEL_VERSION")
    
    # Если версия не получена из Config, используем значение из окружения или дефолт
    if not current_version:
        current_version = os.getenv("ML_MODEL_VERSION", "v1.0")
        logger.info(f"Использую версию модели: {current_version} (из переменной окружения или дефолт)")
        os.environ["ML_MODEL_VERSION"] = current_version

    success = classifier.load_model()
    if not success:
        logger.error("Не удалось загрузить модель при старте приложения")
    else:
        logger.info(f"✅ Модель успешно загружена: версия {classifier.model_version}")
    
    # Запуск worker для обработки очереди (если включен)
    worker_task = None
    if WORKER_ENABLED:
        try:
            worker_task = start_worker(classifier)
            if worker_task:
                logger.info("✅ Worker для обработки очереди запущен")
            else:
                logger.info("ℹ️ Worker не запущен (WORKER_ENABLED=false или ошибка)")
        except Exception as e:
            logger.error(f"Ошибка при запуске worker: {e}", exc_info=True)
    else:
        logger.info("ℹ️ Worker отключен. Используйте REST API для классификации.")
    
    yield
    
    # Shutdown: остановка worker и очистка ресурсов
    logger.info("Остановка приложения...")
    if worker_task:
        try:
            stop_worker()
        except Exception as e:
            logger.error(f"Ошибка при остановке worker: {e}")


# Создание FastAPI приложения
app = FastAPI(
    title="Service Desk Classifier API",
    description="ML Service для автоматической классификации обращений Service Desk",
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


# Обработчик ошибок
@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """Глобальный обработчик ошибок - возвращает 503 с JSON"""
    logger.error(f"Необработанная ошибка: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "Service Unavailable",
            "detail": str(exc)
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Обработчик HTTP исключений - возвращает JSON"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "detail": None
        }
    )


@app.get("/", tags=["Root"])
async def root():
    """Корневой endpoint"""
    return {
        "service": "Service Desk Classifier API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.post(
    "/classify",
    response_model=ClassifyResponse,
    status_code=status.HTTP_200_OK,
    tags=["Classification"],
    summary="Классифицировать текст",
    description="""Классификация текста обращения.
    
**Поведение:**
- Проверяет кэш Redis DB 1 (ключ: cache_predictions:{version}:{hash})
- Если кэш найден → возвращает результат из кэша (быстро)
- Если кэш не найден:
  - Проверяет версию модели из Config Service перед классификацией (автоперезагрузка при несоответствии)
  - Выполняет классификацию через модель
  - Сохраняет результат в кэш (TTL: 3600s)
- Определяет decision на основе confidence_threshold из Config Service
- Версия модели включается в ключ кэша, чтобы после переключения версии не использовать старые результаты

**Ошибки:**
- 400: Некорректный текст (минимум 3 символа)
- 503: Модель не загружена или сервис недоступен"""
)
async def classify_text(request: ClassifyRequest) -> ClassifyResponse:
    """
    Классификация текста обращения
    
    - **text**: Текст обращения (минимум 3 символа)
    - **return_probabilities**: Возвращать ли вероятности (по умолчанию True)
    - **top_n**: Топ-N вероятностей для возврата (если None - все)
    
    Возвращает:
    - **predicted_type**: Предсказанный класс
    - **confidence**: Уверенность модели (0-1)
    - **probabilities**: Массив вероятностей [{"category": "...", "score": 0.95}]
    - **model_version**: Версия модели
    - **decision**: "auto-process" или "manual-review"
    - **processing_time_ms**: Время обработки в миллисекундах
    """
    global _request_count, _error_count, _total_latency_ms
    
    if not classifier.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Модель не загружена. Сервис недоступен."
        )
    
    start_time = time.time()
    _request_count += 1
    
    try:
        # Перед классификацией: быстрая проверка версии модели из Config Service
        try:
            config_url = os.getenv("CONFIG_SERVICE_URL", "http://localhost:8002")
            async with httpx.AsyncClient(timeout=1.5) as client:
                resp = await client.get(f"{config_url}/config")
                if resp.status_code == 200:
                    cfg = resp.json()
                    desired_version = cfg.get("current_model_version")
                    if desired_version and desired_version != classifier.model_version:
                        logger.info(f"Обнаружено несоответствие версии (ML={classifier.model_version}, Config={desired_version}). Перезагружаю модель...")
                        os.environ["ML_MODEL_VERSION"] = desired_version
                        if classifier.reload_model():
                            logger.info(f"Модель успешно перезагружена на версию {desired_version}. Текущая версия ML: {classifier.model_version}")
                        else:
                            logger.warning(f"Перезагрузка модели на версию {desired_version} не удалась, продолжаю с текущей версией {classifier.model_version}")
                    elif desired_version:
                        logger.debug(f"Версии совпадают: ML={classifier.model_version}, Config={desired_version}")
        except Exception as e:
            # Не блокируем классификацию, если Config недоступен
            logger.debug(f"Не удалось проверить версию модели в Config перед классификацией: {e}")

        # Проверка кэша (используем текст как ключ, так как Redis поддерживает длинные ключи)
        import hashlib
        text_hash = hashlib.md5(request.text.encode('utf-8')).hexdigest()
        # Включаем версию модели в ключ кэша, чтобы после переключения версии не использовать старые результаты
        cache_key = f"{CACHE_PREDICTIONS}:{classifier.model_version}:{text_hash}"
        cached_result = get_cache(cache_key)
        
        if cached_result:
            logger.debug(f"Результат получен из кэша для текста: {request.text[:50]}...")
            processing_time = int((time.time() - start_time) * 1000)
            _total_latency_ms += processing_time
            
            # Преобразование кэшированного результата (сортировка по убыванию)
            probabilities_dict = cached_result.get('probabilities', {})
            probabilities_list = [
                ProbabilityItem(category=k, score=v)
                for k, v in sorted(probabilities_dict.items(), key=lambda x: x[1], reverse=True)
            ]
            
            # Применение top_n если указан
            if request.top_n and len(probabilities_list) > request.top_n:
                probabilities_list = probabilities_list[:request.top_n]
            
            # Получение актуального порога уверенности из Config Service и переопределение decision
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
            
            # Переопределение decision на основе актуального порога
            cached_confidence = cached_result['confidence']
            decision = "auto-process" if cached_confidence >= confidence_threshold else "manual-review"
            
            return ClassifyResponse(
                predicted_type=cached_result['predicted_type'],
                confidence=cached_confidence,
                probabilities=probabilities_list if request.return_probabilities else [],
                model_version=cached_result['model_version'],
                decision=decision,
                processing_time_ms=processing_time
            )
        
        # Классификация
        result = classifier.predict(request.text, top_n=request.top_n)
        
        # Преобразование probabilities в список объектов
        probabilities_dict = result.get('probabilities', {})
        probabilities_list = [
            ProbabilityItem(category=k, score=v)
            for k, v in sorted(probabilities_dict.items(), key=lambda x: x[1], reverse=True)
        ]
        
        # Применение top_n если указан
        if request.top_n and len(probabilities_list) > request.top_n:
            probabilities_list = probabilities_list[:request.top_n]
        
        processing_time = int((time.time() - start_time) * 1000)
        _total_latency_ms += processing_time
        
        # Получение актуального порога уверенности из Config Service и переопределение decision
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
        
        # Переопределение decision на основе актуального порога
        decision = "auto-process" if result['confidence'] >= confidence_threshold else "manual-review"
        
        # Сохранение в кэш (сохраняем decision с актуальным порогом)
        cache_data = {
            'predicted_type': result['predicted_type'],
            'confidence': result['confidence'],
            'probabilities': probabilities_dict,
            'model_version': result['model_version'],
            'decision': decision
        }
        set_cache(cache_key, cache_data, ttl=3600)
        
        # Логирование в БД
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO metrics (model_version, metric_name, metric_value, calculated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (result['model_version'], 'classification_count', 1, datetime.utcnow()))
        except Exception as e:
            logger.warning(f"Не удалось сохранить метрику в БД: {e}")
        
        return ClassifyResponse(
            predicted_type=result['predicted_type'],
            confidence=result['confidence'],
            probabilities=probabilities_list if request.return_probabilities else [],
            model_version=result['model_version'],
            decision=decision,
            processing_time_ms=processing_time
        )
        
    except ValueError as e:
        _error_count += 1
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        _error_count += 1
        logger.error(f"Ошибка при классификации: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при классификации: {str(e)}"
        )


@app.get(
    "/model/status",
    response_model=ModelStatusResponse,
    tags=["Model"],
    summary="Статус модели",
    description="""Возвращает информацию о загруженной модели.
    
**Возвращаемые поля:**
- model_version: версия модели
- model_name: название модели (опционально)
- status: 'loaded' | 'not_loaded' (опционально)
- is_loaded: загружена ли модель
- num_classes: количество классов (опционально)
- classes: список классов (опционально)
- accuracy, precision, recall, f1_score: метрики модели (опционально)
- loaded_at: время загрузки модели в ISO формате (опционально)
- memory_usage_mb: использование памяти в МБ (опционально)
- classifier_path, vectorizer_path, label_encoder_path: пути к файлам модели"""
)
async def get_model_status() -> ModelStatusResponse:
    """Получение информации о модели"""
    try:
        info = classifier.get_model_info()
        
        # Получение метрик из БД
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    SELECT metric_name, metric_value
                    FROM metrics
                    WHERE model_version = %s
                    ORDER BY calculated_at DESC
                    LIMIT 10
                """, (classifier.model_version,))
                metrics_rows = cursor.fetchall()
                
                # Поиск последних метрик
                metrics_dict = {}
                for row in metrics_rows:
                    metric_name = row['metric_name']
                    if metric_name in ['accuracy', 'precision', 'recall', 'f1_score']:
                        if metric_name not in metrics_dict:
                            metrics_dict[metric_name] = float(row['metric_value'])
                
                # Добавление метрик в info
                if 'accuracy' in metrics_dict:
                    info['accuracy'] = metrics_dict['accuracy']
                if 'precision' in metrics_dict:
                    info['precision'] = metrics_dict['precision']
                if 'recall' in metrics_dict:
                    info['recall'] = metrics_dict['recall']
                if 'f1_score' in metrics_dict:
                    info['f1_score'] = metrics_dict['f1_score']
        except Exception as e:
            logger.warning(f"Не удалось получить метрики из БД: {e}")
        
        # Добавление дополнительных полей из спецификации
        info['model_name'] = 'classifier_smote_new'  # Используем только стабильную рабочую модель
        info['status'] = 'loaded' if classifier.is_loaded else 'not_loaded'
        if classifier.is_loaded and _service_start_time:
            info['loaded_at'] = _service_start_time.isoformat()
        
        return ModelStatusResponse(**info)
    except Exception as e:
        logger.error(f"Ошибка при получении статуса модели: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при получении статуса: {str(e)}"
        )


@app.post(
    "/classify/batch",
    response_model=BatchClassifyResponse,
    tags=["Classification"],
    summary="Классифицировать пакет текстов",
    description="""Пакетная классификация текстов.
    
**Request:** { texts: string[] } - массив текстов для классификации
**Response:** 
- results: массив результатов [{ text, predicted_type, confidence }]
- total_time_ms: общее время обработки в миллисекундах

**Примечание:** Тексты с длиной менее 3 символов пропускаются."""
)
async def classify_batch(request: BatchClassifyRequest) -> BatchClassifyResponse:
    """Пакетная классификация текстов"""
    global _request_count, _error_count, _total_latency_ms
    
    if not classifier.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Модель не загружена. Сервис недоступен."
        )
    
    start_time = time.time()
    _request_count += 1
    
    try:
        results = []
        for text in request.texts:
            try:
                if not text or len(text.strip()) < 3:
                    continue
                
                result = classifier.predict(text)
                results.append(BatchClassifyItem(
                    text=text,
                    predicted_type=result['predicted_type'],
                    confidence=result['confidence']
                ))
            except Exception as e:
                logger.warning(f"Ошибка при классификации текста в пакете: {e}")
                _error_count += 1
        
        total_time = int((time.time() - start_time) * 1000)
        _total_latency_ms += total_time
        
        return BatchClassifyResponse(
            results=results,
            total_time_ms=total_time
        )
        
    except Exception as e:
        _error_count += 1
        logger.error(f"Ошибка при пакетной классификации: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при пакетной классификации: {str(e)}"
        )


@app.get(
    "/model/list",
    response_model=ModelListResponse,
    tags=["Model"],
    summary="Список доступных моделей",
    description="""Возвращает список всех доступных версий моделей из базы данных.
    
**Response:** 
- models: массив моделей [{ version, name, accuracy?, is_active, created_at? }]
- Модели отсортированы по дате создания (DESC)"""
)
async def get_model_list() -> ModelListResponse:
    """Получение списка доступных моделей"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT version, model_path, accuracy, is_active, created_at
                FROM model_versions
                ORDER BY created_at DESC
            """)
            results = cursor.fetchall()
        
        models = []
        for row in results:
            # Извлечение имени модели из пути
            model_path = row['model_path']
            model_name = model_path.split('/')[-1].replace('.pkl', '') if model_path else 'unknown'
            
            models.append(ModelListItem(
                version=row['version'],
                name=model_name,
                accuracy=float(row['accuracy']) if row['accuracy'] else None,
                is_active=bool(row['is_active']),
                created_at=row['created_at'].isoformat() if row['created_at'] else None
            ))
        
        return ModelListResponse(models=models)
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка моделей: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении списка моделей: {str(e)}"
        )


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Healthcheck",
    description="""Проверка работоспособности сервиса с метриками.
    
**Response (200|503):**
- status: 'healthy' | 'unhealthy'
- model_loaded: загружена ли модель
- model_version: версия модели (опционально)
- uptime_seconds: время работы сервиса в секундах (опционально)
- requests_total: общее количество запросов (опционально)
- errors_total: общее количество ошибок (опционально)
- avg_latency_ms: средняя задержка в мс (опционально)
- message: дополнительное сообщение
- reason: причина, если unhealthy (опционально)

**Статус 503:** возвращается, если модель не загружена"""
)
async def health_check() -> HealthResponse:
    """Проверка здоровья сервиса с метриками"""
    global _service_start_time, _request_count, _error_count, _total_latency_ms
    
    if not classifier.is_loaded:
        return HealthResponse(
            status="unhealthy",
            model_loaded=False,
            model_version=None,
            uptime_seconds=None,
            requests_total=None,
            errors_total=None,
            avg_latency_ms=None,
            message="Модель не загружена",
            reason="Model not loaded"
        )
    
    # Вычисление uptime
    uptime_seconds = None
    if _service_start_time:
        uptime_seconds = int((datetime.utcnow() - _service_start_time).total_seconds())
    
    # Вычисление средней задержки
    avg_latency = None
    if _request_count > 0:
        avg_latency = _total_latency_ms / _request_count
    
    # Проверка статуса worker
    worker_status = "enabled" if WORKER_ENABLED else "disabled"
    if WORKER_ENABLED:
        worker_status = "running" if is_worker_running() else "stopped"
    
    message = "Сервис работает нормально"
    if WORKER_ENABLED:
        message += f" (Worker: {worker_status})"
    
    return HealthResponse(
        status="healthy",
        model_loaded=True,
        model_version=classifier.model_version,
        uptime_seconds=uptime_seconds,
        requests_total=_request_count,
        errors_total=_error_count,
        avg_latency_ms=avg_latency,
        message=message,
        reason=None
    )


@app.post(
    "/reload_model",
    response_model=ReloadResponse,
    tags=["Model"],
    summary="Перезагрузка модели",
    description="""Hot reload модели без остановки сервиса.
    
**Поведение:**
- Обновляет версию модели из Config Service перед перезагрузкой
- Выполняет перезагрузку модели в памяти
- Не требует перезапуска сервиса

**Response:**
- success: успешна ли перезагрузка
- message: сообщение о результате
- model_version: версия модели после перезагрузки (опционально)

**Ошибки:**
- 503: если не удалось перезагрузить модель"""
)
async def reload_model() -> ReloadResponse:
    """Перезагрузка модели (hot reload)"""
    try:
        logger.info("Запрос на перезагрузку модели")
        # Обновляем версию модели из Config Service перед перезагрузкой
        config_url = os.getenv("CONFIG_SERVICE_URL", "http://localhost:8002")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{config_url}/config")
                if resp.status_code == 200:
                    cfg = resp.json()
                    current_version = cfg.get("current_model_version")
                    if current_version:
                        os.environ["ML_MODEL_VERSION"] = current_version
                        logger.info(f"Перед reload установлена версия модели: {current_version}")
        except Exception as e:
            logger.warning(f"Не удалось обновить версию из Config перед reload: {e}")

        success = classifier.reload_model()
        
        if success:
            return ReloadResponse(
                success=True,
                message="Модель успешно перезагружена",
                model_version=classifier.model_version
            )
        else:
            return ReloadResponse(
                success=False,
                message="Не удалось перезагрузить модель. Проверьте логи.",
                model_version=None
            )
    except Exception as e:
        logger.error(f"Ошибка при перезагрузке модели: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Ошибка при перезагрузке модели: {str(e)}"
        )


@app.get(
    "/worker/diagnostics",
    response_model=WorkerDiagnosticsResponse,
    tags=["Worker"],
    summary="Диагностика Worker и очереди",
    description="""Получение диагностической информации о Worker и очереди Redis.
    
**Возвращает:**
- worker_enabled: включен ли Worker (WORKER_ENABLED)
- worker_running: запущен ли Worker
- model_loaded: загружена ли модель
- queue_pending_length: количество тикетов в очереди pending_tickets
- queue_failed_length: количество тикетов в очереди failed_tickets
- redis_connected: подключен ли Redis
- message: сообщение о статусе

**Использование:**
Проверьте этот endpoint, если тикеты не обрабатываются:
1. Если worker_enabled=false → установите WORKER_ENABLED=true
2. Если worker_running=false → проверьте логи ML Service
3. Если queue_pending_length > 0 и worker_running=true → Worker не обрабатывает очередь
4. Если redis_connected=false → проверьте подключение к Redis"""
)
async def worker_diagnostics() -> WorkerDiagnosticsResponse:
    """Диагностика Worker и очереди"""
    try:
        # Проверка статуса Worker
        worker_enabled = WORKER_ENABLED
        worker_running = is_worker_running() if worker_enabled else False
        model_loaded = classifier.is_loaded
        
        # Проверка подключения к Redis и длины очереди
        redis_connected = False
        pending_length = 0
        failed_length = 0
        
        try:
            client = get_redis_queue_client()
            client.ping()
            redis_connected = True
            pending_length = get_queue_length(QUEUE_PENDING_TICKETS)
            failed_length = get_queue_length(QUEUE_FAILED_TICKETS)
        except Exception as e:
            logger.warning(f"Не удалось подключиться к Redis для диагностики: {e}")
            redis_connected = False
        
        # Формирование сообщения
        messages = []
        if not worker_enabled:
            messages.append("Worker отключен (WORKER_ENABLED=false). Установите WORKER_ENABLED=true для автоматической обработки очереди.")
        elif not worker_running:
            messages.append("Worker включен, но не запущен. Проверьте логи ML Service.")
        else:
            messages.append("Worker запущен и работает.")
        
        if not model_loaded:
            messages.append("Модель не загружена. Проверьте наличие файлов модели в models/v1.0/.")
        
        if not redis_connected:
            messages.append("Redis недоступен. Проверьте подключение к Redis.")
        
        if pending_length > 0:
            messages.append(f"В очереди {pending_length} тикет(ов) ожидают обработки.")
        
        if failed_length > 0:
            messages.append(f"В очереди failed_tickets {failed_length} тикет(ов).")
        
        message = " ".join(messages) if messages else "Все системы работают нормально."
        
        return WorkerDiagnosticsResponse(
            worker_enabled=worker_enabled,
            worker_running=worker_running,
            model_loaded=model_loaded,
            queue_pending_length=pending_length,
            queue_failed_length=failed_length,
            redis_connected=redis_connected,
            message=message
        )
    except Exception as e:
        logger.error(f"Ошибка при получении диагностики Worker: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении диагностики: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    log_level = os.getenv("LOG_LEVEL", "INFO").lower()
    uvicorn.run(
        "app:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level=log_level
    )

