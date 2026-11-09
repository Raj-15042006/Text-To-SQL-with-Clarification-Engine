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
            return db_manager.get_schema().filter_by_tables(allowed_tables)
        elif not schema_context.strip():
            return db_manager.get_schema().filter_by_tables([])
        return db_manager.get_schema()

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
        learned_match = None if is_context_followup else self.learner.find_similar_sample(user_query, threshold=0.88)
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
        learned_match = None if is_context_followup else self.learner.find_similar_sample(resolved_query, threshold=0.85)
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
        Generates a concise, analytical executive explanation of execution results.
        """
        if total_rows == 0:
            return "No matching records were found in the active database."

        # Single scalar / formula outcome
        if len(sample_rows) == 1 and len(columns) == 1:
            col = columns[0]
            val = sample_rows[0].get(col)
            col_disp = col.replace("_", " ").title()
            val_fmt = f"{val:,.2f}" if isinstance(val, float) else f"{val:,}" if isinstance(val, int) else str(val)
            return f"The calculated **{col_disp}** is **{val_fmt}**."

        if len(sample_rows) == 1:
            row = sample_rows[0]
            parts = []
            for k, v in row.items():
                if v is not None:
                    k_disp = k.replace("_", " ").title()
                    v_fmt = f"{v:,.2f}" if isinstance(v, float) else f"{v:,}" if isinstance(v, int) else str(v)
                    parts.append(f"**{k_disp}**: {v_fmt}")
            return f"Calculated Result: {', '.join(parts)}."

        # Multi-row summary
        first_row = sample_rows[0]
        lead_val = next(iter(first_row.values()), "")
        return f"The query returned **{total_rows}** matching record(s). Top result: **{lead_val}**."

