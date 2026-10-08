"""Ограниченные PostgreSQL-пулы и интроспекция без чтения строк данных."""

import asyncpg

from sql.policy import _validate_column

COLUMN_QUERY = """
    SELECT relation.relname AS table_name, attribute.attname AS column_name,
           pg_catalog.format_type(attribute.atttypid, attribute.atttypmod) AS data_type,
           has_column_privilege(relation.oid, attribute.attnum, 'SELECT') AS readable
    FROM pg_catalog.pg_class relation
    JOIN pg_catalog.pg_namespace namespace ON namespace.oid = relation.relnamespace
    JOIN pg_catalog.pg_attribute attribute ON attribute.attrelid = relation.oid
    WHERE namespace.nspname = 'public' AND relation.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND attribute.attnum > 0 AND NOT attribute.attisdropped
      AND EXISTS (
          SELECT 1 FROM pg_catalog.pg_attribute accessible
          WHERE accessible.attrelid = relation.oid AND accessible.attnum > 0
            AND NOT accessible.attisdropped
            AND has_column_privilege(relation.oid, accessible.attnum, 'SELECT')
      )
    ORDER BY relation.relname, attribute.attnum LIMIT 2001
"""
RELATION_QUERY = """
    SELECT source.relname AS source_table, source_column.attname AS source_column,
           target.relname AS target_table, target_column.attname AS target_column
    FROM pg_catalog.pg_constraint constraint_record
    JOIN pg_catalog.pg_class source ON source.oid = constraint_record.conrelid
    JOIN pg_catalog.pg_namespace source_schema ON source_schema.oid = source.relnamespace
    JOIN pg_catalog.pg_class target ON target.oid = constraint_record.confrelid
    JOIN pg_catalog.pg_namespace target_schema ON target_schema.oid = target.relnamespace
    CROSS JOIN LATERAL unnest(constraint_record.conkey, constraint_record.confkey)
        AS keys(source_number, target_number)
    JOIN pg_catalog.pg_attribute source_column
      ON source_column.attrelid = source.oid AND source_column.attnum = keys.source_number
    JOIN pg_catalog.pg_attribute target_column
      ON target_column.attrelid = target.oid AND target_column.attnum = keys.target_number
    WHERE constraint_record.contype = 'f' AND source_schema.nspname = 'public'
      AND target_schema.nspname = 'public'
    LIMIT 2001
"""


def column_level(table: str, column: str, person_tables: frozenset[str]) -> str:
    try:
        _validate_column(table, column, person_tables)
    except ValueError:
        return "forbidden"
    if column in ("student_id", "applicant_id") or (
        table in person_tables and column == "id"
    ):
        return "aggregate_only"
    if table == "grades" and column in ("score", "grade", "student_id"):
        return "aggregate_only"
    return "public"


def connection_options(credentials: dict) -> dict:
    return {
        "host": credentials["host"],
        "port": credentials["port"],
        "database": credentials["name"],
        "user": credentials["user"],
        "password": credentials["password"],
        "ssl": credentials.get("ssl", "prefer"),
        "statement_cache_size": 0,
    }


async def inspect_database(credentials: dict) -> dict:
    conn = await asyncpg.connect(
        **connection_options(credentials),
        timeout=5,
        command_timeout=5,
        server_settings={
            "default_transaction_read_only": "on",
            "statement_timeout": "3000",
            "application_name": "db-workspace-inspect",
        },
    )
    try:
        async with conn.transaction(readonly=True):
            columns = await conn.fetch(COLUMN_QUERY)
            relations = await conn.fetch(RELATION_QUERY)
        if len(columns) > 2000 or len(relations) > 2000:
            raise ValueError("Схема слишком велика: максимум 2000 полей и связей.")
        person_tables = frozenset(
            credentials.get("person_tables", ["students", "applicants", "applications"])
        )
        tables = {}
        for column in columns:
            table, name = column["table_name"], column["column_name"]
            if table != table.lower() or name != name.lower():
                raise ValueError(
                    "Сейчас поддерживаются имена таблиц и полей в нижнем регистре."
                )
            tables.setdefault(table, {"name": table, "fields": [], "levels": {}})
            tables[table]["fields"].append([name, column["data_type"]])
            tables[table]["levels"][name] = (
                column_level(table, name, person_tables)
                if column["readable"]
                else "forbidden"
            )
        if not tables:
            raise ValueError("Не найдено доступных таблиц в схеме public.")
        if len(tables) > 200:
            raise ValueError("Слишком много таблиц: максимум 200.")
        return {
            "name": credentials["name"],
            "host": credentials["host"],
            "port": credentials["port"],
            "tables": list(tables.values()),
            "relations": [dict(row) for row in relations],
            "person_tables": sorted(person_tables),
        }
    finally:
        await conn.close(timeout=2)


async def execute_query(credentials, sql, timeout_ms=3000):
    """Открыть соединение, выполнить SELECT в read-only транзакции и закрыть его."""
    from datetime import date, datetime
    from decimal import Decimal
    from uuid import UUID

    connection = await asyncpg.connect(
        **connection_options(credentials),
        timeout=5,
        command_timeout=timeout_ms / 1000 + 2,
        server_settings={
            "default_transaction_read_only": "on",
            "statement_timeout": str(timeout_ms),
        },
    )
    try:
        async with connection.transaction(readonly=True):
            statement = await connection.prepare(sql)
            columns = [attribute.name for attribute in statement.get_attributes()]
            records = await statement.fetch()
        rows = []
        for record in records:
            row = []
            for value in record:
                if isinstance(value, Decimal):
                    value = float(value)
                elif isinstance(value, (date, datetime, UUID)):
                    value = str(value)
                elif isinstance(value, bytes):
                    value = "[binary]"
                row.append(value)
            rows.append(row)
        return columns, rows
    finally:
        await connection.close()
