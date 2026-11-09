import logging
from typing import Optional, List
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/query", tags=["Query"])

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language query from user")
    conversation_id: Optional[str] = Field(None, description="Optional active conversation thread ID")

class ClarificationSubmitRequest(BaseModel):
    option_id: Optional[str] = None
    custom_text: Optional[str] = None

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

    # 1. Retrieve or create persistent conversation thread
    conv = conversation_manager.get_or_create(req.conversation_id, first_query=clean_query, user_id=user_id)
    
    # Context continuation: grab previous turns BEFORE this new user query
    history = conversation_manager.get_history_for_llm(conv.id)

    catalog_key = f"{db_manager.active_source}_{user_id or 'anon'}"
    session = clarification_engine.create_session(clean_query)
    session.conversation_id = conv.id

    # Append user question to conversation
    user_msg = ChatMessage(
        role="user",
        content=clean_query,
        session_id=session.session_id
    )
    conversation_manager.add_message(conv.id, user_msg)

    # Check if query is a standalone mathematical or domain formula
    from backend.modules.nlp_engine import local_nlp_engine
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

    # Fast-path 1: Query Cache Hit (<5ms response for standalone / repeated queries)
    if not is_context_dependent:
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

                conversation_manager.add_message(
                    conv.id,
                    ChatMessage(
                        role="assistant",
                        content=session.natural_explanation,
                        sql=cached_sql,
                        sql_explanation=session.sql_explanation,
                        columns=exec_res.columns,
                        rows=exec_res.rows[:5],
                        row_count=exec_res.row_count,
                        execution_time_ms=exec_res.execution_time_ms,
                        relationships=session.relationships_used,
                        status="success",
                        session_id=session.session_id
                    )
                )
                return session

    schema_ctx = schema.to_compact_llm_context()
    llm = get_llm_provider()

    # 2. Ambiguity Analysis & Single-Pass SQL Generation with Context Continuation
    # Fast-pass: Check for structural ambiguities across all 7 categories
    det_res = ambiguity_detector.detect(clean_query, schema=schema, history=history)
    if det_res.is_ambiguous:
        analysis = det_res.to_query_analysis(clean_query)
        session.analysis = analysis
        session.is_ambiguous = True
        session.ambiguity_category = analysis.ambiguity_type
        session.status = "awaiting_clarification"
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

    try:
        analysis = llm.analyze_query(clean_query, schema_ctx, history=history)
        session.analysis = analysis
        session.is_ambiguous = analysis.is_ambiguous
        session.ambiguity_category = analysis.ambiguity_type
    except Exception as e:
        logger.warning(f"Primary LLM analyze_query failed: {e}. Falling back to Local NLP Provider.")
        try:
            from backend.llm.local_nlp_provider import LocalNLPProvider
            local_provider = LocalNLPProvider()
            analysis = local_provider.analyze_query(clean_query, schema_ctx, history=history)
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

    # 3. Check if clarification is required
    if analysis.is_ambiguous:
        if not analysis.clarification:
            from backend.modules.ambiguity import ClarificationRequest, ClarificationOption, AmbiguityCategory
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

    # 4. Unambiguous -> Direct SQL Generation & Execution
    session.resolved_query = clean_query
    session.status = "generating"

    try:
        # Utilize single-pass SQL if provided; otherwise generate with history
        if analysis.generated_sql and analysis.generated_sql.strip():
            sql_to_validate = analysis.generated_sql.strip()
            sql_explanation = analysis.sql_explanation or "Generated via single-pass intent compiler."
        else:
            try:
                gen_result = llm.generate_sql(clean_query, schema_ctx, history=history)
                sql_to_validate = gen_result.sql
                sql_explanation = gen_result.explanation
            except Exception as e:
                logger.warning(f"Primary LLM generate_sql failed: {e}. Falling back to Local NLP Provider.")
                from backend.llm.local_nlp_provider import LocalNLPProvider
                local_provider = LocalNLPProvider()
                gen_result = local_provider.generate_sql(clean_query, schema_ctx, history=history)
                sql_to_validate = gen_result.sql
                sql_explanation = gen_result.explanation

        session.generated_sql = sql_to_validate
        session.sql_explanation = sql_explanation

        # AST Validation using SQLGlot (with full CTE & subquery support)
        known_tables = schema.get_known_tables_dict()
        active_dialect = "sqlite" if db_manager.active_source == "sample" else "postgres"
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
            # Fallback to the validated original SQL if dialect-sanitized string encountered dialect discrepancy
            retry_orig = db_manager.execute_query(sql_to_validate)
            if retry_orig.success:
                exec_res = retry_orig

        # Self-repair: If unaggregated ORDER BY in scalar aggregate query failed
        if not exec_res.success and "must appear in the GROUP BY clause" in str(exec_res.error_message):
            import re
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
            _populate_relationships_and_explain(
                session=session,
                query_text=clean_query,
                sql=sql_to_validate,
                validation=validation,
                exec_res=exec_res,
                schema=schema,
                llm=llm,
                history=history
            )
            # Store in conversation
            conversation_manager.add_message(
                conv.id,
                ChatMessage(
                    role="assistant",
                    content=session.natural_explanation or "",
                    sql=sql_to_validate,
                    sql_explanation=sql_explanation,
                    columns=exec_res.columns,
                    rows=exec_res.rows[:5],
                    row_count=exec_res.row_count,
                    execution_time_ms=exec_res.execution_time_ms,
                    relationships=session.relationships_used,
                    status="success",
                    session_id=session.session_id
                )
            )
            # Store in high-speed cache
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

    full_schema = db_manager.get_schema()
    allowed_tables = auth_manager.get_allowed_tables_for_user(user, list(full_schema.tables.keys()))
    schema = full_schema.filter_by_tables(allowed_tables)

    schema_ctx = schema.to_compact_llm_context()
    llm = get_llm_provider()

    # Fast-path: Check if selected option contains pre-compiled SQL
    chosen_opt = None
    if session.analysis and session.analysis.clarification and req.option_id:
        for opt in session.analysis.clarification.options:
            if opt.id == req.option_id:
                chosen_opt = opt
                break

    # Record user clarification action in conversation
    if conv_id:
        user_choice_label = req.custom_text or (chosen_opt.label if chosen_opt else req.option_id)
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
                    history=history
                )
                sql_to_validate = gen_result.sql
                sql_explanation = gen_result.explanation

        session.generated_sql = sql_to_validate
        session.sql_explanation = sql_explanation

        # AST Validation with SQLGlot
        known_tables = schema.get_known_tables_dict()
        validation = SQLValidator.validate(sql_to_validate, known_tables=known_tables)
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

        # Self-repair: If unaggregated ORDER BY in scalar aggregate query failed
        if not exec_res.success and "must appear in the GROUP BY clause" in str(exec_res.error_message):
            import re
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
            _populate_relationships_and_explain(
                session=session,
                query_text=session.resolved_query or session.original_query,
                sql=sql_to_validate,
                validation=validation,
                exec_res=exec_res,
                schema=schema,
                llm=llm,
                history=history
            )
            if conv_id:
                conversation_manager.add_message(
                    conv_id,
                    ChatMessage(
                        role="assistant",
                        content=session.natural_explanation or "",
                        sql=sql_to_validate,
                        sql_explanation=sql_explanation,
                        columns=exec_res.columns,
                        rows=exec_res.rows[:5],
                        row_count=exec_res.row_count,
                        execution_time_ms=exec_res.execution_time_ms,
                        relationships=session.relationships_used,
                        status="success",
                        session_id=session.session_id
                    )
                )
            # Store in query cache
            catalog_key = db_manager.active_source
            cache_payload = {
                "generated_sql": sql_to_validate,
                "sql_explanation": sql_explanation,
                "natural_explanation": session.natural_explanation,
                "relationships_used": session.relationships_used
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

    full_schema = db_manager.get_schema()
    allowed_tables = auth_manager.get_allowed_tables_for_user(user, list(full_schema.tables.keys()))
    schema = full_schema.filter_by_tables(allowed_tables)
    known_tables = schema.get_known_tables_dict()
    validation = SQLValidator.validate(sql_to_run, known_tables=known_tables)
    session.validation = validation

    if not validation.is_valid:
        session.status = "error"
        session.error_message = f"Validation failed: {'; '.join(validation.errors)}"
        return session

    exec_res = db_manager.execute_query(validation.sanitized_sql or sql_to_run)
    session.execution = exec_res
    if exec_res.success:
        session.status = "executed"
        if not session.natural_explanation or not session.relationships_used:
            llm = get_llm_provider()
            _populate_relationships_and_explain(
                session=session,
                query_text=session.resolved_query or session.original_query,
                sql=sql_to_run,
                validation=validation,
                exec_res=exec_res,
                schema=schema,
                llm=llm
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
