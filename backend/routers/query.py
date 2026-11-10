import logging
import re
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from backend.database.connection import db_manager, ExecutionResult
from backend.database.schema_extractor import DatabaseSchema
from backend.llm.factory import get_llm_provider
from backend.modules.clarification import clarification_engine, QuerySession
from backend.modules.ambiguity import ambiguity_detector, AmbiguityDetectionResult, AmbiguityCategory, ClarificationRequest, ClarificationOption
from backend.modules.validator import SQLValidator, ValidationResult
from backend.modules.query_cache import query_cache
from backend.modules.learning_engine import learning_engine
from backend.modules.conversation_manager import conversation_manager, ChatMessage
from backend.modules.auth_manager import auth_manager
from backend.modules.relationship_manager import relationship_manager
from backend.modules.semantic_memory import semantic_memory
from backend.modules.governance import governance_manager
from backend.modules.clarification_intelligence import clarification_intelligence
from backend.modules.nlp_engine import local_nlp_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/query", tags=["Query"])

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language query from user")
    conversation_id: Optional[str] = Field(None, description="Optional active conversation thread ID")
    answer_mode: str = Field("smart", description="Disambiguation mode: smart | strict | fast_best_guess")
    mask_pii: bool = Field(False, description="Whether to mask detected PII columns in output")

class ClarificationSubmitRequest(BaseModel):
    option_id: Optional[str] = None
    custom_text: Optional[str] = None
    question_useful: Optional[bool] = None

class DirectExecuteRequest(BaseModel):
    sql: str = Field(..., min_length=1, description="SQL query to validate and execute")


@router.post("/detect-ambiguity", response_model=AmbiguityDetectionResult)
def detect_query_ambiguity(req: QueryRequest):
    """
    Direct ambiguity inspection endpoint. Evaluates a natural language query against
    the active database schema and identifies:
      - Missing filters.
      - Unclear comparison criteria.
      - Ambiguous column names.
      - Unspecified date ranges.
      - Unclear aggregation functions.
      - Ambiguous table relationships.
      - Unspecified sorting and grouping.
    """
    clean_query = req.query.strip()
    if not clean_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    schema = db_manager.get_schema()
    return ambiguity_detector.detect(clean_query, schema=schema)


def _populate_relationships_and_explain(
    session: QuerySession,
    query_text: str,
    sql: str,
    validation: ValidationResult,
    exec_res: ExecutionResult,
    schema: DatabaseSchema,
    llm,
    history: Optional[List[dict]] = None
):
    """
    Safely extracts relational join paths from AST and schema foreign keys,
    populates session.relationships_used, and generates executive-grade natural explanation.
    """
    # 1. Joins from AST
    ast_joins = validation.relationships_used or []

    # 2. Schema foreign keys connecting or involving referenced tables
    rel_records = schema.get_relationships_between(validation.tables_referenced)
    schema_rels = [
        r.get("display") or r.get("description") or f"{r['source_table']} -> {r['target_table']}"
        for r in rel_records
    ]

    # 3. Check if user asked about relationships in general or between tables
    is_rel_query = any(w in query_text.lower() for w in [
        "relationship", "foreign key", "relate", "how are tables connected", 
        "table relation", "joins", "what tables are linked"
    ])
    
    if is_rel_query:
        all_schema_rels = [r["display"] for r in schema.get_all_relationships()]
        combined_rels = list(dict.fromkeys(ast_joins + schema_rels + all_schema_rels))
    else:
        combined_rels = list(dict.fromkeys(ast_joins + schema_rels))

    session.relationships_used = combined_rels

    # 4. Relational context for LLM: pass ONLY if user asked about relationships/joins
    rel_context_str = None
    if is_rel_query:
        if combined_rels:
            rel_context_str = "Foreign Key Relationships:\n" + "\n".join([f"- {r}" for r in combined_rels])
        rel_context_str = (rel_context_str or "") + "\n\nAll Database Schema Foreign Keys:\n" + schema.describe_all_relationships()

    # 5. Generate executive-grade natural explanation with conversational continuation
    try:
        session.natural_explanation = llm.explain_results(
            user_query=query_text,
            sql=sql,
            columns=exec_res.columns,
            sample_rows=exec_res.rows,
            total_rows=exec_res.row_count,
            relationships_context=rel_context_str,
            history=history
        )
    except Exception as exp_err:
        logger.warning(f"Could not generate LLM explanation: {exp_err}")
        session.natural_explanation = (
            f"**Key Findings**: The query successfully retrieved {exec_res.row_count} records.\n\n"
            f"**Database Relationships Used**: {', '.join(combined_rels) if combined_rels else 'Single table query (no joins required)'}."
        )


