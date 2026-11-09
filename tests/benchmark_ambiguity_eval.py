"""
SRS Phase 10: Ambiguity Detection Benchmark & Evaluation Suite
Evaluates the Ambiguity Detector against a golden benchmark dataset of 45 queries
measuring Ambiguity Detection Accuracy, Category Classification Accuracy,
Option Quality, and Latency (ms) according to SRS Section 20.2.
"""

import os
import sys
import time
from typing import List, Dict, Any

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database.schema_extractor import get_default_sample_schema
from backend.modules.ambiguity import (
    AmbiguityCategory,
    AmbiguityDetector,
    ambiguity_detector
)

# Golden benchmark evaluation dataset
BENCHMARK_DATASET = [
    # 1. MISSING FILTERS (5 queries)
    {
        "query": "Show passing students",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.MISSING_FILTER,
        "description": "Missing passing score threshold"
    },
    {
        "query": "Show students who passed in exam",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.MISSING_FILTER,
        "description": "Missing passing cutoff mark"
    },
    {
        "query": "Show active students in university",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.MISSING_FILTER,
        "description": "Undefined active status criteria"
    },
    {
        "query": "Show eligible students for scholarship",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.MISSING_FILTER,
        "description": "Undefined eligibility criteria"
    },
    {
        "query": "Show students who failed",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.MISSING_FILTER,
        "description": "Undefined failing threshold score"
    },

    # 2. UNCLEAR COMPARISON CRITERIA (5 queries)
    {
        "query": "Show top students",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNCLEAR_COMPARISON,
        "description": "Unclear student performance measure (marks vs attendance)"
    },
    {
        "query": "Show top performing students",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNCLEAR_COMPARISON,
        "description": "Superlative qualifier without metric cutoff"
    },
    {
        "query": "Show high-value sales",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNCLEAR_COMPARISON,
        "description": "Subjective magnitude lacking monetary threshold"
    },
    {
        "query": "Show students with poor attendance",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNCLEAR_COMPARISON,
        "description": "Qualitative attendance without percentage cutoff"
    },
    {
        "query": "Show star performers in college",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNCLEAR_COMPARISON,
        "description": "Subjective ranking criteria"
    },

    # 3. AMBIGUOUS COLUMN NAMES (5 queries)
    {
        "query": "Show sales from Mumbai",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.AMBIGUOUS_COLUMN,
        "description": "Location matches store_city vs customer_city"
    },
    {
        "query": "Show sales in Delhi",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.AMBIGUOUS_COLUMN,
        "description": "City matches store_city vs customer_city"
    },
    {
        "query": "Show names from the database",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.AMBIGUOUS_COLUMN,
        "description": "Column name in both students and departments"
    },
    {
        "query": "List codes available",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.AMBIGUOUS_COLUMN,
        "description": "Column code in departments and courses"
    },
    {
        "query": "Show the highest sales",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.AMBIGUOUS_COLUMN,
        "description": "Metric sales represents revenue vs units_sold"
    },

    # 4. UNSPECIFIED DATE RANGES (5 queries)
    {
        "query": "Show revenue last year",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNSPECIFIED_DATE_RANGE,
        "description": "Calendar year vs financial year"
    },
    {
        "query": "Show sales this year",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNSPECIFIED_DATE_RANGE,
        "description": "Calendar year vs fiscal year to date"
    },
    {
        "query": "Show recent sales transactions",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNSPECIFIED_DATE_RANGE,
        "description": "Vague temporal interval without lookback window"
    },
    {
        "query": "Show sales recently",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNSPECIFIED_DATE_RANGE,
        "description": "Unspecified lookback timeframe"
    },
    {
        "query": "Show revenue this quarter",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNSPECIFIED_DATE_RANGE,
        "description": "Calendar quarter vs fiscal quarter"
    },

    # 5. UNCLEAR AGGREGATION FUNCTIONS (5 queries)
    {
        "query": "Show sales by store city",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNCLEAR_AGGREGATION,
        "description": "Grouped sales without SUM, AVG, COUNT"
    },
    {
        "query": "Show revenue per department",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNCLEAR_AGGREGATION,
        "description": "Grouped revenue without aggregation function"
    },
    {
        "query": "Show student marks per course",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNCLEAR_AGGREGATION,
        "description": "Grouped scores without AVG vs SUM vs MAX"
    },
    {
        "query": "Show attendance by department",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNCLEAR_AGGREGATION,
        "description": "Grouped attendance without AVG or MIN"
    },
    {
        "query": "Show salary by department",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNCLEAR_AGGREGATION,
        "description": "Grouped salary without AVG or SUM"
    },

    # 6. AMBIGUOUS TABLE RELATIONSHIPS (5 queries)
    {
        "query": "Show students in Computer Science department",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.AMBIGUOUS_RELATIONSHIP,
        "description": "Major declaration vs Course enrollment join path"
    },
    {
        "query": "Which students are associated with Mathematics department?",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.AMBIGUOUS_RELATIONSHIP,
        "description": "Multiple relationship paths between students and departments"
    },
    {
        "query": "Show students affiliated with Physics department",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.AMBIGUOUS_RELATIONSHIP,
        "description": "Major vs course association"
    },
    {
        "query": "Show students under Engineering department",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.AMBIGUOUS_RELATIONSHIP,
        "description": "Major vs course affiliation"
    },
    {
        "query": "Show students in Data Science department",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.AMBIGUOUS_RELATIONSHIP,
        "description": "Major link vs marks-courses link"
    },

    # 7. UNSPECIFIED SORTING AND GROUPING (5 queries)
    {
        "query": "Show top 5 courses",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNSPECIFIED_SORT_GROUP,
        "description": "Limit 5 without sort metric (enrollment vs credits vs score)"
    },
    {
        "query": "Show first 10 courses",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNSPECIFIED_SORT_GROUP,
        "description": "Limit without ORDER BY criterion"
    },
    {
        "query": "Break down sales over time",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNSPECIFIED_SORT_GROUP,
        "description": "Time trend without grouping granularity"
    },
    {
        "query": "Show sales trend over time",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNSPECIFIED_SORT_GROUP,
        "description": "Unbucketed time grouping"
    },
    {
        "query": "Sort students by marks",
        "expected_ambiguous": True,
        "expected_category": AmbiguityCategory.UNSPECIFIED_SORT_GROUP,
        "description": "Sort without direction (ASC vs DESC)"
    },

    # 8. UNAMBIGUOUS QUERIES (10 queries)
    {
        "query": "How many students are enrolled?",
        "expected_ambiguous": False,
        "expected_category": AmbiguityCategory.NONE,
        "description": "Direct scalar count query"
    },
    {
        "query": "Show all departments",
        "expected_ambiguous": False,
        "expected_category": AmbiguityCategory.NONE,
        "description": "Direct table projection"
    },
    {
        "query": "Calculate compound interest on 10000 at 5% for 3 years",
        "expected_ambiguous": False,
        "expected_category": AmbiguityCategory.NONE,
        "description": "Self-contained financial calculation"
    },
    {
        "query": "What is the BMI for 70kg and 1.75m?",
        "expected_ambiguous": False,
        "expected_category": AmbiguityCategory.NONE,
        "description": "Self-contained healthcare formula"
    },
    {
        "query": "Convert 100 celsius to fahrenheit",
        "expected_ambiguous": False,
        "expected_category": AmbiguityCategory.NONE,
        "description": "Self-contained STEM temperature conversion"
    },
    {
        "query": "Show students where attendance_percentage > 90 order by name asc",
        "expected_ambiguous": False,
        "expected_category": AmbiguityCategory.NONE,
        "description": "Explicit filter, column, and sort direction"
    },
    {
        "query": "Show total revenue from sales",
        "expected_ambiguous": False,
        "expected_category": AmbiguityCategory.NONE,
        "description": "Explicit metric and explicit aggregation (total)"
    },
    {
        "query": "Show average score in course 201",
        "expected_ambiguous": False,
        "expected_category": AmbiguityCategory.NONE,
        "description": "Explicit aggregation (average) and filter (course 201)"
    },
    {
        "query": "Count of courses in department 1",
        "expected_ambiguous": False,
        "expected_category": AmbiguityCategory.NONE,
        "description": "Explicit count and department filter"
    },
    {
        "query": "List all course titles and credits",
        "expected_ambiguous": False,
        "expected_category": AmbiguityCategory.NONE,
        "description": "Unambiguous column projection"
    }
]


