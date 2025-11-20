-- Миграция: Добавление полей для дообучения модели
-- Дата: 2025-11-19
-- Описание: Расширение схемы БД для поддержки дообучения модели на основе обратной связи

-- ============================================================================
-- ВАРИАНТ 1: Минимальное расширение (для быстрого старта)
-- ============================================================================

-- Добавление полей в ticket_events для хранения правильной категории
ALTER TABLE ticket_events
ADD COLUMN IF NOT EXISTS actual_type VARCHAR(255),
ADD COLUMN IF NOT EXISTS actual_type_set_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS actual_type_set_by VARCHAR(255);

-- Добавление полей для обратной связи
ALTER TABLE ticket_events
ADD COLUMN IF NOT EXISTS feedback_status VARCHAR(50) DEFAULT 'none',
ADD COLUMN IF NOT EXISTS feedback_correct_type VARCHAR(255),
ADD COLUMN IF NOT EXISTS feedback_comment TEXT,
ADD COLUMN IF NOT EXISTS feedback_provided_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS feedback_provided_by VARCHAR(255);

-- Добавление полей для отслеживания использования в обучении
ALTER TABLE ticket_events
ADD COLUMN IF NOT EXISTS training_ready BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS training_ready_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS training_used_in_version VARCHAR(50);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_ticket_events_actual_type ON ticket_events(actual_type);
CREATE INDEX IF NOT EXISTS idx_ticket_events_actual_type_set_at ON ticket_events(actual_type_set_at);
CREATE INDEX IF NOT EXISTS idx_ticket_events_feedback_status ON ticket_events(feedback_status);
CREATE INDEX IF NOT EXISTS idx_ticket_events_training_ready ON ticket_events(training_ready);
CREATE INDEX IF NOT EXISTS idx_ticket_events_training_used_in_version ON ticket_events(training_used_in_version);

-- Комментарии к полям
COMMENT ON COLUMN ticket_events.actual_type IS 'Фактическая категория тикета после ручной обработки';
COMMENT ON COLUMN ticket_events.actual_type_set_at IS 'Когда была установлена фактическая категория';
COMMENT ON COLUMN ticket_events.actual_type_set_by IS 'Кто установил фактическую категорию (оператор, система)';
COMMENT ON COLUMN ticket_events.feedback_status IS 'Статус обратной связи: none, correct, incorrect, pending';
COMMENT ON COLUMN ticket_events.feedback_correct_type IS 'Правильная категория по обратной связи';
COMMENT ON COLUMN ticket_events.feedback_comment IS 'Комментарий к обратной связи';
COMMENT ON COLUMN ticket_events.feedback_provided_at IS 'Когда была предоставлена обратная связь';
COMMENT ON COLUMN ticket_events.feedback_provided_by IS 'Кто предоставил обратную связь';
COMMENT ON COLUMN ticket_events.training_ready IS 'Готов ли тикет для использования в обучении';
COMMENT ON COLUMN ticket_events.training_ready_at IS 'Когда тикет был помечен как готовый для обучения';
COMMENT ON COLUMN ticket_events.training_used_in_version IS 'В какой версии модели был использован тикет';

-- ============================================================================
-- ВАРИАНТ 2: Расширенное решение (рекомендуется для production)
-- Раскомментируйте, если хотите использовать расширенную схему
-- ============================================================================

/*
-- Таблица для обратной связи по классификации
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

-- Таблица для истории изменений категорий
CREATE TABLE IF NOT EXISTS category_corrections (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(255) NOT NULL,
    original_type VARCHAR(255),  -- исходная категория (predicted_type)
    corrected_type VARCHAR(255) NOT NULL,  -- исправленная категория
    correction_reason VARCHAR(255),  -- причина исправления ('manual_review', 'feedback', 'admin_correction')
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

COMMENT ON TABLE category_corrections IS 'История исправлений категорий тикетов';
COMMENT ON COLUMN category_corrections.correction_reason IS 'Причина исправления: manual_review, feedback, admin_correction';

-- Таблица для отслеживания использования данных в обучении
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

-- Обновление ticket_events для связи с новыми таблицами
ALTER TABLE ticket_events
ADD COLUMN IF NOT EXISTS has_feedback BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS has_correction BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_ticket_events_has_feedback ON ticket_events(has_feedback);
CREATE INDEX IF NOT EXISTS idx_ticket_events_has_correction ON ticket_events(has_correction);
*/

-- ============================================================================
-- Представления (Views) для удобного доступа к данным для обучения
-- ============================================================================

-- Представление для тикетов, готовых для обучения
CREATE OR REPLACE VIEW training_ready_tickets AS
SELECT 
    ticket_id,
    text,
    actual_type,
    predicted_type,
    confidence,
    decision,
    model_version,
    source,
    created_at,
    actual_type_set_at,
    actual_type_set_by,
    training_ready_at
FROM ticket_events
WHERE training_ready = TRUE
  AND actual_type IS NOT NULL
  AND (training_used_in_version IS NULL OR training_used_in_version = '');

COMMENT ON VIEW training_ready_tickets IS 'Тикеты, готовые для использования в обучении';

-- Представление для тикетов с обратной связью
CREATE OR REPLACE VIEW tickets_with_feedback AS
SELECT 
    ticket_id,
    text,
    predicted_type,
    actual_type,
    feedback_status,
    feedback_correct_type,
    feedback_comment,
    feedback_provided_at,
    feedback_provided_by,
    confidence,
    decision
FROM ticket_events
WHERE feedback_status != 'none'
  AND feedback_status IS NOT NULL;

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
-- Функции для автоматической установки training_ready
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

-- ============================================================================
-- Завершение миграции
-- ============================================================================

-- Логирование завершения миграции
DO $$
BEGIN
    RAISE NOTICE 'Миграция 001_add_retraining_fields.sql успешно выполнена';
    RAISE NOTICE 'Добавлены поля для дообучения модели в таблицу ticket_events';
    RAISE NOTICE 'Созданы индексы и представления для удобного доступа к данным';
END $$;

