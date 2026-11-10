from typing import Optional, List
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.modules.auth_manager import auth_manager
from backend.database.connection import db_manager
from backend.modules.semantic_memory import semantic_memory, VALID_PERSONAS
from backend.modules.governance import governance_manager

router = APIRouter(prefix="/api/governance", tags=["Governance & Semantic Memory"])


def _get_user_and_schema(authorization: Optional[str]):
    user = None
    if authorization and isinstance(authorization, str):
        token = authorization.replace("Bearer ", "").strip()
        user = auth_manager.get_user_by_token(token)
    full_schema = db_manager.get_schema()
    allowed = auth_manager.get_allowed_tables_for_user(user, list(full_schema.tables.keys()))
    scoped = full_schema.filter_by_tables(allowed)
    return user, scoped, allowed


class PersonaRequest(BaseModel):
    persona: str = Field(..., description="One of general, finance, marketing, operations, academic")


class GlossaryCreateRequest(BaseModel):
    term: str = Field(..., min_length=2)
    definition: str = Field(..., min_length=3)
    sql_expression: str = Field(..., min_length=2)
    category: str = "metric"
    auto_approve: bool = True


class GlossaryDecisionRequest(BaseModel):
    status: str = Field(..., description="approved or rejected")


class DualFeedbackRequest(BaseModel):
    session_id: Optional[str] = None
    query: Optional[str] = None
    feedback_result: Optional[int] = None
    feedback_question: Optional[int] = None


@router.get("/summary")
def get_governance_summary(authorization: Optional[str] = Header(None)):
    user, scoped, allowed = _get_user_and_schema(authorization)
    user_id = user["id"] if user else None

    memories = semantic_memory.get_user_memories(user_id, schema=scoped)
    glossary_approved = [g.model_dump() for g in semantic_memory.list_glossary(status="approved", allowed_tables=allowed)]
    glossary_pending = [g.model_dump() for g in semantic_memory.list_glossary(status="pending", allowed_tables=allowed)]
    persona = semantic_memory.get_persona(user_id)
    metrics = governance_manager.compute_quality_metrics(user_id=user_id)
    audit = governance_manager.get_audit_log(user_id=user_id, limit=25)

    return {
        "persona": persona,
        "available_personas": VALID_PERSONAS,
        "personal_memories": memories,
        "glossary_approved": glossary_approved,
        "glossary_pending": glossary_pending,
        "quality_metrics": metrics,
        "audit_log": audit
    }


@router.post("/persona")
def update_user_persona(req: PersonaRequest, authorization: Optional[str] = Header(None)):
    user, _, _ = _get_user_and_schema(authorization)
    user_id = user["id"] if user else None
    saved = semantic_memory.set_persona(user_id, req.persona)
    return {"success": True, "persona": saved, "details": VALID_PERSONAS.get(saved)}


@router.delete("/memory/{mem_id}")
def delete_personal_memory(mem_id: str, authorization: Optional[str] = Header(None)):
    user, _, _ = _get_user_and_schema(authorization)
    user_id = user["id"] if user else None
    ok = semantic_memory.delete_user_memory(user_id, mem_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory item not found.")
    return {"success": True}


@router.post("/glossary")
def add_or_propose_glossary_term(req: GlossaryCreateRequest, authorization: Optional[str] = Header(None)):
    user, _, _ = _get_user_and_schema(authorization)
    username = user["username"] if user else "user"
    term_obj = semantic_memory.propose_term(
        term=req.term,
        definition=req.definition,
        sql_expression=req.sql_expression,
        proposed_by=username,
        category=req.category,
        auto_approve=req.auto_approve
    )
    return {"success": True, "term": term_obj.model_dump()}


@router.post("/glossary/{term_id}/decision")
def decide_glossary_term(term_id: str, req: GlossaryDecisionRequest, authorization: Optional[str] = Header(None)):
    user, _, _ = _get_user_and_schema(authorization)
    reviewer = user["username"] if user else "admin"
    updated = semantic_memory.set_glossary_status(term_id, req.status, reviewer=reviewer)
    if not updated:
        raise HTTPException(status_code=404, detail="Glossary term not found or invalid status.")
    return {"success": True, "term": updated.model_dump()}


@router.post("/feedback")
def submit_dual_feedback(req: DualFeedbackRequest, authorization: Optional[str] = Header(None)):
    ok = governance_manager.record_feedback(
        session_id=req.session_id,
        query=req.query,
        feedback_result=req.feedback_result,
        feedback_question=req.feedback_question
    )
    return {"success": True, "audit_updated": ok}


@router.get("/metrics")
def get_clarification_quality_metrics(authorization: Optional[str] = Header(None)):
    user, _, _ = _get_user_and_schema(authorization)
    user_id = user["id"] if user else None
    return governance_manager.compute_quality_metrics(user_id=user_id)


@router.get("/audit")
def get_audit_entries(limit: int = 50, authorization: Optional[str] = Header(None)):
    user, _, _ = _get_user_and_schema(authorization)
    user_id = user["id"] if user else None
    return {"entries": governance_manager.get_audit_log(user_id=user_id, limit=limit)}

