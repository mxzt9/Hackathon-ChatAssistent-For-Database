"""Разрешённые колонки и два ограничения: число строк и таймаут БД."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PUBLIC = "public"
AGGREGATE_ONLY = "aggregate_only"
LEVELS = {PUBLIC, AGGREGATE_ONLY}

# Части имён колонок, которые нельзя открывать ни в одной таблице:
# паспортные, контактные и прочие чувствительные данные.
SENSITIVE_TOKENS = {
    "passport",
    "snils",
    "inn",
    "phone",
    "mobile",
    "email",
    "mail",
    "address",
    "telegram",
    "password",
    "birth",
    "birthday",
    "salary",
    "card",
    "iban",
}
# В таблицах учащихся дополнительно нельзя открывать ФИО и прочие идентификаторы.
PERSON_IDENTIFYING_COLUMNS = {
    "last_name",
    "first_name",
    "middle_name",
    "full_name",
    "fio",
    "surname",
    "patronymic",
    "name",
    "record_book",
    "record_book_number",
    "photo",
}


@dataclass(frozen=True)
class Limits:
    default_limit: int = 100
    statement_timeout_ms: int = 3000


@dataclass(frozen=True)
class Policy:
    allowed: dict[str, dict[str, str]]  # table -> column -> level
    limits: Limits = field(default_factory=Limits)
    person_tables: frozenset[str] = frozenset({"students", "applicants"})

    @property
    def tables(self) -> set[str]:
        return set(self.allowed)

    def level(self, table: str, column: str) -> str | None:
        return self.allowed.get(table.lower(), {}).get(column.lower())

    def sqlglot_schema(self) -> dict[str, dict[str, str]]:
        """Схема для sqlglot.qualify — только разрешённые колонки (типы не важны)."""
        return {t: {c: "text" for c in cols} for t, cols in self.allowed.items()}


class PolicyError(ValueError):
    pass


def _validate_column(table: str, column: str, person_tables: frozenset[str]) -> None:
    tokens = set(column.split("_"))
    if tokens & SENSITIVE_TOKENS:
        raise PolicyError(
            f"{table}.{column}: чувствительные данные (паспорт/контакты) "
            f"нельзя добавлять в whitelist"
        )
    identifies_person = (
        column in PERSON_IDENTIFYING_COLUMNS
        or any(column.endswith("_" + name) for name in PERSON_IDENTIFYING_COLUMNS)
        or "fio" in tokens
    )
    if (
        table in person_tables or tokens & {"student", "applicant"}
    ) and identifies_person:
        raise PolicyError(
            f"{table}.{column}: данные, позволяющие идентифицировать учащихся, "
            f"нельзя добавлять в whitelist"
        )


def build_policy(raw: dict) -> Policy:
    person_tables = frozenset(
        t.lower() for t in raw.get("person_tables", ["students", "applicants"])
    )
    allowed: dict[str, dict[str, str]] = {}
    for table, cols in raw["allowed"].items():
        table = table.lower()
        if isinstance(cols, list):
            cols = {c: PUBLIC for c in cols}
        normalized = {}
        for col, lvl in cols.items():
            col = col.lower()
            if lvl not in LEVELS:
                raise PolicyError(f"{table}.{col}: неизвестный уровень доступа «{lvl}»")
            _validate_column(table, col, person_tables)
            normalized[col] = lvl
        allowed[table] = normalized

    limits = Limits(**raw.get("limits", {}))

    return Policy(allowed=allowed, limits=limits, person_tables=person_tables)


def load_policy(path: str | Path) -> Policy:
    return build_policy(json.loads(Path(path).read_text(encoding="utf-8")))
