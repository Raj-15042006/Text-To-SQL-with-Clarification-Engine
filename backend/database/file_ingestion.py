import io
import re
import os
import json
import logging
import datetime
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import psycopg
from backend.config import settings
from backend.database.connection import db_manager

logger = logging.getLogger(__name__)

RESERVED_SQL_KEYWORDS = {
    "select", "from", "where", "group", "order", "by", "having", "limit", "offset",
    "table", "user", "column", "check", "constraint", "create", "database", "default",
    "delete", "drop", "index", "insert", "into", "update", "values", "join", "left",
    "right", "outer", "inner", "cross", "on", "as", "all", "any", "and", "or", "not",
    "distinct", "is", "null", "like", "in", "between", "union", "intersect", "except",
    "case", "when", "then", "else", "end", "with", "primary", "key", "foreign", "references"
}

def sanitize_identifier(name: str) -> str:
    """Sanitizes file or column name into a safe, standard SQL identifier."""
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', str(name).strip().lower())
    clean = re.sub(r'_+', '_', clean).strip('_')
    if not clean or clean[0].isdigit():
        clean = f"col_{clean}"
    if clean.startswith("sqlite_"):
        clean = f"tbl_{clean}"
    if clean in RESERVED_SQL_KEYWORDS:
        clean = f"tbl_{clean}"
    return clean[:50]

def infer_sql_type(series: pd.Series, is_postgres: bool = False) -> str:
    """Infers appropriate PostgreSQL / SQLite column type from a pandas Series."""
    try:
        non_null = series.dropna()
    except Exception:
        non_null = [v for v in series if v is not None]

    if len(non_null) == 0:
        return "TEXT"

    dtype = str(series.dtype).lower()
    if "int" in dtype:
        try:
            max_val = non_null.max()
            min_val = non_null.min()
            if min_val >= -2147483648 and max_val <= 2147483647:
                return "INTEGER"
            return "BIGINT" if is_postgres else "INTEGER"
        except Exception:
            return "INTEGER"
    elif "float" in dtype:
        try:
            # Check if all non-null values are actually integers
            if len(non_null) > 0 and (non_null % 1 == 0).all():
                max_val = non_null.max()
                min_val = non_null.min()
                if min_val >= -2147483648 and max_val <= 2147483647:
                    return "INTEGER"
                return "BIGINT" if is_postgres else "INTEGER"
        except Exception:
            pass
        return "DOUBLE PRECISION" if is_postgres else "REAL"
    elif "bool" in dtype:
        return "BOOLEAN" if is_postgres else "INTEGER"
    elif "datetime" in dtype:
        return "TIMESTAMP" if is_postgres else "TEXT"

    # Try parsing dates/timestamps if object
    if dtype == "object":
        sample = non_null.head(15).astype(str) if hasattr(non_null, 'head') else [str(x) for x in non_null[:15]]
        if len(sample) > 0:
            is_date = True
            is_iso_time = True
            for val in sample:
                val_s = str(val).strip()
                if not (re.match(r'^\d{4}-\d{2}-\d{2}$', val_s) or re.match(r'^\d{2}/\d{2}/\d{4}$', val_s)):
                    is_date = False
                if not re.match(r'^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}', val_s):
                    is_iso_time = False
            if is_iso_time:
                return "TIMESTAMP" if is_postgres else "TEXT"
            if is_date:
                return "DATE" if is_postgres else "TEXT"

    return "TEXT"

