import json
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable
from backend.database.schema_extractor import DatabaseSchema

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
REL_FILE = DATA_DIR / "relationships.json"

VALID_CARDINALITIES = {"Many-to-One", "One-to-One", "One-to-Many", "Many-to-Many"}
VALID_CROSS_FILTERS = {"Single", "Both"}


class RelationshipManager:
    """
    Manages custom user-configured table relationships, overrides on native FKs,
    diagram canvas node layouts, cardinality detection, and smart relationship discovery.
    Persisted per user workspace and active data source in data/relationships.json.
    """

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _workspace_key(self, user_id: Optional[str], source_type: str) -> str:
        uid = user_id or "default"
        src = source_type or "sample"
        return f"{uid}::{src}"

    def _ensure_entry(self, key: str) -> Dict[str, Any]:
        if key not in self._store:
            self._store[key] = {
                "relationships": [],
                "native_overrides": {},
                "layouts": {}
            }
        entry = self._store[key]
        entry.setdefault("relationships", [])
        entry.setdefault("native_overrides", {})
        entry.setdefault("layouts", {})
        return entry

    def _load(self):
        try:
            if REL_FILE.exists():
                with open(REL_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._store = data
        except Exception as e:
            logger.error(f"Error loading relationships from {REL_FILE}: {e}")

    def _save(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(REL_FILE, "w", encoding="utf-8") as f:
                json.dump(self._store, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving relationships to {REL_FILE}: {e}")

    def _resolve_col_ci(self, schema: DatabaseSchema, tbl_name: str, col_name: str) -> Tuple[Optional[str], Optional[str]]:
        """Case-insensitive lookup returning canonical (table_name, column_name)."""
        t_low = tbl_name.strip().lower()
        c_low = col_name.strip().lower()
        for t_key, t_meta in schema.tables.items():
            if t_key.lower() == t_low:
                for col in t_meta.columns:
                    if col.name.lower() == c_low:
                        return t_key, col.name
                return t_key, None
        return None, None

    def apply_to_schema(self, schema: DatabaseSchema, user_id: Optional[str] = None) -> DatabaseSchema:
        """
        Applies workspace custom relationships and native FK overrides onto a scoped DatabaseSchema.
        Active relationships become part of TableMeta.foreign_keys and ColumnMeta metadata,
        making them immediately usable by SQL generation and NLP join path resolution.
        """
        key = self._workspace_key(user_id, schema.source_type)
        entry = self._store.get(key)
        if not entry:
            return schema

        native_overrides = entry.get("native_overrides", {})
        manual_rels = entry.get("relationships", [])

        # 1. Process native foreign keys & overrides
        for t_name, t_meta in schema.tables.items():
            updated_native_fks = []
            for fk in t_meta.foreign_keys:
                target = fk.get("references", "")
                ref_tbl, ref_col = target.split(".") if "." in target else (target, "id")
                native_id = f"native::{t_name}.{fk['column']}->{ref_tbl}.{ref_col}"
                ovr = native_overrides.get(native_id)
                if ovr and ovr.get("deleted"):
                    continue
                fk_copy = dict(fk)
                fk_copy["id"] = native_id
                fk_copy["is_manual"] = False
                if ovr:
                    if "cardinality" in ovr:
                        fk_copy["cardinality"] = ovr["cardinality"]
                    if "cross_filter_direction" in ovr:
                        fk_copy["cross_filter_direction"] = ovr["cross_filter_direction"]
                    if "is_active" in ovr:
                        fk_copy["is_active"] = bool(ovr["is_active"])
                updated_native_fks.append(fk_copy)
            t_meta.foreign_keys = updated_native_fks

            # Sync ColumnMeta FK flags with active FKs so far
            active_fk_map = {
                fk["column"].lower(): fk["references"]
                for fk in t_meta.foreign_keys
                if fk.get("is_active", True)
            }
            for col in t_meta.columns:
                c_low = col.name.lower()
                if c_low in active_fk_map:
                    col.is_foreign_key = True
                    col.foreign_key_target = active_fk_map[c_low]
                elif col.is_foreign_key:
                    col.is_foreign_key = False
                    col.foreign_key_target = None

        # 2. Merge user-configured manual relationships
        for rel in manual_rels:
            src_tbl, src_col = self._resolve_col_ci(schema, rel.get("source_table", ""), rel.get("source_column", ""))
            tgt_tbl, tgt_col = self._resolve_col_ci(schema, rel.get("target_table", ""), rel.get("target_column", ""))
            if not (src_tbl and src_col and tgt_tbl and tgt_col):
                continue

            is_active = bool(rel.get("is_active", True))
            fk_entry = {
                "id": rel["id"],
                "column": src_col,
                "references": f"{tgt_tbl}.{tgt_col}",
                "cardinality": rel.get("cardinality", "Many-to-One"),
                "cross_filter_direction": rel.get("cross_filter_direction", "Single"),
                "is_active": is_active,
                "is_manual": True
            }
            t_meta = schema.tables[src_tbl]
            t_meta.foreign_keys.append(fk_entry)

            if is_active:
                for col in t_meta.columns:
                    if col.name == src_col:
                        col.is_foreign_key = True
                        col.foreign_key_target = f"{tgt_tbl}.{tgt_col}"
                        break

        return schema

    def create_relationship(
        self,
        schema: DatabaseSchema,
        user_id: Optional[str],
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str,
        cardinality: str = "Many-to-One",
        cross_filter_direction: str = "Single",
        is_active: bool = True
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        src_tbl, src_col = self._resolve_col_ci(schema, source_table, source_column)
        tgt_tbl, tgt_col = self._resolve_col_ci(schema, target_table, target_column)

        if not src_tbl or not src_col:
            return None, f"Source '{source_table}.{source_column}' was not found in your active workspace schema."
        if not tgt_tbl or not tgt_col:
            return None, f"Target '{target_table}.{target_column}' was not found in your active workspace schema."
        if src_tbl == tgt_tbl and src_col == tgt_col:
            return None, "Cannot create a relationship from a column to itself."

        if cardinality not in VALID_CARDINALITIES:
            cardinality = "Many-to-One"
        if cross_filter_direction not in VALID_CROSS_FILTERS:
            cross_filter_direction = "Single"

        key = self._workspace_key(user_id, schema.source_type)
        entry = self._ensure_entry(key)

        # Check if a native relationship with identical pair was previously deleted -> restore & update
        native_id = f"native::{src_tbl}.{src_col}->{tgt_tbl}.{tgt_col}"
        for fk in schema.tables[src_tbl].foreign_keys:
            if fk.get("id") == native_id:
                return None, f"Relationship '{src_tbl}.{src_col} -> {tgt_tbl}.{tgt_col}' already exists."

        if native_id in entry["native_overrides"] and entry["native_overrides"][native_id].get("deleted"):
            entry["native_overrides"][native_id] = {
                "cardinality": cardinality,
                "cross_filter_direction": cross_filter_direction,
                "is_active": bool(is_active),
                "deleted": False
            }
            self._save()
            return {
                "id": native_id,
                "source_table": src_tbl,
                "source_column": src_col,
                "target_table": tgt_tbl,
                "target_column": tgt_col,
                "cardinality": cardinality,
                "cross_filter_direction": cross_filter_direction,
                "is_active": bool(is_active),
                "is_manual": False
            }, None

        # Check duplicate manual relationship (in either direction between the exact same two columns)
        for existing in entry["relationships"]:
            same_dir = (
                existing["source_table"].lower() == src_tbl.lower()
                and existing["source_column"].lower() == src_col.lower()
                and existing["target_table"].lower() == tgt_tbl.lower()
                and existing["target_column"].lower() == tgt_col.lower()
            )
            rev_dir = (
                existing["source_table"].lower() == tgt_tbl.lower()
                and existing["source_column"].lower() == tgt_col.lower()
                and existing["target_table"].lower() == src_tbl.lower()
                and existing["target_column"].lower() == src_col.lower()
            )
            if same_dir or rev_dir:
                return None, f"A relationship between {src_tbl}.{src_col} and {tgt_tbl}.{tgt_col} already exists."

        rel_obj = {
            "id": f"rel_{uuid.uuid4().hex[:10]}",
            "source_table": src_tbl,
            "source_column": src_col,
            "target_table": tgt_tbl,
            "target_column": tgt_col,
            "cardinality": cardinality,
            "cross_filter_direction": cross_filter_direction,
            "is_active": bool(is_active),
            "is_manual": True
        }
        entry["relationships"].append(rel_obj)
        self._save()
        return rel_obj, None

    def update_relationship(
        self,
        schema: DatabaseSchema,
        user_id: Optional[str],
        rel_id: str,
        source_table: Optional[str] = None,
        source_column: Optional[str] = None,
        target_table: Optional[str] = None,
        target_column: Optional[str] = None,
        cardinality: Optional[str] = None,
        cross_filter_direction: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        key = self._workspace_key(user_id, schema.source_type)
        entry = self._ensure_entry(key)

        if cardinality and cardinality not in VALID_CARDINALITIES:
            return None, f"Invalid cardinality: {cardinality}"
        if cross_filter_direction and cross_filter_direction not in VALID_CROSS_FILTERS:
            return None, f"Invalid cross-filter direction: {cross_filter_direction}"

        # 1. Check manual relationships
        for rel in entry["relationships"]:
            if rel["id"] == rel_id:
                new_src_tbl = source_table or rel["source_table"]
                new_src_col = source_column or rel["source_column"]
                new_tgt_tbl = target_table or rel["target_table"]
                new_tgt_col = target_column or rel["target_column"]

                r_st, r_sc = self._resolve_col_ci(schema, new_src_tbl, new_src_col)
                r_tt, r_tc = self._resolve_col_ci(schema, new_tgt_tbl, new_tgt_col)
                if not (r_st and r_sc and r_tt and r_tc):
                    return None, "Invalid source or target table/column."
                if r_st == r_tt and r_sc == r_tc:
                    return None, "Cannot link a column to itself."

                rel["source_table"] = r_st
                rel["source_column"] = r_sc
                rel["target_table"] = r_tt
                rel["target_column"] = r_tc
                if cardinality:
                    rel["cardinality"] = cardinality
                if cross_filter_direction:
                    rel["cross_filter_direction"] = cross_filter_direction
                if is_active is not None:
                    rel["is_active"] = bool(is_active)

                self._save()
                return dict(rel), None

        # 2. Check native FK override
        if rel_id.startswith("native::"):
            # Verify the native relationship exists in schema
            all_rels = schema.get_all_relationships(include_inactive=True)
            matched_native = next((r for r in all_rels if r.get("id") == rel_id), None)
            if not matched_native:
                return None, f"Relationship '{rel_id}' not found."

            ovr = entry["native_overrides"].get(rel_id, {})
            if cardinality:
                ovr["cardinality"] = cardinality
            if cross_filter_direction:
                ovr["cross_filter_direction"] = cross_filter_direction
            if is_active is not None:
                ovr["is_active"] = bool(is_active)
            ovr["deleted"] = False
            entry["native_overrides"][rel_id] = ovr
            self._save()

            result = dict(matched_native)
            result.update({k: v for k, v in ovr.items() if k != "deleted"})
            return result, None

        return None, f"Relationship '{rel_id}' not found."

    def delete_relationship(self, user_id: Optional[str], source_type: str, rel_id: str) -> bool:
        key = self._workspace_key(user_id, source_type)
        entry = self._ensure_entry(key)

        before = len(entry["relationships"])
        entry["relationships"] = [r for r in entry["relationships"] if r["id"] != rel_id]
        if len(entry["relationships"]) != before:
            self._save()
            return True

        if rel_id.startswith("native::"):
            ovr = entry["native_overrides"].get(rel_id, {})
            ovr["deleted"] = True
            entry["native_overrides"][rel_id] = ovr
            self._save()
            return True

        return False

    def get_layouts(self, user_id: Optional[str], source_type: str) -> Dict[str, Dict[str, float]]:
        key = self._workspace_key(user_id, source_type)
        entry = self._store.get(key, {})
        return dict(entry.get("layouts", {}))

    def save_layouts(self, user_id: Optional[str], source_type: str, layouts: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
        key = self._workspace_key(user_id, source_type)
        entry = self._ensure_entry(key)
        clean_layouts = {}
        for tbl, coords in layouts.items():
            if isinstance(coords, dict) and "x" in coords and "y" in coords:
                clean_layouts[tbl] = {
                    "x": round(float(coords["x"]), 1),
                    "y": round(float(coords["y"]), 1)
                }
        entry["layouts"].update(clean_layouts)
        self._save()
        return dict(entry["layouts"])

    def reset_layouts(self, user_id: Optional[str], source_type: str) -> None:
        key = self._workspace_key(user_id, source_type)
        entry = self._ensure_entry(key)
        entry["layouts"] = {}
        self._save()

    def detect_cardinality_from_data(
        self,
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str,
        exec_fn: Optional[Callable[[str], Any]] = None
    ) -> Dict[str, Any]:
        """
        Inspects column uniqueness and key overlap in the active database
        to suggest accurate Power BI cardinality and report key match coverage.
        """
        default_res = {
            "suggested_cardinality": "Many-to-One",
            "source_total": 0,
            "source_distinct": 0,
            "target_total": 0,
            "target_distinct": 0,
            "match_rate_pct": None,
            "note": "Inferred standard Many-to-One pattern."
        }
        if not exec_fn:
            return default_res

        try:
            q_src = f'SELECT COUNT(*) AS tot, COUNT(DISTINCT "{source_column}") AS dist FROM "{source_table}" WHERE "{source_column}" IS NOT NULL'
            q_tgt = f'SELECT COUNT(*) AS tot, COUNT(DISTINCT "{target_column}") AS dist FROM "{target_table}" WHERE "{target_column}" IS NOT NULL'
            res_s = exec_fn(q_src)
            res_t = exec_fn(q_tgt)

            if not (res_s and res_s.success and res_t and res_t.success):
                return default_res

            s_tot = int(res_s.rows[0].get("tot") or 0) if res_s.rows else 0
            s_dist = int(res_s.rows[0].get("dist") or 0) if res_s.rows else 0
            t_tot = int(res_t.rows[0].get("tot") or 0) if res_t.rows else 0
            t_dist = int(res_t.rows[0].get("dist") or 0) if res_t.rows else 0

            src_unique = (s_tot > 0 and s_tot == s_dist)
            tgt_unique = (t_tot > 0 and t_tot == t_dist)

            if src_unique and tgt_unique:
                card = "One-to-One"
                note = "Both columns contain unique values."
            elif tgt_unique and not src_unique:
                card = "Many-to-One"
                note = f"Target '{target_table}.{target_column}' has unique keys; source contains multiple rows per key."
            elif src_unique and not tgt_unique:
                card = "One-to-Many"
                note = f"Source '{source_table}.{source_column}' has unique keys; target contains multiple rows per key."
            else:
                card = "Many-to-Many"
                note = "Both columns contain duplicate values."

            # Measure referential overlap
            match_pct = None
            if s_tot > 0 and t_tot > 0:
                q_overlap = (
                    f'SELECT COUNT(DISTINCT s."{source_column}") AS matched '
                    f'FROM "{source_table}" s '
                    f'INNER JOIN "{target_table}" t ON s."{source_column}" = t."{target_column}" '
                    f'WHERE s."{source_column}" IS NOT NULL'
                )
                res_ov = exec_fn(q_overlap)
                if res_ov and res_ov.success and res_ov.rows and s_dist > 0:
                    matched_cnt = int(res_ov.rows[0].get("matched") or 0)
                    match_pct = round(min(100.0, (matched_cnt / s_dist) * 100.0), 1)

            return {
                "suggested_cardinality": card,
                "source_total": s_tot,
                "source_distinct": s_dist,
                "target_total": t_tot,
                "target_distinct": t_dist,
                "match_rate_pct": match_pct,
                "note": note
            }
        except Exception as e:
            logger.debug(f"Cardinality inspection failed: {e}")
            return default_res

    def _types_compatible(self, t1: str, t2: str) -> bool:
        def family(dt: str) -> str:
            u = (dt or "TEXT").upper()
            if any(x in u for x in ("INT", "SERIAL")):
                return "INT"
            if any(x in u for x in ("NUMERIC", "DECIMAL", "FLOAT", "REAL", "DOUBLE")):
                return "NUM"
            if any(x in u for x in ("DATE", "TIME")):
                return "DATE"
            return "TEXT"
        f1, f2 = family(t1), family(t2)
        if f1 == f2:
            return True
        if {f1, f2} <= {"INT", "NUM"}:
            return True
        return False

    def auto_detect_candidates(
        self,
        schema: DatabaseSchema,
        exec_fn: Optional[Callable[[str], Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Smartly scans tables in the schema to suggest missing relationships based on:
          - Naming conventions (e.g. `customer_id` -> `customers.id` or `customers.customer_id`)
          - Shared identifier columns (`*_id`, `*_key`, `*_code`)
          - Primary key alignment and optional referential overlap verification
        """
        existing_pairs = set()
        for rel in schema.get_all_relationships(include_inactive=True):
            a = f"{rel['source_table'].lower()}.{rel['source_column'].lower()}"
            b = f"{rel['target_table'].lower()}.{rel['target_column'].lower()}"
            existing_pairs.add((a, b))
            existing_pairs.add((b, a))

        candidates: List[Dict[str, Any]] = []
        table_names = list(schema.tables.keys())

        def singular(name: str) -> str:
            low = name.lower()
            if low.endswith("ies") and len(low) > 4:
                return low[:-3] + "y"
            if low.endswith("s") and not low.endswith("ss") and len(low) > 2:
                return low[:-1]
            return low

        for src_name in table_names:
            src_meta = schema.tables[src_name]
            for src_col in src_meta.columns:
                sc_low = src_col.name.lower()
                is_id_like = sc_low.endswith("_id") or sc_low.endswith("_key") or sc_low.endswith("_code")
                if not is_id_like and not src_col.is_primary_key:
                    continue

                sc_stem = sc_low[:-3] if sc_low.endswith("_id") else None

                for tgt_name in table_names:
                    if src_name == tgt_name:
                        continue
                    tgt_meta = schema.tables[tgt_name]
                    tgt_sing = singular(tgt_name)
                    tgt_tokens = {singular(tok) for tok in tgt_name.lower().split("_") if tok}

                    for tgt_col in tgt_meta.columns:
                        tc_low = tgt_col.name.lower()
                        pair_a = f"{src_name.lower()}.{sc_low}"
                        pair_b = f"{tgt_name.lower()}.{tc_low}"
                        if (pair_a, pair_b) in existing_pairs:
                            continue

                        if not self._types_compatible(src_col.data_type, tgt_col.data_type):
                            continue

                        score = 0
                        reason = ""

                        # Rule 1: `customers.id` matched from `orders.customer_id` (also handles prefixed/suffixed names)
                        if sc_low in (f"{tgt_sing}_id", f"{tgt_name.lower()}_id") and (tc_low == "id" or tc_low == sc_low):
                            score = 95
                            reason = f"Column '{src_col.name}' references '{tgt_name}.{tgt_col.name}' by entity naming pattern."
                        elif sc_stem and sc_stem in tgt_tokens and (tc_low == "id" or tc_low == sc_low):
                            score = 90
                            reason = f"Column '{src_col.name}' matches entity '{sc_stem}' in table '{tgt_name}.{tgt_col.name}'."
                        # Rule 2: Identical key/id column name where target is PK (or unique key)
                        elif sc_low == tc_low and is_id_like and tgt_col.is_primary_key and not src_col.is_primary_key:
                            score = 92
                            reason = f"Foreign identifier '{src_col.name}' matches primary key in '{tgt_name}'."
                        # Rule 3: Identical `*_id` column across two tables (prefer target with fewer/unique rows)
                        elif sc_low == tc_low and sc_low.endswith("_id"):
                            # Avoid duplicating reverse direction unless checked
                            if src_col.is_primary_key and not tgt_col.is_primary_key:
                                continue
                            score = 78
                            reason = f"Shared identifier column '{src_col.name}' across '{src_name}' and '{tgt_name}'."

                        if score > 0:
                            card_info = self.detect_cardinality_from_data(
                                src_name, src_col.name, tgt_name, tgt_col.name, exec_fn=exec_fn
                            )
                            match_pct = card_info.get("match_rate_pct")
                            # If database execution verified 0% overlap and both tables have rows, down-rank
                            if match_pct == 0.0 and card_info.get("source_total", 0) > 0 and card_info.get("target_total", 0) > 0:
                                continue

                            # Avoid duplicate suggestion in opposite order
                            existing_pairs.add((pair_a, pair_b))
                            existing_pairs.add((pair_b, pair_a))

                            candidates.append({
                                "source_table": src_name,
                                "source_column": src_col.name,
                                "target_table": tgt_name,
                                "target_column": tgt_col.name,
                                "cardinality": card_info["suggested_cardinality"],
                                "cross_filter_direction": "Single",
                                "match_rate_pct": match_pct,
                                "confidence": score,
                                "reason": reason
                            })

        candidates.sort(key=lambda c: c["confidence"], reverse=True)
        return candidates


relationship_manager = RelationshipManager()

