"""SELECT, whitelist, JOIN, агрегирование и запрет побочных эффектов."""

import pytest

from sql.guard import check_sql
from sql.policy import Limits, Policy

POLICY = Policy(
    allowed={
        "teachers": {"id": "public", "full_name": "public"},
        "courses": {"id": "public", "name": "public", "teacher_id": "public"},
        "grades": {"grade": "aggregate_only"},
    },
    limits=Limits(default_limit=10),
)


@pytest.mark.parametrize(
    ("condition", "allowed"),
    [
        ("c.teacher_id = t.id", True),
        ("t.id = c.teacher_id AND c.name ILIKE '%math%'", True),
        ("c.id = t.id", False),
        ("c.teacher_id = t.id OR c.id = t.id", False),
        ("c.teacher_id = t.id OR TRUE", False),
        ("TRUE", False),
    ],
)
def test_join_requires_real_foreign_key(condition, allowed):
    relations = [
        {
            "source_table": "courses",
            "source_column": "teacher_id",
            "target_table": "teachers",
            "target_column": "id",
        }
    ]
    result = check_sql(
        f"SELECT t.full_name FROM teachers t JOIN courses c ON {condition}",
        POLICY,
        relations,
    )
    assert result.allowed == allowed, result.reasons


def test_join_uses_intermediate_table():
    policy = Policy(
        allowed={
            "faculties": {"id": "public", "name": "public"},
            "programs": {"id": "public", "faculty_id": "public"},
            "students": {"id": "aggregate_only", "program_id": "public"},
        }
    )
    relations = [
        {
            "source_table": "students",
            "source_column": "program_id",
            "target_table": "programs",
            "target_column": "id",
        },
        {
            "source_table": "programs",
            "source_column": "faculty_id",
            "target_table": "faculties",
            "target_column": "id",
        },
    ]
    valid = check_sql(
        "SELECT f.name, COUNT(s.id) FROM faculties f "
        "LEFT JOIN programs p ON p.faculty_id=f.id "
        "LEFT JOIN students s ON s.program_id=p.id GROUP BY f.name",
        policy,
        relations,
    )
    assert valid.allowed, valid.reasons
    invalid = check_sql(
        "SELECT f.name, COUNT(s.id) FROM faculties f "
        "JOIN students s ON s.program_id=f.id GROUP BY f.name",
        policy,
        relations,
    )
    assert not invalid.allowed


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT full_name FROM teachers",
        "SELECT t.full_name FROM teachers t JOIN courses c ON c.teacher_id=t.id WHERE c.name ILIKE '%математик%'",
        "SELECT AVG(grade) FROM grades",
        "SELECT COUNT(*) FROM teachers",
    ],
)
def test_allowed(sql):
    result = check_sql(sql, POLICY)
    assert result.allowed, result.reasons
    assert "LIMIT 10" in result.sql


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM teachers",
        "SELECT * INTO copy FROM teachers",
        "SELECT id FROM teachers FOR UPDATE",
        "SELECT id FROM teachers; DROP TABLE teachers",
        "SELECT email FROM teachers",
        "SELECT * FROM students",
        "SELECT grade FROM grades",
        "SELECT grade + 1 FROM grades",
        "SELECT AVG(grade) OVER () FROM grades",
        "SELECT pg_sleep(1) FROM teachers",
        "SELECT nextval('sequence') FROM teachers",
        "SELECT private.round(id) FROM teachers",
        "SELECT t FROM teachers t",
        "SELECT row_to_json(t) FROM teachers t",
        "SELECT id FROM pg_catalog.pg_class",
        "SELECT id FROM private.teachers",
        "WITH q AS (SELECT id FROM teachers) SELECT * FROM q",
        "SELECT (SELECT id FROM teachers LIMIT 1) FROM teachers",
    ],
)
def test_rejected(sql):
    assert not check_sql(sql, POLICY).allowed


def test_model_cannot_increase_limit():
    assert "LIMIT 10" in check_sql("SELECT id FROM teachers LIMIT 9999", POLICY).sql
    assert "LIMIT 2" in check_sql("SELECT id FROM teachers LIMIT 2", POLICY).sql
