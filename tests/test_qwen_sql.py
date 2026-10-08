"""Формат ответа модели и исключение закрытых полей из примеров."""

import pytest

from ml.qwen import clean_sql, messages
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
