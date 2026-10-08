"""Синтетические данные для database.create_large_db."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

import psycopg
from psycopg import Connection


@dataclass(frozen=True, slots=True)
class Config:
    host: str
    port: int
    dbname: str
    user: str
    password: str
    students: int
    applications: int
    teachers: int
    courses: int
    grades: int
    seed: int


FACULTIES: Final[list[str]] = [
    "Факультет экономики и управления",
    "Факультет информационных технологий",
    "Факультет инженерной механики",
    "Факультет химической технологии",
    "Факультет энергетики",
]

PROGRAMS: Final[dict[str, list[str]]] = {
    "Факультет экономики и управления": [
        "Экономика",
        "Менеджмент",
        "Бизнес-информатика",
        "Управление персоналом",
    ],
    "Факультет информационных технологий": [
        "Прикладная информатика",
        "Программная инженерия",
        "Информационные системы",
        "Искусственный интеллект",
    ],
    "Факультет инженерной механики": [
        "Машиностроение",
        "Мехатроника и робототехника",
        "Технологические машины",
        "Автоматизация производств",
    ],
    "Факультет химической технологии": [
        "Химическая технология",
        "Нефтехимия",
        "Экология",
        "Материаловедение",
    ],
    "Факультет энергетики": [
        "Электроэнергетика",
        "Теплоэнергетика",
        "Энергетическое машиностроение",
        "Автоматизированные энергосистемы",
    ],
}

COURSE_NAMES: Final[list[str]] = [
    "Математика",
    "Высшая математика",
    "Дискретная математика",
    "Математический анализ",
    "Линейная алгебра",
    "Теория вероятностей",
    "Физика",
    "Информатика",
    "Программирование",
    "Базы данных",
    "Алгоритмы и структуры данных",
    "Экономика",
    "Статистика",
    "Теоретическая механика",
    "Сопротивление материалов",
    "Электротехника",
    "Химия",
    "Термодинамика",
    "Экология",
    "Моделирование систем",
    "Машинное обучение",
    "Управление проектами",
    "Иностранный язык",
]

FIRST_NAMES: Final[list[str]] = [
    "Александр",
    "Алексей",
    "Андрей",
    "Антон",
    "Владимир",
    "Дмитрий",
    "Евгений",
    "Иван",
    "Максим",
    "Михаил",
    "Никита",
    "Павел",
    "Роман",
    "Сергей",
    "Анастасия",
    "Анна",
    "Дарья",
    "Екатерина",
    "Елена",
    "Мария",
]

LAST_NAMES: Final[list[str]] = [
    "Иванов",
    "Петров",
    "Смирнов",
    "Кузнецов",
    "Попов",
    "Соколов",
    "Лебедев",
    "Козлов",
    "Новиков",
    "Морозов",
    "Волков",
    "Алексеев",
    "Семенов",
    "Егоров",
    "Павлов",
]

PATRONYMICS: Final[list[str]] = [
    "Александрович",
    "Алексеевич",
    "Андреевич",
    "Владимирович",
    "Дмитриевич",
    "Евгеньевич",
    "Иванович",
    "Максимович",
    "Михайлович",
    "Сергеевич",
]

APPLICATION_STATUSES: Final[tuple[str, ...]] = (
    "submitted",
    "accepted",
    "rejected",
    "withdrawn",
)


def make_person_name(rng: random.Random, index: int) -> str:
    first_name = rng.choice(FIRST_NAMES)
    last_name = rng.choice(LAST_NAMES)
    patronymic = rng.choice(PATRONYMICS)
    return f"{last_name} {first_name} {patronymic} #{index}"


def make_email(index: int, prefix: str) -> str:
    return f"{prefix}{index}@example.test"


def make_phone(rng: random.Random) -> str:
    return (
        f"+7{rng.randint(900, 999)}"
        f"{rng.randint(100, 999)}"
        f"{rng.randint(10, 99)}"
        f"{rng.randint(10, 99)}"
    )


def make_passport(rng: random.Random) -> tuple[str, str]:
    series = f"{rng.randint(10, 99):02d}{rng.randint(10, 99):02d}"
    number = f"{rng.randint(0, 999999):06d}"
    return series, number


def make_birth_date(rng: random.Random) -> date:
    start = date(1998, 1, 1)
    end = date(2008, 12, 31)
    days = (end - start).days
    return start + timedelta(days=rng.randint(0, days))


def connect(config: Config) -> Connection[tuple[object, ...]]:
    return psycopg.connect(
        host=config.host,
        port=config.port,
        dbname=config.dbname,
        user=config.user,
        password=config.password,
    )


def insert_faculties(conn: Connection[tuple[object, ...]]) -> dict[str, int]:
    result: dict[str, int] = {}

    with conn.cursor() as cur:
        for name in FACULTIES:
            cur.execute("INSERT INTO faculties(name) VALUES (%s) RETURNING id", (name,))
            row = cur.fetchone()

            if row is None:
                raise RuntimeError("Не удалось создать факультет")

            result[name] = int(row[0])

    return result


def insert_programs(
    conn: Connection[tuple[object, ...]], faculty_ids: dict[str, int]
) -> list[int]:
    program_ids: list[int] = []

    with conn.cursor() as cur:
        for faculty_name, programs in PROGRAMS.items():
            faculty_id = faculty_ids[faculty_name]

            for program_name in programs:
                cur.execute(
                    """
                    INSERT INTO programs(faculty_id, name)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (faculty_id, program_name),
                )
                row = cur.fetchone()

                if row is None:
                    raise RuntimeError("Не удалось создать программу")

                program_ids.append(int(row[0]))

    return program_ids


