import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database.schema_extractor import DatabaseSchema, TableMeta, ColumnMeta, get_default_sample_schema
from backend.modules.nlp_engine import local_nlp_engine
from backend.modules.learning_engine import learning_engine
from backend.modules.validator import SQLValidator


def _build_global_enterprise_schema() -> DatabaseSchema:
    base = get_default_sample_schema()
    ge_cols = [
        ("order_id", "INTEGER", True),
        ("order_date", "TEXT", False),
        ("ship_date", "TEXT", False),
        ("ship_mode", "TEXT", False),
        ("transit_days", "INTEGER", False),
        ("customer_id", "INTEGER", False),
        ("customer_name", "TEXT", False),
        ("segment", "TEXT", False),
        ("age_group", "TEXT", False),
        ("gender", "TEXT", False),
        ("country", "TEXT", False),
        ("region", "TEXT", False),
        ("state_province", "TEXT", False),
        ("city", "TEXT", False),
        ("postal_code", "TEXT", False),
        ("regional_manager", "TEXT", False),
        ("product_id", "INTEGER", False),
        ("category", "TEXT", False),
        ("sub_category", "TEXT", False),
        ("product_name", "TEXT", False),
        ("unit_cost", "REAL", False),
        ("unit_price", "REAL", False),
        ("quantity", "INTEGER", False),
        ("gross_sales", "REAL", False),
        ("discount_pct", "REAL", False),
        ("discount_amount", "REAL", False),
        ("net_sales", "REAL", False),
        ("total_cost", "REAL", False),
        ("gross_profit", "REAL", False),
        ("profit_margin_pct", "REAL", False),
        ("shipping_cost", "REAL", False),
        ("net_profit", "REAL", False),
        ("order_status", "TEXT", False),
        ("return_reason", "TEXT", False),
        ("customer_rating", "REAL", False),
        ("payment_method", "TEXT", False),
    ]
    base.tables["global_enterprise"] = TableMeta(
        name="global_enterprise",
        description="Uploaded global enterprise sales dataset",
        primary_keys=["order_id"],
        columns=[ColumnMeta(name=n, data_type=t, is_primary_key=pk) for n, t, pk in ge_cols]
    )
    return base


def test_top3_products_with_metrics_and_sorted_countries():
    schema = _build_global_enterprise_schema()
    q = "Give Top 3 products with their highest net sales,total revenue sorted by countries (give figures for each)"
    sql, _ = local_nlp_engine.generate_sql(q, schema=schema)
    s_low = sql.lower()

    assert "global_enterprise" in s_low, f"Must select global_enterprise over sarah_products, got: {sql}"
    assert "product_name" in s_low, f"Missing product_name in {sql}"
    assert "country" in s_low, f"Missing country in {sql}"
    assert "net_sales" in s_low, f"Missing net_sales figure in {sql}"
    assert ("gross_sales" in s_low or "total_revenue" in s_low or "net_sales" in s_low), f"Missing revenue figure in {sql}"
    assert "limit 3" in s_low

    val = SQLValidator.validate(sql, known_tables=schema.get_known_tables_dict(), dialect="sqlite")
    assert val.is_valid, f"SQL failed validation: {val.errors} | SQL: {sql}"


def test_explicit_column_and_figure_retrieval():
    schema = _build_global_enterprise_schema()

    # 1. Explicit list of mixed text and numeric columns
    q1 = "Retrieve figures from the dataset for product_name, category, country, unit_price, net_sales, net_profit"
    sql1, _ = local_nlp_engine.generate_sql(q1, schema=schema)
    s1 = sql1.lower()
    for col in ["product_name", "category", "country", "unit_price", "net_sales", "net_profit"]:
        assert col in s1, f"Prompted column '{col}' missing in: {sql1}"

    # 2. Only text label columns named + 'give figures' -> must auto-include numeric figures!
    q2 = "Show product_name and category from sarah_products (give figures for each)"
    sql2, _ = local_nlp_engine.generate_sql(q2, schema=get_default_sample_schema())
    s2 = sql2.lower()
    assert "product_name" in s2
    assert "category" in s2
    assert ("unit_price" in s2 or "inventory_count" in s2), f"Numeric figures omitted in: {sql2}"


def test_summary_includes_numeric_figures_and_no_table_cross_poisoning():
    schema = _build_global_enterprise_schema()
    q = "Show summary and sample rows from global_enterprise"

    # Verify learning_engine does not replay an unrelated 'ipl' table sample
    match = learning_engine.find_similar_sample(q, threshold=0.90, allowed_tables=list(schema.tables.keys()))
    if match:
        assert "global_enterprise" in [t.lower() for t in match.tables_used]

    sql, _ = local_nlp_engine.generate_sql(q, schema=schema)
    s_low = sql.lower()
    assert "global_enterprise" in s_low
    assert any(num_col in s_low for num_col in ["net_sales", "gross_sales", "unit_price", "net_profit", "unit_cost", "quantity"]), \
        f"Summary omitted all numeric figures: {sql}"

