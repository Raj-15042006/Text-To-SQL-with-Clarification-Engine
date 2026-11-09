import os
import sys
import pytest

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException
from backend.main import app
from backend.llm.factory import get_llm_provider
from backend.database.connection import db_manager
from backend.database.schema_extractor import get_default_sample_schema
from backend.modules.validator import SQLValidator
from backend.modules.ambiguity import (
    AmbiguityCategory,
    AmbiguityDetector,
    ambiguity_detector
)
from backend.routers.query import detect_query_ambiguity, QueryRequest

def test_sqlglot_validator_security():
    # Valid SELECT
    v1 = SQLValidator.validate("SELECT * FROM students WHERE attendance_percentage > 90")
    assert v1.is_valid is True
    assert v1.statement_type == "SELECT"

    # Prohibited DROP TABLE
    v2 = SQLValidator.validate("DROP TABLE students")
    assert v2.is_valid is False
    assert any("prohibited" in err.lower() or "security" in err.lower() for err in v2.errors)

    # Prohibited DELETE
    v3 = SQLValidator.validate("DELETE FROM students WHERE id = 101")
    assert v3.is_valid is False

    # Prohibited INSERT
    v4 = SQLValidator.validate("INSERT INTO departments VALUES (4, 'Civil', 'CE')")
    assert v4.is_valid is False


def test_sqlglot_schema_verification():
    known = {"students": ["id", "name"], "departments": ["id", "name"]}
    # Valid tables
    v1 = SQLValidator.validate("SELECT name FROM students", known_tables=known)
    assert v1.is_valid is True

    # Hallucinated table
    v2 = SQLValidator.validate("SELECT * FROM unknown_table", known_tables=known)
    assert v2.is_valid is False
    assert any("does not exist" in err for err in v2.errors)


# =============================================================================
# AMBIGUITY DETECTOR TESTS FOR ALL 7 REQUIRED CATEGORIES
# =============================================================================

def test_ambiguity_missing_filters():
    """Identifies missing filtering constraints such as passing cutoff and active status."""
    schema = get_default_sample_schema()

    # 1. Passing score threshold missing
    res1 = ambiguity_detector.detect("Show passing students", schema=schema)
    assert res1.is_ambiguous is True
    assert res1.primary_ambiguity == AmbiguityCategory.MISSING_FILTER
    assert res1.clarification is not None
    assert any("score >= 40" in opt.implied_filter_or_metric for opt in res1.clarification.options)

    # 2. Active status criteria missing
    res2 = ambiguity_detector.detect("Show active students in college", schema=schema)
    assert res2.is_ambiguous is True
    assert res2.primary_ambiguity == AmbiguityCategory.MISSING_FILTER
    assert res2.clarification is not None
    assert len(res2.clarification.options) >= 2

    # Direct method check
    issue = ambiguity_detector.check_missing_filters("Show students who failed", schema=schema)
    assert issue is not None
    assert issue.category == AmbiguityCategory.MISSING_FILTER


def test_ambiguity_unclear_comparison_criteria():
    """Identifies subjective or superlative comparison terms lacking explicit numeric thresholds."""
    schema = get_default_sample_schema()

    # 1. Top students without performance metric
    res1 = ambiguity_detector.detect("Show top students", schema=schema)
    assert res1.is_ambiguous is True
    assert res1.primary_ambiguity == AmbiguityCategory.UNCLEAR_COMPARISON
    assert res1.clarification is not None
    labels = [opt.label.lower() for opt in res1.clarification.options]
    assert any("total marks" in lbl for lbl in labels)
    assert any("average" in lbl for lbl in labels)

    # 2. High-value sales without monetary threshold
    res2 = ambiguity_detector.detect("Show high-value sales transactions", schema=schema)
    assert res2.is_ambiguous is True
    assert res2.primary_ambiguity == AmbiguityCategory.UNCLEAR_COMPARISON
    assert len(res2.clarification.options) >= 2

    # Direct method check
    issue = ambiguity_detector.check_unclear_comparison("Show students with poor attendance", schema=schema)
    assert issue is not None
    assert issue.category == AmbiguityCategory.UNCLEAR_COMPARISON