def run_benchmark():
    schema = get_default_sample_schema()
    detector = ambiguity_detector

    total = len(BENCHMARK_DATASET)
    detection_correct = 0
    category_correct = 0
    option_quality_correct = 0
    latencies = []

    print("\n" + "=" * 80)
    print("SRS PHASE 10: AMBIGUITY DETECTION BENCHMARK & EVALUATION SUITE")
    print("=" * 80)
    print(f"Total Evaluation Test Cases: {total}")
    print(f"Categories Tested: 7 Ambiguity Types + Unambiguous Controls\n")

    results = []

    for idx, item in enumerate(BENCHMARK_DATASET, start=1):
        q = item["query"]
        exp_amb = item["expected_ambiguous"]
        exp_cat = item["expected_category"]
        desc = item["description"]

        t0 = time.perf_counter()
        res = detector.detect(q, schema=schema)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(latency_ms)

        det_ok = (res.is_ambiguous == exp_amb)
        if det_ok:
            detection_correct += 1

        cat_ok = (res.primary_ambiguity == exp_cat)
        if cat_ok:
            category_correct += 1

        # Check option quality if ambiguous
        opt_ok = True
        if exp_amb:
            if not res.clarification or len(res.clarification.options) < 2:
                opt_ok = False
            else:
                for opt in res.clarification.options:
                    if not opt.label or not opt.id:
                        opt_ok = False
                        break
        if opt_ok:
            option_quality_correct += 1

        status_flag = "PASS" if (det_ok and cat_ok and opt_ok) else "FAIL"
        results.append({
            "id": idx,
            "query": q,
            "expected_category": exp_cat.value,
            "predicted_category": res.primary_ambiguity.value,
            "latency_ms": latency_ms,
            "status": status_flag
        })

        icon = "✓" if status_flag == "PASS" else "✗"
        print(f"[{icon}] #{idx:02d} | {status_flag} | {latency_ms:.2f}ms | Exp: {exp_cat.value:25s} | Got: {res.primary_ambiguity.value:25s} | \"{q}\"")

    # Metrics computation
    detection_acc = (detection_correct / total) * 100.0
    category_acc = (category_correct / total) * 100.0
    option_quality_rate = (option_quality_correct / total) * 100.0
    avg_latency = sum(latencies) / len(latencies)
    p95_latency = sorted(latencies)[int(0.95 * len(latencies))]

    print("\n" + "=" * 80)
    print("EVALUATION BENCHMARK SCORECARD")
    print("=" * 80)
    print(f"• Total Evaluation Queries     : {total}")
    print(f"• Ambiguity Detection Accuracy : {detection_acc:.1f}% ({detection_correct}/{total})")
    print(f"• Category Classification Acc  : {category_acc:.1f}% ({category_correct}/{total})")
    print(f"• Option Quality & Resolution  : {option_quality_rate:.1f}% ({option_quality_correct}/{total})")
    print(f"• Average Detection Latency    : {avg_latency:.2f} ms")
    print(f"• 95th Percentile Latency      : {p95_latency:.2f} ms")
    print("=" * 80)

    assert detection_acc == 100.0, f"Expected 100% detection accuracy, got {detection_acc}%"
    assert category_acc == 100.0, f"Expected 100% category classification accuracy, got {category_acc}%"
    assert avg_latency < 5.0, f"Expected sub-5ms detection latency, got {avg_latency:.2f}ms"
    print("\nBENCHMARK CRITERIA SATISFIED: 100% ACCURACY AT SUB-5MS LATENCY!\n")


if __name__ == "__main__":
    run_benchmark()

