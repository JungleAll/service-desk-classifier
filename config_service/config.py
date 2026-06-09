"""Конфигурация Config Service"""

import os
from pathlib import Path

# Настройки API
API_HOST = os.getenv("CONFIG_HOST", "0.0.0.0")
API_PORT = int(os.getenv("CONFIG_PORT", "8002"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Настройки PostgreSQL
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "service_desk_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# Настройки Fallback конфигурации
CONFIG_FALLBACK_DIR = os.getenv("CONFIG_FALLBACK_DIR", "./config_cache")
CONFIG_FALLBACK_ENABLED = os.getenv("CONFIG_FALLBACK_ENABLED", "true").lower() == "true"
CONFIG_SYNC_INTERVAL = int(os.getenv("CONFIG_SYNC_INTERVAL", "300"))  # секунды (5 минут по умолчанию)

