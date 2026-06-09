"""Скрипт для запуска ML Service"""

import uvicorn
import sys
import os
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ml_service.config import API_HOST, API_PORT

if __name__ == "__main__":
    log_level = os.getenv("LOG_LEVEL", "INFO").lower()
    uvicorn.run(
        "ml_service.app:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level=log_level
    )

