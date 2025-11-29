-- Миграция: Добавление полей для дообучения модели (Расширенная схема)
-- Дата: 2025-11-19
-- Описание: Расширение схемы БД для поддержки дообучения модели на основе обратной связи
-- Использует отдельные таблицы для обратной связи и истории изменений

-- ============================================================================
-- Минимальные поля в ticket_events (для связи с новыми таблицами)
-- ============================================================================

-- Добавление полей в ticket_events для хранения правильной категории
ALTER TABLE ticket_events
ADD COLUMN IF NOT EXISTS actual_type VARCHAR(255),
ADD COLUMN IF NOT EXISTS actual_type_set_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS actual_type_set_by VARCHAR(255);

-- Добавление полей для отслеживания использования в обучении
ALTER TABLE ticket_events
ADD COLUMN IF NOT EXISTS training_ready BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS training_ready_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS training_used_in_version VARCHAR(50);

-- Флаги для связи с новыми таблицами
ALTER TABLE ticket_events
ADD COLUMN IF NOT EXISTS has_feedback BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS has_correction BOOLEAN DEFAULT FALSE;

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_ticket_events_actual_type ON ticket_events(actual_type);
CREATE INDEX IF NOT EXISTS idx_ticket_events_actual_type_set_at ON ticket_events(actual_type_set_at);
CREATE INDEX IF NOT EXISTS idx_ticket_events_training_ready ON ticket_events(training_ready);
CREATE INDEX IF NOT EXISTS idx_ticket_events_training_used_in_version ON ticket_events(training_used_in_version);
CREATE INDEX IF NOT EXISTS idx_ticket_events_has_feedback ON ticket_events(has_feedback);
CREATE INDEX IF NOT EXISTS idx_ticket_events_has_correction ON ticket_events(has_correction);

-- Комментарии к полям
COMMENT ON COLUMN ticket_events.actual_type IS 'Фактическая категория тикета после ручной обработки';
COMMENT ON COLUMN ticket_events.actual_type_set_at IS 'Когда была установлена фактическая категория';
COMMENT ON COLUMN ticket_events.actual_type_set_by IS 'Кто установил фактическую категорию (оператор, система)';
COMMENT ON COLUMN ticket_events.training_ready IS 'Готов ли тикет для использования в обучении';
COMMENT ON COLUMN ticket_events.training_ready_at IS 'Когда тикет был помечен как готовый для обучения';
COMMENT ON COLUMN ticket_events.training_used_in_version IS 'В какой версии модели был использован тикет';
COMMENT ON COLUMN ticket_events.has_feedback IS 'Есть ли обратная связь в таблице classification_feedback';
COMMENT ON COLUMN ticket_events.has_correction IS 'Есть ли исправление в таблице category_corrections';

-- ============================================================================
-- Таблица для обратной связи по классификации
-- ============================================================================

