"""Проверки основного сценария: подключение → колонки → публичный чат."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


async def inspect(credentials):
    return {
        "name": credentials["name"],
        "person_tables": ["students"],
        "relations": [],
        "tables": [
            {
                "name": "teachers",
                "fields": [["id", "integer"], ["full_name", "text"], ["email", "text"]],
                "levels": {"id": "public", "full_name": "public", "email": "forbidden"},
            }
        ],
    }


class Model:
    status = "ready"

    def __init__(self, settings):
        self.schema = ""
        self.sql = "SELECT full_name FROM teachers"

    async def warmup(self):
        pass

    async def stop(self):
        pass

    async def generate(self, schema, question):
        self.schema = schema
        return self.sql


async def execute(credentials, sql, timeout):
    return ["full_name"], [["Преподаватель математики"]]


@pytest.fixture
def client():
    app = create_app(
        Settings(sql_backend="model"),
        worker_factory=Model,
        inspector=inspect,
        executor=execute,
    )
    with TestClient(app) as client:
        yield client


def connection(client):
    response = client.post(
        "/api/connections",
        json={
            "host": "127.0.0.1",
            "name": "university",
            "user": "assistant_ro",
            "password": "change_me",
        },
    )
    assert response.status_code == 200
    assert "password" not in response.text
    assert "set-cookie" not in response.headers
    return response.json()


def test_admin_selects_columns_then_shares_chat(client):
    db = connection(client)
    assert not db["published"]
    assert db["tables"][0]["fields"] == []
    assert client.get(f"/api/chats/{db['public_id']}").status_code == 404
    saved = client.put(
        f"/api/connections/{db['id']}/whitelist",
        json={
            "tables": ["teachers"],
            "fields": {"teachers": ["full_name"]},
            "version": 1,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["published"]
    response = client.post(
        f"/api/chats/{db['public_id']}/query", json={"question": "Преподаватели?"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["rows"] == [["Преподаватель математики"]]
    assert "full_name text" in client.app.state.inference.schema
    assert "id integer" not in client.app.state.inference.schema
    assert "email" not in client.app.state.inference.schema
    assert client.get(f"/api/connections/{db['public_id']}").status_code == 404
    assert client.delete(f"/api/connections/{db['id']}").status_code == 200
    assert client.get(f"/api/chats/{db['public_id']}").status_code == 404


@pytest.mark.parametrize("fields", [[], ["email"], ["unknown"]])
def test_rejects_empty_closed_or_unknown_fields(client, fields):
    db = connection(client)
    response = client.put(
        f"/api/connections/{db['id']}/whitelist",
        json={"tables": ["teachers"], "fields": {"teachers": fields}, "version": 1},
    )
    assert response.status_code == 422


def test_generated_sql_cannot_read_unselected_column(client):
    db = connection(client)
    client.put(
        f"/api/connections/{db['id']}/whitelist",
        json={
            "tables": ["teachers"],
            "fields": {"teachers": ["full_name"]},
            "version": 1,
        },
    )
    client.app.state.inference.sql = "SELECT email FROM teachers"
    response = client.post(
        f"/api/chats/{db['public_id']}/query", json={"question": "Контакты?"}
    )
    assert response.status_code == 422


def test_pages_and_widget_are_served(client):
    for path in ("/", "/widget", "/assets/widget.js", "/favicon.ico"):
        assert client.get(path).status_code == 200


@pytest.mark.parametrize("fixed", [True, False])
def test_invalid_join_is_retried_once_before_execution(fixed):
    calls, executed = [], []
    invalid = "SELECT t.full_name FROM teachers t JOIN courses c ON c.id=t.id"

    class RepairModel(Model):
        async def generate(self, schema, question):
            calls.append(question)
            if fixed and len(calls) == 2:
                return "SELECT full_name FROM teachers"
            return invalid

    async def inspect_relations(credentials):
        metadata = await inspect(credentials)
        metadata["tables"].append(
            {
                "name": "courses",
                "fields": [["id", "integer"], ["teacher_id", "integer"]],
                "levels": {"id": "public", "teacher_id": "public"},
            }
        )
        metadata["relations"] = [
            {
                "source_table": "courses",
                "source_column": "teacher_id",
                "target_table": "teachers",
                "target_column": "id",
            }
        ]
        return metadata

    async def track_execution(credentials, sql, timeout):
        executed.append(sql)
        return await execute(credentials, sql, timeout)

    app = create_app(
        Settings(),
        worker_factory=RepairModel,
        inspector=inspect_relations,
        executor=track_execution,
    )
    with TestClient(app) as client:
        response = client.post("/api/query", json={"question": "Покажи преподавателей"})
    assert len(calls) == 2
    assert invalid in calls[1]
    assert "внешних ключей" in calls[1]
    assert response.status_code == (200 if fixed else 422)
    assert len(executed) == (1 if fixed else 0)
    assert all("JOIN" not in sql for sql in executed)
