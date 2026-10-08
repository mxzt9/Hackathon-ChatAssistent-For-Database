"""Логи сервера и процесса модели с ограничением размера файлов."""

import logging
from logging.handlers import RotatingFileHandler

from app.config import ROOT


def configure_logging(filename: str = "server.log") -> None:
    directory = ROOT / "logs"
    directory.mkdir(exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        directory / filename,
        maxBytes=2 * 1024 * 1024,
        backupCount=1,
        encoding="utf-8",
    )
    console_handler = logging.StreamHandler()
    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)

    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # HTTP-записи содержат шаблон маршрута вместо приватной ссылки чата.
    logging.getLogger("uvicorn.access").disabled = True
