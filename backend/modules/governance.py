import json
import re
import uuid
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.database.schema_extractor import DatabaseSchema

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
AUDIT_FILE = DATA_DIR / "audit_log.json"

PII_COL_KEYWORDS = {
    "email", "e_mail", "mail", "phone", "mobile", "cell", "telephone",
    "ssn", "social_security", "passport", "aadhaar", "aadhar", "pan_number",
    "credit_card", "card_number", "cvv", "password", "passwd", "secret",
    "dob", "date_of_birth", "birth_date", "salary", "compensation", "street_address"
}

EMAIL_RX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
PHONE_RX = re.compile(r"^(?:\+?\d[\d\s\-]{7,14}\d)$")


class AuditRecord(BaseModel):
    audit_id: str = Field(default_factory=lambda: f"aud_{uuid.uuid4().hex[:10]}")
    timestamp: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    query: str
    ambiguity_score: float = 0.0
    clarification_asked: bool = False
    clarification_changed_sql: bool = False
    resolution_turns: int = 1
    generated_sql: Optional[str] = None
    tables_used: List[str] = Field(default_factory=list)
    cost_level: str = "Low"
    pii_columns: List[str] = Field(default_factory=list)
    success: bool = True
    execution_time_ms: float = 0.0
    feedback_question: Optional[int] = None  # 1 or -1
    feedback_result: Optional[int] = None    # 1 or -1


