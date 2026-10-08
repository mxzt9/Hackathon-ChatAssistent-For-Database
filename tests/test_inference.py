"""Нативное падение модели не должно завершать HTTP-сервер."""

import os
import time

from fastapi.testclient import TestClient

from app.config import Settings
from app.inference import InferenceWorker
from app.main import create_app


def crashing_model(connection, settings):
    connection.send({"ready": True})
    connection.recv()
    os._exit(13)


def worker(settings):
    return InferenceWorker(settings, target=crashing_model)


async def inspect(credentials):
    return {
        "name": "demo",
        "person_tables": [],
        "relations": [],
        "tables": [
            {
                "name": "teachers",
                "fields": [["id", "integer"]],
                "levels": {"id": "public"},
            }
        ],
    }


def test_model_process_crash_keeps_http_server_alive():
    with TestClient(
        create_app(Settings(), worker_factory=worker, inspector=inspect)
    ) as client:
        deadline = time.monotonic() + 10
        while client.get("/api/health").json()["model"] != "ready":
            assert time.monotonic() < deadline
            time.sleep(0.02)
        response = client.post(
            "/api/query", json={"question": "Сколько преподавателей?"}
        )
        assert response.status_code == 503
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["model"] == "unavailable"
        assert client.get("/").status_code == 200
