import time
import uuid
import copy
import pytest

from backend.database.connection import db_manager, ExecutionResult
from backend.database.schema_extractor import DatabaseSchema, TableMeta, ColumnMeta
from backend.modules.learning_engine import learning_engine
from backend.modules.semantic_memory import semantic_memory
from backend.modules.governance import GovernanceManager, governance_manager
from backend.modules.clarification_intelligence import clarification_intelligence
from backend.modules.ambiguity import ambiguity_detector, AmbiguityCategory
from backend.modules.auth_manager import auth_manager
from backend.modules.query_cache import query_cache
from backend.routers.query import (
    submit_query,
    submit_clarification,
    QueryRequest,
    ClarificationSubmitRequest,
)
from backend.routers.governance import (
    get_governance_summary,
    update_user_persona,
    add_or_propose_glossary_term,
    decide_glossary_term,
    submit_dual_feedback,
    PersonaRequest,
    GlossaryCreateRequest,
    GlossaryDecisionRequest,
    DualFeedbackRequest,
)


@pytest.fixture(autouse=True)
def _isolate_persistent_state():
    """Preserves persistent memory/glossary/replay/audit files across isolated test runs."""
    mem_bak = copy.deepcopy(semantic_memory._memories)
    per_bak = copy.deepcopy(semantic_memory._personas)
    gls_bak = copy.deepcopy(semantic_memory._glossary)
    rpl_bak = copy.deepcopy(semantic_memory._replays)
    aud_bak = copy.deepcopy(governance_manager._audit_log)
    try:
        yield
    finally:
        semantic_memory._memories = mem_bak
        semantic_memory._personas = per_bak
        semantic_memory._glossary = gls_bak
        semantic_memory._replays = rpl_bak
        semantic_memory._save_memories()
        semantic_memory._save_glossary()
        semantic_memory._save_replays()
        governance_manager._audit_log = aud_bak
        governance_manager._save()
        query_cache.clear()


def _login_raj():
    user, token, err = auth_manager.login("raj", "password123")
    assert err is None and user is not None and token is not None
    return user["id"], f"Bearer {token}", user["username"]


def _create_temp_auth_user(role_tag="intel"):
    uname = f"test_{role_tag}_{uuid.uuid4().hex[:6]}"
    user, token, err = auth_manager.register(
        username=uname,
        password="secret123",
        display_name=f"Test {role_tag}",
        email=f"{uname}@example.com"
    )
    assert err is None and user is not None and token is not None
    return user["id"], f"Bearer {token}", uname


def _delete_temp_user(uid: str):
    if uid in auth_manager._users:
        del auth_manager._users[uid]
        auth_manager._save()


def test_ml_ensemble_cv_and_model_status():
    res = learning_engine.retrain()
    assert res["success"] is True
    assert res["sample_count"] >= 200
    assert res["cv_accuracy"] >= 0.65
    assert res["cv_f1_score"] >= 0.60

    status = learning_engine.get_status("local")
    assert status.is_trained is True
    assert status.cv_accuracy > 0
    assert status.cv_f1_score > 0
    assert "Ensemble" in status.model_architecture

    intent, conf = learning_engine.predict_intent("Show top 5 countries by total net sales and revenue")
    assert isinstance(intent, str) and len(intent) > 0
    assert conf > 0.1


def test_personal_memory_decay_and_authenticated_reuse():
    mgr = semantic_memory
    uid = f"u_mem_{uuid.uuid4().hex[:6]}"
    schema = db_manager.get_schema()

    entry = mgr.learn_preference(
        user_id=uid,
        term_key="city_scope",
        trigger_pattern="Show sales in Mumbai",
        preferred_label="Store City = Mumbai",
        implied_constraint="store_city = 'Mumbai'",
        schema=schema,
        table_hint="sales" if "sales" in schema.tables else None
    )

    # Fresh preference -> active and high confidence
    eff, needs_reconf, _ = mgr.compute_effective_confidence(entry, schema)
    assert eff >= 0.85
    assert needs_reconf is False
    assert mgr.find_matching_preference(uid, "city_scope", schema=schema) is not None

    # Temporal decay (> 60 days old) -> triggers reconfirmation
    entry.last_used_ts = time.time() - (70 * 86400)
    eff_old, needs_old, reason_old = mgr.compute_effective_confidence(entry, schema)
    assert eff_old < 0.60
    assert needs_old is True
    assert "decayed over time" in reason_old.lower()

    # Schema-change decay
    entry.last_used_ts = time.time()
    if entry.table_hint and entry.table_hint in schema.tables:
        altered = DatabaseSchema(
            database_name="test_altered",
            tables={
                entry.table_hint: TableMeta(
                    name=entry.table_hint,
                    columns=[ColumnMeta(name="brand_new_col", data_type="TEXT")]
                )
            }
        )
        eff_sch, needs_sch, reason_sch = mgr.compute_effective_confidence(entry, altered)
        assert eff_sch < 0.50
        assert needs_sch is True
        assert "schema changed" in reason_sch.lower()


