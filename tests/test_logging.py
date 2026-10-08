"""Запись и ротация файлов, отсутствие приватной ссылки в HTTP-логе."""

import logging
import subprocess
import sys

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_log_file_rotation_and_utf8(tmp_path):
    code = """
import logging
import sys
from pathlib import Path
import app.logging_config as config

config.ROOT = Path(sys.argv[1])
config.configure_logging()
handler = logging.getLogger().handlers[0]
handler.maxBytes = 128
logging.info('x' * 150)
logging.info('\u0421\u0435\u0440\u0432\u0435\u0440 \u0437\u0430\u043f\u0443\u0449\u0435\u043d')
logging.shutdown()
"""
    subprocess.run([sys.executable, "-c", code, str(tmp_path)], check=True)
    directory = tmp_path / "logs"
    assert "Сервер запущен" in (directory / "server.log").read_text(encoding="utf-8")
    assert (directory / "server.log.1").exists()
    assert not (directory / "server.log.2").exists()


def test_http_log_uses_route_template(caplog):
    caplog.set_level(logging.INFO, logger="app.main")
    token = "private-chat-token"
    with TestClient(create_app(Settings(sql_backend="local"))) as client:
        assert client.get(f"/api/chats/{token}").status_code == 404
    messages = [
        record.message for record in caplog.records if record.name == "app.main"
    ]
    assert any("HTTP GET /api/chats/{public_id}: 404" in text for text in messages)
    assert all(token not in text for text in messages)
