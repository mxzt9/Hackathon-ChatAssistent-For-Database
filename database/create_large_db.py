"""Создать отдельную большую учебную БД: python -m database.create_large_db."""

import argparse
import random
from pathlib import Path

import psycopg
from psycopg import sql

from database.generate_data import (
    Config,
    connect,
    insert_applications,
    insert_courses,
    insert_faculties,
    insert_grades,
    insert_programs,
    insert_students,
    insert_teachers,
    print_counts,
)

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(
        description="Новая БД с синтетическими данными; существующие БД не изменяются"
    )
    parser.add_argument("--name", default="university_large")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--students", type=int, default=10000)
    parser.add_argument("--applications", type=int, default=30000)
    parser.add_argument("--grades", type=int, default=200000)
    args = parser.parse_args()
    if min(args.students, args.applications, args.grades) < 1:
        parser.error("Количество записей должно быть положительным")
    # Используются реквизиты учебного контейнера, а не подключения из .env.
    with psycopg.connect(
        host=args.host,
        port=args.port,
        dbname="postgres",
        user="university",
        password="university",
        autocommit=True,
    ) as admin:
        if admin.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (args.name,)
        ).fetchone():
            parser.error("Эта БД уже существует. Укажите новое имя через --name")
        if not admin.execute(
            "SELECT 1 FROM pg_roles WHERE rolname='assistant_ro'"
        ).fetchone():
            parser.error(
                "Сначала запустите локальный PostgreSQL: docker compose up -d postgres"
            )
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER university").format(
                sql.Identifier(args.name)
            )
        )
    config = Config(
        host=args.host,
        port=args.port,
        dbname=args.name,
        user="university",
        password="university",
        students=args.students,
        applications=args.applications,
        teachers=200,
        courses=240,
        grades=args.grades,
        seed=42,
    )
    rng = random.Random(config.seed)
    with connect(config) as connection:
        connection.execute((ROOT / "schema.sql").read_text(encoding="utf-8"))
        faculties = insert_faculties(connection)
        programs = insert_programs(connection, faculties)
        teachers = insert_teachers(connection, config, rng)
        courses = insert_courses(connection, config, teachers, rng)
        students = insert_students(connection, config, programs, rng)
        insert_applications(connection, config, programs, rng)
        insert_grades(connection, config, students, courses, rng)
        # Роль уже существует; применяем права только внутри новой базы.
        grants = (ROOT / "readonly_role.sql").read_text(encoding="utf-8")
        connection.execute(grants[grants.index("REVOKE ALL ON SCHEMA public") :])
        connection.execute("ANALYZE")
        connection.commit()
        print_counts(connection)
        size = connection.execute(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        ).fetchone()[0]
        print(f"\nБаза {args.name}, размер: {size}")


if __name__ == "__main__":
    main()