def test_team_glossary_approval_and_replay_isolation():
    uid, auth_header, uname = _login_raj()

    # Propose pending glossary term, approve, verify matching
    created = add_or_propose_glossary_term(
        GlossaryCreateRequest(
            term="gross margin impact",
            definition="Difference between net revenue and cost",
            sql_expression="SUM(revenue - net_profit)",
            category="metric",
            auto_approve=False
        ),
        authorization=auth_header
    )
    term_id = created["term"]["id"]
    assert created["term"]["status"] == "pending"

    # Not matched while pending
    assert len(semantic_memory.match_approved_glossary("Show gross margin impact")) == 0

    dec = decide_glossary_term(term_id, GlossaryDecisionRequest(status="approved"), authorization=auth_header)
    assert dec["term"]["status"] == "approved"
    matched = semantic_memory.match_approved_glossary("Show gross margin impact by category")
    assert len(matched) == 1
    assert matched[0].term == "gross margin impact"

    # Replay record + multi-tenant table isolation
    semantic_memory.record_replay(
        user_id=uid,
        original_query="Show orders in Mumbai",
        clarification_question="Customer city or Store city?",
        selected_option_label="Store city",
        applied_constraint="store_city = 'Mumbai'",
        resolved_query="Show orders in Mumbai [Specified details: Store city (store_city = 'Mumbai')]",
        final_sql="SELECT * FROM sales WHERE store_city = 'Mumbai';",
        tables_used=["sales"]
    )
    hit_ok = semantic_memory.find_replay("Show orders in Mumbai", allowed_tables=["sales"])
    assert hit_ok is not None
    hit_blocked = semantic_memory.find_replay("Show orders in Mumbai", allowed_tables=["students"])
    assert hit_blocked is None


def test_schema_gap_never_hallucinates():
    uid, auth_header, _ = _login_raj()
    session = submit_query(
        QueryRequest(query="Show bitcoin wallet balance by hospital diagnosis"),
        authorization=auth_header
    )
    assert session.status == "schema_gap"
    assert session.schema_gap is not None
    assert session.schema_gap["has_gap"] is True
    assert session.generated_sql is None
    assert len(session.thinking_steps) >= 2


def test_ask_after_answer_and_strict_mode_and_thinking_transparency():
    uid, auth_header, _ = _login_raj()
    # Clear any existing memory on raj for city_scope before running test
    semantic_memory._memories[uid] = [
        m for m in semantic_memory._memories.get(uid, [])
        if m.term_key != "city_scope"
    ]
    semantic_memory._replays = []

    # Best-Guess / Ask-After-Answer executes immediately on ambiguous city query
    sess_fast = submit_query(
        QueryRequest(query="Show sales in Mumbai", answer_mode="fast_best_guess"),
        authorization=auth_header
    )
    assert sess_fast.status == "executed"
    assert sess_fast.execution is not None and sess_fast.execution.success is True
    assert sess_fast.ask_after_answer is not None
    assert len(sess_fast.ask_after_answer.get("alternatives", [])) >= 1
    assert len(sess_fast.thinking_steps) >= 3
    assert any(step["phase"] == "Think" for step in sess_fast.thinking_steps)
    assert len(sess_fast.provenance) >= 1
    assert len(sess_fast.confidence_reasons) >= 1

    # Strict mode always clarifies upfront when ambiguous
    sess_strict = submit_query(
        QueryRequest(query="Show sales in Mumbai", answer_mode="strict"),
        authorization=auth_header
    )
    assert sess_strict.status == "awaiting_clarification"
    opts = sess_strict.analysis.clarification.options
    assert len(opts) >= 2
    assert any(
        o.estimated_rows is not None or (o.description and ("in db" in o.description.lower() or "matching" in o.description.lower()))
        for o in opts
    )

    # Resolve strict clarification and verify replay & memory learning works automatically on turn 2!
    resolved = submit_clarification(
        sess_strict.session_id,
        ClarificationSubmitRequest(option_id=opts[0].id, question_useful=True),
        authorization=auth_header
    )
    assert resolved.status == "executed"
    assert resolved.confidence_score >= 70
    assert any("clarification" in r.lower() or "confirmed" in r.lower() for r in resolved.confidence_reasons)

    # Second identical query auto-applies Replay or Personal Memory without re-asking!
    sess_reused = submit_query(
        QueryRequest(query="Show sales in Mumbai", answer_mode="smart"),
        authorization=auth_header
    )
    assert sess_reused.status == "executed"
    assert any(a["source"] == "memory" for a in sess_reused.assumptions)


