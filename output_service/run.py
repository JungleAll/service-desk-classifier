"""Скрипт для запуска Output Service"""

import uvicorn
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from output_service.config import API_HOST, API_PORT, LOG_LEVEL

if __name__ == "__main__":
    uvicorn.run(
        "output_service.app:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level=LOG_LEVEL.lower()
    )

