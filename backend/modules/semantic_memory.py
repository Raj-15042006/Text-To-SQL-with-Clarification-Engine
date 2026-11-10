import json
import uuid
import time
import hashlib
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.database.schema_extractor import DatabaseSchema

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
SEMANTIC_MEM_FILE = DATA_DIR / "semantic_memory.json"
GLOSSARY_FILE = DATA_DIR / "team_glossary.json"
REPLAY_FILE = DATA_DIR / "clarification_replays.json"


class PersonalMemoryEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:8]}")
    user_id: str
    term_key: str  # e.g. "sales_metric", "city_scope", "quarter_type", "pass_threshold"
    trigger_pattern: str
    preferred_label: str
    implied_constraint: str
    table_hint: Optional[str] = None
    schema_fingerprint: Optional[str] = None
    base_confidence: float = 0.95
    created_ts: float = Field(default_factory=time.time)
    last_used_ts: float = Field(default_factory=time.time)
    use_count: int = 1


class GlossaryTerm(BaseModel):
    id: str = Field(default_factory=lambda: f"gls_{uuid.uuid4().hex[:8]}")
    term: str
    definition: str
    sql_expression: str
    category: str = "metric"  # "metric" | "filter" | "entity" | "time"
    tables_related: List[str] = Field(default_factory=list)
    status: str = "pending"  # "pending" | "approved" | "rejected"
    proposed_by: str = "system"
    approved_by: Optional[str] = None
    created_at: float = Field(default_factory=time.time)


class ClarificationReplayTriple(BaseModel):
    id: str = Field(default_factory=lambda: f"rpl_{uuid.uuid4().hex[:8]}")
    user_id: Optional[str] = None
    original_query: str
    clarification_question: str
    selected_option_label: str
    applied_constraint: Optional[str] = None
    resolved_query: str
    final_sql: str
    tables_used: List[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)


VALID_PERSONAS = {
    "general": {
        "label": "General Analyst",
        "description": "Balanced interpretation across all datasets and metrics.",
        "metric_bias": {}
    },
    "finance": {
        "label": "Finance & Executive",
        "description": "Prioritizes net profit, revenue, fiscal quarters, and monetary totals.",
        "metric_bias": {
            "sales": "revenue",
            "quarter": "fiscal_quarter",
            "year": "financial_year",
            "profit": "net_profit"
        }
    },
    "marketing": {
        "label": "Marketing & Growth",
        "description": "Prioritizes customer location, conversion volume, units sold, and customer segments.",
        "metric_bias": {
            "city": "customer_city",
            "sales": "units_sold",
            "quarter": "calendar_quarter"
        }
    },
    "operations": {
        "label": "Operations & Logistics",
        "description": "Prioritizes store location, shipping speed, transit days, and inventory levels.",
        "metric_bias": {
            "city": "store_city",
            "quarter": "calendar_quarter"
        }
    },
    "academic": {
        "label": "Academic & STEM",
        "description": "Prioritizes exam scores, grades, attendance rates, and course performance.",
        "metric_bias": {
            "performance": "SUM(score)",
            "pass": "score >= 50"
        }
    }
}


