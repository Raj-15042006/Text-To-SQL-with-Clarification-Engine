from typing import Optional, List
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from backend.database.connection import db_manager
from backend.database.schema_extractor import DatabaseSchema
from backend.modules.auth_manager import auth_manager
from backend.config import settings

router = APIRouter(prefix="/api/schema", tags=["Schema"])

class ConnectionTestRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    dbname: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None

class ConnectionTestResponse(BaseModel):
    success: bool
    message: str

class SwitchSourceRequest(BaseModel):
    source: str = Field(..., description="'sample' or 'postgresql'")
    host: Optional[str] = None
    port: Optional[int] = None
    dbname: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None

def _get_authenticated_user(authorization: Optional[str]):
    if not authorization or not isinstance(authorization, str):
        return None
    token = authorization.replace("Bearer ", "").strip()
    return auth_manager.get_user_by_token(token)

@router.get("", response_model=DatabaseSchema)
def get_current_schema(authorization: Optional[str] = Header(None)):
    """
    Returns current active database schema metadata scoped to the authenticated user's workspace.
    - Default account 'raj': full access to demo and sample datasets.
    - New accounts: strictly start with 0 datasets until files are uploaded.
    - Unauthenticated: 0 datasets.
    """
    full_schema = db_manager.get_schema()
    user = _get_authenticated_user(authorization)
    allowed = auth_manager.get_allowed_tables_for_user(user, list(full_schema.tables.keys()))
    return full_schema.filter_by_tables(allowed)

@router.post("/test-connection", response_model=ConnectionTestResponse)
def test_connection(req: ConnectionTestRequest):
    """
    Tests live connection to a local or remote PostgreSQL instance without saving.
    """
    success, msg = db_manager.test_postgres_connection(
        host=req.host,
        port=req.port,
        dbname=req.dbname,
        user=req.user,
        password=req.password
    )
    return ConnectionTestResponse(success=success, message=msg)

@router.post("/switch-source")
def switch_data_source(req: SwitchSourceRequest):
    """
    Switches between the built-in sample database and the live PostgreSQL database.
    """
    success, msg = db_manager.set_data_source(
        source=req.source,
        host=req.host,
        port=req.port,
        dbname=req.dbname,
        user=req.user,
        password=req.password
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    from backend.modules.query_cache import query_cache
    query_cache.clear()
    return {
        "success": True,
        "active_source": db_manager.active_source,
        "message": msg
    }

@router.get("/table/{table_name}/data")
def get_table_data(table_name: str, limit: int = 50, authorization: Optional[str] = Header(None)):
    """
    Directly retrieves row preview for any existing table allowed in the user's workspace.
    """
    user = _get_authenticated_user(authorization)
    full_schema = db_manager.get_schema()
    allowed_tables = [t.lower() for t in auth_manager.get_allowed_tables_for_user(user, list(full_schema.tables.keys()))]

    if table_name.lower() not in allowed_tables:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found in your workspace.")

    res = db_manager.execute_query(f'SELECT * FROM "{table_name}" LIMIT {min(limit, 100)}')
    return res

@router.get("/relationships")
def get_schema_relationships(authorization: Optional[str] = Header(None)):
    """
    Returns foreign key relationships scoped to the active user's workspace schema.
    """
    full_schema = db_manager.get_schema()
    user = _get_authenticated_user(authorization)
    allowed = auth_manager.get_allowed_tables_for_user(user, list(full_schema.tables.keys()))
    scoped = full_schema.filter_by_tables(allowed)

    return {
        "database_name": scoped.database_name,
        "relationships": scoped.get_all_relationships()
    }