def _finalize_executed_session(
    session: QuerySession,
    query_text: str,
    sql: str,
    validation: Optional[ValidationResult],
    exec_res: ExecutionResult,
    schema: DatabaseSchema,
    llm,
    history: Optional[List[dict]] = None,
    user_id: Optional[str] = None,
    ambiguity_score: float = 0.0,
    applied_memory_note: Optional[str] = None,
    ask_after_assumption: Optional[Dict[str, Any]] = None,
    was_clarified: bool = False,
    clarification_asked: bool = False,
    clarification_changed_sql: bool = False,
    resolution_turns: int = 1,
    mask_pii: bool = False,
    skip_explain: bool = False
) -> None:
    """
    Runs Section 4/5/6/7 post-execution enrichment: explanation, cost guardrail,
    data-quality NULL scan, PII detection/masking, assumptions, provenance,
    confidence reasons, thinking trace, and immutable audit logging.
    """
    tables_used = (validation.tables_referenced if validation else None) or []

    # 1. Inspect & optionally mask PII BEFORE generating narrative or storing sample rows
    pii_res = governance_manager.inspect_and_mask_pii(
        columns=exec_res.columns,
        rows=exec_res.rows,
        mask_enabled=mask_pii
    )
    session.pii_columns = pii_res["pii_columns"]
    session.pii_warning = pii_res["warning"]
    if mask_pii and pii_res["pii_columns"]:
        exec_res.rows = pii_res["rows"]

    if not skip_explain and validation is not None:
        _populate_relationships_and_explain(
            session=session,
            query_text=query_text,
            sql=sql,
            validation=validation,
            exec_res=exec_res,
            schema=schema,
            llm=llm,
            history=history
        )

    # 2. Cost Guardrail & Data Quality Checks
    session.cost_info = governance_manager.estimate_query_cost(sql, tables_used, db_manager)
    session.data_quality_warnings = governance_manager.check_data_quality(
        tables_referenced=tables_used,
        columns_referenced=exec_res.columns,
        schema=schema,
        db_mgr=db_manager
    )

    # 3. Schema scoring & ML intent metadata
    table_scores: Dict[str, int] = {}
    matched_col_names: List[str] = []
    if schema and schema.tables:
        try:
            m_cols, t_scores, _ = local_nlp_engine._match_columns_and_tables(
                query_text.lower(),
                local_nlp_engine.tokenize(query_text),
                schema,
                local_nlp_engine.STOPWORDS
            )
            table_scores = t_scores
            matched_col_names = [f"{m['table']}.{m['column']}" for m in m_cols]
        except Exception:
            pass

    intent_label = "QUERY_EXECUTION"
    ml_confidence = 0.78
    try:
        intent_label, ml_confidence = learning_engine.predict_intent(query_text)
    except Exception:
        pass

    is_formula = bool(local_nlp_engine.parse_formula(query_text))

    # 4. Transparency: Assumptions, Provenance, Confidence Reasons, Thinking Steps
    session.ambiguity_score = round(ambiguity_score, 2)
    session.tables_used = tables_used
    session.ask_after_answer = ask_after_assumption
    session.assumptions = clarification_intelligence.build_assumptions(
        query=query_text,
        sql=sql,
        tables_used=tables_used,
        schema=schema,
        applied_memory_note=applied_memory_note,
        ask_after_assumption=ask_after_assumption
    )
    session.provenance = clarification_intelligence.build_provenance(query_text, sql)

    conf = clarification_intelligence.compute_confidence(
        ml_confidence=ml_confidence,
        ambiguity_score=ambiguity_score,
        validation_ok=bool(validation.is_valid) if validation else True,
        exec_ok=exec_res.success,
        row_count=exec_res.row_count,
        matched_cols_count=len(matched_col_names) if matched_col_names else len(exec_res.columns),
        is_formula=is_formula,
        was_clarified=was_clarified
    )
    session.confidence_score = conf["confidence_score"]
    session.confidence_level = conf["confidence_level"]
    session.confidence_reasons = conf["confidence_reasons"]

    session.thinking_steps = clarification_intelligence.build_thinking_steps(
        query=query_text,
        intent_label=intent_label,
        ml_confidence=ml_confidence,
        schema=schema,
        tables_used=tables_used,
        sql=sql,
        exec_ok=exec_res.success,
        row_count=exec_res.row_count,
        exec_ms=exec_res.execution_time_ms,
        relationships_used=session.relationships_used,
        ambiguity_score=ambiguity_score,
        table_scores=table_scores,
        matched_cols=matched_col_names,
        cost_level=(session.cost_info or {}).get("cost_level", "Low")
    )

    # 5. Immutable Read-Only Governance Audit Log
    try:
        governance_manager.log_query_event(
            user_id=user_id,
            session_id=session.session_id,
            query=session.original_query,
            ambiguity_score=ambiguity_score,
            clarification_asked=clarification_asked,
            clarification_changed_sql=clarification_changed_sql,
            resolution_turns=resolution_turns,
            generated_sql=sql,
            tables_used=tables_used,
            cost_level=(session.cost_info or {}).get("cost_level", "Low"),
            pii_columns=session.pii_columns,
            success=exec_res.success,
            execution_time_ms=exec_res.execution_time_ms
        )
    except Exception as audit_err:
        logger.warning(f"Audit log warning: {audit_err}")


def _build_assistant_chat_message(
    session: QuerySession,
    sql: str,
    sql_explanation: str,
    exec_res: ExecutionResult,
    status: str = "success"
) -> ChatMessage:
    return ChatMessage(
        role="assistant",
        content=session.natural_explanation or "",
        sql=sql,
        sql_explanation=sql_explanation,
        columns=exec_res.columns,
        rows=exec_res.rows[:5],
        row_count=exec_res.row_count,
        execution_time_ms=exec_res.execution_time_ms,
        relationships=session.relationships_used,
        thinking_steps=session.thinking_steps,
        assumptions=session.assumptions,
        provenance=session.provenance,
        confidence_score=session.confidence_score,
        confidence_level=session.confidence_level,
        confidence_reasons=session.confidence_reasons,
        data_quality_warnings=session.data_quality_warnings,
        pii_warning=session.pii_warning,
        cost_info=session.cost_info,
        ask_after_answer=session.ask_after_answer,
        status=status,
        session_id=session.session_id
    )

