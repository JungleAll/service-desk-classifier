"""Конфигурация Output Service"""

import os

# Настройки API
API_HOST = os.getenv("OUTPUT_HOST", "0.0.0.0")
API_PORT = int(os.getenv("OUTPUT_PORT", "8003"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Настройки PostgreSQL
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "service_desk_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# Настройки Jira
JIRA_URL = os.getenv("JIRA_URL", "https://your-jira-instance.atlassian.net")
JIRA_USER = os.getenv("JIRA_USER", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "SD")
JIRA_ENABLED = os.getenv("JIRA_ENABLED", "true").lower() == "true"

# Настройки retry
MAX_RETRY_ATTEMPTS = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))  # секунды

# Настройки Config Service
CONFIG_SERVICE_URL = os.getenv("CONFIG_SERVICE_URL", "http://localhost:8002")
CONFIG_SERVICE_TIMEOUT = float(os.getenv("CONFIG_SERVICE_TIMEOUT", "2.0"))  # секунды

