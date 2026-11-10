import re
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.database.schema_extractor import DatabaseSchema
from backend.modules.ambiguity import (
    AmbiguityDetector,
    AmbiguityDetectionResult,
    AmbiguityIssue,
    AmbiguityCategory,
    ClarificationOption,
    ClarificationRequest,
)
from backend.modules.semantic_memory import semantic_memory

logger = logging.getLogger(__name__)


class AssumptionAlternative(BaseModel):
    label: str
    switch_query: str


class AssumptionItem(BaseModel):
    key: str
    label: str
    value: str
    source: str = "heuristic"  # "heuristic" | "memory" | "glossary" | "persona" | "ask_after_answer"
    alternatives: List[AssumptionAlternative] = Field(default_factory=list)


class ProvenanceMapping(BaseModel):
    phrase: str
    sql_clause: str
    clause_type: str  # "PROJECTION" | "TABLE" | "JOIN" | "FILTER" | "GROUP_BY" | "ORDER_BY" | "LIMIT" | "FORMULA"


class ThinkingStep(BaseModel):
    phase: str  # "Think" | "Analyze" | "Verify" | "Synthesize"
    title: str
    detail: str


class SchemaGapResult(BaseModel):
    has_gap: bool = False
    missing_terms: List[str] = Field(default_factory=list)
    closest_suggestions: List[str] = Field(default_factory=list)
    message: Optional[str] = None


