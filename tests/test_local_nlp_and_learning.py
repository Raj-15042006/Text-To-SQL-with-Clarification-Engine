"""
Unit Tests for Local NLP Engine and Self-Learning System
Verifies offline NLP parsing, AST SQL generation, model training,
continuous learning loop, and model management API endpoints.
"""

import os
import sys
import pytest

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database.schema_extractor import get_default_sample_schema
from backend.modules.nlp_engine import LocalNLPEngine, local_nlp_engine
from backend.modules.learning_engine import SelfLearningEngine, learning_engine
from backend.llm.local_nlp_provider import LocalNLPProvider
from backend.llm.factory import get_llm_provider, set_active_provider, get_active_provider_name
from backend.routers.model import (
    get_model_status,
    train_model,
    submit_feedback,
    switch_provider,
    list_training_samples,
    FeedbackRequest,
    SwitchProviderRequest
)


def test_local_nlp_formula_parsing():
    """Verifies that mathematical and domain formulas are evaluated directly into SQL."""
    nlp = local_nlp_engine

    # Compound interest
    sql1 = nlp.parse_formula("Calculate compound interest on 10000 at 5% for 3 years")
    assert sql1 is not None
    assert "10000" in sql1
    assert "POWER" in sql1
    assert "future_value" in sql1

    # Simple interest
    sql2 = nlp.parse_formula("Calculate simple interest on 5000 at 4% for 2 years")
    assert sql2 is not None
    assert "5000" in sql2

    # BMI
    sql3 = nlp.parse_formula("What is the BMI for 70kg and 1.75m?")
    assert sql3 is not None
    assert "70" in sql3
    assert "1.75" in sql3

    # Temperature conversion
    sql4 = nlp.parse_formula("Convert 100 celsius to fahrenheit")
    assert sql4 is not None
    assert "100" in sql4
    assert "fahrenheit" in sql4


def test_local_nlp_slot_extraction_and_sql_generation():
    """Verifies slot extraction and deterministic PostgreSQL SQL generation."""
    schema = get_default_sample_schema()
    nlp = local_nlp_engine

    # 1. Count query
    sql1, exp1 = nlp.generate_sql("How many students are enrolled?", schema=schema)
    assert "COUNT(*)" in sql1
    assert "students" in sql1.lower()

    # 2. Filter query
    sql2, exp2 = nlp.generate_sql("Show students with score > 80", schema=schema)
    assert "score" in sql2.lower()
    assert "> 80" in sql2 or "> 80.0" in sql2

    # 3. Sum query
    sql3, exp3 = nlp.generate_sql("Show total revenue from sales", schema=schema)
    assert "SUM" in sql3
    assert "revenue" in sql3.lower()

    # 4. Limit & Order query
    sql4, exp4 = nlp.generate_sql("Show the top 5 highest sales", schema=schema)
    assert "DESC" in sql4
    assert "LIMIT 5" in sql4


def test_self_learning_intent_classification_and_retraining():
    """Verifies training memory, TF-IDF feature extraction, and intent classification."""
    learner = learning_engine

    # 1. Retrain model
    ret_res = learner.retrain()
    assert ret_res["success"] is True
    assert ret_res["sample_count"] >= 10
    assert ret_res["accuracy"] >= 0.80
    assert ret_res["vocabulary_size"] > 20

    # 2. Predict intent
    intent1, conf1 = learner.predict_intent("How many students are enrolled?")
    assert intent1 == "AGGREGATE_COUNT"
    assert conf1 > 0.3

    intent2, conf2 = learner.predict_intent("Calculate compound interest on 10000 at 5% for 3 years")
    assert intent2 == "FORMULA_MATH"

    # 3. Memory similarity search
    match = learner.find_similar_sample("How many students are enrolled?", threshold=0.85)
    assert match is not None
    assert match.intent == "AGGREGATE_COUNT"


