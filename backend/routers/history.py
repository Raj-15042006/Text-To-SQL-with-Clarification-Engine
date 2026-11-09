from typing import List
from fastapi import APIRouter
from backend.modules.clarification import clarification_engine, QuerySession

router = APIRouter(prefix="/api/history", tags=["History"])

@router.get("", response_model=List[QuerySession])
def get_query_history(limit: int = 25):
    """
    Returns recent query sessions with their status, SQL, and outcomes.
    """
    return clarification_engine.list_sessions(limit=limit)
