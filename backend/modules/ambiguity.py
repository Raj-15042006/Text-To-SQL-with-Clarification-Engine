import re
import logging
from enum import Enum
from typing import List, Optional, Dict, Any, Set, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class AmbiguityCategory(str, Enum):
    # Core categories requested
    MISSING_FILTER = "missing_filter"
    UNCLEAR_COMPARISON = "unclear_comparison"
    AMBIGUOUS_COLUMN = "ambiguous_column"
    UNSPECIFIED_DATE_RANGE = "unspecified_date_range"
    UNCLEAR_AGGREGATION = "unclear_aggregation"
    AMBIGUOUS_RELATIONSHIP = "ambiguous_relationship"
    UNSPECIFIED_SORT_GROUP = "unspecified_sort_group"

    # Backward compatibility aliases
    METRIC = "metric"              # e.g., "sales" -> revenue, units sold, or transaction count
    ENTITY = "entity"              # e.g., "Mumbai" -> customer city, store location, or shipping origin
    TIME = "time"                  # e.g., "recent", "last year" -> calendar year vs financial year
    FILTER = "filter"              # e.g., "top students", "high-value" -> what cutoff or threshold?
    AGGREGATION = "aggregation"    # e.g., total vs average vs count
    RELATIONSHIP = "relationship"  # e.g., multiple join paths between tables
    SCOPE = "scope"                # e.g., all records vs specific category/department
    NONE = "none"                  # No material ambiguity detected

class ClarificationOption(BaseModel):
    id: str = Field(description="Unique short identifier for the option, e.g. 'opt_revenue'")
    label: str = Field(description="Human-readable label displayed as a choice, e.g. 'Total Revenue (Sum of total_amount)'")
    description: Optional[str] = Field(default=None, description="Brief explanation of what this option implies")
    implied_filter_or_metric: Optional[str] = Field(default=None, description="The concrete metric, column, or filter mapped to this option")
    estimated_rows: Optional[int] = Field(default=None, description="Estimated What-If matching row count preview")

class ClarificationRequest(BaseModel):
    question: str = Field(description="Clear, concise clarification question directed to the user")
    ambiguity_type: AmbiguityCategory = Field(description="The primary category of ambiguity being resolved")
    options: List[ClarificationOption] = Field(default_factory=list, description="List of concrete, selectable options")
    allow_free_text: bool = Field(default=True, description="Whether the user can provide custom input")

class AmbiguityIssue(BaseModel):
    category: AmbiguityCategory = Field(description="The specific category of ambiguity")
    issue: str = Field(description="Summary of the ambiguity detected")
    description: str = Field(description="Detailed explanation of why this is ambiguous")
    details_summary: Optional[str] = Field(default=None, description="Metadata summary such as candidate columns, tables, or terms")
    suggested_question: Optional[str] = Field(default=None, description="Suggested clarification question")
    suggested_options: List[ClarificationOption] = Field(default_factory=list, description="Candidate options to resolve the ambiguity")

    def __init__(self, **data):
        if "details" in data and "details_summary" not in data:
            d = data.pop("details")
            data["details_summary"] = str(d) if d else None
        super().__init__(**data)

class AmbiguityDetectionResult(BaseModel):
    is_ambiguous: bool = Field(default=False, description="True if any material ambiguity was detected")
    primary_ambiguity: AmbiguityCategory = Field(default=AmbiguityCategory.NONE, description="Primary ambiguity category")
    issues: List[AmbiguityIssue] = Field(default_factory=list, description="All detected ambiguity issues")
    clarification: Optional[ClarificationRequest] = Field(default=None, description="Recommended clarification request")
    missing_information: Optional[str] = Field(default=None, description="Summary of missing information")

    def to_query_analysis(self, user_query: str) -> "QueryAnalysis":
        return QueryAnalysis(
            intent=f"Resolve analytical query: {user_query}",
            is_ambiguous=self.is_ambiguous,
            ambiguity_type=self.primary_ambiguity,
            detected_ambiguities=self.issues,
            missing_information=self.missing_information,
            clarification=self.clarification
        )

class QueryAnalysis(BaseModel):
    intent: str = Field(description="Summary of the user's analytical goal")
    is_ambiguous: bool = Field(description="True if the query lacks essential constraints or has multiple plausible interpretations")
    ambiguity_type: AmbiguityCategory = Field(default=AmbiguityCategory.NONE, description="Type of ambiguity detected if is_ambiguous is True")
    detected_ambiguities: List[AmbiguityIssue] = Field(default_factory=list, description="All specific ambiguities identified in the query")
    missing_information: Optional[str] = Field(default=None, description="Explanation of what specific information is missing or ambiguous")
    clarification: Optional[ClarificationRequest] = Field(default=None, description="The clarification prompt to present to the user if is_ambiguous is True")
    detected_entities: List[str] = Field(default_factory=list, description="Key real-world entities identified in the query, e.g., ['students', 'marks']")
    suggested_tables: List[str] = Field(default_factory=list, description="Database tables likely needed for this query")
    metric: Optional[str] = Field(default=None, description="Primary metric or column to aggregate/measure")
    filters: List[str] = Field(default_factory=list, description="Explicit filters identified in the user query")
    grouping: List[str] = Field(default_factory=list, description="Grouping dimensions identified")
    ordering: Optional[str] = Field(default=None, description="Ordering constraints (e.g. DESC by total_marks)")
    generated_sql: Optional[str] = Field(default=None, description="PostgreSQL SQL query if is_ambiguous is False. Must be SELECT-only using valid schema tables.")
    sql_explanation: Optional[str] = Field(default=None, description="Brief rationale for the SQL structure if is_ambiguous is False")


