"""Подключения, пароли и выбранные колонки в памяти процесса сервера."""

import asyncio
import copy
import logging
import secrets

import asyncpg
from fastapi import HTTPException

LOGGER = logging.getLogger(__name__)


class DemoStore:
    def __init__(self, settings, inspector):
        self.settings, self.inspector = settings, inspector
        self.database = None
        self.connections = {}
        self.connection_credentials = {}
        self.lock = asyncio.Lock()
        self.connection = {
            "host": settings.demo_db_host,
            "port": settings.demo_db_port,
            "name": settings.demo_db_name,
            "user": settings.demo_db_user,
            "password": settings.demo_db_password,
            "ssl": settings.demo_db_ssl,
            "person_tables": ["students", "applicants", "applications"],
        }

    async def get(self, identifier="demo", locked=False):
        if identifier != "demo":
            return copy.deepcopy(self.connections.get(identifier))
        if not locked:
            async with self.lock:
                return await self.get(identifier, locked=True)
        if self.database is None:
            try:
                metadata = await self.inspector(self.connection)
            except (OSError, asyncpg.PostgresError, TimeoutError) as error:
                LOGGER.error(
                    "Ошибка подключения к локальной БД: %s", type(error).__name__
                )
                raise HTTPException(
                    503,
                    "Локальная БД недоступна. Запустите docker compose up -d postgres.",
                ) from None
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
            whitelist = {
                table["name"]: {
                    "enabled": True,
                    "fields": [
                        name
                        for name, _ in table["fields"]
                        if table["levels"][name] != "forbidden"
                    ],
                }
                for table in metadata["tables"]
            }
            self.database = {
                **metadata,
                "id": "demo",
                "version": 1,
                "whitelist": whitelist,
            }
        return copy.deepcopy(self.database)

    async def credentials(self, identifier):
        if identifier != "demo":
            return dict(self.connection_credentials[identifier])
        return dict(self.connection)

    async def create(self, credentials):
        async with self.lock:
            if len(self.connections) >= 8:
                raise HTTPException(409, "Достигнут лимит подключений прототипа: 8.")
            try:
                metadata = await self.inspector(credentials)
            except (OSError, asyncpg.PostgresError, TimeoutError) as error:
                LOGGER.warning("Ошибка подключения к БД: %s", type(error).__name__)
                raise HTTPException(
                    422,
                    "Не удалось подключиться к PostgreSQL. Проверьте адрес, пароль и SSL.",
                ) from None
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
            admin_id, public_id = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
            whitelist = {
                table["name"]: {
                    "enabled": False,
                    "fields": [],
                }
                for table in metadata["tables"]
            }
            self.connections[admin_id] = {
                **metadata,
                "id": admin_id,
                "public_id": public_id,
                "version": 1,
                "published": False,
                "whitelist": whitelist,
            }
            self.connection_credentials[admin_id] = dict(credentials)
            LOGGER.info(
                "Подключение создано, доступных таблиц: %s", len(metadata["tables"])
            )
            return copy.deepcopy(self.connections[admin_id])

    async def public(self, public_id):
        for database in self.connections.values():
            if database["public_id"] == public_id and database["published"]:
                return copy.deepcopy(database)
        return None

    async def update(self, database):
        if database["id"] == "demo":
            self.database = database
        else:
            self.connections[database["id"]] = database

    async def delete(self, identifier):
        async with self.lock:
            if identifier not in self.connections:
                raise HTTPException(404, "Подключение не найдено.")
            del self.connections[identifier]
            del self.connection_credentials[identifier]
            LOGGER.info("Подключение удалено")