def insert_teachers(
    conn: Connection[tuple[object, ...]], config: Config, rng: random.Random
) -> list[int]:
    rows = [(make_person_name(rng, index),) for index in range(1, config.teachers + 1)]

    with conn.cursor() as cur:
        cur.executemany("INSERT INTO teachers(full_name) VALUES (%s)", rows)

    return list(range(1, config.teachers + 1))


def insert_courses(
    conn: Connection[tuple[object, ...]],
    config: Config,
    teacher_ids: list[int],
    rng: random.Random,
) -> list[int]:
    rows: list[tuple[int, str]] = []

    for index in range(config.courses):
        teacher_id = rng.choice(teacher_ids)
        base_name = COURSE_NAMES[index % len(COURSE_NAMES)]
        course_name = f"{base_name} {index // len(COURSE_NAMES) + 1}"
        rows.append((teacher_id, course_name))

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO courses(teacher_id, name)
            VALUES (%s, %s)
            """,
            rows,
        )

    return list(range(1, config.courses + 1))


def insert_students(
    conn: Connection[tuple[object, ...]],
    config: Config,
    program_ids: list[int],
    rng: random.Random,
) -> list[int]:
    rows: list[tuple[int, int, str, date, str, str, str, str]] = []

    for index in range(1, config.students + 1):
        passport_series, passport_number = make_passport(rng)

        rows.append(
            (
                rng.choice(program_ids),
                rng.randint(2021, 2026),
                make_person_name(rng, index),
                make_birth_date(rng),
                make_email(index, "student"),
                make_phone(rng),
                passport_series,
                passport_number,
            )
        )

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO students(
                program_id,
                admission_year,
                full_name,
                birth_date,
                email,
                phone,
                passport_series,
                passport_number
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )

    return list(range(1, config.students + 1))


def insert_applications(
    conn: Connection[tuple[object, ...]],
    config: Config,
    program_ids: list[int],
    rng: random.Random,
) -> None:
    rows: list[tuple[int, int, str, str, str, str, str, str]] = []

    for index in range(1, config.applications + 1):
        passport_series, passport_number = make_passport(rng)

        rows.append(
            (
                rng.choice(program_ids),
                rng.randint(2021, 2026),
                rng.choices(APPLICATION_STATUSES, weights=(35, 30, 25, 10), k=1)[0],
                make_person_name(rng, index),
                make_email(index, "applicant"),
                make_phone(rng),
                passport_series,
                passport_number,
            )
        )

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO applications(
                program_id,
                year,
                status,
                applicant_full_name,
                applicant_email,
                applicant_phone,
                applicant_passport_series,
                applicant_passport_number
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )


def insert_grades(
    conn: Connection[tuple[object, ...]],
    config: Config,
    student_ids: list[int],
    course_ids: list[int],
    rng: random.Random,
) -> None:
    rows = [
        (
            rng.choice(student_ids),
            rng.choice(course_ids),
            rng.choices(population=(2, 3, 4, 5), weights=(8, 27, 40, 25), k=1)[0],
            rng.randint(1, 8),
        )
        for _ in range(config.grades)
    ]

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO grades(student_id, course_id, grade, semester)
            VALUES (%s, %s, %s, %s)
            """,
            rows,
        )


def print_counts(conn: Connection[tuple[object, ...]]) -> None:
    tables = (
        "faculties",
        "programs",
        "students",
        "applications",
        "teachers",
        "courses",
        "grades",
    )

    with conn.cursor() as cur:
        print("\nГотово:")

        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            row = cur.fetchone()
            count = int(row[0]) if row is not None else 0
            print(f"{table:<14} {count}")