def test_ambiguity_ambiguous_column_names():
    """Identifies ambiguous columns mapping to multiple schema fields or tables."""
    schema = get_default_sample_schema()

    # 1. City ambiguity (store_city vs customer_city)
    res1 = ambiguity_detector.detect("Show sales from Mumbai", schema=schema)
    assert res1.is_ambiguous is True
    assert res1.primary_ambiguity == AmbiguityCategory.AMBIGUOUS_COLUMN
    assert res1.clarification is not None
    opt_ids = [opt.id for opt in res1.clarification.options]
    assert "opt_store_city" in opt_ids
    assert "opt_customer_city" in opt_ids

    # 2. 'name' column in both students and departments
    res2 = ambiguity_detector.detect("Show names from the database", schema=schema)
    assert res2.is_ambiguous is True
    assert res2.primary_ambiguity == AmbiguityCategory.AMBIGUOUS_COLUMN
    assert any("student" in opt.label.lower() for opt in res2.clarification.options)
    assert any("department" in opt.label.lower() for opt in res2.clarification.options)

    # 3. 'sales' metric (revenue vs units_sold)
    res3 = ambiguity_detector.detect("Show the highest sales", schema=schema)
    assert res3.is_ambiguous is True
    assert res3.primary_ambiguity in (AmbiguityCategory.AMBIGUOUS_COLUMN, AmbiguityCategory.METRIC)


def test_ambiguity_unspecified_date_ranges():
    """Identifies vague temporal intervals or calendar vs fiscal year ambiguities."""
    schema = get_default_sample_schema()

    # 1. Calendar year vs Fiscal year
    res1 = ambiguity_detector.detect("Show revenue last year", schema=schema)
    assert res1.is_ambiguous is True
    assert res1.primary_ambiguity == AmbiguityCategory.UNSPECIFIED_DATE_RANGE
    assert res1.clarification is not None
    assert any("calendar" in opt.label.lower() for opt in res1.clarification.options)
    assert any("financial" in opt.label.lower() or "fiscal" in opt.label.lower() for opt in res1.clarification.options)

    # 2. "recent" records
    res2 = ambiguity_detector.detect("Show recent sales", schema=schema)
    assert res2.is_ambiguous is True
    assert res2.primary_ambiguity == AmbiguityCategory.UNSPECIFIED_DATE_RANGE
    assert len(res2.clarification.options) >= 3

    # Direct method check
    issue = ambiguity_detector.check_unspecified_date_ranges("Show sales this quarter", schema=schema)
    assert issue is not None
    assert issue.category == AmbiguityCategory.UNSPECIFIED_DATE_RANGE


def test_ambiguity_unclear_aggregation_functions():
    """Identifies metric breakdowns by dimensions omitting SUM, AVG, COUNT, MAX, MIN."""
    schema = get_default_sample_schema()

    # 1. Sales by store city without aggregation
    res1 = ambiguity_detector.detect("Show sales by store city", schema=schema)
    assert res1.is_ambiguous is True
    assert res1.primary_ambiguity == AmbiguityCategory.UNCLEAR_AGGREGATION
    assert res1.clarification is not None
    implied = [opt.implied_filter_or_metric for opt in res1.clarification.options]
    assert any("SUM" in imp for imp in implied)
    assert any("AVG" in imp for imp in implied)
    assert any("COUNT" in imp for imp in implied)

    # 2. Student marks per course
    res2 = ambiguity_detector.detect("Show student marks per course", schema=schema)
    assert res2.is_ambiguous is True
    assert res2.primary_ambiguity == AmbiguityCategory.UNCLEAR_AGGREGATION


def test_ambiguity_ambiguous_table_relationships():
    """Identifies queries where multiple join paths connect candidate tables."""
    schema = get_default_sample_schema()

    # Students and Departments via Major vs Course enrollment
    res = ambiguity_detector.detect("Show students in Computer Science department", schema=schema)
    assert res.is_ambiguous is True
    assert res.primary_ambiguity == AmbiguityCategory.AMBIGUOUS_RELATIONSHIP
    assert res.clarification is not None
    assert any("major" in opt.label.lower() for opt in res.clarification.options)
    assert any("course enrollment" in opt.label.lower() for opt in res.clarification.options)


