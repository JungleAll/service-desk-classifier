-- Service Desk Classifier Database Schema
-- PostgreSQL Database Schema

-- Таблица для хранения всех событий с обращениями
CREATE TABLE IF NOT EXISTS ticket_events (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(255) UNIQUE NOT NULL,
    text TEXT NOT NULL,
    source VARCHAR(50) NOT NULL,  -- 'email', 'chat', 'api', 'web'
    user_id VARCHAR(255),
    email VARCHAR(255),
    priority VARCHAR(20) DEFAULT 'medium',  -- 'low', 'medium', 'high', 'critical'
    category_hint VARCHAR(255),
    metadata JSONB,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed', 'cancelled', 'queued'
    predicted_type VARCHAR(255),
    confidence FLOAT,
    probabilities JSONB,  -- Вероятности для всех классов
    decision VARCHAR(50),  -- 'auto-process', 'manual-review'
    model_version VARCHAR(50),
    jira_ticket_id VARCHAR(255),
    jira_link VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    sent_to_jira_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0
);

-- Индексы для ticket_events
CREATE INDEX IF NOT EXISTS idx_ticket_events_ticket_id ON ticket_events(ticket_id);
CREATE INDEX IF NOT EXISTS idx_ticket_events_status ON ticket_events(status);
CREATE INDEX IF NOT EXISTS idx_ticket_events_created_at ON ticket_events(created_at);
CREATE INDEX IF NOT EXISTS idx_ticket_events_user_id ON ticket_events(user_id);

-- Таблица для метрик модели
CREATE TABLE IF NOT EXISTS metrics (
    id SERIAL PRIMARY KEY,
    model_version VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,  -- 'accuracy', 'precision', 'recall', 'f1'
    metric_value FLOAT NOT NULL,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    period_start TIMESTAMP,
    period_end TIMESTAMP,
    UNIQUE(model_version, metric_name, calculated_at)
);

-- Индексы для metrics
CREATE INDEX IF NOT EXISTS idx_metrics_model_version ON metrics(model_version);
CREATE INDEX IF NOT EXISTS idx_metrics_calculated_at ON metrics(calculated_at);

-- Таблица для конфигурации системы
CREATE TABLE IF NOT EXISTS configuration (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255)
);

-- Таблица для истории изменений конфигурации
CREATE TABLE IF NOT EXISTS config_audit_log (
    id SERIAL PRIMARY KEY,
    field VARCHAR(255) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by VARCHAR(255) NOT NULL,
    reason TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для config_audit_log
CREATE INDEX IF NOT EXISTS idx_config_audit_log_field ON config_audit_log(field);
CREATE INDEX IF NOT EXISTS idx_config_audit_log_changed_at ON config_audit_log(changed_at);

-- Индексы для configuration
CREATE INDEX IF NOT EXISTS idx_configuration_key ON configuration(key);

-- Таблица для истории версий моделей
CREATE TABLE IF NOT EXISTS model_versions (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) UNIQUE NOT NULL,
    model_path VARCHAR(500) NOT NULL,
    vectorizer_path VARCHAR(500) NOT NULL,
    label_encoder_path VARCHAR(500) NOT NULL,
    accuracy FLOAT,
    f1_score FLOAT,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP
);

-- Индексы для model_versions
CREATE INDEX IF NOT EXISTS idx_model_versions_version ON model_versions(version);
CREATE INDEX IF NOT EXISTS idx_model_versions_is_active ON model_versions(is_active);

-- Таблица для логов ошибок
CREATE TABLE IF NOT EXISTS error_logs (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(100) NOT NULL,  -- 'ingestion', 'ml_service', 'config', 'output'
    error_type VARCHAR(100) NOT NULL,
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    ticket_id VARCHAR(255),
    request_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для error_logs
CREATE INDEX IF NOT EXISTS idx_error_logs_service_name ON error_logs(service_name);
CREATE INDEX IF NOT EXISTS idx_error_logs_created_at ON error_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_error_logs_ticket_id ON error_logs(ticket_id);

-- Таблица для audit логов (Output Service)
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,  -- 'jira_created', 'jira_updated', 'classification_completed'
    service_name VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,  -- 'success', 'failed', 'retry'
    details JSONB,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для audit_logs
CREATE INDEX IF NOT EXISTS idx_audit_logs_ticket_id ON audit_logs(ticket_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_status ON audit_logs(status);

-- Вставка начальных значений конфигурации
INSERT INTO configuration (key, value, description) VALUES
    ('service_enabled', 'true', 'Включен ли сервис автоматической классификации'),
    ('confidence_threshold', '0.7', 'Порог уверенности для auto-process'),
    ('current_model_version', 'v1.0', 'Текущая активная версия модели'),
    ('jira_enabled', 'true', 'Включена ли отправка в Jira'),
    ('max_retry_attempts', '3', 'Максимальное количество попыток повтора')
ON CONFLICT (key) DO NOTHING;

-- Вставка информации о модели v1.0 (единственная версия)
-- Используется classifier_smote_new.pkl
INSERT INTO model_versions (version, model_path, vectorizer_path, label_encoder_path, accuracy, f1_score, is_active)
VALUES (
    'v1.0',
    'models/v1.0/classifier_smote_new.pkl',
    'models/v1.0/vectorizer_smote.pkl',
    'models/v1.0/label_encoder_smote.pkl',
    0.9749,
    0.9705,
    TRUE
)
ON CONFLICT (version) DO NOTHING;

