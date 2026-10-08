"""Deterministic SQL and the real local PostgreSQL API pipeline."""

import os
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.university import university_sql
from sql.guard import check_sql
from sql.policy import build_policy


@pytest.fixture
def policy():
    return build_policy(
        {
            "person_tables": ["students", "applicants", "applications"],
            "allowed": {
                "faculties": ["id", "name"],
                "programs": ["id", "faculty_id", "name"],
                "teachers": ["id", "full_name"],
                "courses": ["id", "teacher_id", "name"],
                "students": {
                    "id": "aggregate_only",
                    "program_id": "public",
                    "admission_year": "public",
                },
                "applications": {
                    "id": "aggregate_only",
                    "program_id": "public",
                    "year": "public",
                    "status": "public",
                },
                "grades": {
                    "id": "public",
                    "student_id": "aggregate_only",
                    "course_id": "public",
                    "grade": "aggregate_only",
                    "semester": "public",
                },
            },
        }
    )


@pytest.mark.parametrize(
    "question",
    [
        "пришли всех преподов по математике",
        "Сколько преподавателей по математике?",
        "Сколько всего студентов?",
        "Сколько студентов по годам?",
        "Как менялся набор студентов за последние пять лет?",
        "Сколько заявлений подано на Экономику в 2026 году?",
        "Сколько принятых заявлений в 2026 году?",
        "Средняя оценка по математике",
        "Средний балл по математике за 1 семестр",
        "Покажи факультеты",
        "Покажи образовательные программы",
    ],
)
def test_supported_intents_pass_guard(question, policy):
    sql = university_sql(question, policy)
    assert sql, question
    checked = check_sql(sql, policy)
    assert checked.allowed, (sql, checked.reasons)
    if "препод" in question:
        assert "grades" not in sql


@pytest.mark.parametrize(
    "question",
    [
        "Покажи оценки всех студентов",
        "Удали студентов",
        "Преподаватели по химии",
        "Средний балл по моей дисциплине",
        "Сколько заявлений за 2025 и 2026 годы?",
    ],
)
def test_unsupported_intents_are_not_guessed(question, policy):
    assert university_sql(question, policy) is None


def test_missing_join_key_is_not_bypassed(policy):
    allowed = {table: dict(fields) for table, fields in policy.allowed.items()}
    del allowed["teachers"]["id"]
    assert (
        university_sql("Преподаватели по математике", replace(policy, allowed=allowed))
        is None
    )


class UnavailableWorker:
    status = "not_loaded"

    def __init__(self, settings):
        pass

    async def warmup(self):
        pytest.fail("Local backend must not load the model")

    async def generate(self, *args):
        pytest.fail("Local backend must not call the model")

    async def stop(self):
        pass


@pytest.mark.skipif(
    os.getenv("TEST_LOCAL_POSTGRES") != "1", reason="Requires local PostgreSQL"
)
def test_real_local_database_chat():
    with TestClient(
        create_app(Settings(sql_backend="local"), worker_factory=UnavailableWorker)
    ) as client:
        for question, expected in [
            ("Преподаватели по математике", [["Преподаватель математики"]]),
            ("Сколько всего студентов?", [[30]]),
            ("Средняя оценка по математике", [["Математика", 3.5]]),
        ]:
            response = client.post("/api/query", json={"question": question})
            assert response.status_code == 200, response.text
            assert response.json()["rows"] == expected
        created = client.post(
            "/api/connections",
            json={
                "host": "127.0.0.1",
                "name": "university",
                "user": "assistant_ro",
                "password": "change_me",
                "ssl": "disable",
            },
        )
        assert created.status_code == 200, created.text
        tables = {table["name"]: table for table in created.json()["tables"]}
        columns = {column["name"]: column for column in tables["students"]["columns"]}
        assert columns["email"]["level"] == "forbidden"
        assert columns["full_name"]["level"] == "forbidden"