def clean_cell_value(val: Any, col_type: str) -> Any:
    """Safely cleans and coerces a cell value for SQL insertion without array ambiguity."""
    if val is None:
        return None

    # Complex objects (nested dictionaries, arrays, lists) serialized to JSON string
    if isinstance(val, (list, dict, tuple)):
        try:
            return json.dumps(val, ensure_ascii=False)
        except Exception:
            return str(val)

    # Check for NaN / NaT safely without triggering array boolean ambiguity
    try:
        if pd.isna(val):
            return None
    except (ValueError, TypeError):
        pass

    # Type coercion based on target column type
    if "INT" in col_type:
        try:
            if isinstance(val, str):
                val_cleaned = re.sub(r'[\$,€,£,¥,]', '', val.strip())
                return int(round(float(val_cleaned)))
            return int(round(float(val)))
        except Exception:
            return None
    elif any(t in col_type for t in ("REAL", "DOUBLE", "NUMERIC", "FLOAT")):
        try:
            if isinstance(val, str):
                val_cleaned = re.sub(r'[\$,€,£,¥,]', '', val.strip().replace('%', ''))
                return float(val_cleaned)
            return float(val)
        except Exception:
            return None
    elif "BOOL" in col_type:
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return bool(val)
        if isinstance(val, str):
            v_low = val.strip().lower()
            if v_low in ("true", "1", "yes", "t", "y"):
                return True
            if v_low in ("false", "0", "no", "f", "n"):
                return False
        return None
    elif hasattr(val, 'item'):
        try:
            return val.item()
        except Exception:
            return str(val)
    elif isinstance(val, (pd.Timestamp, datetime.datetime, datetime.date)):
        return val.isoformat()

    return val

def _ingest_into_sqlite(clean_table: str, clean_cols: List[str], sqlite_col_defs_sql: str, clean_records: List[List[Any]]) -> None:
    """Helper to write table into the in-memory/local SQLite database."""
    conn = db_manager._sample_sqlite_conn
    if not conn:
        return
    cur = conn.cursor()
    cur.execute(f'DROP TABLE IF EXISTS "{clean_table}";')
    create_sql = f'CREATE TABLE "{clean_table}" ({sqlite_col_defs_sql});'
    cur.execute(create_sql)

    placeholders = ", ".join(["?"] * len(clean_cols))
    col_names_sql = ", ".join([f'"{c}"' for c in clean_cols])
    insert_sql = f'INSERT INTO "{clean_table}" ({col_names_sql}) VALUES ({placeholders})'
    if clean_records:
        cur.executemany(insert_sql, clean_records)
    conn.commit()

