"""Конфигурация Config Service"""

import os

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

