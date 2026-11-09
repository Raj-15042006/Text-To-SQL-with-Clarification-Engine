"""
Router for Model Training, Continuous Learning, and NLP Status
Provides endpoints to inspect training metrics, trigger local training,
submit feedback to teach the model, and switch providers.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.modules.learning_engine import learning_engine, ModelStatus, TrainingSample
from backend.llm.factory import set_active_provider, get_active_provider_name

router = APIRouter(prefix="/api/model", tags=["Model Training & Learning"])


class FeedbackRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The user question that was answered")
    sql: str = Field(..., min_length=1, description="The generated SQL statement")
    feedback: int = Field(1, description="1 for thumbs up (positive), -1 for thumbs down (negative)")
    corrected_sql: Optional[str] = Field(None, description="Optional user-corrected SQL query")
    tables_used: List[str] = Field(default_factory=list, description="Tables used in the query")


class SwitchProviderRequest(BaseModel):
    provider: str = Field(..., description="'local' for offline self-learning NLP, or 'gemini' for cloud LLM")


@router.get("/status", response_model=ModelStatus)
def get_model_status():
    """Returns training metrics, accuracy, sample count, and active provider."""
    active = get_active_provider_name()
    return learning_engine.get_status(active_provider=active)


@router.post("/train")
def train_model():
    """Triggers local model training and updates model checkpoints."""
    result = learning_engine.retrain()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Training failed."))
    return result


@router.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    """
    Submits user feedback or corrected SQL.
    Records sample in persistent memory and incrementally improves the model.
    """
    sample = learning_engine.record_interaction(
        query=req.query,
        sql=req.sql,
        tables_used=req.tables_used,
        success=(req.feedback > 0),
        feedback=req.feedback,
        corrected_sql=req.corrected_sql
    )
    return {
        "success": True,
        "message": "Feedback recorded. Model updated successfully.",
        "sample_id": sample.id,
        "total_samples": len(learning_engine.memory)
    }


@router.post("/switch-provider")
def switch_provider(req: SwitchProviderRequest):
    """Toggles active provider between 'local' (offline self-learning NLP) and 'gemini'."""
    p = req.provider.lower().strip()
    if p not in ("local", "gemini", "self_learning"):
        raise HTTPException(status_code=400, detail="Provider must be 'local' or 'gemini'.")
    new_provider = set_active_provider(p)
    return {
        "success": True,
        "active_provider": new_provider,
        "message": f"Active provider switched to '{new_provider}'."
    }


@router.get("/samples", response_model=List[TrainingSample])
def list_training_samples(limit: int = 50):
    """Returns recently learned query-to-SQL training samples."""
    return list(reversed(learning_engine.memory))[:limit]