def test_continuous_learning_from_user_feedback():
    """Verifies that user feedback and corrections dynamically update the model memory."""
    learner = learning_engine
    init_count = len(learner.memory)

    # User corrects a query
    query_text = "Show all high honor roll students"
    corrected_sql = "SELECT id, name, attendance_percentage FROM students WHERE attendance_percentage >= 95.0;"
    sample = learner.record_interaction(
        query=query_text,
        sql="SELECT * FROM students;",
        tables_used=["students"],
        success=True,
        feedback=1,
        corrected_sql=corrected_sql
    )

    assert len(learner.memory) == init_count + 1
    assert sample.sql == corrected_sql
    assert sample.corrected_sql == corrected_sql

    # Status check
    status = learner.get_status()
    assert status.is_trained is True
    assert status.sample_count == len(learner.memory)


def test_local_nlp_provider_pipeline():
    """Verifies LocalNLPProvider as an offline drop-in replacement for BaseLLMProvider."""
    provider = LocalNLPProvider()
    schema_ctx = get_default_sample_schema().to_compact_llm_context()

    # 1. Analyze query
    analysis = provider.analyze_query("How many students are enrolled?", schema_context=schema_ctx)
    assert analysis.is_ambiguous is False
    assert analysis.generated_sql is not None
    assert "COUNT(*)" in analysis.generated_sql

    # 2. Ambiguity detection through LocalNLPProvider
    amb_analysis = provider.analyze_query("Show passing students", schema_context=schema_ctx)
    assert amb_analysis.is_ambiguous is True
    assert amb_analysis.clarification is not None

    # 3. Result explanation
    exp = provider.explain_results(
        user_query="How many students are enrolled?",
        sql="SELECT COUNT(*) AS total_students FROM students;",
        columns=["total_students"],
        sample_rows=[{"total_students": 150}],
        total_rows=1
    )
    assert "150" in exp


def test_model_api_endpoints():
    """Verifies model management endpoints."""
    # 1. Status
    status = get_model_status()
    assert status.is_trained is True
    assert status.sample_count >= 10

    # 2. Trigger retrain
    train_res = train_model()
    assert train_res["success"] is True

    # 3. Switch provider
    sw_res = switch_provider(SwitchProviderRequest(provider="local"))
    assert sw_res["success"] is True
    assert get_active_provider_name() == "local"

    # Verify provider factory returns LocalNLPProvider
    active_prov = get_llm_provider()
    assert isinstance(active_prov, LocalNLPProvider)

    # 4. Submit feedback
    fb_res = submit_feedback(FeedbackRequest(
        query="Show department list",
        sql="SELECT id, name, code FROM departments;",
        feedback=1
    ))
    assert fb_res["success"] is True

    # 5. List samples
    samples = list_training_samples(limit=5)
    assert len(samples) > 0

    # Reset active provider
    switch_provider(SwitchProviderRequest(provider="gemini"))


