"""
Local Self-Learning NLP Provider
Implements BaseLLMProvider without relying on external Gemini/cloud APIs.
Uses LocalNLPEngine for schema-linking & SQL generation, and SelfLearningEngine
for continuous improvement from user interactions and feedback.
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional

from backend.llm.base import BaseLLMProvider, SQLGenerationResult
from backend.modules.ambiguity import (
    QueryAnalysis,
    AmbiguityCategory,
    ClarificationRequest,
    ClarificationOption,
    ambiguity_detector
)
from backend.modules.nlp_engine import local_nlp_engine
from backend.modules.learning_engine import learning_engine
from backend.database.connection import db_manager

logger = logging.getLogger(__name__)


class LocalNLPProvider(BaseLLMProvider):
    """
    Self-contained, offline NLP provider with continuous self-learning.
    Operates 100% locally with zero internet dependency or API rate limits.
    """

    def __init__(self):
        self.nlp = local_nlp_engine
        self.learner = learning_engine

    def _resolve_schema_from_context(self, schema_context: str):
        allowed_tables = re.findall(r"^Table:\s*([a-zA-Z0-9_]+)", schema_context, re.M)
        if allowed_tables:
            schema = db_manager.get_schema().filter_by_tables(allowed_tables)
        elif not schema_context.strip():
            return db_manager.get_schema().filter_by_tables([])
        else:
            schema = db_manager.get_schema()

        # Merge any custom/user-configured FK links encoded in schema_context
        curr_tbl = None
        for line in schema_context.splitlines():
            t_match = re.match(r"^Table:\s*([a-zA-Z0-9_]+)", line.strip())
            if t_match:
                curr_tbl = t_match.group(1)
                continue
            if curr_tbl and curr_tbl in schema.tables:
                fk_match = re.match(r"^FK:\s*([a-zA-Z0-9_]+)\s*->\s*([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)(?:\s*\(([^)]+)\))?", line.strip())
                if fk_match:
                    col_name = fk_match.group(1)
                    ref_target = fk_match.group(2)
                    cardinality = fk_match.group(3) or "Many-to-One"
                    t_meta = schema.tables[curr_tbl]
                    exists = any(
                        fk.get("column") == col_name and fk.get("references") == ref_target
                        for fk in t_meta.foreign_keys
                    )
                    if not exists:
                        t_meta.foreign_keys.append({
                            "column": col_name,
                            "references": ref_target,
                            "cardinality": cardinality,
                            "is_active": True,
                            "is_manual": True
                        })
                        for col in t_meta.columns:
                            if col.name == col_name:
                                col.is_foreign_key = True
                                col.foreign_key_target = ref_target
                                break

        return schema

    def analyze_query(
        self, 
        user_query: str, 
        schema_context: str, 
        history: Optional[List[Dict[str, Any]]] = None
    ) -> QueryAnalysis:
        """
        Analyzes query intent, performs entity extraction and ambiguity detection,
        and generates PostgreSQL SQL locally.
        """
        schema = self._resolve_schema_from_context(schema_context)

        # 1. Structural Ambiguity Detection (All 7 categories)
        det_res = ambiguity_detector.detect(user_query, schema=schema, history=history)
        if det_res.is_ambiguous:
            return det_res.to_query_analysis(user_query)

        # 2. Predict Analytical Intent using Trained ML Model
        intent, confidence = self.learner.predict_intent(user_query)

        # 3. Check for Learned Memory Match (skip static match for dynamic context follow-ups)
        is_context_followup = bool(
            history and (
                any(re.search(rf"\b{w}\b", user_query.lower()) for w in ["his", "her", "their", "them", "it", "those", "which", "whose", "now", "also"])
                or any(p in user_query.lower() for p in ["now show", "now only", "also", "what about", "how about", "sort them", "what was his"])
            )
        )
        learned_match = None if is_context_followup else self.learner.find_similar_sample(
            user_query, threshold=0.90, allowed_tables=list(schema.tables.keys())
        )
        if learned_match:
            sql = learned_match.sql
            explanation = f"Generated from learned pattern (intent: {intent}, confidence: {confidence * 100:.1f}%)."
            tables_used = learned_match.tables_used
        else:
            # 4. Synthesize SQL via Schema-Linking NLP Engine
            sql, explanation = self.nlp.generate_sql(user_query, schema=schema, history=history)
            slots = self.nlp.extract_slots(user_query, schema=schema, history=history)
            tables_used = slots.tables

        return QueryAnalysis(
            intent=f"Analytical goal: {intent} (confidence: {confidence:.2f})",
            is_ambiguous=False,
            ambiguity_type=AmbiguityCategory.NONE,
            suggested_tables=tables_used,
            generated_sql=sql,
            sql_explanation=explanation
        )

    def generate_sql(
        self, 
        resolved_query: str, 
        schema_context: str, 
        clarification_notes: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None
    ) -> SQLGenerationResult:
        """
        Generates PostgreSQL-compliant SQL query based on resolved intent and schema.
        """
        schema = self._resolve_schema_from_context(schema_context)

        # Check for learned pattern match first (skip for dynamic context follow-ups)
        is_context_followup = bool(
            history and (
                any(re.search(rf"\b{w}\b", resolved_query.lower()) for w in ["his", "her", "their", "them", "it", "those", "which", "whose", "now", "also"])
                or any(p in resolved_query.lower() for p in ["now show", "now only", "also", "what about", "how about", "sort them", "what was his"])
            )
        )
        learned_match = None if is_context_followup else self.learner.find_similar_sample(
            resolved_query, threshold=0.90, allowed_tables=list(schema.tables.keys())
        )
        if learned_match:
            return SQLGenerationResult(
                sql=learned_match.sql,
                explanation=f"Synthesized from trained memory pattern ({learned_match.intent}).",
                tables_used=learned_match.tables_used
            )

        sql, explanation = self.nlp.generate_sql(resolved_query, schema=schema, history=history)
        slots = self.nlp.extract_slots(resolved_query, schema=schema, history=history)
        return SQLGenerationResult(
            sql=sql,
            explanation=explanation,
            tables_used=slots.tables
        )

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
        Generates a ChatGPT-style structured analytical explanation with key findings,
        highlighted figures for top records, and statistical distribution across numeric columns.
        """
        if total_rows == 0:
            return (
                "**Analysis Complete**: I executed the query cleanly, and **0 matching records** were found in the active dataset.\n\n"
                "- **Suggestion**: Check filter criteria or inspect available values in the sidebar tables."
            )

        def _fmt_num(v: Any) -> str:
            if isinstance(v, bool):
                return str(v)
            if isinstance(v, float):
                return f"{v:,.2f}"
            if isinstance(v, int):
                return f"{v:,}"
            return str(v)

        def _is_num(v: Any) -> bool:
            return isinstance(v, (int, float)) and not isinstance(v, bool)

        # 1. Single scalar / formula outcome
        if len(sample_rows) == 1 and len(columns) == 1:
            col = columns[0]
            val = sample_rows[0].get(col)
            col_disp = col.replace("_", " ").title()
            val_fmt = _fmt_num(val)
            return f"**Direct Answer**: The calculated **{col_disp}** is **{val_fmt}**."

        # 2. Single structured row (e.g. formula breakdown or team bowling metrics)
        if len(sample_rows) == 1:
            row = sample_rows[0]
            parts = []
            for k, v in row.items():
                if v is not None:
                    k_disp = k.replace("_", " ").title()
                    parts.append(f"**{k_disp}**: `{_fmt_num(v)}`")
            return f"**Analytical Result**:\n\n- " + "\n- ".join(parts)

        # 3. Multi-row analytical summary + highlights + numeric statistics
        lines = [f"**Answer**: Retrieved **{total_rows}** matching record(s) with complete figures across {len(columns)} column(s):"]

        # Highlight top 3 records cleanly with both labels & numeric figures
        highlight_limit = min(3, len(sample_rows))
        lines.append("\n### Key Highlights & Top Figures")
        for idx in range(highlight_limit):
            r = sample_rows[idx]
            label_parts = []
            fig_parts = []
            for col in columns:
                val = r.get(col)
                if val is None:
                    continue
                c_disp = col.replace("_", " ").title()
                if _is_num(val) and col.lower() not in ("id", "season", "enrollment_year") and not col.lower().endswith("_id"):
                    fig_parts.append(f"{c_disp}: **{_fmt_num(val)}**")
                else:
                    label_parts.append(f"**{val}**")

            title_str = " · ".join(label_parts[:2]) if label_parts else f"Row #{idx + 1}"
            figs_str = " | ".join(fig_parts[:4])
            if figs_str:
                lines.append(f"- **{idx + 1}.** {title_str} — {figs_str}")
            else:
                lines.append(f"- **{idx + 1}.** {title_str}")

        # Statistical Distribution across numeric columns (when multiple rows exist)
        num_stats = []
        for col in columns:
            c_low = col.lower()
            if c_low == "id" or c_low.endswith("_id") or c_low in ("season", "enrollment_year", "postal_code"):
                continue
            vals = [float(r[col]) for r in sample_rows if r.get(col) is not None and _is_num(r.get(col))]
            if len(vals) >= 2:
                c_disp = col.replace("_", " ").title()
                tot_v = sum(vals)
                avg_v = tot_v / len(vals)
                max_v = max(vals)
                min_v = min(vals)
                num_stats.append(
                    f"`{c_disp}`: Sum **{_fmt_num(round(tot_v, 2))}** · Avg **{_fmt_num(round(avg_v, 2))}** · Range **{_fmt_num(round(min_v, 2))} – {_fmt_num(round(max_v, 2))}**"
                )

        if num_stats:
            lines.append("\n### Quantitative Summary (Across Returned Rows)")
            for st in num_stats[:3]:
                lines.append(f"- {st}")

        if relationships_context:
            lines.append("\n*Multi-table schema relationships were resolved cleanly via active foreign keys.*")

        return "\n".join(lines)