class GovernanceManager:
    """
    Implements Section 6 & 7 Security, Cost Guardrails, Data Quality, PII Awareness,
    Immutable Read-Only Audit Logging, and Clarification Quality Metrics.
    """

    def __init__(self):
        self._audit_log: List[AuditRecord] = []
        self._load()

    def _load(self):
        try:
            if AUDIT_FILE.exists():
                raw = json.load(open(AUDIT_FILE, "r", encoding="utf-8"))
                if isinstance(raw, list):
                    self._audit_log = [AuditRecord(**x) for x in raw]
        except Exception as e:
            logger.warning(f"Could not load audit log: {e}")

    def _save(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(AUDIT_FILE, "w", encoding="utf-8") as f:
                json.dump([r.model_dump() for r in self._audit_log[-1000:]], f, indent=2)
        except Exception as e:
            logger.error(f"Could not save audit log: {e}")

    # ---------------------------------------------------------------------
    # 1. Query Cost Guardrails (EXPLAIN + Row Scan Estimation)
    # ---------------------------------------------------------------------
    def estimate_query_cost(
        self,
        sql: str,
        tables_referenced: List[str],
        db_mgr
    ) -> Dict[str, Any]:
        clean_sql = (sql or "").strip().rstrip(";")
        if not clean_sql or not tables_referenced:
            return {
                "cost_level": "Low",
                "estimated_rows_scanned": 0,
                "plan_summary": "Scalar computation (no table scan required).",
                "warning": None
            }

        total_rows = 0
        for t in tables_referenced:
            try:
                res = db_mgr.execute_query(f'SELECT COUNT(*) AS cnt FROM "{t}"')
                if res.success and res.rows:
                    total_rows += int(res.rows[0].get("cnt") or 0)
            except Exception:
                pass

        plan_parts = []
        is_full_scan = False
        try:
            if db_mgr.active_source == "postgresql":
                exp_res = db_mgr.execute_query(f"EXPLAIN {clean_sql}")
                if exp_res.success and exp_res.rows:
                    plan_parts = [str(next(iter(r.values()))) for r in exp_res.rows[:4]]
                    if any("Seq Scan" in p for p in plan_parts):
                        is_full_scan = True
            else:
                exp_res = db_mgr.execute_query(f"EXPLAIN QUERY PLAN {clean_sql}")
                if exp_res.success and exp_res.rows:
                    plan_parts = [str(r.get("detail") or r) for r in exp_res.rows[:4]]
                    if any("SCAN" in p.upper() for p in plan_parts):
                        is_full_scan = True
        except Exception:
            pass

        has_where = " where " in f" {clean_sql.lower()} "
        has_small_limit = False
        m_lim = re.search(r"\blimit\s+(\d+)\b", clean_sql, re.I)
        if m_lim and int(m_lim.group(1)) <= 100:
            has_small_limit = True

        cost_level = "Low"
        warning = None
        if total_rows >= 50000 and not has_where and not has_small_limit:
            cost_level = "High"
            warning = f"High scan cost: query scans ~{total_rows:,} rows without a WHERE filter or narrow LIMIT. Consider adding a date/category filter."
        elif (is_full_scan and total_rows >= 5000 and not has_where) or len(tables_referenced) >= 3:
            cost_level = "Medium"
            if total_rows >= 5000 and not has_where:
                warning = f"Moderate scan: evaluates ~{total_rows:,} rows across {', '.join(tables_referenced)}."

        return {
            "cost_level": cost_level,
            "estimated_rows_scanned": total_rows,
            "plan_summary": "; ".join(plan_parts) if plan_parts else f"Reads up to {total_rows:,} rows across {len(tables_referenced)} table(s).",
            "warning": warning
        }

    # ---------------------------------------------------------------------
    # 2. Data-Quality Warnings (NULL / Completeness Check)
    # ---------------------------------------------------------------------
    def check_data_quality(
        self,
        tables_referenced: List[str],
        columns_referenced: List[str],
        schema: Optional[DatabaseSchema],
        db_mgr
    ) -> List[str]:
        warnings: List[str] = []
        if not tables_referenced or not schema:
            return warnings

        checked = 0
        for tbl in tables_referenced[:2]:
            t_meta = schema.tables.get(tbl)
            if not t_meta:
                continue

            # Pick columns to check (either referenced in query or up to 3 nullable data columns)
            ref_low = {c.lower() for c in columns_referenced}
            cols_to_check = [c.name for c in t_meta.columns if c.name.lower() in ref_low and not c.is_primary_key]
            if not cols_to_check:
                cols_to_check = [c.name for c in t_meta.columns if not c.is_primary_key][:3]

            for col in cols_to_check[:3]:
                if checked >= 4:
                    break
                checked += 1
                try:
                    q = f'SELECT COUNT(*) AS tot, SUM(CASE WHEN "{col}" IS NULL OR CAST("{col}" AS TEXT) = \'\' THEN 1 ELSE 0 END) AS nulls FROM "{tbl}"'
                    res = db_mgr.execute_query(q)
                    if res.success and res.rows:
                        tot = int(res.rows[0].get("tot") or 0)
                        nulls = int(res.rows[0].get("nulls") or 0)
                        if tot > 0 and nulls > 0:
                            pct = round((nulls / tot) * 100.0, 1)
                            if pct >= 10.0:
                                warnings.append(
                                    f"Data quality warning: {pct}% ({nulls}/{tot}) of `{tbl}.{col}` values are NULL or empty; aggregations/filters may exclude missing records."
                                )
                except Exception:
                    pass

        return warnings

    # ---------------------------------------------------------------------
    # 3. PII-Aware Detection & Masking
    # ---------------------------------------------------------------------
    @staticmethod
    def _mask_val(col_name: str, val: Any) -> Any:
        if val is None:
            return None
        s = str(val)
        c_low = col_name.lower()
        if EMAIL_RX.match(s) or "mail" in c_low:
            if "@" in s:
                local, dom = s.split("@", 1)
                masked_local = (local[0] + "***") if local else "***"
                return f"{masked_local}@{dom}"
        if PHONE_RX.match(s) or any(k in c_low for k in ("phone", "mobile", "ssn", "aadhaar", "card")):
            if len(s) >= 4:
                return "*" * max(3, len(s) - 4) + s[-4:]
            return "****"
        if "password" in c_low or "secret" in c_low:
            return "••••••••"
        if "salary" in c_low:
            return "[REDACTED]"
        if len(s) > 2:
            return s[0] + "***" + s[-1]
        return "***"

    def inspect_and_mask_pii(
        self,
        columns: List[str],
        rows: List[Dict[str, Any]],
        mask_enabled: bool = False
    ) -> Dict[str, Any]:
        pii_cols: List[str] = []
        for col in columns:
            c_low = col.lower()
            if c_low in PII_COL_KEYWORDS or any(k in c_low for k in ("email", "phone", "mobile", "ssn", "passport", "aadhaar", "credit_card", "password")):
                pii_cols.append(col)
                continue
            # Value-based sampling across top 5 rows
            for r in rows[:5]:
                val = r.get(col)
                if isinstance(val, str) and (EMAIL_RX.match(val.strip()) or PHONE_RX.match(val.strip())):
                    pii_cols.append(col)
                    break

        pii_cols = list(dict.fromkeys(pii_cols))
        processed_rows = rows
        if mask_enabled and pii_cols and rows:
            processed_rows = []
            for r in rows:
                nr = dict(r)
                for pcol in pii_cols:
                    if pcol in nr:
                        nr[pcol] = self._mask_val(pcol, nr[pcol])
                processed_rows.append(nr)

        warning = None
        if pii_cols:
            if mask_enabled:
                warning = f"PII-Aware Mode Active: Masked sensitive column(s) {', '.join(f'`{c}`' for c in pii_cols)}."
            else:
                warning = f"PII Notice: Output includes sensitive column(s) {', '.join(f'`{c}`' for c in pii_cols)}. Consider masking or aggregating."

        return {
            "pii_columns": pii_cols,
            "rows": processed_rows,
            "warning": warning
        }

    # ---------------------------------------------------------------------
    # 4. Audit Log & Section 7 Evaluation Metrics
    # ---------------------------------------------------------------------
    def log_query_event(
        self,
        user_id: Optional[str],
        session_id: Optional[str],
        query: str,
        ambiguity_score: float = 0.0,
        clarification_asked: bool = False,
        clarification_changed_sql: bool = False,
        resolution_turns: int = 1,
        generated_sql: Optional[str] = None,
        tables_used: Optional[List[str]] = None,
        cost_level: str = "Low",
        pii_columns: Optional[List[str]] = None,
        success: bool = True,
        execution_time_ms: float = 0.0
    ) -> AuditRecord:
        # Update existing session entry if clarification completed the session
        for existing in reversed(self._audit_log):
            if session_id and existing.session_id == session_id:
                existing.clarification_changed_sql = clarification_changed_sql
                existing.resolution_turns = resolution_turns
                existing.generated_sql = generated_sql
                existing.tables_used = tables_used or existing.tables_used
                existing.cost_level = cost_level
                existing.pii_columns = pii_columns or existing.pii_columns
                existing.success = success
                existing.execution_time_ms = execution_time_ms
                self._save()
                return existing

        rec = AuditRecord(
            user_id=user_id,
            session_id=session_id,
            query=query,
            ambiguity_score=round(ambiguity_score, 3),
            clarification_asked=clarification_asked,
            clarification_changed_sql=clarification_changed_sql,
            resolution_turns=resolution_turns,
            generated_sql=generated_sql,
            tables_used=tables_used or [],
            cost_level=cost_level,
            pii_columns=pii_columns or [],
            success=success,
            execution_time_ms=execution_time_ms
        )
        self._audit_log.append(rec)
        self._save()
        return rec

    def record_feedback(
        self,
        session_id: Optional[str],
        query: Optional[str] = None,
        feedback_result: Optional[int] = None,
        feedback_question: Optional[int] = None
    ) -> bool:
        for rec in reversed(self._audit_log):
            if (session_id and rec.session_id == session_id) or (query and rec.query == query):
                if feedback_result is not None:
                    rec.feedback_result = feedback_result
                if feedback_question is not None:
                    rec.feedback_question = feedback_question
                self._save()
                return True
        return False

    def get_audit_log(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        logs = self._audit_log
        if user_id:
            logs = [r for r in logs if r.user_id == user_id]
        return [r.model_dump() for r in reversed(logs)][:limit]

    def compute_quality_metrics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        logs = self._audit_log
        if user_id:
            logs = [r for r in logs if r.user_id == user_id]

        total = len(logs)
        if total == 0:
            return {
                "total_queries": 0,
                "clarification_rate_pct": 0.0,
                "question_usefulness_pct": 100.0,
                "avg_resolution_turns": 1.0,
                "silent_failure_rate_pct": 0.0,
                "avg_ambiguity_score": 0.0,
                "positive_feedback_rate_pct": 100.0,
                "pii_flagged_queries": 0
            }

        clarified = [r for r in logs if r.clarification_asked]
        clar_rate = round((len(clarified) / total) * 100.0, 1)

        useful_cnt = sum(1 for r in clarified if r.clarification_changed_sql or r.feedback_question == 1)
        q_usefulness = round((useful_cnt / len(clarified)) * 100.0, 1) if clarified else 100.0

        avg_turns = round(sum(r.resolution_turns for r in logs) / total, 2)
        avg_amb = round(sum(r.ambiguity_score for r in logs) / total, 3)

        # Silent failure: unclarified query that either failed execution or received thumbs down
        unclarified = [r for r in logs if not r.clarification_asked]
        silent_fails = sum(1 for r in unclarified if (not r.success or r.feedback_result == -1))
        silent_rate = round((silent_fails / max(1, len(unclarified))) * 100.0, 1)

        fb_items = [r for r in logs if r.feedback_result is not None]
        pos_fb = round((sum(1 for r in fb_items if r.feedback_result == 1) / len(fb_items)) * 100.0, 1) if fb_items else 100.0

        pii_cnt = sum(1 for r in logs if r.pii_columns)

        return {
            "total_queries": total,
            "clarification_rate_pct": clar_rate,
            "question_usefulness_pct": q_usefulness,
            "avg_resolution_turns": avg_turns,
            "silent_failure_rate_pct": silent_rate,
            "avg_ambiguity_score": avg_amb,
            "positive_feedback_rate_pct": pos_fb,
            "pii_flagged_queries": pii_cnt
        }


governance_manager = GovernanceManager()

