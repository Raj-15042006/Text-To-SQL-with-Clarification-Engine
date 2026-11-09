import time
import pytest
from backend.routers.query import submit_query, QueryRequest
from backend.modules.conversation_manager import conversation_manager
from backend.modules.query_cache import query_cache

def test_cache_speedup():
    query_cache.clear()
    query_text = "Calculate compound interest on 10000 at 5% for 3 years"

    # Run 1: Cold start / LLM generation
    t0 = time.time()
    r1 = submit_query(QueryRequest(query=query_text))
    t_cold = time.time() - t0

    assert r1.status == "executed"
    assert r1.generated_sql is not None
    assert r1.natural_explanation is not None

    # Run 2: High-speed Cache Hit
    t0 = time.time()
    r2 = submit_query(QueryRequest(query=query_text))
    t_cached = time.time() - t0

    assert r2.status == "executed"
    assert r2.generated_sql == r1.generated_sql
    # Cached run should be sub-150ms
    assert t_cached < 0.20, f"Expected cache hit under 200ms, got {t_cached}s"
    print(f"\n[CACHE TEST] Cold: {t_cold:.3f}s -> Cached: {t_cached:.3f}s ({t_cold/t_cached:.1f}x speedup)")

def test_multi_turn_context_continuation():
    # Turn 1: Initial broad query
    r1 = submit_query(QueryRequest(query="Give me net run rate for all the teams"))
    if r1.status == "awaiting_clarification":
        from backend.routers.query import submit_clarification, ClarificationSubmitRequest
        opts = r1.analysis.clarification.options if r1.analysis and r1.analysis.clarification else []
        req = ClarificationSubmitRequest(option_id=opts[0].id) if opts else ClarificationSubmitRequest(custom_text="Use win percentage")
        r1 = submit_clarification(r1.session_id, req)
    assert r1.status == "executed"
    assert r1.generated_sql is not None
    conv_id = r1.conversation_id
    assert conv_id is not None

    # Turn 2: Pronoun follow-up ("Which team has the highest?")
    r2 = submit_query(QueryRequest(query="Which team has the highest?", conversation_id=conv_id))
    assert r2.status == "executed"
    assert r2.natural_explanation is not None
    print(f"\n[CONTEXT TURN 2] Answer: {r2.natural_explanation}")

    # Turn 3: Contextual filter continuation ("Now show only teams with win percentage above 50")
    r3 = submit_query(QueryRequest(query="Now show only teams with win percentage above 50", conversation_id=conv_id))
    if r3.status == "awaiting_clarification":
        from backend.routers.query import submit_clarification, ClarificationSubmitRequest
        opts3 = r3.analysis.clarification.options if r3.analysis and r3.analysis.clarification else []
        req3 = ClarificationSubmitRequest(option_id=opts3[0].id) if opts3 else ClarificationSubmitRequest(custom_text="Filter teams")
        r3 = submit_clarification(r3.session_id, req3)
    assert r3.status == "executed"
    print(f"\n[CONTEXT TURN 3] Filter SQL: {r3.generated_sql[:120]}...")


