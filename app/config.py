"""Настройки прототипа из .env."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    sql_backend: str = "model"
    model_id: str = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
    device: str = "auto"
    torch_threads: int = 2
    demo_db_host: str = "127.0.0.1"
    demo_db_port: int = 5432
    demo_db_name: str = "university"
    demo_db_user: str = "assistant_ro"
    demo_db_password: str = "change_me"
    demo_db_ssl: str = "disable"
    rows_limit: int = 100
    statement_timeout_ms: int = 3000

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        defaults = cls()
        values = {}
        for name in cls.__dataclass_fields__:
            value = os.getenv(name.upper())
            if value is not None:
                values[name] = (
                    int(value) if isinstance(getattr(defaults, name), int) else value
                )
        settings = cls(**values)
        if settings.sql_backend not in ("model", "local"):
            raise ValueError("SQL_BACKEND должен быть model или local")
        if not 1 <= settings.rows_limit <= 1000:
            raise ValueError("ROWS_LIMIT должен быть от 1 до 1000")
        if settings.statement_timeout_ms <= 0 or settings.torch_threads <= 0:
            raise ValueError("Таймаут и число потоков должны быть положительными")
        return settings
