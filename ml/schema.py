"""Подготовка DDL для модели: только таблицы и разрешённые поля."""

from pglast import ast, parse_sql
from pglast.enums import ConstrType
from pglast.stream import RawStream

from sql.policy import PUBLIC, Policy


def prepare_schema(ddl: str, policy: Policy | None = None) -> str:
    creates = [
        item.stmt for item in parse_sql(ddl) if isinstance(item.stmt, ast.CreateStmt)
    ]
    if not creates:
        raise ValueError("Schema has no CREATE TABLE statements")
    result = []
    for create in creates:
        table = create.relation.relname
        if create.relation.schemaname not in (None, "public"):
            raise ValueError("Only local/public schema is supported")
        if policy is not None and table not in policy.tables:
            continue
        elements = []
        for element in create.tableElts:
            if isinstance(element, ast.Constraint):
                local = [field.sval for field in element.fk_attrs or element.keys or ()]
                visible = policy is None or all(
                    policy.level(table, name) for name in local
                )
                if (
                    element.contype
                    in (ConstrType.CONSTR_PRIMARY, ConstrType.CONSTR_UNIQUE)
                    and visible
                ):
                    elements.append(element)
                elif element.contype == ConstrType.CONSTR_FOREIGN and visible:
                    referenced = element.pktable.relname
                    foreign = [field.sval for field in element.pk_attrs or ()]
                    if policy is None or (
                        referenced in policy.tables
                        and all(policy.level(referenced, name) for name in foreign)
                    ):
                        elements.append(element)
                continue
            if not isinstance(element, ast.ColumnDef):
                continue
            if policy is not None and policy.level(table, element.colname) is None:
                continue
            constraints = []
            for constraint in element.constraints or ():
                # DEFAULT/CHECK могут содержать закрытые значения и вызовы функций.
                if constraint.contype in (
                    ConstrType.CONSTR_PRIMARY,
                    ConstrType.CONSTR_NOTNULL,
                ):
                    constraints.append(constraint)
                elif constraint.contype == ConstrType.CONSTR_FOREIGN:
                    referenced = constraint.pktable.relname
                    columns = [field.sval for field in constraint.pk_attrs or ()]
                    if policy is None or (
                        referenced in policy.tables
                        and all(policy.level(referenced, name) for name in columns)
                    ):
                        constraints.append(constraint)
            element.constraints = tuple(constraints)
            elements.append(element)
        if not elements:
            continue
        create.tableElts = tuple(elements)
        create.constraints = None
        result.append(RawStream()(create) + ";")
    schema = "\n".join(result)
    if not schema:
        raise ValueError("Whitelist has no visible schema columns")
    return schema


def schema_columns(schema: str) -> dict[str, list[str]]:
    return {
        item.stmt.relation.relname: [
            column.colname
            for column in item.stmt.tableElts
            if isinstance(column, ast.ColumnDef)
        ]
        for item in parse_sql(schema)
        if isinstance(item.stmt, ast.CreateStmt)
    }


def schema_policy(schema: str) -> Policy:
    return Policy(
        allowed={
            table: {column: PUBLIC for column in columns}
            for table, columns in schema_columns(schema).items()
        }
    )
