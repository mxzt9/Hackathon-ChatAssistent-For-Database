"""Opt-in real Qwen inference, SQL guard and PostgreSQL execution."""

import os
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def wait_for_model(client):
    deadline = time.monotonic() + 120
    while True:
        status = client.get("/api/health").json()["model"]
        if status == "ready":
            return
        assert status != "unavailable", "Qwen failed to load"
        assert time.monotonic() < deadline, "Qwen load timeout"
        time.sleep(0.1)


@pytest.mark.skipif(
    os.getenv("RUN_QWEN_INTEGRATION") != "1",
    reason="Requires downloaded Qwen weights and local demo PostgreSQL",
)
def test_qwen_queries_real_database():
    settings = Settings(
        sql_backend="model",
        device="auto",
    )
    with TestClient(create_app(settings)) as client:
        wait_for_model(client)
        for question, expected in [
            (
                "Покажи всех преподавателей по математике",
                [["Преподаватель математики"]],
            ),
            ("Сколько всего студентов?", [[30]]),
            ("Какова средняя оценка всех студентов?", [[3.5]]),
        ]:
            response = client.post("/api/query", json={"question": question})
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["error"] is None, result
            assert result["meta"]["engine"] == "model"
            assert result["rows"] == expected, result


@pytest.mark.skipif(
    os.getenv("RUN_QWEN_INTEGRATION") != "1" or os.getenv("TEST_LARGE_POSTGRES") != "1",
    reason="Requires Qwen and university_large",
)
def test_year_filter_and_status_grouping():
    import psycopg

    with psycopg.connect(
        host="127.0.0.1",
        dbname="university_large",
        user="assistant_ro",
        password="change_me",
    ) as connection:
        expected_statuses = dict(
            connection.execute(
                "SELECT status, COUNT(*) FROM applications GROUP BY status"
            ).fetchall()
        )
        accepted = expected_statuses["accepted"]
    settings = Settings(sql_backend="model", demo_db_name="university_large")
    with TestClient(create_app(settings)) as client:
        wait_for_model(client)
        for question, expected in [
            ("Сколько студентов поступило в 2026 году?", [[1666]]),
            ("Сколько заявлений со статусом accepted?", [[accepted]]),
        ]:
            response = client.post("/api/query", json={"question": question})
            assert response.status_code == 200, response.text
            assert response.json()["rows"] == expected, response.json()
        response = client.post(
            "/api/query", json={"question": "Посчитай заявления по статусам."}
        )
        assert response.status_code == 200, response.text
        assert dict(response.json()["rows"]) == expected_statuses
