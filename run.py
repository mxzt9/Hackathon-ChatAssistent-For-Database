"""Запуск: python run.py, затем http://127.0.0.1:8000."""

import os

import uvicorn
from dotenv import load_dotenv

from app.logging_config import configure_logging

if __name__ == "__main__":
    load_dotenv()
    configure_logging()
    uvicorn.run(
        "app.main:app",
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "8000")),
        log_config=None,
        access_log=False,
    )
