"""Проверка простых SELECT: таблицы, колонки, агрегаты и LIMIT.

Прототип поддерживает JOIN, GROUP BY, HAVING и ORDER BY.
CTE, вложенные SELECT, UNION и оконные функции пока не поддерживаются.
"""

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.qualify import qualify

from sql.policy import AGGREGATE_ONLY, Policy

SAFE_FUNCTIONS = {
    "count",
    "avg",
    "sum",
    "min",
    "max",
    "round",
    "abs",
    "lower",
    "upper",
    "coalesce",
    "nullif",
    "extract",
    "date_trunc",
    "timestamp_trunc",
    "cast",
    "year",
    "month",
    "day",
    "length",
    "substring",
    "trim",
    "floor",
    "ceil",
    "current_date",
    "current_timestamp",
    "filter",
}
SAFE_AGGREGATES = (exp.Count, exp.Avg, exp.Sum, exp.Min, exp.Max)


@dataclass
class GuardResult:
    allowed: bool
    sql: str | None = None
    error: str | None = None
    code: str | None = None
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    explain: dict = field(default_factory=dict)


def check_sql(
    raw_sql: str, policy: Policy, relations: list[dict] | None = None
) -> GuardResult:
    try:
        return validate(raw_sql, policy, relations)
    except (ValueError, SqlglotError) as error:
        return GuardResult(
            allowed=False,
            code="invalid_sql",
            reasons=[str(error)],
            error="Запрос отклонён: " + str(error),
        )


def validate_joins(tree, aliases, relations):
    permitted = {
        frozenset(
            (
                (r["source_table"], r["source_column"]),
                (r["target_table"], r["target_column"]),
            )
        )
        for r in relations
    }
    connected = {tree.args["from_"].this.alias_or_name}

    def conditions(node):
        if isinstance(node, exp.Paren):
            yield from conditions(node.this)
        elif isinstance(node, exp.And):
            yield from conditions(node.this)
            yield from conditions(node.expression)
        else:
            yield node

    for join in tree.args.get("joins", []):
        target = join.this.alias_or_name
        on = join.args.get("on")
        linked = False
        if on is None:
            raise ValueError(
                "JOIN должен содержать ON по внешнему ключу; CROSS JOIN запрещён"
            )
        for condition in conditions(on):
            columns = list(condition.find_all(exp.Column))
            tables = {column.table for column in columns}
            if len(tables) < 2:
                continue
            if not (
                isinstance(condition, exp.EQ)
                and isinstance(condition.this, exp.Column)
                and isinstance(condition.expression, exp.Column)
            ):
                raise ValueError(
                    "Связи в JOIN должны быть равенствами внешних ключей, объединёнными AND"
                )
            left, right = condition.this, condition.expression
            pair = frozenset(
                ((aliases[left.table], left.name), (aliases[right.table], right.name))
            )
            if pair not in permitted:
                raise ValueError(
                    f"JOIN {condition.sql()}: такой связи нет среди внешних ключей схемы"
                )
            if target in tables and tables - {target} <= connected:
                linked = True
        if not linked:
            raise ValueError(
                f"JOIN {target} не связан внешним ключом с предыдущими таблицами"
            )
        connected.add(target)


def validate(raw_sql, policy, relations=None):
    if not raw_sql or len(raw_sql) > 10000:
        raise ValueError("SQL пустой или слишком длинный")

    statements = [
        tree for tree in sqlglot.parse(raw_sql, read="postgres") if tree is not None
    ]

    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ValueError("Разрешён ровно один SELECT")
    tree = statements[0]

    if len(list(tree.find_all(exp.Select))) != 1 or tree.args.get("with_"):
        raise ValueError("Вложенные SELECT и WITH пока не поддерживаются")
    if tree.args.get("into") or tree.args.get("locks") or tree.find(exp.Window):
        raise ValueError("SELECT INTO, блокировки и оконные функции запрещены")
    if tree.find(exp.Dot):
        raise ValueError(
            "Обращения к функциям другой схемы и составным полям запрещены"
        )
    for node in tree.walk():
        node.comments = None
    aliases = {}
    for table in tree.find_all(exp.Table):
        if (
            table.catalog
            or table.db not in ("", "public")
            or table.name not in policy.tables
        ):
            raise ValueError(f"Таблица {table.sql()} не разрешена")
        aliases[table.alias_or_name] = table.name
        table.set("db", None)
    if not aliases:
        raise ValueError("Выберите данные из разрешённой таблицы")
    for column in tree.find_all(exp.Column):
        if not column.table and column.name in aliases:
            raise ValueError("Чтение целой строки таблицы запрещено")
    for function in tree.find_all(exp.Func):
        if isinstance(function, (exp.And, exp.Or, exp.Not, exp.Case, exp.If)):
            continue
        name = (
            function.name.lower()
            if isinstance(function, exp.Anonymous)
            else function.sql_name().lower()
        )
        if name not in SAFE_FUNCTIONS:
            raise ValueError(f"Функция {name} не разрешена")
    # sqlglot связывает поля с таблицами по выбранной администратором схеме.
    tree = qualify(
        tree,
        dialect="postgres",
        schema=policy.sqlglot_schema(),
        identify=False,
        validate_qualify_columns=True,
    )
    aliases = {table.alias_or_name: table.name for table in tree.find_all(exp.Table)}
    if relations is not None:
        validate_joins(tree, aliases, relations)
    exposed = list(tree.expressions)
    if tree.args.get("group"):
        exposed.append(tree.args["group"])
    if tree.args.get("order"):
        exposed.append(tree.args["order"])
    for expression in exposed:
        for column in expression.find_all(exp.Column):
            table = aliases.get(column.table)
            if table is None:
                continue  # ORDER BY может ссылаться на алиас результата.
            if policy.level(table, column.name) != AGGREGATE_ONLY:
                continue
            parent = column.parent
            while parent is not None and not isinstance(
                parent, SAFE_AGGREGATES + (exp.Select,)
            ):
                parent = parent.parent
            if not isinstance(parent, SAFE_AGGREGATES):
                raise ValueError(
                    f"{table}.{column.name} доступна только внутри COUNT/AVG/SUM/MIN/MAX"
                )
    for key in ("limit", "offset"):
        value = tree.args.get(key)
        if value is not None and (
            not isinstance(value.expression, exp.Literal)
            or not value.expression.is_int
            or int(value.expression.this) < 0
        ):
            raise ValueError(f"{key.upper()} должен быть неотрицательным целым числом")
    if tree.args.get("offset"):
        raise ValueError("Пагинация пока не поддерживается; уточните запрос фильтром")
    limit = tree.args.get("limit")
    count = (
        min(int(limit.expression.this), policy.limits.default_limit)
        if limit
        else policy.limits.default_limit
    )
    tree = tree.limit(count)
    return GuardResult(
        allowed=True,
        sql=tree.sql(dialect="postgres", pretty=True),
        explain={
            "tables": sorted(set(aliases.values())),
            "limit": count,
            "joins": [join.sql(dialect="postgres") for join in tree.find_all(exp.Join)],
            "filters": [
                where.sql(dialect="postgres") for where in tree.find_all(exp.Where)
            ],
            "aggregates": [
                aggregate.sql(dialect="postgres")
                for aggregate in tree.find_all(exp.AggFunc)
            ],
        },
    )