@router.post("", response_model=QuerySession)
def submit_query(req: QueryRequest, authorization: Optional[str] = Header(None)):
    """
    Submits a natural language database question.
    1. Attaches or initializes persistent conversation thread for context continuation.
    2. Checks high-speed query cache for standalone/repeated queries (<5ms response).
    3. Single-pass LLM call analyzes ambiguity and generates SQL simultaneously.
    4. If ambiguous -> returns clarification questions with options.
    5. If unambiguous -> validates with SQLGlot, executes read-only, and generates concise explanation.
    6. Saves full conversation messages with row data persistently.
    """
    clean_query = req.query.strip()
    if not clean_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # Identify authenticated user
    user = None
    if authorization and isinstance(authorization, str):
        token = authorization.replace("Bearer ", "").strip()
        user = auth_manager.get_user_by_token(token)
    user_id = user["id"] if user else None

    # Resolve active workspace schema for authenticated user
    full_schema = db_manager.get_schema()
    allowed_tables = auth_manager.get_allowed_tables_for_user(user, list(full_schema.tables.keys()))
    schema = full_schema.filter_by_tables(allowed_tables)
    relationship_manager.apply_to_schema(schema, user_id=user["id"] if user else None)

    # 1. Retrieve or create persistent conversation thread
    conv = conversation_manager.get_or_create(req.conversation_id, first_query=clean_query, user_id=user_id)
    
    # Context continuation: grab previous turns BEFORE this new user query
    history = conversation_manager.get_history_for_llm(conv.id)

    persona = semantic_memory.get_persona(user_id)
    catalog_key = f"{db_manager.active_source}_{user_id or 'anon'}_{persona}"
    session = clarification_engine.create_session(clean_query)
    session.conversation_id = conv.id
    session._mask_pii = req.mask_pii
    session._answer_mode = req.answer_mode

    # Append user question to conversation
    user_msg = ChatMessage(
        role="user",
        content=clean_query,
        session_id=session.session_id
    )
    conversation_manager.add_message(conv.id, user_msg)

    # Check if query is a standalone mathematical or domain formula
    is_standalone_formula = bool(local_nlp_engine.parse_formula(clean_query))

    # Tenancy check: If workspace has 0 datasets and this is NOT a formula, guide the user
    if not schema.tables and not is_standalone_formula:
        session.status = "no_dataset"
        session.natural_explanation = (
            "No database tables found in your workspace. "
            "Please upload a dataset (CSV, Excel, or JSON) using the **Upload Data** button above to begin querying your data."
        )
        conversation_manager.add_message(
            conv.id,
            ChatMessage(
                role="assistant",
                content=session.natural_explanation,
                status="no_dataset",
                session_id=session.session_id
            )
        )
        return session

    # Detect if query relies on previous context / follow-ups
    followup_pronouns = {
        "it", "they", "them", "that", "this", "which", "who", "highest", "lowest",
        "second", "top", "more", "now", "also", "formula", "why", "previous", "again",
        "his", "her", "their", "its", "whose", "those", "ones", "he", "she", "him"
    }
    query_words = set(clean_query.lower().split())
    is_context_dependent = bool(history and (query_words & followup_pronouns))
    active_dialect = "sqlite" if db_manager.active_source == "sample" else "postgres"
    known_tables = schema.get_known_tables_dict()

    # Fast-path 1: Query Cache Hit (<5ms response for standalone / repeated queries)
    if not is_context_dependent and req.answer_mode != "strict":
        cached = query_cache.get(clean_query, catalog=catalog_key)
        if cached and cached.get("generated_sql"):
            cached_sql = cached["generated_sql"]
            exec_res = db_manager.execute_query(cached_sql)
            if exec_res.success:
                session.resolved_query = clean_query
                session.generated_sql = cached_sql
                session.sql_explanation = cached.get("sql_explanation") or "Retrieved via high-speed query accelerator."
                session.execution = exec_res
                session.relationships_used = cached.get("relationships_used") or []
                session.status = "executed"

                # Instant explanation formatting
                if exec_res.row_count == 0:
                    session.natural_explanation = "No matching records were found in the active database."
                elif len(exec_res.rows) == 1 and len(exec_res.columns) == 1:
                    col = exec_res.columns[0]
                    val = exec_res.rows[0].get(col)
                    col_disp = col.replace("_", " ").title()
                    val_fmt = f"{val:,.2f}" if isinstance(val, float) else f"{val:,}" if isinstance(val, int) else str(val)
                    session.natural_explanation = f"The calculated **{col_disp}** is **{val_fmt}**."
                else:
                    session.natural_explanation = cached.get("natural_explanation") or f"The query returned {exec_res.row_count} matching records."

                cache_val = SQLValidator.validate(cached_sql, known_tables=known_tables, dialect=active_dialect)
                session.validation = cache_val
                _finalize_executed_session(
                    session=session,
                    query_text=clean_query,
                    sql=cached_sql,
                    validation=cache_val if cache_val.is_valid else None,
                    exec_res=exec_res,
                    schema=schema,
                    llm=None,
                    history=history,
                    user_id=user_id,
                    ambiguity_score=0.05,
                    applied_memory_note=cached.get("applied_memory_note"),
                    mask_pii=req.mask_pii,
                    skip_explain=True
                )

                conversation_manager.add_message(
                    conv.id,
                    _build_assistant_chat_message(
                        session=session,
                        sql=cached_sql,
                        sql_explanation=session.sql_explanation,
                        exec_res=exec_res,
                        status="success"
                    )
                )
                return session

    schema_ctx = schema.to_compact_llm_context()
    llm = get_llm_provider()

    # Section 3 & 8 Pre-Checks: Approved Team Glossary, Clarification Replay, Example-Based Calibration
    glossary_hits = semantic_memory.match_approved_glossary(clean_query, allowed_tables=allowed_tables)
    replay_hit = (
        semantic_memory.find_replay(clean_query, allowed_tables=allowed_tables)
        if (user_id and not is_context_dependent and req.answer_mode != "strict")
        else None
    )
    calib = (
        clarification_intelligence.detect_and_calibrate_expected_value(clean_query, schema, db_manager)
        if (not is_standalone_formula and schema.tables)
        else None
    )

    # Section 5: Schema-Gap Detection (Never hallucinate missing schema columns/tables)
    if (
        not is_standalone_formula
        and not is_context_dependent
        and not glossary_hits
        and not replay_hit
        and not calib
        and schema.tables
    ):
        try:
            _, tbl_scores, _ = local_nlp_engine._match_columns_and_tables(
                clean_query.lower(),
                local_nlp_engine.tokenize(clean_query),
                schema,
                local_nlp_engine.STOPWORDS
            )
            gap = clarification_intelligence.detect_schema_gap(
                clean_query, schema, tbl_scores, has_history=bool(history)
            )
            if gap.has_gap:
                session.status = "schema_gap"
                session.schema_gap = gap.model_dump()
                session.natural_explanation = gap.message
                session.confidence_score = 18
                session.confidence_level = "Low"
                session.confidence_reasons = [
                    "- Requested entities/columns are not present in your authorized active schema"
                ]
                session.thinking_steps = clarification_intelligence.build_thinking_steps(
                    query=clean_query,
                    intent_label="SCHEMA_GAP_GUARD",
                    ml_confidence=0.90,
                    schema=schema,
                    tables_used=[],
                    sql="",
                    exec_ok=False,
                    row_count=0,
                    exec_ms=0.0,
                    relationships_used=[],
                    ambiguity_score=0.0,
                    table_scores=tbl_scores,
                    matched_cols=[]
                )
                conversation_manager.add_message(
                    conv.id,
                    ChatMessage(
                        role="assistant",
                        content=gap.message or "Requested fields do not exist in the connected tables.",
                        confidence_score=18,
                        confidence_level="Low",
                        confidence_reasons=session.confidence_reasons,
                        thinking_steps=session.thinking_steps,
                        status="schema_gap",
                        session_id=session.session_id
                    )
                )
                return session
        except Exception as gap_err:
            logger.debug(f"Schema gap check skipped: {gap_err}")

    # 2. Ambiguity Analysis, Scoring, Execution Divergence, Personal Memory & Ask-After-Answer
    det_res = ambiguity_detector.detect(clean_query, schema=schema, history=history)
    effective_query = clean_query
    ambiguity_score = 0.12
    applied_memory_note = None
    ask_after_assumption = None
    direct_sql_override = None
    skip_analyze = False

    if calib and calib.get("best_match"):
        bm = calib["best_match"]
        direct_sql_override = bm["sql"]
        applied_memory_note = (
            f"Example-Based Calibration: target ~{calib['expected_target']:,.0f} matched "
            f"`{bm['table']}.{bm['column']}` (SUM = {bm['computed_value']:,.2f}, error {bm['relative_error']*100:.1f}%)"
        )
        ambiguity_score = 0.20
        skip_analyze = True
    elif replay_hit and not is_standalone_formula:
        effective_query = replay_hit.resolved_query or clean_query
        applied_memory_note = f"Clarification Replay: reused confirmed interpretation '{replay_hit.selected_option_label}'"
        if replay_hit.original_query.lower().strip() == clean_query.lower().strip() and replay_hit.final_sql:
            direct_sql_override = replay_hit.final_sql
        ambiguity_score = 0.20
        skip_analyze = True
    elif glossary_hits:
        g_top = glossary_hits[0]
        effective_query = f"{clean_query} ({g_top.term}: {g_top.sql_expression})"
        applied_memory_note = f"Approved Team Glossary applied: `{g_top.term}` = `{g_top.sql_expression}`"
        ambiguity_score = 0.18
        skip_analyze = True
    elif det_res.is_ambiguous:
        lookup_uid = user_id or "__anon_ephemeral__"
        enrich = clarification_intelligence.score_and_enrich_ambiguity(
            query=clean_query,
            det_res=det_res,
            schema=schema,
            db_mgr=db_manager,
            user_id=lookup_uid,
            answer_mode=req.answer_mode
        )
        ambiguity_score = enrich.get("ambiguity_score", 0.65)
        applied_memory_note = enrich.get("applied_memory_note")
        ask_after_assumption = enrich.get("ask_after_answer_assumption")
        session._ambiguity_score = ambiguity_score

        if enrich.get("should_ask_before"):
            analysis = det_res.to_query_analysis(clean_query)
            session.analysis = analysis
            session.is_ambiguous = True
            session.ambiguity_category = analysis.ambiguity_type
            session.ambiguity_score = ambiguity_score
            session.status = "awaiting_clarification"
            try:
                governance_manager.log_query_event(
                    user_id=user_id,
                    session_id=session.session_id,
                    query=clean_query,
                    ambiguity_score=ambiguity_score,
                    clarification_asked=True,
                    clarification_changed_sql=False,
                    resolution_turns=1,
                    success=True
                )
            except Exception:
                pass
            conversation_manager.add_message(
                conv.id,
                ChatMessage(
                    role="assistant",
                    content=analysis.clarification.question if analysis.clarification else "Please clarify your request:",
                    status="awaiting_clarification",
                    clarification=analysis.clarification,
                    session_id=session.session_id
                )
            )
            return session
        else:
            # Resolved via Personal Memory, Execution Divergence, or Ask-After-Answer Best Guess
            skip_analyze = True
            chosen_constraint = enrich.get("memory_constraint")
            chosen_label = enrich.get("memory_label")
            if not chosen_constraint and ask_after_assumption:
                chosen_constraint = ask_after_assumption.get("assumed_constraint")
                chosen_label = ask_after_assumption.get("assumed_label")
            if chosen_constraint and chosen_constraint.strip().lower().startswith(("select", "with")):
                direct_sql_override = chosen_constraint.strip()
            elif chosen_constraint or chosen_label:
                effective_query = f"{clean_query} [Specified details: {chosen_label or ''} ({chosen_constraint or ''})]"

    if not skip_analyze:
        try:
            analysis = llm.analyze_query(effective_query, schema_ctx, history=history)
            session.analysis = analysis
            session.is_ambiguous = analysis.is_ambiguous
            session.ambiguity_category = analysis.ambiguity_type
        except Exception as e:
            logger.warning(f"Primary LLM analyze_query failed: {e}. Falling back to Local NLP Provider.")
            try:
                from backend.llm.local_nlp_provider import LocalNLPProvider
                local_provider = LocalNLPProvider()
                analysis = local_provider.analyze_query(effective_query, schema_ctx, history=history)
                session.analysis = analysis
                session.is_ambiguous = analysis.is_ambiguous
                session.ambiguity_category = analysis.ambiguity_type
            except Exception as local_err:
                session.status = "error"
                session.error_message = f"Analysis error: {str(local_err)}"
                conversation_manager.add_message(
                    conv.id,
                    ChatMessage(role="assistant", content=session.error_message, status="error", session_id=session.session_id)
                )
                return session

        # 3. Check if LLM itself detected ambiguity
        if analysis.is_ambiguous:
            if not analysis.clarification:
                analysis.clarification = ClarificationRequest(
                    question=f"Please clarify your requirement for '{clean_query}':",
                    ambiguity_type=analysis.ambiguity_type if analysis.ambiguity_type != AmbiguityCategory.NONE else AmbiguityCategory.METRIC,
                    options=[
                        ClarificationOption(id="opt_1", label="Measure by total revenue", implied_filter_or_metric="revenue"),
                        ClarificationOption(id="opt_2", label="Measure by units sold", implied_filter_or_metric="units_sold")
                    ],
                    allow_free_text=True
                )
            session.status = "awaiting_clarification"
            session.ambiguity_score = max(ambiguity_score, 0.65)
            conversation_manager.add_message(
                conv.id,
                ChatMessage(
                    role="assistant",
                    content=analysis.clarification.question,
                    status="awaiting_clarification",
                    clarification=analysis.clarification,
                    session_id=session.session_id
                )
            )
            return session
    else:
        analysis = det_res.to_query_analysis(clean_query) if det_res.is_ambiguous else None
        if analysis:
            analysis.is_ambiguous = False
            session.analysis = analysis
        session.is_ambiguous = False

    # 4. Unambiguous (or Resolved via Intelligence/Memory/Calibration) -> SQL Generation & Execution
    session.resolved_query = effective_query
    session.status = "generating"

    try:
        if direct_sql_override:
            sql_to_validate = direct_sql_override
            sql_explanation = applied_memory_note or "Executed via clarification intelligence resolver."
        elif not skip_analyze and session.analysis and session.analysis.generated_sql and session.analysis.generated_sql.strip():
            sql_to_validate = session.analysis.generated_sql.strip()
            sql_explanation = session.analysis.sql_explanation or "Generated via single-pass intent compiler."
        else:
            clar_notes = applied_memory_note
            try:
                gen_result = llm.generate_sql(effective_query, schema_ctx, clarification_notes=clar_notes, history=history)
                sql_to_validate = gen_result.sql
                sql_explanation = gen_result.explanation
            except Exception as e:
                logger.warning(f"Primary LLM generate_sql failed: {e}. Falling back to Local NLP Provider.")
                from backend.llm.local_nlp_provider import LocalNLPProvider
                local_provider = LocalNLPProvider()
                gen_result = local_provider.generate_sql(effective_query, schema_ctx, clarification_notes=clar_notes, history=history)
                sql_to_validate = gen_result.sql
                sql_explanation = gen_result.explanation

        session.generated_sql = sql_to_validate
        session.sql_explanation = sql_explanation

        # AST Validation using SQLGlot (with full CTE & subquery support)
        validation = SQLValidator.validate(sql_to_validate, known_tables=known_tables, dialect=active_dialect)
        session.validation = validation

        if not validation.is_valid:
            session.status = "error"
            session.error_message = f"Validation failed: {'; '.join(validation.errors)}"
            conversation_manager.add_message(
                conv.id,
                ChatMessage(
                    role="assistant",
                    content=session.error_message,
                    sql=sql_to_validate,
                    status="error",
                    session_id=session.session_id
                )
            )
            return session

        # Read-Only Execution with Automated Query Self-Repair
        exec_res = db_manager.execute_query(validation.sanitized_sql or sql_to_validate)
        if not exec_res.success and validation.sanitized_sql:
            retry_orig = db_manager.execute_query(sql_to_validate)
            if retry_orig.success:
                exec_res = retry_orig

        if not exec_res.success and "must appear in the GROUP BY clause" in str(exec_res.error_message):
            if "GROUP BY" not in sql_to_validate.upper() and re.search(r"\b(SUM|COUNT|AVG|MIN|MAX)\(", sql_to_validate, re.I):
                repaired_sql = re.sub(r"\s+ORDER\s+BY\s+[a-zA-Z0-9_.]+(\s+(ASC|DESC))?", "", sql_to_validate, flags=re.I)
                retry_res = db_manager.execute_query(repaired_sql)
                if retry_res.success:
                    sql_to_validate = repaired_sql
                    session.generated_sql = repaired_sql
                    exec_res = retry_res
                    logger.info("Auto-repaired unaggregated ORDER BY in scalar aggregate query.")

        session.execution = exec_res

        if exec_res.success:
            session.status = "executed"
            _finalize_executed_session(
                session=session,
                query_text=clean_query,
                sql=sql_to_validate,
                validation=validation,
                exec_res=exec_res,
                schema=schema,
                llm=llm,
                history=history,
                user_id=user_id,
                ambiguity_score=ambiguity_score,
                applied_memory_note=applied_memory_note,
                ask_after_assumption=ask_after_assumption,
                was_clarified=False,
                clarification_asked=False,
                clarification_changed_sql=False,
                resolution_turns=1,
                mask_pii=req.mask_pii
            )
            # Store in conversation
            conversation_manager.add_message(
                conv.id,
                _build_assistant_chat_message(
                    session=session,
                    sql=sql_to_validate,
                    sql_explanation=sql_explanation,
                    exec_res=exec_res,
                    status="success"
                )
            )
            # Store in high-speed cache only when not masking PII and not temporary calibration
            if not req.mask_pii and not calib:
                query_cache.set(clean_query, {
                    "generated_sql": sql_to_validate,
                    "sql_explanation": sql_explanation,
                    "natural_explanation": session.natural_explanation,
                    "relationships_used": session.relationships_used
                }, catalog=catalog_key)

            # Continuously teach the model from executed query
            try:
                learning_engine.record_interaction(
                    query=clean_query,
                    sql=sql_to_validate,
                    tables_used=validation.tables_referenced,
                    success=True,
                    feedback=1
                )
            except Exception as learn_err:
                logger.warning(f"Could not record learning interaction: {learn_err}")
        else:
            session.status = "error"
            session.error_message = exec_res.error_message
            try:
                governance_manager.log_query_event(
                    user_id=user_id,
                    session_id=session.session_id,
                    query=clean_query,
                    ambiguity_score=ambiguity_score,
                    generated_sql=sql_to_validate,
                    tables_used=validation.tables_referenced,
                    success=False
                )
            except Exception:
                pass
            conversation_manager.add_message(
                conv.id,
                ChatMessage(
                    role="assistant",
                    content=f"Execution error: {exec_res.error_message}",
                    sql=sql_to_validate,
                    status="error",
                    session_id=session.session_id
                )
            )

    except Exception as e:
        session.status = "error"
        session.error_message = f"Pipeline error: {str(e)}"
        conversation_manager.add_message(
            conv.id,
            ChatMessage(role="assistant", content=session.error_message, status="error", session_id=session.session_id)
        )

    return session


