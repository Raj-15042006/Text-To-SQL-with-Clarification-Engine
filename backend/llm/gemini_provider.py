import json
import time
import logging
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

from backend.config import settings
from backend.llm.base import BaseLLMProvider, SQLGenerationResult
from backend.modules.ambiguity import (
    QueryAnalysis,
    AmbiguityCategory,
    ClarificationRequest,
    ClarificationOption,
    ambiguity_detector
)

logger = logging.getLogger(__name__)

class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model or settings.GEMINI_MODEL or "gemini-3.8-flash"
        self.client = genai.Client(api_key=self.api_key)

    def _call_with_retry(self, fn_builder, max_retries: int = 2, initial_delay: float = 0.5):
        """
        Executes a model call with fast failover to high-availability gemini-3.1-flash-lite.
        If the primary model hits 503, immediately falls back to avoid multi-second retry lag.
        """
        candidate_models = [self.model_name]
        if "3.1-flash-lite" not in self.model_name:
            candidate_models.append("gemini-3.1-flash-lite")

        last_error = None
        for model_to_use in candidate_models:
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    return fn_builder(model_to_use)
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    # On 503 / unavailable, if there's another candidate, break immediately to fallback
                    if ("503" in err_str or "unavailable" in err_str) and len(candidate_models) > 1 and model_to_use != candidate_models[-1]:
                        logger.warning(f"Model {model_to_use} 503 high demand. Fast-failing over to {candidate_models[-1]}...")
                        break
                    if any(k in err_str for k in ("429", "resource_exhausted", "quota")):
                        logger.warning(
                            f"Model {model_to_use} rate issue (attempt {attempt+1}/{max_retries}): {e}. Waiting {delay}s..."
                        )
                        time.sleep(delay)
                        delay *= 1.5
                    else:
                        break # Non-retriable error, try next candidate or raise
        raise last_error

    def _format_history(self, history: Optional[List[Dict[str, Any]]]) -> str:
        if not history:
            return ""
        lines = ["\nPrior Conversation History (Context Continuation):"]
        for turn in history[-6:]: # Keep last 6 relevant turns
            role = turn.get("role", "user")
            content = turn.get("content", "")
            sql = turn.get("sql")
            sample_rows = turn.get("sample_rows")
            if role == "user":
                lines.append(f"- User: \"{content}\"")
            else:
                parts = []
                if sql:
                    parts.append(f"Executed SQL: {sql}")
                if sample_rows:
                    parts.append(f"Top Result Data: {json.dumps(sample_rows[:3], default=str)}")
                if content:
                    parts.append(f"Answer: {content[:250]}")
                summary = " | ".join(parts) if parts else (content[:250] or "Executed")
                lines.append(f"- Assistant: {summary}")
        return "\n".join(lines) + "\n"

    def analyze_query(
        self, 
        user_query: str, 
        schema_context: str, 
        history: Optional[List[Dict[str, Any]]] = None
    ) -> QueryAnalysis:
        """
        Analyzes user query against database schema and conversation history to detect ambiguities or generate SQL.
        Trained with universal multi-domain formula intelligence across Finance, E-Commerce, Healthcare,
        Supply Chain, HR, Academics, Physics, Chemistry, Mathematics, Statistics, and Multi-Sport analytics.
        """
        # Fast deterministic ambiguity detection pass (identifies all 7 ambiguity categories)
        det_res = ambiguity_detector.detect(user_query, schema=None, history=history)
        if det_res.is_ambiguous:
            return det_res.to_query_analysis(user_query)

        history_str = self._format_history(history)

        system_instruction = (
            "You are an expert Text-to-SQL Clarification & Universal Multi-Domain Formula Engine for PostgreSQL.\n"
            "Your objective is to evaluate whether the query is ambiguous, needs clarification, or can be answered immediately.\n"
            "You possess deep domain intelligence across ALL worldwide professional disciplines and scientific formulas.\n\n"
            "MULTI-TURN CONVERSATION & CONTEXT CONTINUATION:\n"
            "- When 'Prior Conversation History' is provided, resolve all pronouns ('it', 'they', 'highest', 'best', 'the top one', 'explain the formula', 'now for X') using prior turns.\n"
            "- If the user asks a follow-up about a previous result (e.g., 'Which one is highest?', 'What formula did you use?', 'Now show only values > 10'), treat it as continuing that topic.\n\n"
            "UNIVERSAL MULTI-DOMAIN FORMULAS & CALCULATION ENGINE:\n"
            "You understand and compute formulas across ANY domain in the world, including but not limited to:\n\n"
            "1. FINANCE & BANKING:\n"
            "   * Compound Interest & Future Value: FV = P * (1 + r/n)^(n*t)\n"
            "     SQL: `SELECT ROUND(P * POWER(1.0 + (r / n::numeric), n * t), 2) AS future_value;`\n"
            "   * Simple Interest: SI = (P * R * T) / 100\n"
            "   * CAGR (Compound Annual Growth Rate): ((end_val / start_val) ^ (1 / years) - 1) * 100\n"
            "     SQL: `SELECT ROUND((POWER(end_val::numeric / NULLIF(start_val, 0), 1.0 / NULLIF(years, 0)) - 1.0) * 100, 2) AS cagr;`\n"
            "   * Loan EMI: [P * r * (1 + r)^n] / [(1 + r)^n - 1] (r = monthly rate)\n"
            "   * Return on Investment (ROI): ((gain - cost) / cost) * 100\n"
            "   * Profit Margins: Gross Margin = ((revenue - cogs) / revenue) * 100, Net Margin = (net_profit / revenue) * 100\n"
            "   * Working Capital = current_assets - current_liabilities; Current Ratio = current_assets / current_liabilities\n\n"
            "2. SALES, E-COMMERCE & MARKETING:\n"
            "   * Customer Lifetime Value (CLV/LTV): average_order_value * purchase_frequency * customer_lifespan\n"
            "   * Customer Acquisition Cost (CAC): total_marketing_spend / new_customers_acquired\n"
            "   * Churn Rate: (customers_lost / customers_start) * 100; Retention Rate: 100 - Churn Rate\n"
            "   * Average Order Value (AOV): total_revenue / total_orders\n"
            "   * Conversion Rate: (conversions / total_visitors) * 100\n"
            "   * Return on Ad Spend (ROAS): revenue_generated / ad_spend; CTR: (clicks / impressions) * 100\n\n"
            "3. HEALTHCARE, MEDICINE & FITNESS:\n"
            "   * Body Mass Index (BMI):\n"
            "     Metric: weight_kg / (height_m ^ 2)  -> `SELECT ROUND(weight_kg::numeric / POWER(height_m, 2), 2) AS bmi;`\n"
            "     Imperial: (weight_lbs / (height_inches ^ 2)) * 703\n"
            "   * Mean Arterial Pressure (MAP): (2 * diastolic_bp + systolic_bp) / 3\n"
            "   * Basal Metabolic Rate (BMR) (Mifflin-St Jeor):\n"
            "     Male: 10*weight_kg + 6.25*height_cm - 5*age + 5 | Female: 10*weight_kg + 6.25*height_cm - 5*age - 161\n"
            "   * Drug Dosage: dosage_mg_per_kg * weight_kg\n"
            "   * Body Surface Area (Mosteller): SQRT((height_cm * weight_kg) / 3600.0)\n\n"
            "4. SUPPLY CHAIN, LOGISTICS & INVENTORY:\n"
            "   * Economic Order Quantity (EOQ): SQRT((2 * annual_demand * order_cost) / holding_cost_per_unit)\n"
            "     SQL: `SELECT ROUND(SQRT((2.0 * annual_demand * order_cost) / NULLIF(holding_cost, 0)), 2) AS eoq;`\n"
            "   * Reorder Point (ROP): (lead_time_days * avg_daily_usage) + safety_stock\n"
            "   * Inventory Turnover Ratio: cogs / average_inventory\n"
            "   * Days Sales of Inventory (DSI): (average_inventory / cogs) * 365\n"
            "   * Overall Equipment Effectiveness (OEE): Availability * Performance * Quality * 100\n\n"
            "5. HUMAN RESOURCES & WORKFORCE:\n"
            "   * Employee Turnover Rate: (separations / avg_employees) * 100\n"
            "   * Absenteeism Rate: (unplanned_absent_days / total_workdays) * 100\n"
            "   * Revenue per Employee: total_revenue / employee_count\n\n"
            "6. EDUCATION & ACADEMICS:\n"
            "   * Weighted GPA / CGPA: SUM(grade_points * credits) / SUM(credits)\n"
            "   * Percentile Rank: PERCENT_RANK() OVER (ORDER BY score) * 100\n\n"
            "7. PHYSICS, CHEMISTRY, STEM & MATHEMATICS:\n"
            "   * Kinetic Energy: 0.5 * mass * velocity^2 -> `SELECT ROUND(0.5 * mass * POWER(velocity, 2), 2) AS kinetic_energy;`\n"
            "   * Potential Energy: mass * 9.80665 * height\n"
            "   * Force: mass * acceleration (F = m*a)\n"
            "   * Ohm's Law & Electrical Power: V = I * R, P = V * I = I^2 * R\n"
            "   * Temperature Conversions: C to F: (celsius * 9/5) + 32 | F to C: (fahrenheit - 32) * 5/9 | C to Kelvin: celsius + 273.15\n"
            "   * Density: mass / volume; Half-life Decay: N0 * POWER(0.5, time / half_life)\n"
            "   * Statistics: STDDEV(), VARIANCE(), CORR(x, y), COVAR_SAMP(x, y), Z-Score: (x - AVG(x) OVER()) / NULLIF(STDDEV(x) OVER(), 0)\n\n"
            "8. SPORTS ANALYTICS (MULTI-SPORT):\n"
            "   * Cricket: Net Run Rate (NRR) using CTE across innings ((runs_for/overs_for) - (runs_against/overs_against)), Strike Rate, Economy Rate, Batting Average\n"
            "   * Basketball: True Shooting % = PTS / (2 * (FGA + 0.44 * FTA)) * 100, eFG% = (FGM + 0.5 * 3PM) / FGA * 100\n"
            "   * Football/Soccer: Goals per 90 min = (goals / (minutes_played / 90.0)), Shot conversion rate\n"
            "   * Baseball: ERA = (9 * earned_runs) / innings_pitched, Batting Average = hits / at_bats, OPS = OBP + SLG\n\n"
            "STANDALONE COMPUTATIONS & PURE CALCULATIONS RULE:\n"
            "- If the user asks for ANY mathematical, scientific, financial, or domain formula calculation (with specific values or hypothetical scenario) NOT requiring a physical database table:\n"
            "  * DO NOT mark as ambiguous!\n"
            "  * DO NOT say tables are missing!\n"
            "  * Set is_ambiguous = False and generate a standalone PostgreSQL expression directly: `SELECT <calculation> AS <metric_name>;`\n"
            "  * PostgreSQL evaluates pure mathematical expressions instantly!\n\n"
            "DATABASE TABLE FORMULA RULE:\n"
            "- When table(s) in the database match the domain concept, map the formula over the appropriate columns using aggregations (`SUM`, `AVG`), CTEs (`WITH ... AS`), window functions, or expressions.\n\n"
            "AMBIGUITY EVALUATION & RESOLUTION RULES (IDENTIFY ALL 7 CATEGORIES):\n"
            "Evaluate whether the query exhibits any of the following 7 ambiguity categories:\n"
            "1. MISSING FILTERS ('missing_filter'): Criteria omitted (e.g. passing/failing score cutoff, active status definition, mutations without WHERE clause).\n"
            "2. UNCLEAR COMPARISON CRITERIA ('unclear_comparison'): Subjective or superlative terms ('top students', 'high-value sales', 'poor attendance') without numeric thresholds or metric definitions.\n"
            "3. AMBIGUOUS COLUMN NAMES ('ambiguous_column'): Names mapping to multiple fields or tables (e.g. 'Mumbai' matching store_city vs customer_city, or 'name' occurring in multiple tables, or 'sales' meaning revenue vs units_sold).\n"
            "4. UNSPECIFIED DATE RANGES ('unspecified_date_range'): Vague or unstated temporal bounds ('last year' -> calendar vs fiscal year, 'recent', 'this quarter').\n"
            "5. UNCLEAR AGGREGATION FUNCTIONS ('unclear_aggregation'): Grouped metrics ('sales by store_city', 'marks per course') without specifying SUM, AVG, COUNT, MAX, or MIN.\n"
            "6. AMBIGUOUS TABLE RELATIONSHIPS ('ambiguous_relationship'): Multiple valid join paths or foreign keys connecting tables (e.g. students & departments via major vs course enrollment).\n"
            "7. UNSPECIFIED SORTING AND GROUPING ('unspecified_sort_group'): 'top 5 courses' without sort metric, 'break down over time' without interval, or sort without direction.\n\n"
            "If any ambiguity exists, set is_ambiguous=True, select the appropriate ambiguity_type from the above categories, and provide at least 2 clear options in clarification.options.\n"
            "If unambiguous or a pure formula/calculation, set is_ambiguous=False, ambiguity_type='none', and generate the optimal PostgreSQL query in 'generated_sql'.\n"
            "STRICT PROJECTION: Select ONLY the specific column(s) requested (no SELECT * unless explicitly requested)."
        )

        prompt = (
            f"{system_instruction}\n\n"
            f"Database Schema:\n{schema_context}\n"
            f"{history_str}\n\n"
            f"User Query: \"{user_query}\"\n\n"
            "Evaluate ambiguity. If unambiguous or a formula/calculation, generate the optimal PostgreSQL query in generated_sql directly. Produce the QueryAnalysis JSON."
        )

        def do_call(target_model):
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=QueryAnalysis,
                temperature=0.0,
                thinking_config=types.ThinkingConfig(thinking_budget=settings.LLM_THINKING_BUDGET)
            )
            return self.client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config
            )

        try:
            response = self._call_with_retry(do_call)
            parsed_data = json.loads(response.text)
            return QueryAnalysis.model_validate(parsed_data)
        except Exception as e:
            logger.error(f"Error in Gemini analyze_query: {e}")
            raise RuntimeError(f"LLM Provider Error: {str(e)}")

    def generate_sql(
        self, 
        resolved_query: str, 
        schema_context: str, 
        clarification_notes: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None
    ) -> SQLGenerationResult:
        """
        Generates PostgreSQL-compliant SQL query based on the resolved intent, schema context, and conversation history.
        Universal multi-domain formula support across Finance, E-commerce, Healthcare, Supply Chain, STEM, and Sports.
        """
        history_str = self._format_history(history)
        clarification_context = f"\nClarifications resolved:\n{clarification_notes}\n" if clarification_notes else ""

        system_instruction = (
            "You are an expert PostgreSQL DBA and Text-to-SQL Generator with universal multi-domain formula intelligence.\n"
            "Generate an optimal, syntactically correct PostgreSQL SQL query answering the user's question.\n\n"
            "CONSTRAINTS & UNIVERSAL FORMULA CAPABILITIES:\n"
            "1. UNIVERSAL DOMAIN FORMULAS & CTEs: Support Common Table Expressions (`WITH ... AS (...) SELECT ...`) and expressions for formulas across ANY domain:\n"
            "   - Finance: CAGR, Compound Interest, Simple Interest, EMI, ROI, Margins, Working Capital\n"
            "   - Sales & Marketing: CLV, CAC, Churn Rate, Retention Rate, AOV, Conversion Rate, ROAS\n"
            "   - Healthcare: BMI, MAP, BMR, Drug Dosage, Body Surface Area\n"
            "   - Supply Chain: EOQ, Reorder Point, Inventory Turnover, DSI, OEE\n"
            "   - HR: Employee Turnover Rate, Absenteeism, Revenue per Employee\n"
            "   - STEM & Physics: Kinetic/Potential Energy, Ohm's Law, Force, Electrical Power, Half-life decay, Temperature conversions\n"
            "   - Statistics: STDDEV, VARIANCE, CORR, Z-Scores, percentiles\n"
            "   - Sports: Cricket NRR/Strike Rate/Economy, Basketball True Shooting %, Football Goals/90, Baseball ERA/OPS\n"
            "2. STANDALONE NON-TABLE CALCULATIONS: If the query is a pure calculation or formula without requiring a physical database table, generate a direct `SELECT <expression> AS ...;` query without requiring any table.\n"
            "3. STRICT PROJECTION: Select ONLY the specific column(s) requested by the user prompt. NEVER use `SELECT *` unless explicitly asked for all columns.\n"
            "4. CONTEXT CONTINUATION: Use prior conversation history to resolve pronouns ('it', 'highest', 'that item', 'the formula used').\n"
            "5. Read-only SELECT queries only. NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER.\n"
            "6. Output must strictly conform to the SQLGenerationResult JSON schema."
        )

        prompt = (
            f"{system_instruction}\n\n"
            f"Available Database Schema:\n{schema_context}\n"
            f"{history_str}\n"
            f"{clarification_context}\n"
            f"Resolved User Question: \"{resolved_query}\"\n\n"
            "Generate the PostgreSQL SQL and explanation. Return SQLGenerationResult JSON."
        )

        def do_call(target_model):
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SQLGenerationResult,
                temperature=0.0,
                thinking_config=types.ThinkingConfig(thinking_budget=settings.LLM_THINKING_BUDGET)
            )
            return self.client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config
            )

        try:
            response = self._call_with_retry(do_call)
            parsed_data = json.loads(response.text)
            return SQLGenerationResult.model_validate(parsed_data)
        except Exception as e:
            logger.error(f"Error in Gemini generate_sql: {e}")
            raise RuntimeError(f"SQL Generation Error: {str(e)}")

    def explain_results(
        self, 
        user_query: str, 
        sql: str, 
        columns: List[str], 
        sample_rows: List[Dict[str, Any]], 
        total_rows: int,
        relationships_context: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Produces a concise, direct, accurate answer to the user's prompt based on query results and conversation context.
        Features instant fast-paths for 0 rows and single scalar/formula calculations to eliminate redundant latency.
        """
        # Instant fast-path 1: No rows returned
        if total_rows == 0:
            return "No matching records were found in the active database."

        # Instant fast-path 2: Single scalar/calculation (e.g. compound interest, count, sum)
        if len(sample_rows) == 1 and len(columns) == 1:
            col = columns[0]
            val = sample_rows[0].get(col)
            if val is not None:
                col_display = col.replace("_", " ").title()
                if isinstance(val, (int, float)):
                    val_fmt = f"{val:,.2f}" if isinstance(val, float) else f"{val:,}"
                else:
                    val_fmt = str(val)
                return f"The calculated **{col_display}** is **{val_fmt}**."

        history_str = self._format_history(history)
        rel_str = f"\nRelevant Schema Foreign Key Relationships (use ONLY if user asked about relationships):\n{relationships_context}\n" if relationships_context else ""

        system_instruction = (
            "You are a helpful, direct data assistant answering the user's question based strictly on executed query results.\n"
            "STRICT RULES (ANSWER ONLY WHAT IS ASKED):\n"
            "1. Answer ONLY what the user asked in their prompt. Be direct, clear, and concise (1-3 sentences).\n"
            "2. DO NOT write unsolicited essays, hypothetical schema redesigns, or generic business advice.\n"
            "3. Directly cite the exact values, names, and numbers from the query results.\n"
            "4. For formulas across ANY domain (Finance, Healthcare, E-Commerce, Supply Chain, Physics, Statistics, Sports, etc.): State the computed numbers directly, citing the formula/metric applied and any top ranking or key outcome requested.\n"
            "5. If user asks a follow-up (e.g., 'Which one is highest?' or 'What formula did you use?'), answer it directly referencing the previous context."
        )

        prompt = (
            f"{system_instruction}\n\n"
            f"{history_str}\n"
            f"User Question: \"{user_query}\"\n"
            f"SQL Executed: {sql}\n"
            f"Total Records Returned: {total_rows}\n"
            f"Query Results Data: {json.dumps(sample_rows[:10], default=str)}\n"
            f"{rel_str}\n"
            "Provide the direct, concise answer to the user's question:"
        )

        def do_call(target_model):
            config = types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=160,
                thinking_config=types.ThinkingConfig(thinking_budget=settings.LLM_THINKING_BUDGET)
            )
            return self.client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config
            )

        try:
            response = self._call_with_retry(do_call)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error in Gemini explain_results: {e}")
            if sample_rows and len(sample_rows) == 1:
                val_strs = [f"**{v}**" for v in sample_rows[0].values() if v is not None]
                return f"Result: {', '.join(val_strs)}."
            return f"The query returned {total_rows} matching record(s)."
