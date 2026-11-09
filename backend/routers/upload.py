import io
import re
import os
import json
import datetime
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException
from typing import Optional

import pandas as pd
from backend.database.file_ingestion import ingest_dataframe, ingest_sql_script, sanitize_identifier
from backend.database.connection import db_manager
from backend.modules.auth_manager import auth_manager
from backend.config import settings
import psycopg

router = APIRouter(prefix="/api/upload", tags=["Upload"])

@router.post("")
async def upload_data_file(
    file: UploadFile = File(...),
    custom_table_name: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None)
):
    """
    Directly converts uploaded files (.csv, .xlsx, .xls, .sql, .json) into live database tables.
    Automatically infers schema types and loads all records into the active database.
    Saves and associates the uploaded dataset with the active user account.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    # Identify user
    user = None
    if authorization and isinstance(authorization, str):
        token = authorization.replace("Bearer ", "").strip()
        user = auth_manager.get_user_by_token(token)
    if not user:
        all_u = auth_manager.list_all_users()
        user = all_u[0] if all_u else None
    user_id = user["id"] if user else None

    filename = file.filename
    ext = Path(filename).suffix.lower()
    base_name = custom_table_name or Path(filename).stem
    table_name = sanitize_identifier(base_name)

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    try:
        if ext in (".csv", ".tsv", ".txt"):
            df = None
            last_err = None
            for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
                try:
                    df = pd.read_csv(io.BytesIO(contents), encoding=enc)
                    # If only 1 column was detected, it might be semicolon or tab delimited
                    if df is not None and len(df.columns) <= 1:
                        try:
                            df_alt = pd.read_csv(io.BytesIO(contents), encoding=enc, sep=None, engine='python')
                            if df_alt is not None and len(df_alt.columns) > len(df.columns):
                                df = df_alt
                        except Exception:
                            pass
                    break
                except Exception as e:
                    last_err = e
                    try:
                        df = pd.read_csv(io.BytesIO(contents), encoding=enc, sep=None, engine='python')
                        break
                    except Exception as e2:
                        last_err = e2
                        continue
            if df is None:
                raise ValueError(f"Could not parse CSV/TSV file: {last_err}")
            result = ingest_dataframe(df, table_name)

        elif ext in (".xlsx", ".xls"):
            try:
                df = pd.read_excel(io.BytesIO(contents))
            except Exception:
                df = pd.read_excel(io.BytesIO(contents), engine="openpyxl")
            result = ingest_dataframe(df, table_name)

        elif ext == ".json":
            # Smart JSON ingestion: handles list of dicts, nested dicts with data/records key, or ndjson
            text_str = contents.decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text_str)
                if isinstance(parsed, list):
                    df = pd.DataFrame(parsed)
                elif isinstance(parsed, dict):
                    extracted = False
                    for key in ("data", "records", "items", "rows", "results", "players", "transactions", "users", "sales"):
                        if key in parsed and isinstance(parsed[key], list):
                            df = pd.DataFrame(parsed[key])
                            extracted = True
                            break
                    if not extracted:
                        df = pd.json_normalize(parsed)
                else:
                    df = pd.read_json(io.StringIO(text_str))
            except Exception:
                df = pd.read_json(io.StringIO(text_str), lines=True)

            result = ingest_dataframe(df, table_name)

        elif ext == ".sql":
            sql_text = contents.decode("utf-8", errors="replace")
            result = ingest_sql_script(sql_text)

        elif ext == ".parquet":
            df = pd.read_parquet(io.BytesIO(contents))
            result = ingest_dataframe(df, table_name)

        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file format '{ext}'. Supported formats: .csv, .tsv, .xlsx, .xls, .sql, .json, .parquet"
            )

        # Record dataset association to user account
        if result.get("success") and user_id:
            row_count = result.get("row_count") or result.get("rows_ingested", 0)
            col_list = result.get("columns", [])
            table_info = {
                "table_name": result.get("table_name", table_name),
                "filename": filename,
                "row_count": row_count,
                "column_count": len(col_list),
                "columns": col_list,
                "uploaded_at": datetime.datetime.now().isoformat(),
                "user_id": user_id
            }
            auth_manager.record_uploaded_table(user_id, table_info)
            result["account_saved"] = True
            result["user_id"] = user_id
            result["row_count"] = row_count
            result["column_count"] = len(col_list)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file '{filename}': {str(e)}")

@router.delete("/{table_name}")
async def delete_uploaded_table(
    table_name: str,
    authorization: Optional[str] = Header(None)
):
    """
    Drops an uploaded table from the active database and removes it from user records.
    """
    clean_table = sanitize_identifier(table_name)
    user = None
    if authorization and isinstance(authorization, str):
        token = authorization.replace("Bearer ", "").strip()
        user = auth_manager.get_user_by_token(token)
    if not user:
        all_u = auth_manager.list_all_users()
        user = all_u[0] if all_u else None
    user_id = user["id"] if user else None

    # Drop table from active database and local SQLite
    try:
        if db_manager.active_source == "postgresql":
            try:
                dsn = settings.get_postgres_dsn(readonly=False)
                with psycopg.connect(dsn, connect_timeout=5) as conn:
                    with conn.cursor() as cur:
                        cur.execute(f'DROP TABLE IF EXISTS "{clean_table}" CASCADE;')
                        conn.commit()
            except Exception:
                pass

        # Also remove from SQLite cache
        if db_manager._sample_sqlite_conn:
            try:
                cur = db_manager._sample_sqlite_conn.cursor()
                cur.execute(f'DROP TABLE IF EXISTS "{clean_table}";')
                db_manager._sample_sqlite_conn.commit()
            except Exception:
                pass

        # Refresh schema
        db_manager.get_schema(force_refresh=True)

        # Remove from user account records
        if user_id:
            auth_manager.remove_uploaded_table(user_id, clean_table)

        from backend.modules.query_cache import query_cache
        query_cache.clear()

        return {"success": True, "message": f"Table '{clean_table}' dropped successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete table '{clean_table}': {str(e)}")
