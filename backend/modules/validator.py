from typing import List, Set, Optional, Dict
import sqlglot
from sqlglot import exp
from pydantic import BaseModel, Field

class ValidationResult(BaseModel):
    is_valid: bool
    sanitized_sql: Optional[str] = None
    ast_representation: Optional[str] = None
    statement_type: Optional[str] = None
    tables_referenced: List[str] = Field(default_factory=list)
    columns_referenced: List[str] = Field(default_factory=list)
    joins_detected: List[Dict[str, str]] = Field(default_factory=list)
    relationships_used: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

class SQLValidator:
    """
    Validates generated SQL queries using SQLGlot AST inspection with PostgreSQL dialect.
    Enforces read-only safety, structure checks, and schema alignment.
    """

    # Prohibited SQL statement AST types
    FORBIDDEN_EXPRESSIONS = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Alter,
        exp.Create,
        exp.Command,
    )

    # Keywords or patterns that should be strictly blocked
    FORBIDDEN_KEYWORDS = {
        "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE",
        "GRANT", "REVOKE", "COPY", "EXECUTE", "VACUUM", "REINDEX",
        "CALL", "DO", "LOCK", "ALTER TABLE", "CREATE TABLE"
    }

    @classmethod
    def validate(
        cls, 
        sql: str, 
        known_tables: Optional[Dict[str, List[str]]] = None,
        dialect: Optional[str] = None
    ) -> ValidationResult:
        if not sql or not sql.strip():
            return ValidationResult(
                is_valid=False,
                errors=["SQL statement is empty."]
            )

        clean_sql = sql.strip().rstrip(";")
        errors: List[str] = []
        warnings: List[str] = []
        tables_referenced: List[str] = []
        columns_referenced: List[str] = []
        parsed_ast = None
        statement_type = None

        # 1. Parse AST with PostgreSQL dialect (with fallback to default)
        try:
            parsed = sqlglot.parse_one(clean_sql, read="postgres")
            parsed_ast = str(parsed)
            statement_type = parsed.key.upper() if hasattr(parsed, "key") else type(parsed).__name__
        except Exception as e:
            try:
                parsed = sqlglot.parse_one(clean_sql)
                parsed_ast = str(parsed)
                statement_type = parsed.key.upper() if hasattr(parsed, "key") else type(parsed).__name__
            except Exception as e2:
                return ValidationResult(
                    is_valid=False,
                    errors=[f"SQL syntax parsing error: {str(e2)}"]
                )

        # 2. Check Statement Type - MUST BE SELECT OR WITH ... SELECT
        is_select = isinstance(parsed, exp.Select) or (
            isinstance(parsed, exp.Union) and all(isinstance(sub, exp.Select) for sub in parsed.flatten())
        )
        if not is_select:
            errors.append(f"Security violation: Only SELECT queries are permitted. Found statement of type '{statement_type}'.")

        # 3. Check for any nested or embedded forbidden AST nodes
        for forbidden in cls.FORBIDDEN_EXPRESSIONS:
            if parsed.find(forbidden):
                errors.append(f"Security violation: Prohibited operation '{forbidden.__name__}' found in AST.")

        # 4. Extract referenced tables, CTEs, and columns
        cte_names = set()
        for cte in parsed.find_all(exp.CTE):
            if cte.alias_or_name:
                cte_names.add(cte.alias_or_name.lower())

        subquery_aliases = set()
        for subquery in parsed.find_all(exp.Subquery):
            if subquery.alias:
                subquery_aliases.add(subquery.alias.lower())

        extracted_tables = set()
        for table in parsed.find_all(exp.Table):
            if table.name:
                tbl_lower = table.name.lower()
                # Exclude in-memory CTE names and subquery aliases from physical schema tables
                if tbl_lower not in cte_names and tbl_lower not in subquery_aliases:
                    extracted_tables.add(tbl_lower)
        tables_referenced = sorted(list(extracted_tables))

        extracted_cols = set()
        for col in parsed.find_all(exp.Column):
            if col.name and col.name != "*":
                extracted_cols.add(col.name.lower())
        columns_referenced = sorted(list(extracted_cols))

        # 5. Schema verification if known_tables is provided
        # Note: Queries without physical tables (e.g. pure formulas, CTE-only, or VALUES) are completely valid
        if known_tables and tables_referenced:
            lower_known = {k.lower(): [c.lower() for c in v] for k, v in known_tables.items()}
            for tbl in tables_referenced:
                if tbl not in lower_known:
                    errors.append(f"Schema violation: Table '{tbl}' does not exist in the active database schema.")

        # 6. Safety check for LIMIT clause (prevent returning millions of rows accidentally)
        has_limit = bool(parsed.find(exp.Limit))
        if not has_limit:
            warnings.append("Notice: Query has no LIMIT clause. Backend will apply a default ceiling limit (e.g. 100).")

        # 7. Extract JOINs and relationships used
        joins_detected = []
        relationships_used = []
        for j in parsed.find_all(exp.Join):
            tbl_name = j.this.name if hasattr(j.this, "name") and j.this.name else str(j.this)
            on_expr = j.args.get("on")
            on_clause = on_expr.sql("postgres") if on_expr else "CROSS / NATURAL"
            side = j.side or "INNER"
            join_repr = f"{side} JOIN {tbl_name} ON {on_clause}"
            joins_detected.append({
                "table": tbl_name,
                "type": side,
                "on": on_clause,
                "representation": join_repr
            })
            relationships_used.append(join_repr)

        # Transpile cleanly back to requested dialect (postgres or sqlite)
        target_dialect = dialect or "postgres"
        try:
            sanitized_sql = parsed.sql(dialect=target_dialect, pretty=True)
        except Exception:
            sanitized_sql = clean_sql

        is_valid = len(errors) == 0
        return ValidationResult(
            is_valid=is_valid,
            sanitized_sql=sanitized_sql if is_valid else None,
            ast_representation=parsed_ast,
            statement_type=statement_type,
            tables_referenced=tables_referenced,
            columns_referenced=columns_referenced,
            joins_detected=joins_detected,
            relationships_used=relationships_used,
            errors=errors,
            warnings=warnings
        )