def test_pii_detection_masking_cost_and_data_quality():
    gov = GovernanceManager()

    tmp_tbl = f"tmp_pii_{uuid.uuid4().hex[:6]}"
    conn = db_manager._sample_sqlite_conn
    assert conn is not None
    conn.execute(f"CREATE TABLE {tmp_tbl} (id INTEGER PRIMARY KEY, email TEXT, phone TEXT, amount REAL)")
    conn.execute(f"INSERT INTO {tmp_tbl} VALUES (1, 'alice@example.com', '+1-555-010-9988', 100.0)")
    conn.execute(f"INSERT INTO {tmp_tbl} VALUES (2, NULL, NULL, NULL)")
    conn.execute(f"INSERT INTO {tmp_tbl} VALUES (3, NULL, '9876543210', NULL)")
    conn.commit()
    db_manager._schema_cache = None

    try:
        schema = db_manager.get_schema()
        dq_warnings = gov.check_data_quality([tmp_tbl], ["email", "amount"], schema, db_manager)
        assert any("NULL" in w for w in dq_warnings)

        exec_res = db_manager.execute_query(f"SELECT id, email, phone, amount FROM {tmp_tbl}")
        assert exec_res.success
        masked = gov.inspect_and_mask_pii(exec_res.columns, exec_res.rows, mask_enabled=True)
        assert "email" in masked["pii_columns"]
        assert "phone" in masked["pii_columns"]
        assert masked["rows"][0]["email"] == "a***@example.com"
        assert masked["rows"][0]["phone"].endswith("9988")
        assert "***" in masked["rows"][0]["phone"] or "*" in masked["rows"][0]["phone"]

        cost = gov.estimate_query_cost(f"SELECT * FROM {tmp_tbl}", [tmp_tbl], db_manager)
        assert cost["cost_level"] == "Low"
        assert cost["estimated_rows_scanned"] == 3
    finally:
        conn.execute(f"DROP TABLE IF EXISTS {tmp_tbl}")
        conn.commit()
        db_manager._schema_cache = None


def test_execution_divergence_suppression_and_example_calibration():
    # 1. Execution-Divergence Check: when candidate options return identical probe outputs, skip clarification
    class MockDB:
        def execute_query(self, sql):
            return ExecutionResult(success=True, columns=["student_id", "score"], rows=[{"student_id": 1, "score": 85}], row_count=1)

    schema = db_manager.get_schema()
    det = ambiguity_detector.detect("Show passing students", schema=schema)
    assert det.is_ambiguous is True
    enriched = clarification_intelligence.score_and_enrich_ambiguity(
        query="Show passing students",
        det_res=det,
        schema=schema,
        db_mgr=MockDB(),
        user_id="__test_div__",
        answer_mode="strict"
    )
    assert enriched["divergence_suppressed"] is True
    assert enriched["should_ask_before"] is False

    # 2. Example-Based Calibration: match approximate expected total against real numeric column sums
    if "sales" in schema.tables:
        res_rev = db_manager.execute_query("SELECT SUM(revenue) AS rev FROM sales")
        if res_rev.success and res_rev.rows and res_rev.rows[0].get("rev"):
            target = float(res_rev.rows[0]["rev"])
            calib = clarification_intelligence.detect_and_calibrate_expected_value(
                f"Show total metric expected around {int(round(target))}",
                schema,
                db_manager
            )
            assert calib is not None
            assert calib["best_match"]["relative_error"] < 0.05


