from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from backend.database.connection import db_manager
from backend.database.schema_extractor import DatabaseSchema
from backend.modules.auth_manager import auth_manager
from backend.modules.relationship_manager import relationship_manager
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

class RelationshipCreateRequest(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    cardinality: str = "Many-to-One"
    cross_filter_direction: str = "Single"
    is_active: bool = True

class RelationshipUpdateRequest(BaseModel):
    source_table: Optional[str] = None
    source_column: Optional[str] = None
    target_table: Optional[str] = None
    target_column: Optional[str] = None
    cardinality: Optional[str] = None
    cross_filter_direction: Optional[str] = None
    is_active: Optional[bool] = None

class CardinalityInspectRequest(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str

class AutoDetectRequest(BaseModel):
    apply: bool = False
    candidates: Optional[List[RelationshipCreateRequest]] = None

class DiagramLayoutRequest(BaseModel):
    layouts: Dict[str, Dict[str, float]]

def _get_authenticated_user(authorization: Optional[str]):
    if not authorization or not isinstance(authorization, str):
        return None
    token = authorization.replace("Bearer ", "").strip()
    return auth_manager.get_user_by_token(token)

def _get_scoped_schema(authorization: Optional[str]):
    full_schema = db_manager.get_schema()
    user = _get_authenticated_user(authorization)
    user_id = user["id"] if user else None
    allowed = auth_manager.get_allowed_tables_for_user(user, list(full_schema.tables.keys()))
    scoped = full_schema.filter_by_tables(allowed)
    relationship_manager.apply_to_schema(scoped, user_id=user_id)
    return scoped, user

@router.get("", response_model=DatabaseSchema)
def get_current_schema(authorization: Optional[str] = Header(None)):
    """
    Returns current active database schema metadata scoped to the authenticated user's workspace,
    enriched with any manually configured table relationships.
    """
    scoped, _ = _get_scoped_schema(authorization)
    return scoped

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

def _clear_query_cache():
    try:
        from backend.modules.query_cache import query_cache
        query_cache.clear()
    except Exception:
        pass

@router.get("/relationships")
def get_schema_relationships(
    include_inactive: bool = True,
    authorization: Optional[str] = Header(None)
):
    """
    Returns all native + manually configured relationships and saved diagram positions
    scoped to the active user's workspace schema.
    """
    scoped, user = _get_scoped_schema(authorization)
    user_id = user["id"] if user else None
    layouts = relationship_manager.get_layouts(user_id=user_id, source_type=scoped.source_type)

    return {
        "database_name": scoped.database_name,
        "source_type": scoped.source_type,
        "relationships": scoped.get_all_relationships(include_inactive=include_inactive),
        "layouts": layouts
    }

@router.post("/relationships")
def create_schema_relationship(
    req: RelationshipCreateRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Manually creates a Power BI-style relationship between two workspace tables/columns.
    """
    full_schema = db_manager.get_schema()
    user = _get_authenticated_user(authorization)
    user_id = user["id"] if user else None
    allowed = auth_manager.get_allowed_tables_for_user(user, list(full_schema.tables.keys()))
    scoped = full_schema.filter_by_tables(allowed)
    relationship_manager.apply_to_schema(scoped, user_id=user_id)

    rel_obj, err = relationship_manager.create_relationship(
        schema=scoped,
        user_id=user_id,
        source_table=req.source_table,
        source_column=req.source_column,
        target_table=req.target_table,
        target_column=req.target_column,
        cardinality=req.cardinality,
        cross_filter_direction=req.cross_filter_direction,
        is_active=req.is_active
    )
    if err:
        raise HTTPException(status_code=400, detail=err)

    _clear_query_cache()
    # Re-apply so response reflects exact updated relationships
    updated_scoped, _ = _get_scoped_schema(authorization)
    return {
        "success": True,
        "relationship": rel_obj,
        "relationships": updated_scoped.get_all_relationships(include_inactive=True)
    }

@router.put("/relationships/{rel_id}")
def update_schema_relationship(
    rel_id: str,
    req: RelationshipUpdateRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Updates cardinality, cross-filter direction, active status, or columns of an existing relationship.
    """
    scoped, user = _get_scoped_schema(authorization)
    user_id = user["id"] if user else None

    updated, err = relationship_manager.update_relationship(
        schema=scoped,
        user_id=user_id,
        rel_id=rel_id,
        source_table=req.source_table,
        source_column=req.source_column,
        target_table=req.target_table,
        target_column=req.target_column,
        cardinality=req.cardinality,
        cross_filter_direction=req.cross_filter_direction,
        is_active=req.is_active
    )
    if err:
        raise HTTPException(status_code=400, detail=err)

    _clear_query_cache()
    updated_scoped, _ = _get_scoped_schema(authorization)
    return {
        "success": True,
        "relationship": updated,
        "relationships": updated_scoped.get_all_relationships(include_inactive=True)
    }

@router.delete("/relationships/{rel_id}")
def delete_schema_relationship(
    rel_id: str,
    authorization: Optional[str] = Header(None)
):
    """
    Deletes a manual relationship or hides/removes a native foreign key from the workspace model.
    """
    scoped, user = _get_scoped_schema(authorization)
    user_id = user["id"] if user else None

    deleted = relationship_manager.delete_relationship(
        user_id=user_id,
        source_type=scoped.source_type,
        rel_id=rel_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Relationship '{rel_id}' not found.")

    _clear_query_cache()
    updated_scoped, _ = _get_scoped_schema(authorization)
    return {
        "success": True,
        "relationships": updated_scoped.get_all_relationships(include_inactive=True)
    }

@router.post("/relationships/detect-cardinality")
def inspect_relationship_cardinality(
    req: CardinalityInspectRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Inspects key uniqueness and matching overlap between two columns to recommend cardinality.
    """
    scoped, _ = _get_scoped_schema(authorization)
    t_names_low = {k.lower(): k for k in scoped.tables.keys()}
    s_tbl = t_names_low.get(req.source_table.lower())
    t_tbl = t_names_low.get(req.target_table.lower())
    if not s_tbl or not t_tbl:
        raise HTTPException(status_code=404, detail="Source or target table not found in active workspace.")

    return relationship_manager.detect_cardinality_from_data(
        source_table=s_tbl,
        source_column=req.source_column,
        target_table=t_tbl,
        target_column=req.target_column,
        exec_fn=db_manager.execute_query
    )

@router.post("/relationships/auto-detect")
def auto_detect_schema_relationships(
    req: AutoDetectRequest = AutoDetectRequest(),
    authorization: Optional[str] = Header(None)
):
    """
    Smartly scans workspace tables for undetected relationships, and optionally applies them.
    """
    scoped, user = _get_scoped_schema(authorization)
    user_id = user["id"] if user else None

    if req.apply and req.candidates:
        applied = []
        for cand in req.candidates:
            rel_obj, err = relationship_manager.create_relationship(
                schema=scoped,
                user_id=user_id,
                source_table=cand.source_table,
                source_column=cand.source_column,
                target_table=cand.target_table,
                target_column=cand.target_column,
                cardinality=cand.cardinality,
                cross_filter_direction=cand.cross_filter_direction,
                is_active=cand.is_active
            )
            if rel_obj:
                applied.append(rel_obj)
        _clear_query_cache()
        updated_scoped, _ = _get_scoped_schema(authorization)
        return {
            "success": True,
            "applied_count": len(applied),
            "relationships": updated_scoped.get_all_relationships(include_inactive=True)
        }

    candidates = relationship_manager.auto_detect_candidates(
        schema=scoped,
        exec_fn=db_manager.execute_query
    )
    if req.apply and candidates:
        applied = []
        for c in candidates:
            rel_obj, _ = relationship_manager.create_relationship(
                schema=scoped,
                user_id=user_id,
                source_table=c["source_table"],
                source_column=c["source_column"],
                target_table=c["target_table"],
                target_column=c["target_column"],
                cardinality=c["cardinality"],
                cross_filter_direction=c.get("cross_filter_direction", "Single"),
                is_active=True
            )
            if rel_obj:
                applied.append(rel_obj)
        _clear_query_cache()
        updated_scoped, _ = _get_scoped_schema(authorization)
        return {
            "success": True,
            "applied_count": len(applied),
            "candidates": candidates,
            "relationships": updated_scoped.get_all_relationships(include_inactive=True)
        }

    return {
        "success": True,
        "candidates": candidates,
        "applied_count": 0
    }

@router.put("/diagram-layout")
def save_diagram_layout(
    req: DiagramLayoutRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Persists table card (x, y) positions for the Model View relationship diagram.
    """
    scoped, user = _get_scoped_schema(authorization)
    user_id = user["id"] if user else None
    saved = relationship_manager.save_layouts(
        user_id=user_id,
        source_type=scoped.source_type,
        layouts=req.layouts
    )
    return {"success": True, "layouts": saved}

@router.delete("/diagram-layout")
def reset_diagram_layout(authorization: Optional[str] = Header(None)):
    """
    Resets saved diagram node positions back to automatic arrangement.
    """
    scoped, user = _get_scoped_schema(authorization)
    user_id = user["id"] if user else None
    relationship_manager.reset_layouts(user_id=user_id, source_type=scoped.source_type)
    return {"success": True}