@router.post("/{session_id}/clarify", response_model=QuerySession)
def submit_clarification(
    session_id: str, 
    req: ClarificationSubmitRequest, 
    authorization: Optional[str] = Header(None)
):
    """
    Submits user's choice to an ambiguous question.
    Rewrites the resolved query, generates SQL, validates with SQLGlot, and executes.
    Appends the clarification and answer to the saved conversation.
    """
    session = clarification_engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Query session not found.")

    if not req.option_id and not req.custom_text:
        raise HTTPException(status_code=400, detail="Must provide an option_id or custom_text.")

    # Record turn & rewrite
    session = clarification_engine.apply_clarification(
        session=session,
        option_id=req.option_id,
        custom_text=req.custom_text
    )

    conv_id = getattr(session, "conversation_id", None)
    history = conversation_manager.get_history_for_llm(conv_id) if conv_id else []

    user = None
    if authorization and isinstance(authorization, str):
        token = authorization.replace("Bearer ", "").strip()
        user = auth_manager.get_user_by_token(token)
    user_id = user["id"] if user else None

    if req.question_useful is not None:
        try:
            governance_manager.record_feedback(
                session_id=session.session_id,
                feedback_question=1 if req.question_useful else -1
            )
        except Exception:
            pass

    full_schema = db_manager.get_schema()
    allowed_tables = auth_manager.get_allowed_tables_for_user(user, list(full_schema.tables.keys()))
    schema = full_schema.filter_by_tables(allowed_tables)
    relationship_manager.apply_to_schema(schema, user_id=user_id)

    schema_ctx = schema.to_compact_llm_context()
    llm = get_llm_provider()
    active_dialect = "sqlite" if db_manager.active_source == "sample" else "postgres"

    # Fast-path: Check if selected option contains pre-compiled SQL
    chosen_opt = None
    if session.analysis and session.analysis.clarification and req.option_id:
        for opt in session.analysis.clarification.options:
            if opt.id == req.option_id:
                chosen_opt = opt
                break

    # Record user clarification action in conversation
    user_choice_label = req.custom_text or (chosen_opt.label if chosen_opt else req.option_id or "")
    if conv_id:
        conversation_manager.add_message(
            conv_id,
            ChatMessage(
                role="user",
                content=f"Selected: {user_choice_label}",
                session_id=session.session_id
            )
        )

    direct_sql = None
    if chosen_opt and chosen_opt.implied_filter_or_metric:
        raw_imp = chosen_opt.implied_filter_or_metric.strip()
        if raw_imp.lower().startswith("select") or raw_imp.lower().startswith("with"):
            direct_sql = raw_imp

    try:
        if direct_sql:
            sql_to_validate = direct_sql
            sql_explanation = f"Executed based on selection: '{chosen_opt.label}'."
        else:
            clarification_notes = "; ".join([
                f"Q: {t.question} -> Answer: {t.selected_option_label or t.custom_response}"
                for t in session.clarifications
            ])
            try:
                gen_result = llm.generate_sql(
                    resolved_query=session.resolved_query or session.original_query,
                    schema_context=schema_ctx,
                    clarification_notes=clarification_notes,
                    history=history
                )
                sql_to_validate = gen_result.sql
                sql_explanation = gen_result.explanation
            except Exception as e:
                logger.warning(f"Primary LLM clarify generate_sql failed: {e}. Falling back to Local NLP Provider.")
                from backend.llm.local_nlp_provider import LocalNLPProvider
                local_provider = LocalNLPProvider()
                gen_result = local_provider.generate_sql(
                    session.resolved_query or session.original_query,
                    schema_ctx,
                    clarification_notes=clarification_notes,
                    history=history
                )
                sql_to_validate = gen_result.sql
                sql_explanation = gen_result.explanation

        session.generated_sql = sql_to_validate
        session.sql_explanation = sql_explanation

        # AST Validation with SQLGlot
        known_tables = schema.get_known_tables_dict()
        validation = SQLValidator.validate(sql_to_validate, known_tables=known_tables, dialect=active_dialect)
        session.validation = validation

        if not validation.is_valid:
            session.status = "error"
            session.error_message = f"Validation failed: {'; '.join(validation.errors)}"
            if conv_id:
                conversation_manager.add_message(
                    conv_id,
                    ChatMessage(role="assistant", content=session.error_message, sql=sql_to_validate, status="error", session_id=session.session_id)
                )
            return session

        # Read-Only Execution with Automated Query Self-Repair
        exec_res = db_manager.execute_query(validation.sanitized_sql or sql_to_validate)
        if not exec_res.success and validation.sanitized_sql:
            retry_orig = db_manager.execute_query(sql_to_validate)
            if retry_orig.success:
                exec_res = retry_orig

        # Self-repair: If unaggregated ORDER BY in scalar aggregate query failed
        if not exec_res.success and "must appear in the GROUP BY clause" in str(exec_res.error_message):
            if "GROUP BY" not in sql_to_validate.upper() and re.search(r"\b(SUM|COUNT|AVG|MIN|MAX)\(", sql_to_validate, re.I):
                repaired_sql = re.sub(r"\s+ORDER\s+BY\s+[a-zA-Z0-9_.]+(\s+(ASC|DESC))?", "", sql_to_validate, flags=re.I)
                retry_res = db_manager.execute_query(repaired_sql)
                if retry_res.success:
                    sql_to_validate = repaired_sql
                    session.generated_sql = repaired_sql
                    exec_res = retry_res
                    logger.info("Auto-repaired unaggregated ORDER BY in scalar aggregate query.")

        session.execution = exec_res

        if exec_res.success:
            session.status = "executed"
            applied_constraint = (chosen_opt.implied_filter_or_metric if chosen_opt else None) or req.custom_text
            _finalize_executed_session(
                session=session,
                query_text=session.resolved_query or session.original_query,
                sql=sql_to_validate,
                validation=validation,
                exec_res=exec_res,
                schema=schema,
                llm=llm,
                history=history,
                user_id=user_id,
                ambiguity_score=float(getattr(session, "_ambiguity_score", getattr(session, "ambiguity_score", 0.65))),
                applied_memory_note=f"Confirmed clarification: '{user_choice_label}'",
                was_clarified=True,
                clarification_asked=True,
                clarification_changed_sql=True,
                resolution_turns=len(session.clarifications) + 1,
                mask_pii=bool(getattr(session, "_mask_pii", False))
            )

            # Learn Personal Semantic Memory & Clarification Replay Triple for authenticated users
            if user_id:
                try:
                    clar_cat = session.analysis.clarification.ambiguity_type if (session.analysis and session.analysis.clarification) else AmbiguityCategory.METRIC
                    clar_q = session.analysis.clarification.question if (session.analysis and session.analysis.clarification) else ""
                    term_key = clarification_intelligence._derive_term_key(clar_cat, None, session.original_query.lower())
                    table_hint = validation.tables_referenced[0] if validation.tables_referenced else None
                    semantic_memory.learn_preference(
                        user_id=user_id,
                        term_key=term_key,
                        trigger_pattern=session.original_query,
                        preferred_label=user_choice_label,
                        implied_constraint=applied_constraint or user_choice_label,
                        schema=schema,
                        table_hint=table_hint
                    )
                    semantic_memory.record_replay(
                        user_id=user_id,
                        original_query=session.original_query,
                        clarification_question=clar_q,
                        selected_option_label=user_choice_label,
                        applied_constraint=applied_constraint,
                        resolved_query=session.resolved_query or session.original_query,
                        final_sql=sql_to_validate,
                        tables_used=validation.tables_referenced
                    )
                except Exception as mem_err:
                    logger.warning(f"Could not save semantic memory/replay: {mem_err}")

            if conv_id:
                conversation_manager.add_message(
                    conv_id,
                    _build_assistant_chat_message(
                        session=session,
                        sql=sql_to_validate,
                        sql_explanation=sql_explanation,
                        exec_res=exec_res,
                        status="success"
                    )
                )
            # Store in query cache
            persona = semantic_memory.get_persona(user_id)
            catalog_key = f"{db_manager.active_source}_{user_id or 'anon'}_{persona}"
            cache_payload = {
                "generated_sql": sql_to_validate,
                "sql_explanation": sql_explanation,
                "natural_explanation": session.natural_explanation,
                "relationships_used": session.relationships_used,
                "applied_memory_note": f"Clarification Replay / Personal Memory: '{user_choice_label}'"
            }
            query_cache.set(session.original_query, cache_payload, catalog=catalog_key)
            if session.resolved_query:
                query_cache.set(session.resolved_query, cache_payload, catalog=catalog_key)

            # Continuously teach the model from successfully clarified query
            try:
                learning_engine.record_interaction(
                    query=session.resolved_query or session.original_query,
                    sql=sql_to_validate,
                    tables_used=validation.tables_referenced,
                    success=True,
                    feedback=1
                )
            except Exception as learn_err:
                logger.warning(f"Could not record clarification learning interaction: {learn_err}")
        else:
            session.status = "error"
            session.error_message = exec_res.error_message
            if conv_id:
                conversation_manager.add_message(
                    conv_id,
                    ChatMessage(role="assistant", content=f"Execution error: {exec_res.error_message}", sql=sql_to_validate, status="error", session_id=session.session_id)
                )

    except Exception as e:
        session.status = "error"
        session.error_message = f"Clarification execution error: {str(e)}"
        if conv_id:
            conversation_manager.add_message(
                conv_id,
                ChatMessage(role="assistant", content=session.error_message, status="error", session_id=session.session_id)
            )

    return session