def test_ambiguity_unspecified_sorting_and_grouping():
    """Identifies missing sort columns, vague time groupings, and unspecified sort directions."""
    schema = get_default_sample_schema()

    # 1. Top 5 courses without sort metric
    res1 = ambiguity_detector.detect("Show top 5 courses", schema=schema)
    assert res1.is_ambiguous is True
    assert res1.primary_ambiguity == AmbiguityCategory.UNSPECIFIED_SORT_GROUP
    assert res1.clarification is not None
    assert any("enrollment" in opt.label.lower() for opt in res1.clarification.options)

    # 2. Sales over time without granularity
    res2 = ambiguity_detector.detect("Break down sales over time", schema=schema)
    assert res2.is_ambiguous is True
    assert res2.primary_ambiguity == AmbiguityCategory.UNSPECIFIED_SORT_GROUP
    assert any("month" in opt.label.lower() for opt in res2.clarification.options)
    assert any("year" in opt.label.lower() for opt in res2.clarification.options)

    # 3. Sort students by marks without direction
    res3 = ambiguity_detector.detect("Sort students by marks", schema=schema)
    assert res3.is_ambiguous is True
    assert res3.primary_ambiguity == AmbiguityCategory.UNSPECIFIED_SORT_GROUP
    assert any("descending" in opt.label.lower() for opt in res3.clarification.options)
    assert any("ascending" in opt.label.lower() for opt in res3.clarification.options)


from fastapi import HTTPException
from backend.routers.query import detect_query_ambiguity, QueryRequest

def test_detect_ambiguity_api_endpoint():
    """Tests the dedicated POST /api/query/detect-ambiguity endpoint logic."""
    res = detect_query_ambiguity(QueryRequest(query="Show passing students"))
    assert res.is_ambiguous is True
    assert res.primary_ambiguity == AmbiguityCategory.MISSING_FILTER
    assert res.clarification is not None
    assert len(res.clarification.options) >= 2
    assert len(res.issues) >= 1

    # Empty query check
    with pytest.raises(HTTPException) as exc_info:
        detect_query_ambiguity(QueryRequest(query="   "))
    assert exc_info.value.status_code == 400


def test_unambiguous_queries_pass_cleanly():
    """Verifies that explicit, self-contained, or formula queries are not falsely marked ambiguous."""
    schema = get_default_sample_schema()

    # 1. Explicit count query
    res1 = ambiguity_detector.detect("How many students are enrolled?", schema=schema)
    assert res1.is_ambiguous is False
    assert res1.primary_ambiguity == AmbiguityCategory.NONE

    # 2. Standalone formula calculation
    res2 = ambiguity_detector.detect("Calculate compound interest on 10000 at 5% for 3 years", schema=schema)
    assert res2.is_ambiguous is False

    # 3. Direct schema projection
    res3 = ambiguity_detector.detect("Show all departments", schema=schema)
    assert res3.is_ambiguous is False

    # 4. Explicit criteria and sorting
    res4 = ambiguity_detector.detect("Show students with score > 80 sorted by score descending", schema=schema)
    assert res4.is_ambiguous is False


if __name__ == "__main__":
    print("Running SQLGlot security tests...")
    test_sqlglot_validator_security()
    test_sqlglot_schema_verification()
    print("PASS: Security & schema validation.")

    print("Running tests for all 7 ambiguity detector categories...")
    test_ambiguity_missing_filters()
    test_ambiguity_unclear_comparison_criteria()
    test_ambiguity_ambiguous_column_names()
    test_ambiguity_unspecified_date_ranges()
    test_ambiguity_unclear_aggregation_functions()
    test_ambiguity_ambiguous_table_relationships()
    test_ambiguity_unspecified_sorting_and_grouping()
    print("PASS: All 7 ambiguity categories verified.")

    print("Running API endpoint and unambiguous query tests...")
    test_detect_ambiguity_api_endpoint()
    test_unambiguous_queries_pass_cleanly()
    print("PASS: API endpoint and unambiguous queries verified.")

    print("\nALL AMBIGUITY DETECTOR TESTS PASSED SUCCESSFULLY!")