def test_worldwide_mathematical_formulas_expanded():
    """Verifies worldwide financial, sports, physics, geometry, and unit conversion formulas."""
    nlp = local_nlp_engine

    # 1. Financial: Loan EMI
    sql_emi = nlp.parse_formula("Calculate loan EMI for 500000 at 8.5% for 5 years")
    assert sql_emi is not None
    assert "monthly_emi" in sql_emi
    assert "500000" in sql_emi

    # 2. Financial: CAGR
    sql_cagr = nlp.parse_formula("Calculate CAGR from 100000 to 250000 over 5 years")
    assert sql_cagr is not None
    assert "cagr_percentage" in sql_cagr

    # 3. Sports: Cricket Net Run Rate (NRR)
    sql_nrr = nlp.parse_formula("Calculate net run rate with 180 runs in 20 overs scored and 150 runs in 20 overs conceded")
    assert sql_nrr is not None
    assert "net_run_rate" in sql_nrr

    # 4. Sports: Batting Strike Rate
    sql_sr = nlp.parse_formula("batting strike rate for 75 runs in 42 balls")
    assert sql_sr is not None
    assert "batting_strike_rate" in sql_sr

    # 5. Physics: Kinetic Energy
    sql_ke = nlp.parse_formula("Kinetic energy of 1200 kg car moving at 25 m/s")
    assert sql_ke is not None
    assert "kinetic_energy_joules" in sql_ke

    # 6. Geometry: Circle Area
    sql_circle = nlp.parse_formula("Area of circle with radius 7")
    assert sql_circle is not None
    assert "circle_area" in sql_circle

    # 7. Conversions: km to miles
    sql_conv = nlp.parse_formula("Convert 50 km to miles")
    assert sql_conv is not None
    assert "miles" in sql_conv

    # 8. Percentages: 25% of 480
    sql_pct = nlp.parse_formula("25 percent of 480")
    assert sql_pct is not None
    assert "percentage_value" in sql_pct

    # 9. Math function evaluation
    sql_math = nlp.parse_formula("calculate sqrt(144) + power(2, 3) * 5")
    assert sql_math is not None
    assert "result" in sql_math


def test_context_awareness_and_multi_turn_continuation():
    """Verifies that conversation history enables contextual follow-ups, pronoun resolution, and filter inheritance."""
    schema = get_default_sample_schema()
    nlp = local_nlp_engine

    # Turn 1
    history = [
        {"role": "user", "content": "Show students with score > 80"},
        {"role": "assistant", "content": "Found students", "sql": "SELECT students.name, marks.score FROM students JOIN marks ON marks.student_id = students.id WHERE marks.score > 80;"}
    ]

    # Follow-up 1: incremental filter refinement with 'Now show only those...'
    sql1, exp1 = nlp.generate_sql("Now show only those with attendance above 75", schema=schema, history=history)
    assert "attendance_percentage > 75" in sql1
    assert "marks.score > 80" in sql1 or "score > 80" in sql1
    assert "Continued context" in exp1

    # Follow-up 2: pronoun aggregation with 'What is their average score?'
    history.append({"role": "user", "content": "Now show only those with attendance above 75"})
    history.append({"role": "assistant", "content": exp1, "sql": sql1})

    sql2, exp2 = nlp.generate_sql("What is their average score?", schema=schema, history=history)
    assert "AVG(marks.score)" in sql2 or "AVG(score)" in sql2
    assert "marks.score > 80" in sql2 or "score > 80" in sql2
    assert "JOIN marks" in sql2 or "marks" in sql2

    # Follow-up 3: sorting with 'Sort them by score descending'
    sql3, exp3 = nlp.generate_sql("Sort them by score descending", schema=schema, history=history)
    assert "ORDER BY score DESC" in sql3 or "ORDER BY marks.score DESC" in sql3
    assert "marks.score > 80" in sql3 or "score > 80" in sql3


if __name__ == "__main__":
    print("Testing local NLP formula parsing...")
    test_local_nlp_formula_parsing()
    print("PASS: Formula parsing.")

    print("Testing slot extraction and SQL generation...")
    test_local_nlp_slot_extraction_and_sql_generation()
    print("PASS: Slot extraction & SQL generation.")

    print("Testing self-learning intent classification...")
    test_self_learning_intent_classification_and_retraining()
    print("PASS: Intent classification & retraining.")

    print("Testing continuous learning feedback loop...")
    test_continuous_learning_from_user_feedback()
    print("PASS: Feedback loop & sample memory.")

    print("Testing LocalNLPProvider pipeline...")
    test_local_nlp_provider_pipeline()
    print("PASS: LocalNLPProvider pipeline.")

    print("Testing model API endpoints...")
    test_model_api_endpoints()
    print("PASS: Model API endpoints.")

    print("\nALL LOCAL NLP & SELF-LEARNING TESTS PASSED SUCCESSFULLY!")