@router.post("/{session_id}/execute", response_model=QuerySession)
def execute_session_sql(
    session_id: str, 
    req: Optional[DirectExecuteRequest] = None,
    authorization: Optional[str] = Header(None)
):
    """
    Executes or re-executes validated SQL for a session.
    """
    session = clarification_engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Query session not found.")

    sql_to_run = req.sql if (req and req.sql) else session.generated_sql
    if not sql_to_run:
        raise HTTPException(status_code=400, detail="No SQL available to execute.")

    user = None
    if authorization and isinstance(authorization, str):
        token = authorization.replace("Bearer ", "").strip()
        user = auth_manager.get_user_by_token(token)
    user_id = user["id"] if user else None

    full_schema = db_manager.get_schema()
    allowed_tables = auth_manager.get_allowed_tables_for_user(user, list(full_schema.tables.keys()))
    schema = full_schema.filter_by_tables(allowed_tables)
    relationship_manager.apply_to_schema(schema, user_id=user_id)
    known_tables = schema.get_known_tables_dict()
    active_dialect = "sqlite" if db_manager.active_source == "sample" else "postgres"
    validation = SQLValidator.validate(sql_to_run, known_tables=known_tables, dialect=active_dialect)
    session.validation = validation

    if not validation.is_valid:
        session.status = "error"
        session.error_message = f"Validation failed: {'; '.join(validation.errors)}"
        return session

    exec_res = db_manager.execute_query(validation.sanitized_sql or sql_to_run)
    if not exec_res.success and validation.sanitized_sql:
        retry_orig = db_manager.execute_query(sql_to_run)
        if retry_orig.success:
            exec_res = retry_orig
    session.execution = exec_res
    if exec_res.success:
        session.status = "executed"
        session.generated_sql = sql_to_run
        llm = get_llm_provider()
        _finalize_executed_session(
            session=session,
            query_text=session.resolved_query or session.original_query,
            sql=sql_to_run,
            validation=validation,
            exec_res=exec_res,
            schema=schema,
            llm=llm,
            user_id=user_id,
            ambiguity_score=float(getattr(session, "ambiguity_score", 0.0)),
            mask_pii=bool(getattr(session, "_mask_pii", False))
        )
    else:
        session.status = "error"
        session.error_message = exec_res.error_message

    return session


@router.get("/{session_id}", response_model=QuerySession)
def get_session_details(session_id: str):
    session = clarification_engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Query session not found.")
    return session