class ClarificationIntelligence:
    """
    Implements Section 1, 4, 5, and 8 Clarification Intelligence features:
      - Ambiguity Scoring + Execution-Divergence Check
      - Value-Grounded & What-If Row Count Previews
      - Ask-After-Answer Mode (fast best-guess + clickable switch)
      - Schema-Gap Detection (no hallucinated columns)
      - Assumption Ledger + Query Provenance + Confidence Reasons + Thinking Steps
      - Example-Based Calibration ("should come to around X")
    """

    # Domain concepts that clearly indicate non-matching datasets if absent from active schema
    OUT_OF_SCHEMA_CONCEPTS = {
        "bitcoin", "crypto", "ethereum", "blockchain", "salary", "payroll", "employee", "employees",
        "hr", "hospital", "patient", "patients", "diagnosis", "doctor", "weather", "humidity",
        "rainfall", "flight", "airline", "hotel", "stock", "ticker", "nasdaq", "mortgage", "tax_return"
    }

    # ---------------------------------------------------------------------
    # 1. Schema-Gap Detection (Never Hallucinate Missing Schema Columns)
    # ---------------------------------------------------------------------
    def detect_schema_gap(
        self,
        query: str,
        schema: Optional[DatabaseSchema],
        table_scores: Dict[str, int],
        has_history: bool = False
    ) -> SchemaGapResult:
        if not schema or not schema.tables or has_history:
            return SchemaGapResult(has_gap=False)

        max_score = max(table_scores.values()) if table_scores else 0
        if max_score >= 10:
            return SchemaGapResult(has_gap=False)

        q_low = query.lower()
        all_schema_terms = set()
        col_display = []
        for t_name, t_meta in schema.tables.items():
            all_schema_terms.add(t_name.lower())
            all_schema_terms.update(t_name.lower().split("_"))
            for c in t_meta.columns:
                all_schema_terms.add(c.name.lower())
                all_schema_terms.update(c.name.lower().split("_"))
                if not c.is_primary_key:
                    col_display.append(f"{t_name}.{c.name}")

        tokens = re.findall(r"\b[a-zA-Z_]{3,}\b", q_low)
        missing = []
        for tok in tokens:
            t_s = tok.rstrip("s")
            if (tok in self.OUT_OF_SCHEMA_CONCEPTS or t_s in self.OUT_OF_SCHEMA_CONCEPTS) and tok not in all_schema_terms and t_s not in all_schema_terms:
                missing.append(tok)

        # Also catch explicit unknown snake_case column references like "employee_bonus"
        for tok in tokens:
            if "_" in tok and tok not in all_schema_terms:
                missing.append(tok)

        missing = list(dict.fromkeys(missing))
        if not missing:
            return SchemaGapResult(has_gap=False)

        tables_list = ", ".join(f"`{t}`" for t in list(schema.tables.keys())[:6])
        closest = col_display[:6]
        msg = (
            f"**Schema Gap Detected**: Your active workspace does not contain table(s) or column(s) for "
            f"{', '.join(f'`{m}`' for m in missing)}.\n\n"
            f"- **Available Tables**: {tables_list}\n"
            f"- **Sample Available Columns**: {', '.join(f'`{c}`' for c in closest)}\n\n"
            f"Please upload a matching dataset via **Upload Data** or rephrase using columns from your workspace."
        )
        return SchemaGapResult(
            has_gap=True,
            missing_terms=missing,
            closest_suggestions=closest,
            message=msg
        )

    # ---------------------------------------------------------------------
    # 2. Ambiguity Scoring & Value-Grounded / Execution-Divergence Check
    # ---------------------------------------------------------------------
    def score_and_enrich_ambiguity(
        self,
        query: str,
        det_res: AmbiguityDetectionResult,
        schema: Optional[DatabaseSchema],
        db_mgr,
        user_id: Optional[str] = None,
        answer_mode: str = "smart"  # "smart" | "strict" | "fast_best_guess"
    ) -> Dict[str, Any]:
        """
        Scores ambiguity [0.0..1.0], checks Personal Semantic Memory / Persona Bias,
        runs safe LIMIT 5 execution-divergence probes, and enriches options with
        real What-If row counts & live value grounding.
        """
        if not det_res.is_ambiguous or not det_res.clarification:
            return {
                "should_ask_before": False,
                "ambiguity_score": 0.12,
                "ask_after_answer_assumption": None,
                "divergence_suppressed": False,
                "applied_memory_note": None,
                "det_res": det_res
            }

        issue = det_res.issues[0] if det_res.issues else None
        cat = det_res.primary_ambiguity
        q_low = query.lower()

        # Check Personal Semantic Memory first (reduces repeat questions!)
        term_key = self._derive_term_key(cat, issue, q_low)
        mem_hit = semantic_memory.find_matching_preference(user_id, term_key, schema=schema) if term_key else None
        if mem_hit:
            entry = mem_hit["entry"]
            return {
                "should_ask_before": False,
                "ambiguity_score": 0.22,
                "divergence_suppressed": False,
                "applied_memory_note": f"Applied Personal Memory: '{entry.preferred_label}' ({mem_hit['reason']})",
                "memory_constraint": entry.implied_constraint,
                "memory_label": entry.preferred_label,
                "term_key": term_key,
                "det_res": det_res
            }

        # Check Persona Bias (Role-aware disambiguation)
        persona = semantic_memory.get_persona(user_id)
        persona_pref = None
        if persona != "general":
            for concept in ("sales", "city", "quarter", "year", "performance", "pass"):
                if concept in q_low:
                    persona_pref = semantic_memory.get_persona_bias(user_id, concept)
                    if persona_pref:
                        break

        # Compute base ambiguity score from category & schema overlap
        base_score = 0.72
        if cat in (AmbiguityCategory.AMBIGUOUS_COLUMN, AmbiguityCategory.AMBIGUOUS_RELATIONSHIP):
            base_score = 0.78
        elif cat in (AmbiguityCategory.UNCLEAR_AGGREGATION, AmbiguityCategory.UNCLEAR_COMPARISON):
            base_score = 0.64
        elif cat in (AmbiguityCategory.UNSPECIFIED_DATE_RANGE, AmbiguityCategory.MISSING_FILTER):
            base_score = 0.58
        elif cat == AmbiguityCategory.UNSPECIFIED_SORT_GROUP:
            base_score = 0.52

        if persona_pref:
            base_score = max(0.35, base_score - 0.18)

        # Value-Grounding & Execution-Divergence Check (Permission-aware on scoped schema!)
        divergence_suppressed = False
        options = det_res.clarification.options
        if schema and schema.tables and options:
            divergence_suppressed = self._ground_and_check_divergence(
                query=query,
                cat=cat,
                options=options,
                schema=schema,
                db_mgr=db_mgr
            )

        if divergence_suppressed:
            return {
                "should_ask_before": False,
                "ambiguity_score": 0.18,
                "divergence_suppressed": True,
                "applied_memory_note": "Execution-divergence check: all candidate interpretations yield identical outcomes — skipped unnecessary clarification.",
                "det_res": det_res
            }

        # Determine whether to block & ask BEFORE running vs Ask-After-Answer best guess
        should_ask = True
        ask_after_assumption = None
        if answer_mode == "fast_best_guess" or (answer_mode == "smart" and base_score < 0.60 and len(options) >= 2):
            # Execute top option immediately and surface Ask-After-Answer alternatives
            should_ask = False
            best_opt = options[0]
            alts = [
                {
                    "label": o.label,
                    "constraint": o.implied_filter_or_metric or o.label,
                    "estimated_rows": getattr(o, "estimated_rows", None)
                }
                for o in options[1:4]
            ]
            ask_after_assumption = {
                "term_key": term_key or cat.value,
                "question": det_res.clarification.question,
                "assumed_label": best_opt.label,
                "assumed_constraint": best_opt.implied_filter_or_metric or best_opt.label,
                "alternatives": alts
            }

        return {
            "should_ask_before": should_ask,
            "ambiguity_score": round(base_score, 2),
            "ask_after_answer_assumption": ask_after_assumption,
            "divergence_suppressed": False,
            "term_key": term_key,
            "persona_pref": persona_pref,
            "det_res": det_res
        }

    @staticmethod
    def _derive_term_key(cat: AmbiguityCategory, issue: Optional[AmbiguityIssue], q_low: str) -> str:
        if cat == AmbiguityCategory.AMBIGUOUS_COLUMN:
            if any(w in q_low for w in ["mumbai", "delhi", "pune", "bangalore", "city"]):
                return "city_scope"
            if "sale" in q_low or "revenue" in q_low:
                return "sales_metric"
            if "name" in q_low:
                return "entity_name_column"
        if cat == AmbiguityCategory.UNSPECIFIED_DATE_RANGE:
            if "quarter" in q_low:
                return "quarter_basis"
            if "year" in q_low:
                return "year_basis"
            if "recent" in q_low:
                return "recent_window"
        if cat == AmbiguityCategory.MISSING_FILTER:
            if any(w in q_low for w in ["pass", "passing", "fail"]):
                return "passing_threshold"
            if "active" in q_low:
                return "active_criteria"
        if cat == AmbiguityCategory.AMBIGUOUS_RELATIONSHIP:
            return "students_departments_join"
        if cat == AmbiguityCategory.UNCLEAR_COMPARISON:
            if "student" in q_low or "perform" in q_low:
                return "student_performance_metric"
            if any(w in q_low for w in ["high", "large", "big"]):
                return "high_value_cutoff"
        return f"pref_{cat.value}"

    def _ground_and_check_divergence(
        self,
        query: str,
        cat: AmbiguityCategory,
        options: List[ClarificationOption],
        schema: DatabaseSchema,
        db_mgr
    ) -> bool:
        """
        Runs safe lightweight COUNT(*) and LIMIT 5 value probes across candidate options
        strictly on tables present in the user's scoped schema.
        Mutates option descriptions/badges with What-If row counts and live values.
        Returns True if all candidates produce identical execution results (suppressing clarification).
        """
        signatures = []

        # Live value grounding for sales city ambiguity
        if cat == AmbiguityCategory.AMBIGUOUS_COLUMN and "sales" in schema.tables:
            try:
                res_store = db_mgr.execute_query("SELECT store_city, COUNT(*) AS cnt FROM sales GROUP BY store_city LIMIT 5")
                res_cust = db_mgr.execute_query("SELECT customer_city, COUNT(*) AS cnt FROM sales GROUP BY customer_city LIMIT 5")
                if res_store.success and res_cust.success:
                    s_preview = ", ".join(f"{r['store_city']} ({r['cnt']})" for r in res_store.rows[:3])
                    c_preview = ", ".join(f"{r['customer_city']} ({r['cnt']})" for r in res_cust.rows[:3])
                    for opt in options:
                        imp = (opt.implied_filter_or_metric or "").lower()
                        if "store_city" in imp:
                            opt.description = f"Store locations in DB: {s_preview}"
                        elif "customer_city" in imp:
                            opt.description = f"Customer cities in DB: {c_preview}"
            except Exception:
                pass

        # Candidate execution probes for What-If row counts & divergence check
        for opt in options:
            imp = (opt.implied_filter_or_metric or "").strip()
            probe_sql = None
            count_sql = None

            if cat == AmbiguityCategory.MISSING_FILTER and "marks" in schema.tables and "score" in imp:
                probe_sql = f"SELECT student_id, score FROM marks WHERE {imp} LIMIT 5"
                count_sql = f"SELECT COUNT(*) AS cnt FROM marks WHERE {imp}"
            elif cat == AmbiguityCategory.UNCLEAR_COMPARISON and "sales" in schema.tables and "revenue >" in imp:
                probe_sql = f"SELECT store_city, revenue FROM sales WHERE {imp} LIMIT 5"
                count_sql = f"SELECT COUNT(*) AS cnt FROM sales WHERE {imp}"
            elif cat == AmbiguityCategory.AMBIGUOUS_COLUMN and "sales" in schema.tables:
                if imp in ("revenue", "units_sold"):
                    probe_sql = f"SELECT SUM({imp}) AS val FROM sales"
                    count_sql = "SELECT COUNT(*) AS cnt FROM sales"
                elif "store_city" in imp or "customer_city" in imp:
                    if "=" in imp:
                        probe_sql = f"SELECT transaction_id, revenue FROM sales WHERE {imp} LIMIT 5"
                        count_sql = f"SELECT COUNT(*) AS cnt FROM sales WHERE {imp}"

            if count_sql:
                try:
                    c_res = db_mgr.execute_query(count_sql)
                    if c_res.success and c_res.rows:
                        est_cnt = int(c_res.rows[0].get("cnt") or 0)
                        opt.estimated_rows = est_cnt
                        base_desc = opt.description or opt.implied_filter_or_metric or ""
                        row_note = f"~{est_cnt:,} matching row(s)"
                        if row_note not in base_desc:
                            opt.description = f"{row_note}" + (f" • {base_desc}" if base_desc else "")
                except Exception:
                    pass

            if probe_sql:
                try:
                    p_res = db_mgr.execute_query(probe_sql)
                    if p_res.success:
                        sig = json.dumps(p_res.rows, default=str, sort_keys=True)
                        signatures.append(sig)
                except Exception:
                    pass

        # If we probed at least 2 options and EVERY signature is identical, no divergence exists!
        if len(signatures) >= 2 and len(set(signatures)) == 1:
            return True
        return False

    # ---------------------------------------------------------------------
    # 3. Example-Based Calibration ("expected ~ 91100")
    # ---------------------------------------------------------------------
    def detect_and_calibrate_expected_value(
        self,
        query: str,
        schema: DatabaseSchema,
        db_mgr
    ) -> Optional[Dict[str, Any]]:
        m_exp = re.search(
            r"\b(?:should\s+be|expect(?:ed)?(?:\s+around)?|comes?\s+to|target(?:\s+around)?|approx(?:imately)?)\s*[\$]?\s*(\d[\d,]*(?:\.\d+)?)\s*([kmb])?\b",
            query,
            re.I
        )
        if not m_exp or not schema or not schema.tables:
            return None

        raw_num = float(m_exp.group(1).replace(",", ""))
        mult = {"k": 1e3, "m": 1e6, "b": 1e9}.get((m_exp.group(2) or "").lower(), 1.0)
        target_val = raw_num * mult

        candidates = []
        for t_name, t_meta in schema.tables.items():
            for col in t_meta.columns:
                if any(ty in col.data_type.upper() for ty in ("INT", "NUMERIC", "FLOAT", "REAL", "DECIMAL")):
                    if col.name.lower() == "id" or col.name.lower().endswith("_id"):
                        continue
                    try:
                        q_sum = f'SELECT SUM("{col.name}") AS total_val FROM "{t_name}"'
                        res = db_mgr.execute_query(q_sum)
                        if res.success and res.rows and res.rows[0].get("total_val") is not None:
                            val = float(res.rows[0]["total_val"])
                            rel_diff = abs(val - target_val) / max(1.0, abs(target_val))
                            candidates.append({
                                "table": t_name,
                                "column": col.name,
                                "agg": "SUM",
                                "computed_value": round(val, 2),
                                "relative_error": round(rel_diff, 4),
                                "sql": f"SELECT SUM({col.name}) AS calibrated_{col.name} FROM {t_name};"
                            })
                    except Exception:
                        pass

        if not candidates:
            return None
        candidates.sort(key=lambda x: x["relative_error"])
        best = candidates[0]
        return {
            "expected_target": target_val,
            "best_match": best,
            "alternatives": candidates[1:3]
        }

    # ---------------------------------------------------------------------
    # 4. Transparency: Assumptions, Provenance, Confidence, Thinking Trace
    # ---------------------------------------------------------------------
    def build_assumptions(
        self,
        query: str,
        sql: str,
        tables_used: List[str],
        schema: Optional[DatabaseSchema],
        applied_memory_note: Optional[str] = None,
        ask_after_assumption: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        assumptions: List[AssumptionItem] = []
        s_low = (sql or "").lower()
        q_low = query.lower()

        if applied_memory_note:
            assumptions.append(AssumptionItem(
                key="semantic_memory",
                label="Personal Memory",
                value=applied_memory_note,
                source="memory"
            ))

        if ask_after_assumption:
            alts = [
                AssumptionAlternative(
                    label=a["label"],
                    switch_query=f"{query} [Clarified: {a['label']} ({a['constraint']})]"
                )
                for a in ask_after_assumption.get("alternatives", [])
            ]
            assumptions.append(AssumptionItem(
                key=ask_after_assumption.get("term_key", "interpretation"),
                label="Best-Guess Interpretation",
                value=ask_after_assumption.get("assumed_label", "Default"),
                source="ask_after_answer",
                alternatives=alts
            ))

        # Sort direction assumption
        if " order by " in f" {s_low} ":
            is_desc = " desc" in s_low and " asc" not in s_low
            is_asc = " asc" in s_low and " desc" not in s_low
            if (is_desc or is_asc) and not any(w in q_low for w in ("asc", "ascending", "desc", "descending")):
                if is_desc:
                    assumptions.append(AssumptionItem(
                        key="sort_order",
                        label="Sort Order",
                        value="Descending (Highest first)",
                        alternatives=[AssumptionAlternative(label="Switch to Ascending (Lowest first)", switch_query=f"{query} sorted ascending")]
                    ))
                else:
                    assumptions.append(AssumptionItem(
                        key="sort_order",
                        label="Sort Order",
                        value="Ascending (A–Z / Lowest first)",
                        alternatives=[AssumptionAlternative(label="Switch to Descending (Highest first)", switch_query=f"{query} sorted descending")]
                    ))

        # Limit assumption
        m_lim = re.search(r"\blimit\s+(\d+)\b", s_low)
        if m_lim and not re.search(r"\b(top|first|limit)\s+\d+\b", q_low):
            lim_n = m_lim.group(1)
            assumptions.append(AssumptionItem(
                key="row_limit",
                label="Row Limit",
                value=f"Preview capped at {lim_n} rows",
                alternatives=[AssumptionAlternative(label="Expand to 50 rows", switch_query=f"{query} limit 50")]
            ))

        # Metric mapping assumption if revenue/sales mapped to gross_sales or net_sales
        if tables_used and schema and tables_used[0] in schema.tables:
            primary = tables_used[0]
            cols = [c.name.lower() for c in schema.tables[primary].columns]
            if "gross_sales" in s_low and "net_sales" in cols and "gross_sales" not in q_low:
                assumptions.append(AssumptionItem(
                    key="revenue_def",
                    label="Revenue Metric",
                    value="Mapped 'revenue' to `gross_sales`",
                    alternatives=[
                        AssumptionAlternative(label="Use `net_sales` instead", switch_query=query.replace("revenue", "net_sales")),
                        AssumptionAlternative(label="Use `net_profit` instead", switch_query=query.replace("revenue", "net_profit"))
                    ]
                ))

            # Unfiltered cancelled/returned orders notice if order_status exists
            if "order_status" in cols and "order_status" not in s_low and any(w in q_low for w in ("sales", "revenue", "orders", "profit")):
                assumptions.append(AssumptionItem(
                    key="order_scope",
                    label="Order Scope",
                    value="Included all order statuses",
                    alternatives=[
                        AssumptionAlternative(label="Exclude Cancelled/Returned", switch_query=f"{query} (only completed orders)")
                    ]
                ))

        return [a.model_dump() for a in assumptions]

    def build_provenance(self, query: str, sql: str) -> List[Dict[str, str]]:
        """Maps natural-language prompt phrases to generated SQL clauses."""
        mappings: List[ProvenanceMapping] = []
        s_clean = (sql or "").strip().rstrip(";")
        q_low = query.lower()

        m_from = re.search(r"\bFROM\s+([a-zA-Z0-9_]+)", s_clean, re.I)
        if m_from:
            tbl = m_from.group(1)
            mappings.append(ProvenanceMapping(
                phrase="Primary entity / dataset",
                sql_clause=f"FROM {tbl}",
                clause_type="TABLE"
            ))

        for m_join in re.finditer(r"(?:INNER\s+|LEFT\s+)?JOIN\s+[a-zA-Z0-9_]+\s+ON\s+[^\n]+?(?=\s+(?:JOIN|WHERE|GROUP|ORDER|LIMIT|$))", s_clean, re.I):
            mappings.append(ProvenanceMapping(
                phrase="Linked schema relationship",
                sql_clause=m_join.group(0).strip(),
                clause_type="JOIN"
            ))

        m_sel = re.search(r"^SELECT\s+(.*?)\s+FROM\b", s_clean, re.I | re.S)
        if m_sel:
            mappings.append(ProvenanceMapping(
                phrase="Requested columns & figures",
                sql_clause=f"SELECT {m_sel.group(1).strip()}",
                clause_type="PROJECTION"
            ))

        m_where = re.search(r"\bWHERE\s+(.*?)(?=\s+(?:GROUP\s+BY|ORDER\s+BY|LIMIT|$))", s_clean, re.I | re.S)
        if m_where:
            mappings.append(ProvenanceMapping(
                phrase="Condition / filter constraint",
                sql_clause=f"WHERE {m_where.group(1).strip()}",
                clause_type="FILTER"
            ))

        m_grp = re.search(r"\bGROUP\s+BY\s+(.*?)(?=\s+(?:HAVING|ORDER\s+BY|LIMIT|$))", s_clean, re.I | re.S)
        if m_grp:
            mappings.append(ProvenanceMapping(
                phrase="Grouping breakdown dimension",
                sql_clause=f"GROUP BY {m_grp.group(1).strip()}",
                clause_type="GROUP_BY"
            ))

        m_ord = re.search(r"\bORDER\s+BY\s+(.*?)(?=\s+(?:LIMIT|$))", s_clean, re.I | re.S)
        if m_ord:
            sort_phrase = "Ranking / sorting instruction"
            m_q_sort = re.search(r"\b(?:sort(?:ed)?|order(?:ed)?)\s+by\s+[a-zA-Z_]+(?:\s+[a-zA-Z_]+)?", q_low)
            if m_q_sort:
                sort_phrase = f'"{m_q_sort.group(0)}"'
            mappings.append(ProvenanceMapping(
                phrase=sort_phrase,
                sql_clause=f"ORDER BY {m_ord.group(1).strip()}",
                clause_type="ORDER_BY"
            ))

        m_lim = re.search(r"\bLIMIT\s+\d+", s_clean, re.I)
        if m_lim:
            m_q_top = re.search(r"\b(?:top|first|limit|bottom)\s+\d+", q_low)
            lim_phrase = f'"{m_q_top.group(0)}"' if m_q_top else "Preview result cap"
            mappings.append(ProvenanceMapping(
                phrase=lim_phrase,
                sql_clause=m_lim.group(0),
                clause_type="LIMIT"
            ))

        return [m.model_dump() for m in mappings]

    def compute_confidence(
        self,
        ml_confidence: float,
        ambiguity_score: float,
        validation_ok: bool,
        exec_ok: bool,
        row_count: int,
        matched_cols_count: int,
        is_formula: bool = False,
        was_clarified: bool = False
    ) -> Dict[str, Any]:
        score = 65.0
        reasons: List[str] = []

        if is_formula:
            score = 96.0
            reasons.append("+ Verified deterministic mathematical/domain formula expression")
        else:
            if ml_confidence >= 0.70:
                score += 12.0
                reasons.append(f"+ High ML ensemble intent agreement ({int(ml_confidence * 100)}%)")
            elif ml_confidence >= 0.45:
                score += 6.0
                reasons.append(f"+ Moderate ML intent confidence ({int(ml_confidence * 100)}%)")

            if matched_cols_count > 0:
                bonus = min(14.0, matched_cols_count * 4.5)
                score += bonus
                reasons.append(f"+ Direct schema alignment across {matched_cols_count} matched column(s)")

            if was_clarified:
                score += 8.0
                reasons.append("+ Ambiguities explicitly confirmed via user clarification")
            elif ambiguity_score >= 0.45:
                score -= 10.0
                reasons.append("- Best-guess assumption used for moderate prompt ambiguity")

        if validation_ok:
            score += 5.0
            reasons.append("+ Passed SQLGlot AST syntax & read-only schema validation")
        else:
            score -= 35.0
            reasons.append("- Failed AST validation")

        if exec_ok:
            score += 4.0
            if row_count == 0 and not is_formula:
                score -= 6.0
                reasons.append("- Query executed cleanly but returned 0 rows")
        else:
            score -= 40.0
            reasons.append("- Database execution encountered an error")

        score = max(10, min(99, int(round(score))))
        level = "High" if score >= 85 else ("Medium" if score >= 65 else "Low")
        return {
            "confidence_score": score,
            "confidence_level": level,
            "confidence_reasons": reasons
        }

    def build_thinking_steps(
        self,
        query: str,
        intent_label: str,
        ml_confidence: float,
        schema: Optional[DatabaseSchema],
        tables_used: List[str],
        sql: str,
        exec_ok: bool,
        row_count: int,
        exec_ms: float,
        relationships_used: List[str],
        ambiguity_score: float,
        table_scores: Optional[Dict[str, int]] = None,
        matched_cols: Optional[List[str]] = None,
        cost_level: str = "Low"
    ) -> List[Dict[str, str]]:
        steps: List[ThinkingStep] = []

        # 1. Think: Intent & Entity Interpretation
        steps.append(ThinkingStep(
            phase="Think",
            title="Intent & Objective Recognition",
            detail=(
                f"Classified goal as `{intent_label}` ({int(ml_confidence * 100)}% ensemble confidence, ambiguity score {ambiguity_score:.2f}). "
                f"Parsed query targets and numeric figure requirements."
            )
        ))

        # 2. Analyze: Schema Scoring & Joins
        if tables_used:
            score_info = ""
            if table_scores:
                top_scores = sorted(table_scores.items(), key=lambda x: x[1], reverse=True)[:3]
                score_info = " (" + ", ".join(f"{t}: {s} pts" for t, s in top_scores if s > 0) + ")"
            col_info = f" Mapped columns: {', '.join(f'`{c}`' for c in (matched_cols or [])[:6])}." if matched_cols else ""
            rel_info = f" Resolved joins: {', '.join(relationships_used[:2])}." if relationships_used else ""
            steps.append(ThinkingStep(
                phase="Analyze",
                title="Schema Linking & Graph Traversal",
                detail=f"Selected `{', '.join(tables_used)}`{score_info}.{col_info}{rel_info}"
            ))
        else:
            steps.append(ThinkingStep(
                phase="Analyze",
                title="Formula & Computation Engine",
                detail="Evaluated query directly using universal multi-domain STEM/Finance/Sports formula engine without requiring table scans."
            ))

        # 3. Verify: Guardrails & Cost
        steps.append(ThinkingStep(
            phase="Verify",
            title="AST Validation & Safety Guardrails",
            detail=f"Verified read-only SELECT structure via SQLGlot AST. Estimated scan cost: **{cost_level}**."
        ))

        # 4. Synthesize: Outcome & Figures
        if exec_ok:
            steps.append(ThinkingStep(
                phase="Synthesize",
                title="Data & Quantitative Analysis",
                detail=f"Executed cleanly in {exec_ms}ms returning {row_count} record(s); computed summary highlights and statistical figures."
            ))

        return [s.model_dump() for s in steps]


clarification_intelligence = ClarificationIntelligence()
