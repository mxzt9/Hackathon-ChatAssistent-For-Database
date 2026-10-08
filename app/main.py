"""API подключения PostgreSQL, выбора колонок и публичного чата."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from time import perf_counter
from typing import Literal

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pglast import parse_sql
from pglast.stream import RawStream
from pydantic import BaseModel, Field

from app.config import ROOT, Settings
from app.database import execute_query, inspect_database
from app.inference import InferenceWorker
from app.store import DemoStore
from app.university import university_sql
from sql.guard import check_sql
from sql.policy import Policy, build_policy

LOGGER = logging.getLogger(__name__)


class Connection(BaseModel):
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.:-]+$")
    port: int = Field(default=5432, ge=1, le=65535)
    name: str = Field(min_length=1, max_length=100)
    user: str = Field(min_length=1, max_length=100)
    password: str = Field(max_length=500)
    ssl: Literal["disable", "prefer", "require", "verify-full"] = "prefer"
    person_tables: list[str] = Field(
        default_factory=lambda: ["students", "applicants", "applications"],
        max_length=100,
    )


class DemoAccess(BaseModel):
    tables: list[str] = Field(max_length=200)
    fields: dict[str, list[str]] | None = Field(default=None, max_length=200)
    version: int = Field(ge=1)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def make_policy(database: dict, settings: Settings) -> Policy:
    allowed = {}
    for table in database["tables"]:
        access = database["whitelist"][table["name"]]
        if access["enabled"]:
            allowed[table["name"]] = {
                name: table["levels"][name] for name in access["fields"]
            }
    return build_policy(
        {
            "allowed": allowed,
            "person_tables": database["person_tables"],
            "limits": {
                "default_limit": settings.rows_limit,
                "statement_timeout_ms": settings.statement_timeout_ms,
            },
        }
    )


def identifier(name):
    return '"' + name.replace('"', '""') + '"'


def model_schema(database: dict, policy: Policy) -> str:
    statements = []
    for table in database["tables"]:
        name = table["name"]
        if name not in policy.allowed:
            continue
        fields = []
        for column, datatype in table["fields"]:
            if column not in policy.allowed[name]:
                continue
            if datatype in ("ARRAY", "USER-DEFINED"):
                datatype = "TEXT"
            fields.append(f"{identifier(column)} {datatype}")
        for relation in database["relations"]:
            if relation["source_table"] != name:
                continue
            source, target, target_col = (
                relation["source_column"],
                relation["target_table"],
                relation["target_column"],
            )
            if source in policy.allowed[name] and policy.level(target, target_col):
                fields.append(
                    f"FOREIGN KEY ({identifier(source)}) REFERENCES {identifier(target)} ({identifier(target_col)})"
                )
        statements.append(f"CREATE TABLE {identifier(name)} ({', '.join(fields)});")
    if not statements:
        raise HTTPException(409, "Выберите хотя бы одну разрешённую таблицу.")
    schema = "\n".join(
        RawStream()(item.stmt) + ";" for item in parse_sql("\n".join(statements))
    )
    restricted = [
        f"{table}.{column}"
        for table, columns in policy.allowed.items()
        for column, level in columns.items()
        if level == "aggregate_only"
    ]
    if restricted:
        schema += "\n-- aggregate_only: " + ", ".join(restricted)
    if len(schema) > 20000:
        raise HTTPException(
            422, "Схема слишком велика для модели. Сократите whitelist."
        )
    return schema


def create_app(
    settings: Settings | None = None,
    worker_factory=InferenceWorker,
    inspector=inspect_database,
    executor=execute_query,
) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = DemoStore(settings, inspector)
        app.state.inference = worker_factory(settings)
        warmup = (
            asyncio.create_task(app.state.inference.warmup())
            if settings.sql_backend == "model"
            else None
        )
        try:
            yield
        finally:
            if warmup is not None:
                warmup.cancel()
                with suppress(asyncio.CancelledError):
                    await warmup
            await app.state.inference.stop()

    app = FastAPI(title="Чат с PostgreSQL", lifespan=lifespan)

    async def process_question(database, payload):
        started = perf_counter()
        question = payload.question.strip()
        if not question:
            raise HTTPException(422, "Введите вопрос.")
        policy = make_policy(database, settings)
        schema = model_schema(database, policy)
        if settings.sql_backend == "local":
            sql = university_sql(question, policy)
            if sql is None:
                raise HTTPException(
                    422,
                    "Этот вопрос не поддерживается локальными шаблонами. Включите Qwen или выберите пример.",
                )
        else:
            sql = await app.state.inference.generate(schema, question)
        LOGGER.info("SQL модели: %s", sql)
        # Если админ изменил разрешения за время генерации, старый запрос не выполняем.
        current = await app.state.store.get(database["id"])
        if not current or current["version"] != database["version"]:
            raise HTTPException(409, "Настройки изменились. Повторите вопрос.")
        checked = check_sql(sql, policy)
        if not checked.allowed:
            raise HTTPException(422, checked.error)
        credentials = await app.state.store.credentials(database["id"])
        try:
            columns, rows = await executor(
                credentials, checked.sql, settings.statement_timeout_ms
            )
        except (OSError, asyncpg.PostgresError, TimeoutError):
            raise HTTPException(
                503,
                "Не удалось выполнить запрос в PostgreSQL. Проверьте БД или уточните вопрос.",
            ) from None
        LOGGER.info("SQL выполнен: %s строк", len(rows))
        answer = (
            f"Результат: {rows[0][0]}"
            if len(rows) == 1 and len(columns) == 1
            else f"Найдено строк: {len(rows)}."
        )
        if not rows:
            answer = "Подходящих данных не найдено."
        return {
            "answer": answer,
            "sql": checked.sql,
            "columns": columns,
            "rows": rows,
            "error": None,
            "meta": {
                "engine": "university" if settings.sql_backend == "local" else "model",
                "total_ms": round((perf_counter() - started) * 1000),
                "explain": checked.explain,
            },
        }

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "model": app.state.inference.status,
            "sql_backend": settings.sql_backend,
        }

    @app.get("/api/database")
    async def database_info():
        database = await app.state.store.get("demo")
        return {
            "name": database["name"],
            "version": database["version"],
            "configured": bool(make_policy(database, settings).allowed),
            "sql_backend": settings.sql_backend,
            "tables": [
                {
                    "name": table["name"],
                    "enabled": database["whitelist"][table["name"]]["enabled"],
                    "fields": database["whitelist"][table["name"]]["fields"],
                }
                for table in database["tables"]
            ],
        }

    @app.post("/api/query")
    async def question(payload: Question):
        return await process_question(await app.state.store.get("demo"), payload)

    def management_info(database):
        return {
            "id": database["id"],
            "public_id": database.get("public_id"),
            "name": database["name"],
            "published": database.get("published", False),
            "version": database["version"],
            "tables": [
                {
                    "name": table["name"],
                    "enabled": database["whitelist"][table["name"]]["enabled"],
                    "fields": database["whitelist"][table["name"]]["fields"],
                    "columns": [
                        {"name": name, "type": datatype, "level": table["levels"][name]}
                        for name, datatype in table["fields"]
                    ],
                }
                for table in database["tables"]
            ],
        }

    @app.post("/api/connections")
    async def connect(payload: Connection):
        return management_info(await app.state.store.create(payload.model_dump()))

    @app.get("/api/connections/{admin_id}")
    async def connection_info(admin_id: str):
        database = await app.state.store.get(admin_id)
        if not database or admin_id == "demo":
            raise HTTPException(404, "Подключение не найдено.")
        return management_info(database)

    @app.put("/api/connections/{admin_id}/whitelist")
    async def configure(admin_id: str, payload: DemoAccess):
        async with app.state.store.lock:
            database = await app.state.store.get(admin_id, locked=True)
            if not database or admin_id == "demo":
                raise HTTPException(404, "Подключение не найдено.")
            if database["version"] != payload.version:
                raise HTTPException(409, "Настройки изменились. Обновите страницу.")
            if set(payload.tables) - set(database["whitelist"]):
                raise HTTPException(422, "Неизвестная таблица.")
            if payload.fields is not None and set(payload.fields) - set(
                database["whitelist"]
            ):
                raise HTTPException(422, "Неизвестная таблица в списке полей.")
            whitelist = {}
            for table in database["tables"]:
                name = table["name"]
                fields = (
                    payload.fields.get(name, [])
                    if payload.fields is not None
                    else [
                        column
                        for column, level in table["levels"].items()
                        if level != "forbidden"
                    ]
                )
                if any(
                    column not in table["levels"]
                    or table["levels"][column] == "forbidden"
                    for column in fields
                ):
                    raise HTTPException(422, "Неизвестное или закрытое поле.")
                if name in payload.tables and not fields:
                    raise HTTPException(
                        422, "Выберите хотя бы одно поле для каждой включённой таблицы."
                    )
                whitelist[name] = {
                    "enabled": name in payload.tables,
                    "fields": sorted(set(fields)),
                }
            candidate = {
                **database,
                "published": True,
                "version": database["version"] + 1,
                "whitelist": whitelist,
            }
            await asyncio.to_thread(
                model_schema, candidate, make_policy(candidate, settings)
            )
            await app.state.store.update(candidate)
        return management_info(candidate)

    @app.delete("/api/connections/{admin_id}")
    async def remove_connection(admin_id: str):
        await app.state.store.delete(admin_id)
        return {"ok": True}

    @app.get("/api/chats/{public_id}")
    async def chat_info(public_id: str):
        database = await app.state.store.public(public_id)
        if not database:
            raise HTTPException(404, "Чат не найден или ещё не настроен.")
        return {
            "name": database["name"],
            "configured": True,
            "sql_backend": settings.sql_backend,
        }

    @app.post("/api/chats/{public_id}/query")
    async def chat_question(public_id: str, payload: Question):
        database = await app.state.store.public(public_id)
        if not database:
            raise HTTPException(404, "Чат не найден или ещё не настроен.")
        return await process_question(database, payload)

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "frontend/index.html")

    @app.get("/setup/{admin_id}")
    async def setup(admin_id: str):
        return FileResponse(ROOT / "frontend/index.html")

    @app.get("/demo")
    async def demo():
        return FileResponse(ROOT / "frontend/demo.html")

    @app.get("/chat/{public_id}")
    async def public_chat(public_id: str):
        return FileResponse(ROOT / "frontend/widget.html")

    @app.get("/widget")
    async def widget():
        return FileResponse(ROOT / "frontend/widget.html")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return FileResponse(ROOT / "frontend/favicon.svg", media_type="image/svg+xml")

    app.mount("/assets", StaticFiles(directory=ROOT / "frontend"), name="assets")
    return app


app = create_app()
