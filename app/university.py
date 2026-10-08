"""SQL for supported university intents. Results always come from PostgreSQL.

This is an explicit deterministic backend, not a claim of model accuracy.
Only the known university schema is supported; every query still passes the guard.
"""

import re
from datetime import datetime, timedelta, timezone

from sql.policy import Policy


def university_sql(question: str, policy: Policy) -> str | None:
    text = " ".join(question.lower().replace("ё", "е").split())
    if re.search(
        r"\b(insert|update|delete|drop|alter|удали|удалить|измени|изменить)\b", text
    ):
        return None
    if any(
        word in text for word in ("моей", "моему", "мой ", "кроме", "больше", "меньше")
    ):
        return None
    years = re.findall(r"\b(?:19|20)\d{2}\b", text)
    if len(years) > 1 or any(
        word in text
        for word in ("кроме", "не математ", "не эконом", "или ", "старше", "младше")
    ):
        return None
    subject = next(
        (
            stem
            for stem in ("математик", "экономик", "информатик", "физик")
            if stem in text
        ),
        None,
    )
    if (
        subject is None
        and re.search(r"\b(?:по|на)\s+", text)
        and not any(phrase in text for phrase in ("по годам", "набор"))
    ):
        return None
    if (
        sum(stem in text for stem in ("математик", "экономик", "информатик", "физик"))
        > 1
    ):
        return None
    quoted = "'%" + subject + "%'" if subject else None
    grouped = any(
        phrase in text
        for phrase in (
            "по годам",
            "каждый год",
            "за последние",
            "динамик",
            "менял",
            "менялся",
        )
    )
    recent = re.search(r"за последние\s+(\d+|пять|три|десять)\s+лет", text)
    words = {"пять": 5, "три": 3, "десять": 10}

    def available(required):
        return all(
            policy.level(table, column)
            for table, columns in required.items()
            for column in columns
        )

    def year_filter(column):
        if years:
            return f"{column} = {int(years[0])}"
        if recent:
            value = recent.group(1)
            count = words[value] if value in words else int(value)
            if not 1 <= count <= 100:
                return "FALSE"
            current_year = datetime.now(timezone(timedelta(hours=3))).year
            return f"{column} BETWEEN {current_year - count + 1} AND {current_year}"
        return None

    def where(filters):
        return " WHERE " + " AND ".join(filters) if filters else ""

    if any(word in text for word in ("преподавател", "препод", "учител")) and not any(
        word in text for word in ("оцен", "балл", "студент")
    ):
        if years or grouped:
            return None
        required = {"teachers": ["id", "full_name"]}
        join = ""
        filters = []
        if subject:
            required["courses"] = ["teacher_id", "name"]
            join = " JOIN courses c ON c.teacher_id = t.id"
            filters.append(f"c.name ILIKE {quoted}")
        if not available(required):
            return None
        if "сколько" in text or "количеств" in text:
            return (
                "SELECT COUNT(DISTINCT t.id) AS teachers_count FROM teachers t"
                + join
                + where(filters)
            )
        return (
            "SELECT DISTINCT t.full_name FROM teachers t"
            + join
            + where(filters)
            + " ORDER BY t.full_name"
        )

    if ("средн" in text or "avg" in text) and any(
        word in text for word in ("оцен", "балл", "grade")
    ):
        if years or grouped:
            return None
        required = {"grades": ["grade", "course_id"], "courses": ["id", "name"]}
        if not available(required):
            return None
        filters = [f"c.name ILIKE {quoted}"] if subject else []
        if "семестр" in text:
            semester = re.search(r"(?:за|в)?\s*(\d+)\s*семестр|семестр\s*(\d+)", text)
            if semester is None or not available({"grades": ["semester"]}):
                return None
            filters.append(
                f"g.semester = {int(semester.group(1) or semester.group(2))}"
            )
        return (
            "SELECT c.name AS course, ROUND(AVG(g.grade), 2) AS average_grade FROM grades g JOIN courses c ON c.id = g.course_id"
            + where(filters)
            + " GROUP BY c.name ORDER BY c.name"
        )

    count = any(
        word in text
        for word in (
            "сколько",
            "количеств",
            "число",
            "динамик",
            "менял",
            "набор",
            "по годам",
        )
    )
    if count and any(
        word in text
        for word in ("студент", "учащ", "заявлен", "абитуриент", "поступлен", "набор")
    ):
        applications = any(word in text for word in ("заявлен", "абитуриент"))
        table = "applications" if applications else "students"
        year = "year" if applications else "admission_year"
        required = {table: [year]}
        filters = []
        join = ""
        if subject:
            required[table].append("program_id")
            required["programs"] = ["id", "name"]
            join = " JOIN programs p ON p.id = x.program_id"
            filters.append(f"p.name ILIKE {quoted}")
        condition = year_filter("x." + year)
        if condition:
            filters.append(condition)
        if applications:
            status = next(
                (
                    value
                    for word, value in (
                        ("принят", "accepted"),
                        ("отклон", "rejected"),
                        ("отозван", "withdrawn"),
                    )
                    if word in text
                ),
                None,
            )
            if status:
                required[table].append("status")
                filters.append(f"x.status = '{status}'")
        if not available(required):
            return None
        projection = (
            f"x.{year} AS year, COUNT(*) AS total" if grouped else "COUNT(*) AS total"
        )
        suffix = f" GROUP BY x.{year} ORDER BY x.{year}" if grouped else ""
        return f"SELECT {projection} FROM {table} x" + join + where(filters) + suffix

    for word, table in (
        ("факультет", "faculties"),
        ("программ", "programs"),
        ("дисциплин", "courses"),
        ("курс", "courses"),
    ):
        if (
            word in text
            and not any(
                token in text for token in ("студент", "заявлен", "оцен", "балл")
            )
            and available({table: ["name"]})
        ):
            if "сколько" in text:
                return f"SELECT COUNT(*) AS total FROM {table}"
            return f"SELECT name FROM {table} ORDER BY name"
    return None