class AmbiguityDetector:
    """
    Comprehensive, schema-aware ambiguity detector for natural language Text-to-SQL.
    Identifies 7 distinct categories of ambiguity:
      1. Missing filters
      2. Unclear comparison criteria
      3. Ambiguous column names
      4. Unspecified date ranges
      5. Unclear aggregation functions
      6. Ambiguous table relationships
      7. Unspecified sorting and grouping
    """

    # Standalone math/domain calculation indicators that never need database tables
    FORMULA_PATTERNS = [
        re.compile(r"\b(emi|loan\s+emi|monthly\s+installment|mortgage)\b", re.I),
        re.compile(r"\b(compound\s+interest|simple\s+interest|cagr|future\s+value|roi|return\s+on\s+investment|profit\s+margin|markup|rule\s+of\s+72|doubling\s+time)\b", re.I),
        re.compile(r"\b(net\s+run\s+rate|nrr|batting\s+strike\s+rate|bowling\s+economy|bowling\s+strike\s+rate|required\s+run\s+rate|rrr)\b", re.I),
        re.compile(r"\b(bmi|body\s+mass\s+index|basal\s+metabolic\s+rate|bmr|mean\s+arterial\s+pressure|heart\s+rate|target\s+hr|max\s+hr|karvonen)\b", re.I),
        re.compile(r"\b(kinetic\s+energy|potential\s+energy|ohm'?s?\s+law|half-life|voltage|resistance|newton'?s?\s+second\s+law|f\s*=\s*ma|density|pressure|work\s+done|mass\s+energy|e\s*=\s*mc)\b", re.I),
        re.compile(r"\b(area\s+of\s+circle|circumference\s+of\s+circle|circle\s+with\s+radius|volume\s+of\s+sphere|volume\s+of\s+cylinder|volume\s+of\s+cone|area\s+of\s+triangle|hypotenuse|pythagor|area\s+of\s+rectangle|trapezoid|ellipse)\b", re.I),
        re.compile(r"\b(standard\s+deviation|variance|z[-_ ]?score|pearson\s+correlation|linear\s+regression|bayes\b|covariance|r[-_ ]?squared)\b", re.I),
        re.compile(r"\b(sharpe\s+ratio|capm|wacc|npv|p/e\s+ratio|dividend\s+yield|cac\b|ltv\b|runway|monthly\s+burn|break[- ]even|inventory\s+turnover|eoq\b)\b", re.I),
        re.compile(r"\b(haversine|great[- ]circle|population\s+density|map\s+scale|solar\s+elevation)\b", re.I),
        re.compile(r"\b(box\s+office|streaming\s+completion|drop[- ]off\s+rate)\b", re.I),
        re.compile(r"\b(true\s+shooting|ts%|effective\s+field\s+goal|efg%|earned\s+run\s+average|era\b|batting\s+avg|running\s+pace)\b", re.I),
        re.compile(r"\bconvert\s+\d+(?:\.\d+)?\s*(?:celsius|fahrenheit|kelvin|km|miles|meters|feet|inches|cm|kg|lbs|pounds|grams|ounces|liters|gallons|kmh|mph|bar|psi|atm|kpa|joules|calories|kwh)\b", re.I),
        re.compile(r"\b(?:\d+(?:\.\d+)?\s*(?:%|percent)\s*(?:of)\s*\d+|\d+\s+is\s+what\s+percent|\bpercent(?:age)?\s+(?:change|increase|decrease|growth)\s+from\b)", re.I),
        re.compile(r"\b(calculate|compute|evaluate|what\s+is)\s+[\d\.\+\-\*\/\^\(\)\s%a-zA-Z_,]+$", re.I),
    ]

    def _is_standalone_calculation(self, query: str) -> bool:
        """Determines if the query is a pure self-contained mathematical or domain formula calculation."""
        try:
            from backend.modules.formula_engine import formula_engine
            if formula_engine.can_handle(query):
                return True
        except Exception:
            pass

        # Must contain digits
        if not re.search(r"\d+", query):
            return False
        for pat in self.FORMULA_PATTERNS:
            if pat.search(query):
                return True
        return False

    def _has_explicit_numeric_threshold(self, query: str) -> bool:
        """Checks if the query already includes a concrete numeric comparison threshold (e.g. > 80, >= 50)."""
        return bool(re.search(
            r"([><]=?|!=|=|\babove\b|\bover\b|\bgreater\s+than\b|\bmore\s+than\b|\bless\s+than\b|\bbelow\b|\bunder\b|\bexceeding\b)\s*\$?\s*\d+",
            query,
            re.I
        ) or re.search(r"\bbetween\s+\d+\s+and\s+\d+\b", query, re.I))

    def _has_explicit_aggregation(self, query: str) -> bool:
        """Checks if the query already specifies an explicit aggregation operation."""
        return bool(re.search(
            r"\b(total|sum\b|overall|average\b|avg\b|mean\b|count\b|number\s+of|how\s+many|maximum|max\b|highest|peak|minimum|min\b|lowest)\b",
            query,
            re.I
        ))

    # =========================================================================
    # 1. MISSING FILTERS
    # =========================================================================
    def check_missing_filters(self, query: str, schema: Optional[Any] = None) -> Optional[AmbiguityIssue]:
        """
        Identifies queries where filtering criteria are missing or unspecified:
        - Passing/failing criteria without a score threshold.
        - Active/inactive status without definition.
        - Broad operations or queries requiring filtering predicates.
        """
        q_lower = query.lower()

        # Check for passing / failing without explicit cutoff score
        if re.search(r"\b(passing|passed|pass|failing|failed|fail)\b", q_lower):
            if not self._has_explicit_numeric_threshold(query):
                return AmbiguityIssue(
                    category=AmbiguityCategory.MISSING_FILTER,
                    issue="Passing/failing score threshold is not specified.",
                    description="The query asks for passing or failing records but does not specify the qualifying threshold score (e.g. >= 40, >= 50, or >= 60).",
                    details={"matched_term": "passing/failing criteria"},
                    suggested_question="What minimum score defines a passing mark?",
                    suggested_options=[
                        ClarificationOption(id="opt_pass_40", label="Passing mark >= 40 (Minimum Pass)", implied_filter_or_metric="score >= 40"),
                        ClarificationOption(id="opt_pass_50", label="Passing mark >= 50 (Standard Pass)", implied_filter_or_metric="score >= 50"),
                        ClarificationOption(id="opt_pass_60", label="Passing mark >= 60 (First-Class Pass)", implied_filter_or_metric="score >= 60"),
                        ClarificationOption(id="opt_pass_all", label="All students regardless of score", implied_filter_or_metric="1=1")
                    ]
                )

        # Check for active / inactive / eligible status without explicit filter
        match_active = re.search(r"\b(active|inactive|eligible)\s+(students?|users?|customers?|accounts?|members?)\b", q_lower)
        if match_active:
            status_word = match_active.group(1)
            entity_word = match_active.group(2)
            return AmbiguityIssue(
                category=AmbiguityCategory.MISSING_FILTER,
                issue=f"Criteria for '{status_word}' {entity_word} is unspecified.",
                description=f"The database records {entity_word}, but no explicit filter defines what constitutes an '{status_word}' record.",
                details={"status": status_word, "entity": entity_word},
                suggested_question=f"How should '{status_word}' {entity_word} be identified?",
                suggested_options=[
                    ClarificationOption(id="opt_act_recent", label="Enrolled in the latest academic year", implied_filter_or_metric="enrollment_year = 2024"),
                    ClarificationOption(id="opt_act_attendance", label="Attendance rate >= 75%", implied_filter_or_metric="attendance_percentage >= 75"),
                    ClarificationOption(id="opt_act_all", label=f"All registered {entity_word}", implied_filter_or_metric="id IS NOT NULL")
                ]
            )

        # Dynamic order_status scope check when order_status exists in active schema
        if schema and hasattr(schema, "tables"):
            status_tables = [
                t_name for t_name, t_meta in schema.tables.items()
                if any(c.name.lower() in ("order_status", "status") for c in t_meta.columns)
            ]
            if status_tables and re.search(r"\b(valid\s+orders?|completed\s+orders?|how\s+many\s+orders?|total\s+orders?|orders?\s+by\s+[a-z_]+)\b", q_lower):
                if not any(k in q_lower for k in ("cancelled", "canceled", "returned", "pending", "shipped", "delivered", "all status", "status =", "regardless")):
                    target_tbl = status_tables[0]
                    status_col = next(
                        c.name for c in schema.tables[target_tbl].columns
                        if c.name.lower() in ("order_status", "status")
                    )
                    return AmbiguityIssue(
                        category=AmbiguityCategory.MISSING_FILTER,
                        issue=f"Order status filter scope on '{target_tbl}.{status_col}' is unspecified.",
                        description=f"The '{target_tbl}' table includes '{status_col}' values (such as Completed, Cancelled, Returned). Clarify whether to exclude cancelled/returned rows.",
                        details={"table": target_tbl, "column": status_col},
                        suggested_question=f"Which '{status_col}' records should be included?",
                        suggested_options=[
                            ClarificationOption(
                                id="opt_ord_completed",
                                label=f"Completed / fulfilled orders only (exclude Cancelled & Returned)",
                                implied_filter_or_metric=f"{status_col} NOT IN ('Cancelled', 'Returned')"
                            ),
                            ClarificationOption(
                                id="opt_ord_all",
                                label="All orders regardless of status",
                                implied_filter_or_metric="1=1"
                            )
                        ]
                    )

        # Check for destructive statement missing WHERE clause
        if re.search(r"^\s*(delete|remove|truncate|drop|update)\b", q_lower):
            if "where" not in q_lower:
                return AmbiguityIssue(
                    category=AmbiguityCategory.MISSING_FILTER,
                    issue="Missing WHERE filter condition on modification operation.",
                    description="Modification operations require an explicit WHERE filter to prevent modifying entire tables.",
                    details={"operation": "mutation_without_filter"},
                    suggested_question="Please provide the specific filter condition (WHERE clause) to target records:",
                    suggested_options=[
                        ClarificationOption(id="opt_flt_id", label="Filter by specific ID", implied_filter_or_metric="WHERE id = ..."),
                        ClarificationOption(id="opt_flt_dept", label="Filter by Department", implied_filter_or_metric="WHERE department_id = ...")
                    ]
                )

        return None

    # =========================================================================
    # 2. UNCLEAR COMPARISON CRITERIA
    # =========================================================================
    def check_unclear_comparison(self, query: str, schema: Optional[Any] = None) -> Optional[AmbiguityIssue]:
        """
        Identifies queries with subjective or comparative qualifiers lacking explicit measurement criteria:
        - "top students", "best students", "star performers", "worst students"
        - "high-value", "high spending", "large orders", "low value"
        - "poor attendance", "good attendance"
        """
        q_lower = query.lower()

        # If explicit numeric cutoff or threshold is already present, comparison is clear
        if self._has_explicit_numeric_threshold(query):
            return None

        # Check for top/best/worst performance
        match_perf = re.search(r"\b(top|best|star|worst|lowest|underperforming|highest)(\s+performing)?\s+(students?|performers?|performances?)\b", q_lower)
        if match_perf:
            # If query already specifies the metric (e.g. "top students by attendance" or "top students by score"), it's clear
            if not any(k in q_lower for k in ["by score", "by marks", "by attendance", "by gpa", "by grade"]):
                return AmbiguityIssue(
                    category=AmbiguityCategory.UNCLEAR_COMPARISON,
                    issue="Unclear performance measurement criteria for students.",
                    description="It is unclear whether student performance should be ranked by total marks, average percentage, or attendance rate.",
                    details={"target": "student_performance"},
                    suggested_question="How should student performance be measured?",
                    suggested_options=[
                        ClarificationOption(id="opt_total_score", label="Total Marks (Sum of scores across all courses)", implied_filter_or_metric="SUM(score)"),
                        ClarificationOption(id="opt_avg_score", label="Average Marks (Mean percentage across courses)", implied_filter_or_metric="AVG(score)"),
                        ClarificationOption(id="opt_attendance", label="Attendance Percentage (Highest attendance)", implied_filter_or_metric="attendance_percentage"),
                        ClarificationOption(id="opt_grade_a", label="Grade A achievements", implied_filter_or_metric="grade = 'A'")
                    ]
                )

        # Check for high-value / large sales without monetary threshold
        match_high_val = re.search(r"\b(high[- ]value|high[- ]spending|large|big|valuable|low[- ]value|small)\s+(sales?|orders?|transactions?|customers?|purchases?)\b", q_lower)
        if match_high_val:
            term = match_high_val.group(1)
            entity = match_high_val.group(2)
            return AmbiguityIssue(
                category=AmbiguityCategory.UNCLEAR_COMPARISON,
                issue=f"Monetary cutoff threshold for '{term}' {entity} is unspecified.",
                description=f"The query asks for '{term}' {entity} without defining a specific monetary or volume threshold.",
                details={"term": term, "entity": entity},
                suggested_question=f"What threshold defines '{term}' {entity}?",
                suggested_options=[
                    ClarificationOption(id="opt_val_1000", label="Revenue > $1,000", implied_filter_or_metric="revenue > 1000"),
                    ClarificationOption(id="opt_val_5000", label="Revenue > $5,000", implied_filter_or_metric="revenue > 5000"),
                    ClarificationOption(id="opt_val_10000", label="Revenue > $10,000", implied_filter_or_metric="revenue > 10000"),
                    ClarificationOption(id="opt_val_top10", label="Top 10% highest transactions", implied_filter_or_metric="top 10 percent")
                ]
            )

        # Check for poor / good attendance
        match_att = re.search(r"\b(poor|low|bad|good|high)\s+attendance\b", q_lower)
        if match_att:
            adj = match_att.group(1)
            is_low = adj in ("poor", "low", "bad")
            return AmbiguityIssue(
                category=AmbiguityCategory.UNCLEAR_COMPARISON,
                issue=f"No percentage threshold defined for '{adj} attendance'.",
                description=f"The cutoff percentage for '{adj} attendance' is not specified.",
                details={"attribute": "attendance_percentage", "qualifier": adj},
                suggested_question=f"What percentage threshold defines '{adj} attendance'?",
                suggested_options=[
                    ClarificationOption(id="opt_att_75", label="Attendance < 75%" if is_low else "Attendance >= 75%", implied_filter_or_metric="attendance_percentage < 75" if is_low else "attendance_percentage >= 75"),
                    ClarificationOption(id="opt_att_60", label="Attendance < 60%" if is_low else "Attendance >= 85%", implied_filter_or_metric="attendance_percentage < 60" if is_low else "attendance_percentage >= 85"),
                    ClarificationOption(id="opt_att_50", label="Attendance < 50%" if is_low else "Attendance >= 90%", implied_filter_or_metric="attendance_percentage < 50" if is_low else "attendance_percentage >= 90")
                ]
            )

        # Metric definition ambiguity (Section 2: churn, retention, conversion rate, etc.)
        m_def = re.search(r"\b(churn(?:\s+rate)?|retention(?:\s+rate)?|conversion(?:\s+rate)?)\b", q_lower)
        if m_def and not any(k in q_lower for k in ("defined as", "using ", "inactivity", "cancelled", "canceled", "formula")):
            metric_phrase = m_def.group(1)
            schema_cols = set()
            if schema and hasattr(schema, "tables"):
                for t_meta in schema.tables.values():
                    schema_cols.update(c.name.lower() for c in t_meta.columns)
            if metric_phrase.replace(" ", "_") not in schema_cols:
                return AmbiguityIssue(
                    category=AmbiguityCategory.UNCLEAR_COMPARISON,
                    issue=f"Domain definition for metric '{metric_phrase}' is ambiguous.",
                    description=f"'{metric_phrase}' can mean explicit cancellation status, 30-day inactivity, or net repeat activity.",
                    details={"metric_term": metric_phrase},
                    suggested_question=f"How is '{metric_phrase}' defined in your business logic?",
                    suggested_options=[
                        ClarificationOption(
                            id="opt_def_cancel",
                            label="Explicit Cancelled / Returned status records",
                            implied_filter_or_metric="order_status = 'Cancelled'"
                        ),
                        ClarificationOption(
                            id="opt_def_inactivity_30",
                            label="No activity / orders in the last 30 days",
                            implied_filter_or_metric="days_since_last_order > 30"
                        ),
                        ClarificationOption(
                            id="opt_def_repeat",
                            label="Customers / entities with repeat activity (>= 2 records)",
                            implied_filter_or_metric="COUNT(*) >= 2"
                        )
                    ]
                )

        return None

    # =========================================================================
    # 3. AMBIGUOUS COLUMN NAMES
    # =========================================================================
    def check_ambiguous_columns(self, query: str, schema: Optional[Any] = None) -> Optional[AmbiguityIssue]:
        """
        Identifies queries referencing column names or attributes that map to multiple candidate fields:
        - City / Location ambiguity (e.g., store_city vs customer_city vs students.city)
        - Column 'name' occurring in multiple tables (e.g. students.name vs departments.name)
        - Column 'code' occurring in departments.code vs courses.code
        - Metric 'sales' matching revenue vs units_sold
        """
        q_lower = query.lower()

        # 1. Location / City Ambiguity (SRS Section 4 & Appendix A)
        # Check if query mentions a location/city or "city" in context of sales
        known_cities = ["mumbai", "delhi", "pune", "bangalore", "bengaluru", "kolkata", "chennai", "hyderabad", "new york", "chicago", "london", "paris"]
        found_city = None
        for c in known_cities:
            if re.search(rf"\b{c}\b", q_lower):
                found_city = c.title()
                break

        has_sales_context = any(w in q_lower for w in ["sale", "sales", "revenue", "transaction", "unit"])
        
        # If user explicitly specified "store" or "customer", it is already disambiguated
        user_specified_store = bool(re.search(r"\b(store|branch|outlet)\b", q_lower))
        user_specified_customer = bool(re.search(r"\b(customer|client|buyer)\b", q_lower))
        
        # Check if the schema actually contains both store_city and customer_city
        has_both_city_columns = True
        if schema and hasattr(schema, "tables"):
            sales_tbl = schema.tables.get("sales")
            if sales_tbl:
                cols = {c.name.lower() for c in sales_tbl.columns}
                has_both_city_columns = ("store_city" in cols and "customer_city" in cols)
            else:
                has_both_city_columns = False

        if not (user_specified_store or user_specified_customer) and has_both_city_columns:
            if (found_city and has_sales_context) or (re.search(r"\b(by|in|from|for)\s+city\b", q_lower) and has_sales_context):
                loc_label = found_city or "the specified city"
                return AmbiguityIssue(
                    category=AmbiguityCategory.AMBIGUOUS_COLUMN,
                    issue=f"Location '{loc_label}' could refer to store location or customer residence.",
                    description=f"The database has both 'store_city' (store location) and 'customer_city' (customer residence).",
                    details={"candidates": ["store_city", "customer_city"], "location": loc_label},
                    suggested_question=f"Does '{loc_label}' refer to the store location or customer location?",
                    suggested_options=[
                        ClarificationOption(
                            id="opt_store_city",
                            label="Store City (Physical store location)",
                            implied_filter_or_metric=f"store_city = '{loc_label}'" if found_city else "store_city"
                        ),
                        ClarificationOption(
                            id="opt_customer_city",
                            label="Customer City (Customer shipping/billing location)",
                            implied_filter_or_metric=f"customer_city = '{loc_label}'" if found_city else "customer_city"
                        )
                    ]
                )

        # 2. General Sales metric ambiguity (revenue vs units_sold)
        if re.search(r"\b(highest\s+sales?|top\s+sales?|maximum\s+sales?|best\s+sales?)\b", q_lower) or re.search(r"^(show|list|get)\s+(the\s+)?sales?\s*$", q_lower):
            if not any(k in q_lower for k in ["revenue", "units", "transaction_count", "units_sold"]):
                return AmbiguityIssue(
                    category=AmbiguityCategory.AMBIGUOUS_COLUMN,
                    issue="'Sales' could refer to total monetary revenue or units sold.",
                    description="The sales table tracks both 'revenue' (monetary amount) and 'units_sold' (physical item count).",
                    details={"candidates": ["revenue", "units_sold"]},
                    suggested_question="How should sales be measured?",
                    suggested_options=[
                        ClarificationOption(id="opt_rev", label="Total Revenue (Monetary value in `revenue`)", implied_filter_or_metric="revenue"),
                        ClarificationOption(id="opt_units", label="Units Sold (Product volume in `units_sold`)", implied_filter_or_metric="units_sold"),
                        ClarificationOption(id="opt_tx_cnt", label="Transaction Count (Number of completed sales)", implied_filter_or_metric="COUNT(transaction_id)")
                    ]
                )

        # 3. Duplicate column name across tables: 'name' or 'code'
        if re.search(r"\b(show|list|get|display|select)\s+(the\s+)?(names?|codes?)\b", q_lower) and not re.search(r"\b(student\s+name|department\s+name|course\s+name|course\s+title)\b", q_lower):
            target_col = "name" if "name" in q_lower else "code"
            if target_col == "name":
                return AmbiguityIssue(
                    category=AmbiguityCategory.AMBIGUOUS_COLUMN,
                    issue="Ambiguous column 'name' exists in both 'students' and 'departments' tables.",
                    description="Multiple tables have a 'name' column. Please specify which entity's name is requested.",
                    details={"column": "name", "tables": ["students", "departments"]},
                    suggested_question="Which entity's name should be displayed?",
                    suggested_options=[
                        ClarificationOption(id="opt_col_student", label="Student Name (`students.name`)", implied_filter_or_metric="students.name"),
                        ClarificationOption(id="opt_col_dept", label="Department Name (`departments.name`)", implied_filter_or_metric="departments.name")
                    ]
                )
            else:
                return AmbiguityIssue(
                    category=AmbiguityCategory.AMBIGUOUS_COLUMN,
                    issue="Ambiguous column 'code' exists in both 'departments' and 'courses' tables.",
                    description="Both 'departments' and 'courses' contain a 'code' column.",
                    details={"column": "code", "tables": ["departments", "courses"]},
                    suggested_question="Which entity's code should be displayed?",
                    suggested_options=[
                        ClarificationOption(id="opt_col_dept_code", label="Department Code (`departments.code`)", implied_filter_or_metric="departments.code"),
                        ClarificationOption(id="opt_col_course_code", label="Course Code (`courses.code`)", implied_filter_or_metric="courses.code")
                    ]
                )

        return None

    # =========================================================================
    # 4. UNSPECIFIED DATE RANGES
    # =========================================================================
    def check_unspecified_date_ranges(self, query: str, schema: Optional[Any] = None) -> Optional[AmbiguityIssue]:
        """
        Identifies queries with vague temporal expressions or unspecified date intervals:
        - "last year" -> calendar year vs financial/fiscal year
        - "recent" / "recently" -> 7 days, 30 days, or 90 days
        - "last quarter" / "this quarter" -> calendar quarter vs fiscal quarter
        - "over time" without date range
        """
        q_lower = query.lower()

        # 1. Calendar year vs Fiscal year for "last year" / "this year"
        match_yr = re.search(r"\b(last|previous|past|this|current)\s+year\b", q_lower)
        if match_yr:
            yr_term = match_yr.group(0)
            return AmbiguityIssue(
                category=AmbiguityCategory.UNSPECIFIED_DATE_RANGE,
                issue=f"Unspecified whether '{yr_term}' refers to calendar year or financial/fiscal year.",
                description="Calendar years run Jan 1 - Dec 31, while financial/fiscal years run Apr 1 - Mar 31.",
                details={"temporal_phrase": yr_term},
                suggested_question=f"Do you mean the {yr_term} calendar year or financial/fiscal year?",
                suggested_options=[
                    ClarificationOption(id="opt_cal_yr", label="Calendar Year (January 1 - December 31)", implied_filter_or_metric="calendar_year"),
                    ClarificationOption(id="opt_fin_yr", label="Financial Year (April 1 - March 31)", implied_filter_or_metric="financial_year"),
                    ClarificationOption(id="opt_all_time", label="All-time historical records", implied_filter_or_metric="all_time")
                ]
            )

        # 2. "recent" / "recently" / "latest"
        match_rec = re.search(r"\b(recent|recently|lately)\b", q_lower)
        if match_rec:
            return AmbiguityIssue(
                category=AmbiguityCategory.UNSPECIFIED_DATE_RANGE,
                issue="Date range for 'recent' records is not specified.",
                description="The query specifies 'recent' without defining the lookback window.",
                details={"matched_term": match_rec.group(0)},
                suggested_question="What timeframe should be considered 'recent'?",
                suggested_options=[
                    ClarificationOption(id="opt_rec_7d", label="Past 7 days", implied_filter_or_metric="INTERVAL '7 days'"),
                    ClarificationOption(id="opt_rec_30d", label="Past 30 days (Last month)", implied_filter_or_metric="INTERVAL '30 days'"),
                    ClarificationOption(id="opt_rec_90d", label="Past 90 days (Last quarter)", implied_filter_or_metric="INTERVAL '90 days'"),
                    ClarificationOption(id="opt_rec_365d", label="Past 1 year", implied_filter_or_metric="INTERVAL '1 year'")
                ]
            )

        # 3. "quarter"
        match_qtr = re.search(r"\b(last|previous|past|this|current)\s+quarter\b", q_lower)
        if match_qtr:
            q_term = match_qtr.group(0)
            return AmbiguityIssue(
                category=AmbiguityCategory.UNSPECIFIED_DATE_RANGE,
                issue=f"Unclear whether '{q_term}' refers to calendar quarter or fiscal quarter.",
                description="Calendar quarters and fiscal quarters have different starting months.",
                details={"matched_term": q_term},
                suggested_question=f"Should '{q_term}' be evaluated on a calendar quarter or fiscal quarter basis?",
                suggested_options=[
                    ClarificationOption(id="opt_cal_q", label="Calendar Quarter (Q1: Jan-Mar, Q2: Apr-Jun, ...)", implied_filter_or_metric="calendar_quarter"),
                    ClarificationOption(id="opt_fin_q", label="Fiscal Quarter (Q1: Apr-Jun, Q2: Jul-Sep, ...)", implied_filter_or_metric="fiscal_quarter")
                ]
            )

        return None

    # =========================================================================
    # 5. UNCLEAR AGGREGATION FUNCTIONS
    # =========================================================================
    def check_unclear_aggregations(self, query: str, schema: Optional[Any] = None) -> Optional[AmbiguityIssue]:
        """
        Identifies queries asking for numeric metrics broken down by groups or dimensions
        without specifying the aggregation function (SUM, AVG, COUNT, MAX, MIN):
        - "Show sales by store city"
        - "Show revenue per department"
        - "Show student marks per course"
        """
        q_lower = query.lower()

        # If query already specifies an explicit aggregation, it's clear!
        if self._has_explicit_aggregation(query):
            return None

        # Pattern: <metric> by/per/for each <dimension>
        match_grp_metric = re.search(
            r"\b(sales|revenue|marks?|scores?|attendance|salaries?|salary|spending|expenses?)\s+(by|per|for\s+each)\s+([a-zA-Z_]+(?:\s+[a-zA-Z_]+)?)\b",
            q_lower
        )
        if match_grp_metric:
            metric_term = match_grp_metric.group(1)
            prep = match_grp_metric.group(2)
            dim_term = match_grp_metric.group(3)
            return AmbiguityIssue(
                category=AmbiguityCategory.UNCLEAR_AGGREGATION,
                issue=f"Aggregation function for '{metric_term}' {prep} '{dim_term}' is not specified.",
                description=f"When grouping '{metric_term}' by '{dim_term}', the calculation could be SUM (total), AVG (average), COUNT (number of records), or MAX (peak value).",
                details={"metric": metric_term, "dimension": dim_term},
                suggested_question=f"How should '{metric_term}' be aggregated {prep} {dim_term}?",
                suggested_options=[
                    ClarificationOption(id="opt_agg_sum", label=f"Total Sum (`SUM({metric_term})`)", implied_filter_or_metric=f"SUM({metric_term})"),
                    ClarificationOption(id="opt_agg_avg", label=f"Average / Mean (`AVG({metric_term})`)", implied_filter_or_metric=f"AVG({metric_term})"),
                    ClarificationOption(id="opt_agg_count", label="Count of Records (`COUNT(*)`)", implied_filter_or_metric="COUNT(*)"),
                    ClarificationOption(id="opt_agg_max", label=f"Maximum Value (`MAX({metric_term})`)", implied_filter_or_metric=f"MAX({metric_term})")
                ]
            )

        return None

    # =========================================================================
    # 6. AMBIGUOUS TABLE RELATIONSHIPS
    # =========================================================================
    def check_ambiguous_relationships(self, query: str, schema: Optional[Any] = None) -> Optional[AmbiguityIssue]:
        """
        Identifies queries involving tables connected by multiple valid join paths:
        - Students and Departments:
            Path 1: students.department_id = departments.id (Student's Major department)
            Path 2: students -> marks -> courses -> departments (Departments where student took courses)
        - General multiple foreign key links (e.g. billing_address vs shipping_address).
        """
        q_lower = query.lower()

        # Check for students and departments relationship ambiguity
        has_students = any(w in q_lower for w in ["student", "students"])
        has_departments = any(w in q_lower for w in ["department", "departments", "dept", "engineering", "computer science", "mathematics", "physics", "chemistry"])
        
        # When query connects students to departments with words like "in", "associated with", "affiliated", "under"
        if has_students and has_departments and re.search(r"\b(in|associated\s+with|affiliated\s+with|under|taking|majoring)\b", q_lower):
            # If explicit link is already mentioned, skip
            if not ("major" in q_lower or "declared" in q_lower or "course enrollment" in q_lower or "took courses" in q_lower):
                return AmbiguityIssue(
                    category=AmbiguityCategory.AMBIGUOUS_RELATIONSHIP,
                    issue="Multiple relationship join paths connect 'students' and 'departments'.",
                    description="Students can be linked to departments via their declared Major (direct foreign key) or via Course Enrollment (courses taken in that department).",
                    details={"table_a": "students", "table_b": "departments", "paths": ["major", "course_enrollment"]},
                    suggested_question="Which relationship connects students to departments?",
                    suggested_options=[
                        ClarificationOption(
                            id="opt_rel_major",
                            label="Declared Major (Direct affiliation via `students.department_id = departments.id`)",
                            implied_filter_or_metric="students.department_id = departments.id"
                        ),
                        ClarificationOption(
                            id="opt_rel_courses",
                            label="Course Enrollment (Students who took courses offered by the department)",
                            implied_filter_or_metric="students JOIN marks ON students.id = marks.student_id JOIN courses ON marks.course_id = courses.id WHERE courses.department_id = departments.id"
                        )
                    ]
                )

        # Dynamic check: multiple active FKs connecting two tables mentioned in the query
        if schema and hasattr(schema, "tables"):
            pair_fks: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
            for src_t, t_meta in schema.tables.items():
                for fk in getattr(t_meta, "foreign_keys", []) or []:
                    if not fk.get("is_active", True):
                        continue
                    ref = str(fk.get("references", ""))
                    if "." not in ref:
                        continue
                    tgt_t, tgt_c = ref.split(".", 1)
                    if tgt_t not in schema.tables:
                        continue
                    pair_fks.setdefault((src_t, tgt_t), []).append({
                        "src_table": src_t,
                        "src_col": fk.get("column"),
                        "tgt_table": tgt_t,
                        "tgt_col": tgt_c
                    })

            for (src_t, tgt_t), edges in pair_fks.items():
                if len(edges) >= 2:
                    src_stem = src_t.lower().rstrip("s")
                    tgt_stem = tgt_t.lower().rstrip("s")
                    if (src_t.lower() in q_lower or src_stem in q_lower) and (tgt_t.lower() in q_lower or tgt_stem in q_lower):
                        explicitly_chosen = any(str(e["src_col"]).lower() in q_lower for e in edges)
                        if not explicitly_chosen:
                            opts = [
                                ClarificationOption(
                                    id=f"opt_fk_{idx}",
                                    label=f"Join via `{e['src_table']}.{e['src_col']}` -> `{e['tgt_table']}.{e['tgt_col']}`",
                                    implied_filter_or_metric=f"{e['src_table']}.{e['src_col']} = {e['tgt_table']}.{e['tgt_col']}"
                                )
                                for idx, e in enumerate(edges[:4], 1)
                            ]
                            return AmbiguityIssue(
                                category=AmbiguityCategory.AMBIGUOUS_RELATIONSHIP,
                                issue=f"Multiple active foreign-key paths exist between '{src_t}' and '{tgt_t}'.",
                                description=f"Detected {len(edges)} relationship keys linking '{src_t}' to '{tgt_t}'. Select which path should join the tables.",
                                details={"table_a": src_t, "table_b": tgt_t, "paths": [e["src_col"] for e in edges]},
                                suggested_question=f"Which join relationship between '{src_t}' and '{tgt_t}' should be used?",
                                suggested_options=opts
                            )

        return None

    # =========================================================================
    # 7. UNSPECIFIED SORTING AND GROUPING
    # =========================================================================
    def check_unspecified_sorting_grouping(self, query: str, schema: Optional[Any] = None) -> Optional[AmbiguityIssue]:
        """
        Identifies queries with missing sorting criteria or ambiguous grouping dimensions:
        - "top 5 courses", "top 10 products" without a sort column
        - "break down sales over time" without granularity (monthly, yearly, daily)
        - "sort students by marks" without direction (ascending vs descending)
        """
        q_lower = query.lower()

        # 1. Top N items without explicit sort column
        match_top_n = re.search(r"\b(top|first|bottom|last)\s+(\d+)\s+([a-zA-Z_]+)\b", q_lower)
        if match_top_n:
            n_count = match_top_n.group(2)
            item_entity = match_top_n.group(3)
            # Whitelist domain-standard ranking expressions that have unambiguous metrics
            explicit_ranking_whitelist = [
                "by score", "by average score", "by avg score", "by total score", "by marks", "by credits",
                "by revenue", "by total revenue", "by net sales", "by gross sales", "by sales", "by total sales",
                "by date", "by attendance", "by enrollment", "by price", "by rating", "by wins", "by wickets", "by runs",
                "wicket", "wickets", "run scorer", "run scorers", "batsman", "batsmen", "bowler", "bowlers",
                "best economy", "economy", "strike rate", "award", "awards", "motm", "mvp",
                "highest", "lowest", "most", "least", "best", "worst", "wins", "win"
            ]
            if any(k in q_lower for k in explicit_ranking_whitelist):
                return None

            # If entity is course
            if "course" in item_entity:
                return AmbiguityIssue(
                    category=AmbiguityCategory.UNSPECIFIED_SORT_GROUP,
                    issue=f"Sort metric for 'top {n_count} courses' is not specified.",
                    description=f"Ranking top {n_count} courses requires specifying whether to sort by enrollment count, average score, or course credits.",
                    details={"limit": n_count, "entity": item_entity},
                    suggested_question=f"Which metric should be used to rank the top {n_count} courses?",
                    suggested_options=[
                        ClarificationOption(id="opt_sort_enroll", label="Highest Enrollment (Count of enrolled students)", implied_filter_or_metric="COUNT(marks.student_id) DESC"),
                        ClarificationOption(id="opt_sort_avg", label="Highest Average Marks (Average student score)", implied_filter_or_metric="AVG(marks.score) DESC"),
                        ClarificationOption(id="opt_sort_credits", label="Course Credits (Highest credits first)", implied_filter_or_metric="credits DESC")
                    ]
                )
            else:
                return AmbiguityIssue(
                    category=AmbiguityCategory.UNSPECIFIED_SORT_GROUP,
                    issue=f"Sort column for 'top {n_count} {item_entity}' is not specified.",
                    description=f"The query specifies a LIMIT of {n_count} but does not specify which column or metric to ORDER BY.",
                    details={"limit": n_count, "entity": item_entity},
                    suggested_question=f"Which metric should be used to rank the top {n_count} {item_entity}?",
                    suggested_options=[
                        ClarificationOption(id="opt_sort_m1", label="Sort by primary metric (Highest first)", implied_filter_or_metric="ORDER BY 1 DESC"),
                        ClarificationOption(id="opt_sort_id", label="Sort by ID (Ascending)", implied_filter_or_metric="ORDER BY id ASC")
                    ]
                )

        # 2. Vague time grouping: "over time", "by time", "trend"
        if re.search(r"\b(over\s+time|trend\s+over\s+time|grouped\s+by\s+time|by\s+time)\b", q_lower):
            if not any(k in q_lower for k in ["daily", "by day", "monthly", "by month", "quarterly", "by quarter", "yearly", "by year", "annual"]):
                return AmbiguityIssue(
                    category=AmbiguityCategory.UNSPECIFIED_SORT_GROUP,
                    issue="Time grouping granularity (monthly, quarterly, yearly) is unspecified.",
                    description="Grouping over time requires selecting a time bucket granularity.",
                    details={"matched_term": "over time"},
                    suggested_question="At what time interval should the data be grouped?",
                    suggested_options=[
                        ClarificationOption(id="opt_grp_month", label="Group by Month (`DATE_TRUNC('month', transaction_date)`)", implied_filter_or_metric="DATE_TRUNC('month', transaction_date)"),
                        ClarificationOption(id="opt_grp_quarter", label="Group by Quarter (`DATE_TRUNC('quarter', transaction_date)`)", implied_filter_or_metric="DATE_TRUNC('quarter', transaction_date)"),
                        ClarificationOption(id="opt_grp_year", label="Group by Year (`DATE_TRUNC('year', transaction_date)`)", implied_filter_or_metric="DATE_TRUNC('year', transaction_date)"),
                        ClarificationOption(id="opt_grp_day", label="Group by Day (`DATE_TRUNC('day', transaction_date)`)", implied_filter_or_metric="DATE_TRUNC('day', transaction_date)")
                    ]
                )

        # 3. Sort direction unspecified
        match_sort_dir = re.search(r"\b(sort|order)\s+(students?|records?|rows?|results?|sales?)\s+by\s+([a-zA-Z_]+)\b", q_lower)
        if match_sort_dir:
            sort_target = match_sort_dir.group(3)
            if not any(k in q_lower for k in ["asc", "desc", "ascending", "descending", "highest", "lowest", "newest", "oldest"]):
                return AmbiguityIssue(
                    category=AmbiguityCategory.UNSPECIFIED_SORT_GROUP,
                    issue=f"Sort direction for '{sort_target}' (ascending vs descending) is not specified.",
                    description=f"The query requests ordering by '{sort_target}' without specifying whether values should be in ascending or descending order.",
                    details={"sort_column": sort_target},
                    suggested_question=f"In which order should '{sort_target}' be sorted?",
                    suggested_options=[
                        ClarificationOption(id="opt_sort_desc", label=f"Descending (Highest / Newest '{sort_target}' first)", implied_filter_or_metric=f"ORDER BY {sort_target} DESC"),
                        ClarificationOption(id="opt_sort_asc", label=f"Ascending (Lowest / Oldest '{sort_target}' first)", implied_filter_or_metric=f"ORDER BY {sort_target} ASC")
                    ]
                )

        return None

    # =========================================================================
    # MAIN DETECTION DISPATCHER
    # =========================================================================
    def detect(
        self,
        query: str,
        schema: Optional[Any] = None,
        history: Optional[List[Dict[str, Any]]] = None
    ) -> AmbiguityDetectionResult:
        """
        Runs all 7 ambiguity detectors against the user query and schema.
        Returns an AmbiguityDetectionResult containing all detected issues
        and a prioritized ClarificationRequest.
        """
        clean_q = query.strip()
        if not clean_q:
            return AmbiguityDetectionResult(
                is_ambiguous=True,
                primary_ambiguity=AmbiguityCategory.MISSING_FILTER,
                missing_information="Query is empty.",
                clarification=ClarificationRequest(
                    question="Please provide a database question or query:",
                    ambiguity_type=AmbiguityCategory.MISSING_FILTER,
                    options=[
                        ClarificationOption(id="opt_ex1", label="Show total student enrollment count", implied_filter_or_metric="COUNT(*)"),
                        ClarificationOption(id="opt_ex2", label="Show departments and courses", implied_filter_or_metric="departments")
                    ]
                )
            )

        # 0. Standalone math / formula queries are NOT ambiguous
        if self._is_standalone_calculation(clean_q):
            return AmbiguityDetectionResult(is_ambiguous=False, primary_ambiguity=AmbiguityCategory.NONE)

        # Context continuation check: If query is a concise follow-up to previous clarification
        # e.g., "total marks", "revenue", "mumbai store", we don't re-flag it
        if history:
            last_turn = history[-1] if history else {}
            if "clarif" in str(last_turn.get("content", "")).lower() or last_turn.get("status") == "awaiting_clarification":
                if len(clean_q.split()) <= 4:
                    return AmbiguityDetectionResult(is_ambiguous=False, primary_ambiguity=AmbiguityCategory.NONE)
            # Conversational pronoun / continuation where parent context is available
            q_words = set(re.findall(r"\b[a-zA-Z]+\b", clean_q.lower()))
            if (q_words & {"his", "her", "their", "them", "it", "those"}) or any(p in clean_q.lower() for p in ["now show only", "sort them", "what about", "what was his", "how about"]):
                for h in reversed(history):
                    if h.get("sql") or any(t in str(h.get("content", "")).lower() for t in (schema.tables.keys() if schema and schema.tables else [])):
                        return AmbiguityDetectionResult(is_ambiguous=False, primary_ambiguity=AmbiguityCategory.NONE)

        # Prioritized issue collection:
        # If user explicitly groups by/per a dimension, aggregation is the primary structural question
        has_grouping_phrase = bool(re.search(r"\b(by|per|for\s+each)\s+[a-zA-Z_]+\b", clean_q, re.I))

        # Check all 7 ambiguity categories
        issue_col = self.check_ambiguous_columns(clean_q, schema)
        issue_date = self.check_unspecified_date_ranges(clean_q, schema)
        issue_agg = self.check_unclear_aggregations(clean_q, schema)
        issue_rel = self.check_ambiguous_relationships(clean_q, schema)
        issue_cmp = self.check_unclear_comparison(clean_q, schema)
        issue_flt = self.check_missing_filters(clean_q, schema)
        issue_sort = self.check_unspecified_sorting_grouping(clean_q, schema)

        issues: List[AmbiguityIssue] = []

        if has_grouping_phrase and issue_agg:
            issues.append(issue_agg)
            for iss in [issue_col, issue_date, issue_rel, issue_cmp, issue_flt, issue_sort]:
                if iss and iss != issue_agg:
                    issues.append(iss)
        else:
            for iss in [issue_col, issue_date, issue_agg, issue_rel, issue_cmp, issue_flt, issue_sort]:
                if iss:
                    issues.append(iss)

        if not issues:
            return AmbiguityDetectionResult(
                is_ambiguous=False,
                primary_ambiguity=AmbiguityCategory.NONE,
                issues=[]
            )

        # Primary ambiguity is the first high-priority issue detected
        primary = issues[0]
        clarification_req = ClarificationRequest(
            question=primary.suggested_question or f"Please clarify: {primary.issue}",
            ambiguity_type=primary.category,
            options=primary.suggested_options,
            allow_free_text=True
        )

        all_summaries = "; ".join([iss.issue for iss in issues])
        return AmbiguityDetectionResult(
            is_ambiguous=True,
            primary_ambiguity=primary.category,
            issues=issues,
            clarification=clarification_req,
            missing_information=all_summaries
        )

    def analyze(
        self,
        query: str,
        schema: Optional[Any] = None,
        history: Optional[List[Dict[str, Any]]] = None
    ) -> QueryAnalysis:
        """Convenience method returning a QueryAnalysis model directly."""
        res = self.detect(query, schema=schema, history=history)
        return res.to_query_analysis(query)

# Global singleton detector instance
ambiguity_detector = AmbiguityDetector()