CREATE TABLE IF NOT EXISTS classification_feedback (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(255) NOT NULL,
    feedback_type VARCHAR(50) NOT NULL,  -- 'correct', 'incorrect', 'partial'
    original_predicted_type VARCHAR(255),  -- что предсказала модель
    correct_type VARCHAR(255),  -- правильная категория
    confidence_at_feedback FLOAT,  -- уверенность модели на момент обратной связи
    comment TEXT,  -- комментарий пользователя/оператора
    provided_by VARCHAR(255),  -- кто предоставил обратную связь
    provided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE,  -- обработана ли обратная связь для обучения
    processed_at TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES ticket_events(ticket_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_classification_feedback_ticket_id ON classification_feedback(ticket_id);
CREATE INDEX IF NOT EXISTS idx_classification_feedback_type ON classification_feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_classification_feedback_processed ON classification_feedback(processed);
CREATE INDEX IF NOT EXISTS idx_classification_feedback_provided_at ON classification_feedback(provided_at);

COMMENT ON TABLE classification_feedback IS 'Обратная связь по классификации тикетов';
COMMENT ON COLUMN classification_feedback.feedback_type IS 'Тип обратной связи: correct, incorrect, partial';
COMMENT ON COLUMN classification_feedback.processed IS 'Обработана ли обратная связь для использования в обучении';

-- ============================================================================
-- Таблица для истории изменений категорий
-- ============================================================================

CREATE TABLE IF NOT EXISTS category_corrections (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(255) NOT NULL,
    original_type VARCHAR(255),  -- исходная категория (predicted_type)
    corrected_type VARCHAR(255) NOT NULL,  -- исправленная категория
    correction_reason VARCHAR(255),  -- причина исправления ('manual_review', 'feedback', 'admin_correction', 'jira_sync')
    corrected_by VARCHAR(255) NOT NULL,  -- кто исправил
    corrected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confidence_at_correction FLOAT,  -- уверенность модели на момент исправления
    used_in_training BOOLEAN DEFAULT FALSE,  -- использовано ли в обучении
    used_in_version VARCHAR(50),  -- в какой версии модели использовано
    FOREIGN KEY (ticket_id) REFERENCES ticket_events(ticket_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_category_corrections_ticket_id ON category_corrections(ticket_id);
CREATE INDEX IF NOT EXISTS idx_category_corrections_corrected_type ON category_corrections(corrected_type);
CREATE INDEX IF NOT EXISTS idx_category_corrections_used_in_training ON category_corrections(used_in_training);
CREATE INDEX IF NOT EXISTS idx_category_corrections_corrected_at ON category_corrections(corrected_at);
CREATE INDEX IF NOT EXISTS idx_category_corrections_correction_reason ON category_corrections(correction_reason);

COMMENT ON TABLE category_corrections IS 'История исправлений категорий тикетов';
COMMENT ON COLUMN category_corrections.correction_reason IS 'Причина исправления: manual_review, feedback, admin_correction, jira_sync';

-- ============================================================================
-- Таблица для отслеживания использования данных в обучении
-- ============================================================================

CREATE TABLE IF NOT EXISTS training_data_usage (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(255) NOT NULL,
    model_version VARCHAR(50) NOT NULL,  -- версия модели, в которой использованы данные
    training_type VARCHAR(50) NOT NULL,  -- 'initial', 'retraining', 'incremental'
    data_type VARCHAR(50) NOT NULL,  -- 'manual_review', 'feedback', 'correction'
    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES ticket_events(ticket_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_training_data_usage_ticket_id ON training_data_usage(ticket_id);
CREATE INDEX IF NOT EXISTS idx_training_data_usage_model_version ON training_data_usage(model_version);
CREATE INDEX IF NOT EXISTS idx_training_data_usage_training_type ON training_data_usage(training_type);

COMMENT ON TABLE training_data_usage IS 'Отслеживание использования тикетов в обучении моделей';
COMMENT ON COLUMN training_data_usage.training_type IS 'Тип обучения: initial, retraining, incremental';
COMMENT ON COLUMN training_data_usage.data_type IS 'Тип данных: manual_review, feedback, correction';

-- ============================================================================
-- Представления (Views) для удобного доступа к данным для обучения
-- ============================================================================

-- Представление для тикетов, готовых для обучения
CREATE OR REPLACE VIEW training_ready_tickets AS
SELECT 
    te.ticket_id,
    te.text,
    te.actual_type,
    te.predicted_type,
    te.confidence,
    te.decision,
    te.model_version,
    te.source,
    te.created_at,
    te.actual_type_set_at,
    te.actual_type_set_by,
    te.training_ready_at,
    cc.corrected_type,
    cc.correction_reason,
    cc.corrected_at
FROM ticket_events te
LEFT JOIN category_corrections cc ON te.ticket_id = cc.ticket_id 
    AND cc.used_in_training = FALSE
    AND cc.id = (
        SELECT id FROM category_corrections 
        WHERE ticket_id = te.ticket_id 
        ORDER BY corrected_at DESC 
        LIMIT 1
    )
WHERE te.training_ready = TRUE
  AND te.actual_type IS NOT NULL
  AND (te.training_used_in_version IS NULL OR te.training_used_in_version = '');

COMMENT ON VIEW training_ready_tickets IS 'Тикеты, готовые для использования в обучении';

-- Представление для тикетов с обратной связью
CREATE OR REPLACE VIEW tickets_with_feedback AS
SELECT 
    te.ticket_id,
    te.text,
    te.predicted_type,
    te.actual_type,
    cf.feedback_type,
    cf.correct_type,
    cf.comment,
    cf.provided_at,
    cf.provided_by,
    cf.processed,
    te.confidence,
    te.decision
FROM ticket_events te
LEFT JOIN classification_feedback cf ON te.ticket_id = cf.ticket_id
WHERE te.has_feedback = TRUE
   OR cf.id IS NOT NULL;

COMMENT ON VIEW tickets_with_feedback IS 'Тикеты с обратной связью по классификации';

-- Представление для тикетов с manual-review, ожидающих разметки
CREATE OR REPLACE VIEW manual_review_pending AS
SELECT 
    ticket_id,
    text,
    predicted_type,
    confidence,
    decision,
    created_at,
    processed_at
FROM ticket_events
WHERE decision = 'manual-review'
  AND actual_type IS NULL
  AND status = 'completed'
ORDER BY created_at DESC;

COMMENT ON VIEW manual_review_pending IS 'Тикеты с manual-review, ожидающие установки правильной категории';

-- ============================================================================
-- Функции для автоматической установки training_ready и обновления флагов
-- ============================================================================

-- Функция для автоматической установки training_ready при установке actual_type
CREATE OR REPLACE FUNCTION set_training_ready_on_actual_type()
RETURNS TRIGGER AS $$
BEGIN
    -- Если установлена actual_type и decision='manual-review', помечаем как готовый
    IF NEW.actual_type IS NOT NULL 
       AND NEW.decision = 'manual-review' 
       AND (OLD.actual_type IS NULL OR OLD.actual_type != NEW.actual_type) THEN
        NEW.training_ready = TRUE;
        NEW.training_ready_at = CURRENT_TIMESTAMP;
        NEW.actual_type_set_at = CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для автоматической установки training_ready
DROP TRIGGER IF EXISTS trigger_set_training_ready ON ticket_events;
CREATE TRIGGER trigger_set_training_ready
    BEFORE UPDATE ON ticket_events
    FOR EACH ROW
    EXECUTE FUNCTION set_training_ready_on_actual_type();

COMMENT ON FUNCTION set_training_ready_on_actual_type() IS 'Автоматически устанавливает training_ready=TRUE при установке actual_type для тикетов с manual-review';

-- Функция для обновления флага has_feedback при добавлении обратной связи
CREATE OR REPLACE FUNCTION update_has_feedback_flag()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE ticket_events
    SET has_feedback = TRUE
    WHERE ticket_id = NEW.ticket_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для обновления флага has_feedback
DROP TRIGGER IF EXISTS trigger_update_has_feedback ON classification_feedback;
CREATE TRIGGER trigger_update_has_feedback
    AFTER INSERT ON classification_feedback
    FOR EACH ROW
    EXECUTE FUNCTION update_has_feedback_flag();

COMMENT ON FUNCTION update_has_feedback_flag() IS 'Автоматически обновляет has_feedback=TRUE при добавлении обратной связи';

-- Функция для обновления флага has_correction при добавлении исправления
CREATE OR REPLACE FUNCTION update_has_correction_flag()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE ticket_events
    SET has_correction = TRUE
    WHERE ticket_id = NEW.ticket_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для обновления флага has_correction
DROP TRIGGER IF EXISTS trigger_update_has_correction ON category_corrections;
CREATE TRIGGER trigger_update_has_correction
    AFTER INSERT ON category_corrections
    FOR EACH ROW
    EXECUTE FUNCTION update_has_correction_flag();

COMMENT ON FUNCTION update_has_correction_flag() IS 'Автоматически обновляет has_correction=TRUE при добавлении исправления категории';

-- ============================================================================
-- Завершение миграции
-- ============================================================================

-- Логирование завершения миграции
DO $$
BEGIN
    RAISE NOTICE 'Миграция 001_add_retraining_fields_extended.sql успешно выполнена';
    RAISE NOTICE 'Созданы таблицы: classification_feedback, category_corrections, training_data_usage';
    RAISE NOTICE 'Добавлены поля в ticket_events: actual_type, training_ready, has_feedback, has_correction';
    RAISE NOTICE 'Созданы индексы, представления и триггеры для автоматического обновления';
END $$;

