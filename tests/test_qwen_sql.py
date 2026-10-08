"""Формат ответа модели и исключение закрытых полей из примеров."""

import pytest

from ml.qwen import QwenSqlModel, clean_sql, messages
from ml.schema import prepare_schema
from sql.policy import Policy


@pytest.mark.parametrize(
    "answer",
    [
        "SELECT COUNT(*) FROM students;",
        "```sql\nSELECT COUNT(*) FROM students;\n```",
        '{"sql": "SELECT COUNT(*) FROM students"}',
    ],
)
def test_sql_response_formats(answer):
    assert clean_sql(answer).startswith("SELECT count(*) FROM students")


@pytest.mark.parametrize(
    "answer",
    [
        "DELETE FROM students",
        "SELECT id FROM students; DROP TABLE students;",
        "SELECT",
        '{"sql": 123}',
        "-- unsupported",
    ],
)
def test_invalid_response_rejected(answer):
    with pytest.raises(ValueError):
        clean_sql(answer)


def test_restricted_schema_does_not_add_hidden_field_examples():
    schema = prepare_schema(
        "CREATE TABLE students (id bigint, admission_year smallint, email text);",
        Policy(allowed={"students": {"id": "aggregate_only"}}),
    )
    prompt = messages(schema, "Сколько студентов?")[1]["content"]
    assert "admission_year" not in prompt
    assert "email" not in prompt


SCHEMA = "CREATE TABLE teachers(id int, full_name text);"


def test_generation_repairs_invalid_sql(monkeypatch):
    model = QwenSqlModel.__new__(QwenSqlModel)
    outputs = iter(["SELECT surname FROM teachers", "SELECT full_name FROM teachers"])
    calls = []

    def complete(chat, limit):
        calls.append(chat.copy())
        return next(outputs)

    monkeypatch.setattr(model, "complete", complete)
    assert "full_name" in model.generate(SCHEMA, "List teachers")
    assert len(calls) == 2
    assert "Validation error" in calls[1][-1]["content"]
    assert "surname" in calls[1][-1]["content"]


def test_generation_does_not_bypass_repeated_validation_failure(monkeypatch):
    model = QwenSqlModel.__new__(QwenSqlModel)
    monkeypatch.setattr(model, "complete", lambda chat, limit: "DELETE FROM teachers")
    with pytest.raises(ValueError):
        model.generate(SCHEMA, "Delete teachers")


def test_examples_use_only_visible_schema():
    prompt = messages("CREATE TABLE books(id int, title text);", "List books")[1][
        "content"
    ]
    assert "full_name" not in prompt
    assert "teachers" not in prompt
