import uuid
import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from backend.modules.ambiguity import QueryAnalysis, ClarificationRequest
from backend.modules.validator import ValidationResult
from backend.database.connection import ExecutionResult

class ClarificationTurn(BaseModel):
    turn_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str
    selected_option_id: Optional[str] = None
    selected_option_label: Optional[str] = None
    custom_response: Optional[str] = None
    applied_constraint: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())

class QuerySession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: Optional[str] = None
    original_query: str
    status: str = "initialized"  # "analyzing", "awaiting_clarification", "generating", "ready", "executed", "error", "schema_gap", "no_dataset"
    analysis: Optional[QueryAnalysis] = None
    clarifications: List[ClarificationTurn] = Field(default_factory=list)
    resolved_query: Optional[str] = None
    generated_sql: Optional[str] = None
    sql_explanation: Optional[str] = None
    validation: Optional[ValidationResult] = None
    execution: Optional[ExecutionResult] = None
    natural_explanation: Optional[str] = None
    relationships_used: List[str] = Field(default_factory=list)
    is_ambiguous: Optional[bool] = None
    ambiguity_category: Optional[str] = None
    ambiguity_score: float = 0.0
    thinking_steps: List[Dict[str, str]] = Field(default_factory=list)
    assumptions: List[Dict[str, Any]] = Field(default_factory=list)
    provenance: List[Dict[str, str]] = Field(default_factory=list)
    confidence_score: int = 90
    confidence_level: str = "High"
    confidence_reasons: List[str] = Field(default_factory=list)
    data_quality_warnings: List[str] = Field(default_factory=list)
    pii_columns: List[str] = Field(default_factory=list)
    pii_warning: Optional[str] = None
    cost_info: Optional[Dict[str, Any]] = None
    ask_after_answer: Optional[Dict[str, Any]] = None
    schema_gap: Optional[Dict[str, Any]] = None
    tables_used: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())

    model_config = {"extra": "allow"}

class ClarificationEngine:
    """
    Coordinates session state, query rewriting, and clarification progression.
    """
    def __init__(self):
        self._sessions: Dict[str, QuerySession] = {}

    @property
    def sessions(self) -> Dict[str, QuerySession]:
        return self._sessions

    def create_session(self, user_query: str) -> QuerySession:
        session = QuerySession(
            original_query=user_query.strip(),
            status="analyzing"
        )
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[QuerySession]:
        return self._sessions.get(session_id)

    def list_sessions(self, limit: int = 20) -> List[QuerySession]:
        all_sessions = list(self._sessions.values())
        all_sessions.sort(key=lambda s: s.created_at, reverse=True)
        return all_sessions[:limit]

    def rewrite_query(
        self, 
        original_query: str, 
        clarifications: List[ClarificationTurn]
    ) -> str:
        """
        Combines original natural query and answered clarifications into a 
        concise, unambiguous resolved query string.
        """
        if not clarifications:
            return original_query

        clarification_clauses = []
        for turn in clarifications:
            answer = turn.selected_option_label or turn.custom_response or ""
            if turn.applied_constraint:
                clarification_clauses.append(f"{answer} ({turn.applied_constraint})")
            elif answer:
                clarification_clauses.append(answer)

        merged_answers = "; ".join(clarification_clauses)
        return f"{original_query} [Specified details: {merged_answers}]"

    def apply_clarification(
        self,
        session: QuerySession,
        option_id: Optional[str] = None,
        custom_text: Optional[str] = None
    ) -> QuerySession:
        """
        Records the user's clarification answer and rewrites the resolved query.
        """
        question = ""
        option_label = None
        applied_constraint = None

        if session.analysis and session.analysis.clarification:
            question = session.analysis.clarification.question
            if option_id:
                for opt in session.analysis.clarification.options:
                    if opt.id == option_id:
                        option_label = opt.label
                        applied_constraint = opt.implied_filter_or_metric
                        break

        turn = ClarificationTurn(
            question=question,
            selected_option_id=option_id,
            selected_option_label=option_label,
            custom_response=custom_text,
            applied_constraint=applied_constraint
        )
        session.clarifications.append(turn)
        session.resolved_query = self.rewrite_query(session.original_query, session.clarifications)
        session.status = "generating"
        session.updated_at = datetime.datetime.now().isoformat()
        return session

clarification_engine = ClarificationEngine()