def ingest_dataframe(df: pd.DataFrame, table_name: str) -> Dict[str, Any]:
    """
    Ingests a pandas DataFrame into either the active PostgreSQL database or the local SQLite database.
    Creates table with inferred schema and inserts records with robust type coercion and NaN handling.
    """
    clean_table = sanitize_identifier(table_name)
    if not clean_table:
        clean_table = "uploaded_data"

    if df is None or len(df.columns) == 0:
        raise ValueError("The uploaded dataset contains no columns or data.")

    # Clean and deduplicate column names
    clean_cols = []
    used_cols = set()
    for col in df.columns:
        c_name = sanitize_identifier(str(col))
        orig_name = c_name
        counter = 1
        while c_name in used_cols:
            c_name = f"{orig_name}_{counter}"
            counter += 1
        used_cols.add(c_name)
        clean_cols.append(c_name)

    df.columns = clean_cols

    is_pg = (db_manager.active_source == "postgresql")

    # Infer column types for both Postgres and SQLite
    pg_col_defs = []
    sqlite_col_defs = []
    col_types = []
    for col in clean_cols:
        pg_type = infer_sql_type(df[col], is_postgres=True)
        sqlite_type = infer_sql_type(df[col], is_postgres=False)
        col_types.append(pg_type if is_pg else sqlite_type)
        pg_col_defs.append(f'"{col}" {pg_type}')
        sqlite_col_defs.append(f'"{col}" {sqlite_type}')

    pg_col_defs_sql = ", ".join(pg_col_defs)
    sqlite_col_defs_sql = ", ".join(sqlite_col_defs)

    # Convert DataFrame records safely
    clean_records = []
    for row in df.itertuples(index=False):
        clean_row = [clean_cell_value(val, ctype) for val, ctype in zip(row, col_types)]
        clean_records.append(clean_row)

    pg_success = False
    if is_pg:
        # Ingest into PostgreSQL using write credentials
        try:
            dsn = settings.get_postgres_dsn(readonly=False)
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute(f'DROP TABLE IF EXISTS "{clean_table}" CASCADE;')
                    create_sql = f'CREATE TABLE "{clean_table}" ({pg_col_defs_sql});'
                    cur.execute(create_sql)

                    # Grant SELECT to readonly user if different
                    try:
                        if settings.DB_READONLY_USER and settings.DB_READONLY_USER != settings.DB_USER:
                            cur.execute(f'GRANT SELECT ON TABLE "{clean_table}" TO "{settings.DB_READONLY_USER}";')
                    except Exception:
                        pass

                    # Batch insert
                    placeholders = ", ".join(["%s"] * len(clean_cols))
                    col_names_sql = ", ".join([f'"{c}"' for c in clean_cols])
                    insert_sql = f'INSERT INTO "{clean_table}" ({col_names_sql}) VALUES ({placeholders})'
                    if clean_records:
                        cur.executemany(insert_sql, clean_records)
                    conn.commit()
            pg_success = True
            # Also mirror into sample SQLite conn so source-switching maintains uploaded tables
            try:
                _ingest_into_sqlite(clean_table, clean_cols, sqlite_col_defs_sql, clean_records)
            except Exception as e_sq:
                logger.warning(f"Secondary SQLite mirror failed: {e_sq}")
        except Exception as pg_err:
            logger.warning(f"PostgreSQL ingestion failed: {pg_err}. Falling back to SQLite sample storage.")
            # Graceful fallback to SQLite
            _ingest_into_sqlite(clean_table, clean_cols, sqlite_col_defs_sql, clean_records)
    else:
        # Ingest into sample SQLite database
        _ingest_into_sqlite(clean_table, clean_cols, sqlite_col_defs_sql, clean_records)

    # Refresh schema cache
    db_manager.get_schema(force_refresh=True)

    # Invalidate query cache so new data is live
    from backend.modules.query_cache import query_cache
    query_cache.clear()

    return {
        "success": True,
        "table_name": clean_table,
        "rows_ingested": len(clean_records),
        "row_count": len(clean_records),
        "columns": clean_cols,
        "column_count": len(clean_cols),
        "message": f"Successfully created table '{clean_table}' with {len(clean_records)} records."
    }

def ingest_sql_script(sql_content: str) -> Dict[str, Any]:
    """
    Executes a SQL script containing CREATE TABLE and INSERT statements safely.
    """
    created_tables = []
    for match in re.finditer(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?([a-zA-Z0-9_]+)["`]?', sql_content, re.IGNORECASE):
        created_tables.append(match.group(1).lower())

    if db_manager.active_source == "postgresql":
        try:
            dsn = settings.get_postgres_dsn(readonly=False)
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql_content)
                    # Grant select on any created tables
                    for tbl in created_tables:
                        try:
                            if settings.DB_READONLY_USER and settings.DB_READONLY_USER != settings.DB_USER:
                                cur.execute(f'GRANT SELECT ON TABLE "{tbl}" TO "{settings.DB_READONLY_USER}";')
                        except Exception:
                            pass
                    conn.commit()
        except Exception as e:
            logger.warning(f"PostgreSQL script execution failed: {e}. Executing on SQLite.")
            conn = db_manager._sample_sqlite_conn
            if conn:
                conn.executescript(sql_content)
                conn.commit()
    else:
        conn = db_manager._sample_sqlite_conn
        if conn:
            conn.executescript(sql_content)
            conn.commit()

    db_manager.get_schema(force_refresh=True)
    from backend.modules.query_cache import query_cache
    query_cache.clear()

    return {
        "success": True,
        "tables_created": created_tables,
        "table_name": created_tables[0] if created_tables else "sql_dataset",
        "rows_ingested": 1,
        "row_count": 1,
        "columns": [],
        "column_count": 0,
        "message": f"Successfully executed SQL script. Tables created: {', '.join(created_tables) if created_tables else 'Complete'}."
    }

