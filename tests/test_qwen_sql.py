"""Формат ответа модели и исключение закрытых полей из примеров."""

import pytest

from ml.qwen import QwenSqlModel, check_plan_sql, clean_sql, messages, parse_plan
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


SCHEMA = "CREATE TABLE teachers(id int, full_name text); CREATE TABLE courses(id int, teacher_id int);"
PLAN = {
    "entity": "teachers",
    "operation": "count",
    "metric": None,
    "fields": [],
    "filters": [
        {"column": "teachers.full_name", "value": "Иванов", "match": "surname"}
    ],
    "group_by": [],
}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(c.id) FROM teachers t JOIN courses c ON c.teacher_id=t.id WHERE t.full_name ILIKE 'Иванов %'",
        "SELECT COUNT(*) FROM teachers WHERE full_name ILIKE '%Иванов%'",
    ],
)
def test_sql_must_count_planned_entity_and_match_surname(sql):
    with pytest.raises(ValueError):
        check_plan_sql(sql, SCHEMA, PLAN)


def test_two_stage_generation_repairs_against_same_plan(monkeypatch):
    import json

    model = QwenSqlModel.__new__(QwenSqlModel)
    outputs = iter(
        [
            json.dumps(PLAN),
            "SELECT COUNT(*) FROM teachers WHERE full_name ILIKE '%Иванов%'",
            "SELECT COUNT(*) FROM teachers WHERE full_name ILIKE 'Иванов %'",
        ]
    )
    calls = []

    def complete(chat, limit):
        calls.append(chat.copy())
        return next(outputs)

    monkeypatch.setattr(model, "complete", complete)
    sql = model.generate(SCHEMA, "Сколько преподавателей с фамилией Иванов?")
    assert "Иванов %" in sql
    assert len(calls) == 3
    assert "Validated plan" in calls[1][1]["content"]
    assert "Validation error" in calls[2][-1]["content"]


def test_plan_cannot_invent_columns():
    import json

    invalid = {**PLAN, "fields": ["teachers.surname"]}
    with pytest.raises(ValueError):
        parse_plan(json.dumps(invalid), SCHEMA)


@pytest.mark.parametrize(
    "arrays",
    [
        {},
        {"fields": None, "filters": None, "group_by": None},
        {"fields": "teachers.full_name", "filters": {}, "group_by": ""},
    ],
)
def test_optional_plan_arrays_are_normalized(arrays):
    import json

    plan = parse_plan(
        json.dumps({"entity": "teachers", "operation": "list", **arrays}), SCHEMA
    )
    assert isinstance(plan["fields"], list)
    assert plan["filters"] == []
    assert plan["group_by"] == []


def test_plan_arrays_do_not_accept_arbitrary_types():
    import json

    with pytest.raises(ValueError, match="filters"):
        parse_plan(json.dumps({**PLAN, "filters": 42}), SCHEMA)


def test_plan_resolves_entity_columns_without_table_prefix():
    import json

    raw = {
        **PLAN,
        "fields": ["full_name"],
        "filters": [{"column": "full_name", "value": "Иванов", "match": "surname"}],
    }
    plan = parse_plan(json.dumps(raw), SCHEMA)
    assert plan["fields"] == ["teachers.full_name"]
    assert plan["filters"][0]["column"] == "teachers.full_name"