def test_dynamic_ambiguity_and_counterfactual_benchmark():
    base_schema = db_manager.get_schema()
    dyn_schema = DatabaseSchema(
        database_name="dyn_test_db",
        tables={
            "orders": TableMeta(
                name="orders",
                columns=[
                    ColumnMeta(name="id", data_type="INTEGER", is_primary_key=True),
                    ColumnMeta(name="buyer_id", data_type="INTEGER", is_foreign_key=True, foreign_key_target="users.id"),
                    ColumnMeta(name="approver_id", data_type="INTEGER", is_foreign_key=True, foreign_key_target="users.id"),
                    ColumnMeta(name="order_status", data_type="TEXT"),
                    ColumnMeta(name="total_amount", data_type="REAL"),
                ],
                foreign_keys=[
                    {"column": "buyer_id", "references": "users.id", "is_active": True},
                    {"column": "approver_id", "references": "users.id", "is_active": True},
                ]
            ),
            "users": TableMeta(
                name="users",
                columns=[
                    ColumnMeta(name="id", data_type="INTEGER", is_primary_key=True),
                    ColumnMeta(name="name", data_type="TEXT"),
                ]
            ),
            "sales": base_schema.tables.get("sales", TableMeta(name="sales", columns=[])),
            "students": base_schema.tables.get("students", TableMeta(name="students", columns=[])),
            "departments": base_schema.tables.get("departments", TableMeta(name="departments", columns=[])),
        }
    )

    # Dynamic multi-FK ambiguity
    r_fk = ambiguity_detector.detect("Show orders joined with users", schema=dyn_schema)
    assert r_fk.is_ambiguous is True
    assert r_fk.primary_ambiguity == AmbiguityCategory.AMBIGUOUS_RELATIONSHIP

    # Dynamic order_status scope ambiguity
    r_stat = ambiguity_detector.detect("How many total orders are there?", schema=dyn_schema)
    assert r_stat.is_ambiguous is True
    assert r_stat.primary_ambiguity == AmbiguityCategory.MISSING_FILTER

    # Dynamic metric definition ambiguity
    r_churn = ambiguity_detector.detect("Show monthly customer churn by segment", schema=dyn_schema)
    assert r_churn.is_ambiguous is True

    # Counterfactual Ambiguity Benchmark (Section 7):
    counterfactual_pairs = [
        ("Show store city revenue > 1000 in 2024", "Show Mumbai sales"),
        ("Show total revenue summed by store_city", "Show sales by store city"),
        ("Show top students ranked by score >= 80", "Show top students"),
        ("Show students majoring in Engineering via students.department_id", "Show students in Engineering department"),
        ("Show top 5 courses sorted by average score descending", "Show top 5 courses"),
    ]
    passed_cf = 0
    for clear_q, vague_q in counterfactual_pairs:
        res_clear = ambiguity_detector.detect(clear_q, schema=dyn_schema)
        res_vague = ambiguity_detector.detect(vague_q, schema=dyn_schema)
        if not res_clear.is_ambiguous and res_vague.is_ambiguous:
            passed_cf += 1
    assert passed_cf == len(counterfactual_pairs)


def test_section7_metrics_and_governance_router():
    uid, auth_header, _ = _login_raj()
    update_user_persona(PersonaRequest(persona="finance"), authorization=auth_header)

    res = submit_query(
        QueryRequest(query="Show top 3 countries by revenue and units sold"),
        authorization=auth_header
    )
    assert res.status == "executed"
    assert "Key Highlights" in (res.natural_explanation or "") or "**Answer**" in (res.natural_explanation or "")
    assert any(s["phase"] == "Synthesize" for s in res.thinking_steps)

    fb = submit_dual_feedback(
        DualFeedbackRequest(session_id=res.session_id, feedback_result=1, feedback_question=1),
        authorization=auth_header
    )
    assert fb["audit_updated"] is True

    summary = get_governance_summary(authorization=auth_header)
    assert summary["persona"] == "finance"
    assert summary["quality_metrics"]["total_queries"] >= 1
    assert summary["quality_metrics"]["positive_feedback_rate_pct"] >= 0.0