class SemanticMemoryManager:
    """
    Manages Section 3 & 8 capabilities:
      - Personal Semantic Memory with Time & Schema-Change Confidence Decay
      - Self-Growing Team Glossary with Admin Approval Workflow
      - Clarification Replay Triples for Few-Shot Reuse
      - Multi-Persona Role Disambiguation Preferences
    """

    def __init__(self):
        self._memories: Dict[str, List[PersonalMemoryEntry]] = {}  # user_id -> list
        self._personas: Dict[str, str] = {}  # user_id -> persona_key
        self._glossary: List[GlossaryTerm] = []
        self._replays: List[ClarificationReplayTriple] = []
        self._load_all()

    def _load_all(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if SEMANTIC_MEM_FILE.exists():
                raw = json.load(open(SEMANTIC_MEM_FILE, "r", encoding="utf-8"))
                for uid, items in raw.get("memories", {}).items():
                    self._memories[uid] = [PersonalMemoryEntry(**x) for x in items]
                self._personas = raw.get("personas", {})
        except Exception as e:
            logger.warning(f"Could not load semantic memory: {e}")

        try:
            if GLOSSARY_FILE.exists():
                raw_g = json.load(open(GLOSSARY_FILE, "r", encoding="utf-8"))
                self._glossary = [GlossaryTerm(**x) for x in raw_g]
            else:
                self._seed_initial_glossary()
        except Exception as e:
            logger.warning(f"Could not load team glossary: {e}")

        try:
            if REPLAY_FILE.exists():
                raw_r = json.load(open(REPLAY_FILE, "r", encoding="utf-8"))
                self._replays = [ClarificationReplayTriple(**x) for x in raw_r]
        except Exception as e:
            logger.warning(f"Could not load clarification replays: {e}")

    def _seed_initial_glossary(self):
        self._glossary = [
            GlossaryTerm(
                id="gls_seed_1",
                term="Honor Roll Student",
                definition="Students with attendance >= 90% and average score >= 85.",
                sql_expression="students.attendance_percentage >= 90 AND marks.score >= 85",
                category="entity",
                tables_related=["students", "marks"],
                status="approved",
                proposed_by="system",
                approved_by="admin"
            ),
            GlossaryTerm(
                id="gls_seed_2",
                term="High-Value Sale",
                definition="Sales transactions exceeding $15,000 in revenue.",
                sql_expression="revenue > 15000",
                category="filter",
                tables_related=["sales"],
                status="approved",
                proposed_by="system",
                approved_by="admin"
            ),
        ]
        self._save_glossary()

    def _save_memories(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "memories": {uid: [m.model_dump() for m in lst] for uid, lst in self._memories.items()},
                "personas": self._personas
            }
            with open(SEMANTIC_MEM_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.error(f"Failed saving semantic memory: {e}")

    def _save_glossary(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(GLOSSARY_FILE, "w", encoding="utf-8") as f:
                json.dump([g.model_dump() for g in self._glossary], f, indent=2)
        except Exception as e:
            logger.error(f"Failed saving team glossary: {e}")

    def _save_replays(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(REPLAY_FILE, "w", encoding="utf-8") as f:
                json.dump([r.model_dump() for r in self._replays[-250:]], f, indent=2)
        except Exception as e:
            logger.error(f"Failed saving clarification replays: {e}")

    @staticmethod
    def compute_schema_fingerprint(schema: Optional[DatabaseSchema], table_name: Optional[str] = None) -> str:
        if not schema or not schema.tables:
            return "empty"
        if table_name and table_name in schema.tables:
            t_meta = schema.tables[table_name]
            sig = f"{t_meta.name}:" + ",".join(f"{c.name}:{c.data_type}" for c in t_meta.columns)
        else:
            parts = []
            for t in sorted(schema.tables.keys()):
                t_meta = schema.tables[t]
                parts.append(f"{t}(" + ",".join(c.name for c in t_meta.columns) + ")")
            sig = "|".join(parts)
        return hashlib.sha256(sig.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def compute_effective_confidence(mem: PersonalMemoryEntry, current_schema: Optional[DatabaseSchema]) -> Tuple[float, bool, str]:
        """
        Applies both temporal confidence decay and schema-change decay.
        Returns (effective_confidence, needs_reconfirmation, reason).
        """
        age_days = max(0.0, (time.time() - mem.last_used_ts) / 86400.0)
        # Gentle decay over 30+ days (~0.008 per day)
        time_decay = max(0.35, 1.0 - (age_days * 0.008))
        eff = round(mem.base_confidence * time_decay, 3)

        # Schema change check
        if mem.schema_fingerprint and current_schema and mem.table_hint and mem.table_hint in current_schema.tables:
            cur_fp = SemanticMemoryManager.compute_schema_fingerprint(current_schema, mem.table_hint)
            if cur_fp != mem.schema_fingerprint:
                eff = round(eff * 0.45, 3)
                return eff, True, f"Table '{mem.table_hint}' schema changed since this preference was saved."

        if eff < 0.60:
            return eff, True, f"Preference confidence decayed over time ({int(age_days)} days unused)."

        return eff, False, f"Active preference (confidence {int(eff * 100)}%)."

    def learn_preference(
        self,
        user_id: Optional[str],
        term_key: str,
        trigger_pattern: str,
        preferred_label: str,
        implied_constraint: str,
        schema: Optional[DatabaseSchema] = None,
        table_hint: Optional[str] = None
    ) -> PersonalMemoryEntry:
        uid = user_id or "default"
        fp = self.compute_schema_fingerprint(schema, table_hint) if schema else None
        user_mems = self._memories.setdefault(uid, [])

        # Update if term_key already exists for this user
        for m in user_mems:
            if m.term_key == term_key:
                m.trigger_pattern = trigger_pattern
                m.preferred_label = preferred_label
                m.implied_constraint = implied_constraint
                m.table_hint = table_hint or m.table_hint
                m.schema_fingerprint = fp or m.schema_fingerprint
                m.base_confidence = 0.98
                m.last_used_ts = time.time()
                m.use_count += 1
                self._save_memories()
                return m

        entry = PersonalMemoryEntry(
            user_id=uid,
            term_key=term_key,
            trigger_pattern=trigger_pattern,
            preferred_label=preferred_label,
            implied_constraint=implied_constraint,
            table_hint=table_hint,
            schema_fingerprint=fp
        )
        user_mems.append(entry)
        self._save_memories()
        return entry

    def get_user_memories(self, user_id: Optional[str], schema: Optional[DatabaseSchema] = None) -> List[Dict[str, Any]]:
        uid = user_id or "default"
        out = []
        for m in self._memories.get(uid, []):
            eff, needs_reconfirm, reason = self.compute_effective_confidence(m, schema)
            d = m.model_dump()
            d["effective_confidence"] = eff
            d["needs_reconfirmation"] = needs_reconfirm
            d["decay_reason"] = reason
            out.append(d)
        return out

    def delete_user_memory(self, user_id: Optional[str], mem_id: str) -> bool:
        uid = user_id or "default"
        mems = self._memories.get(uid, [])
        new_mems = [m for m in mems if m.id != mem_id]
        if len(new_mems) != len(mems):
            self._memories[uid] = new_mems
            self._save_memories()
            return True
        return False

    def find_matching_preference(
        self,
        user_id: Optional[str],
        term_key: str,
        schema: Optional[DatabaseSchema] = None
    ) -> Optional[Dict[str, Any]]:
        uid = user_id or "default"
        for m in self._memories.get(uid, []):
            if m.term_key == term_key:
                eff, needs_reconfirm, reason = self.compute_effective_confidence(m, schema)
                if not needs_reconfirm and eff >= 0.60:
                    m.last_used_ts = time.time()
                    m.use_count += 1
                    self._save_memories()
                    return {
                        "entry": m,
                        "effective_confidence": eff,
                        "reason": reason
                    }
        return None

    # --- Team Glossary Workflow ---
    def propose_term(
        self,
        term: str,
        definition: str,
        sql_expression: str,
        proposed_by: str = "user",
        category: str = "metric",
        tables_related: Optional[List[str]] = None,
        auto_approve: bool = False
    ) -> GlossaryTerm:
        t_clean = term.strip()
        for existing in self._glossary:
            if existing.term.lower() == t_clean.lower():
                existing.definition = definition
                existing.sql_expression = sql_expression
                if auto_approve:
                    existing.status = "approved"
                    existing.approved_by = proposed_by
                self._save_glossary()
                return existing

        item = GlossaryTerm(
            term=t_clean,
            definition=definition,
            sql_expression=sql_expression,
            category=category,
            tables_related=tables_related or [],
            status="approved" if auto_approve else "pending",
            proposed_by=proposed_by,
            approved_by=proposed_by if auto_approve else None
        )
        self._glossary.append(item)
        self._save_glossary()
        return item

    def set_glossary_status(self, term_id: str, status: str, reviewer: str = "admin") -> Optional[GlossaryTerm]:
        if status not in ("approved", "rejected", "pending"):
            return None
        for g in self._glossary:
            if g.id == term_id:
                g.status = status
                if status == "approved":
                    g.approved_by = reviewer
                self._save_glossary()
                return g
        return None

    def list_glossary(self, status: Optional[str] = None, allowed_tables: Optional[List[str]] = None) -> List[GlossaryTerm]:
        items = self._glossary
        if status:
            items = [g for g in items if g.status == status]
        if allowed_tables is not None:
            allowed_low = {t.lower() for t in allowed_tables}
            items = [
                g for g in items
                if not g.tables_related or all(t.lower() in allowed_low for t in g.tables_related)
            ]
        return items

    def match_approved_glossary(self, query: str, allowed_tables: Optional[List[str]] = None) -> List[GlossaryTerm]:
        q_low = query.lower()
        approved = self.list_glossary(status="approved", allowed_tables=allowed_tables)
        matched = []
        for g in approved:
            t_low = g.term.lower()
            if re.search(rf"\b{re.escape(t_low)}\b", q_low):
                matched.append(g)
        return matched

    # --- Clarification Replay Store ---
    def record_replay(
        self,
        user_id: Optional[str],
        original_query: str,
        clarification_question: str,
        selected_option_label: str,
        applied_constraint: Optional[str],
        resolved_query: str,
        final_sql: str,
        tables_used: Optional[List[str]] = None
    ) -> ClarificationReplayTriple:
        triple = ClarificationReplayTriple(
            user_id=user_id,
            original_query=original_query.strip(),
            clarification_question=clarification_question,
            selected_option_label=selected_option_label,
            applied_constraint=applied_constraint,
            resolved_query=resolved_query,
            final_sql=final_sql,
            tables_used=tables_used or []
        )
        self._replays.append(triple)
        self._save_replays()
        return triple

    def find_replay(self, query: str, allowed_tables: Optional[List[str]] = None) -> Optional[ClarificationReplayTriple]:
        q_tokens = set(re.findall(r"\b[a-zA-Z0-9_]+\b", query.lower()))
        if not q_tokens:
            return None
        allowed_low = {t.lower() for t in allowed_tables} if allowed_tables is not None else None

        best_score = 0.0
        best_triple = None
        for r in reversed(self._replays):
            r_tables = {t.lower() for t in r.tables_used}
            if allowed_low is not None and r_tables and not r_tables.issubset(allowed_low):
                continue
            r_tokens = set(re.findall(r"\b[a-zA-Z0-9_]+\b", r.original_query.lower()))
            if not r_tokens:
                continue
            jaccard = len(q_tokens & r_tokens) / max(1, len(q_tokens | r_tokens))
            if jaccard > best_score:
                best_score = jaccard
                best_triple = r

        return best_triple if best_score >= 0.72 else None

    # --- Persona Preferences ---
    def get_persona(self, user_id: Optional[str]) -> str:
        return self._personas.get(user_id or "default", "general")

    def set_persona(self, user_id: Optional[str], persona: str) -> str:
        p = persona.lower().strip()
        if p not in VALID_PERSONAS:
            p = "general"
        self._personas[user_id or "default"] = p
        self._save_memories()
        return p

    def get_persona_bias(self, user_id: Optional[str], concept_key: str) -> Optional[str]:
        p = self.get_persona(user_id)
        return VALID_PERSONAS.get(p, {}).get("metric_bias", {}).get(concept_key)


semantic_memory = SemanticMemoryManager()

