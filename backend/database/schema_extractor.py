from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class ColumnMeta(BaseModel):
    name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    foreign_key_target: Optional[str] = None  # e.g. "students.id"

class TableMeta(BaseModel):
    name: str
    description: Optional[str] = None
    columns: List[ColumnMeta] = Field(default_factory=list)
    primary_keys: List[str] = Field(default_factory=list)
    foreign_keys: List[Dict[str, Any]] = Field(default_factory=list) # e.g. [{"column": "dept_id", "references": "departments.id"}]

class DatabaseSchema(BaseModel):
    source_type: str = "sample"  # "postgresql" or "sample"
    database_name: str
    tables: Dict[str, TableMeta] = Field(default_factory=dict)

    def get_known_tables_dict(self) -> Dict[str, List[str]]:
        """Returns {table_name: [col1, col2, ...]} for SQLGlot verification."""
        return {tbl_name: [c.name for c in tbl.columns] for tbl_name, tbl in self.tables.items()}

    def to_compact_llm_context(self, relevant_tables: Optional[List[str]] = None) -> str:
        """
        Formats schema into an ultra-compact, high-signal prompt string.
        Selectively filters tables if relevant_tables is given to prevent context overloading.
        """
        lines = []
        target_tables = relevant_tables if relevant_tables else list(self.tables.keys())
        
        for tbl_name in target_tables:
            tbl = self.tables.get(tbl_name)
            if not tbl:
                continue
            cols_str = []
            for col in tbl.columns:
                col_repr = f"{col.name} ({col.data_type})"
                if col.is_primary_key:
                    col_repr += " [PK]"
                if col.is_foreign_key and col.foreign_key_target:
                    col_repr += f" [FK -> {col.foreign_key_target}]"
                cols_str.append(col_repr)
            lines.append(f"Table: {tbl.name}")
            lines.append(f"  Columns: {', '.join(cols_str)}")
            active_fks = [fk for fk in tbl.foreign_keys if fk.get("is_active", True)]
            if active_fks:
                fk_lines = [
                    f"  FK: {fk['column']} -> {fk['references']} ({fk.get('cardinality', 'Many-to-One')})"
                    for fk in active_fks
                ]
                lines.extend(fk_lines)
            lines.append("")
        return "\n".join(lines).strip()

    def get_all_relationships(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        Returns foreign key relationships in the active database schema.
        By default, returns only active relationships for SQL join generation.
        Set include_inactive=True for Model View visualization and management.
        """
        rels = []
        for t_name, t_meta in self.tables.items():
            for fk in t_meta.foreign_keys:
                is_active = fk.get("is_active", True)
                if not include_inactive and not is_active:
                    continue
                target = fk["references"]
                ref_tbl, ref_col = target.split(".") if "." in target else (target, "id")
                cardinality = fk.get("cardinality", "Many-to-One")
                cross_filter = fk.get("cross_filter_direction", "Single")
                is_manual = bool(fk.get("is_manual", False))
                rel_id = fk.get("id") or f"native::{t_name}.{fk['column']}->{ref_tbl}.{ref_col}"
                display_str = f"{t_name}.{fk['column']} → {ref_tbl}.{ref_col}"
                desc_str = f"{t_name}.{fk['column']} references {ref_tbl}.{ref_col} ({cardinality})"
                rels.append({
                    "id": rel_id,
                    "source_table": t_name,
                    "source_column": fk["column"],
                    "target_table": ref_tbl,
                    "target_column": ref_col,
                    "display": display_str,
                    "description": desc_str,
                    "join_condition": f"{t_name}.{fk['column']} = {ref_tbl}.{ref_col}",
                    "cardinality": cardinality,
                    "cross_filter_direction": cross_filter,
                    "is_active": is_active,
                    "is_manual": is_manual,
                    "is_native": not is_manual
                })
        return rels

    def get_relationships_between(self, table_names: List[str]) -> List[Dict[str, Any]]:
        """
        Finds foreign key relationships connecting or involving the given set of tables.
        If multiple tables are provided, finds direct connections between them.
        If one table is provided, returns all links connected to it.
        If none are provided, returns all relationships in the database.
        """
        all_rels = self.get_all_relationships()
        if not table_names:
            return all_rels

        lower_names = {t.lower() for t in table_names}
        if len(lower_names) > 1:
            matched = [
                r for r in all_rels 
                if r["source_table"].lower() in lower_names and r["target_table"].lower() in lower_names
            ]
            if matched:
                return matched

        # Fallback to any relationship touching the listed tables
        matched = [
            r for r in all_rels 
            if r["source_table"].lower() in lower_names or r["target_table"].lower() in lower_names
        ]
        return matched if matched else all_rels

    def filter_by_tables(self, allowed_table_names: Optional[List[str]]) -> "DatabaseSchema":
        """
        Returns a new DatabaseSchema containing only the tables specified in allowed_table_names.
        If allowed_table_names is None or empty, returns a schema with 0 tables.
        Also filters foreign_keys in TableMeta to only reference allowed tables.
        """
        if allowed_table_names is None:
            return DatabaseSchema(
                source_type=self.source_type,
                database_name=self.database_name,
                tables={}
            )
        allowed_set = {t.lower() for t in allowed_table_names}
        filtered_tables = {}
        for t_name, t_meta in self.tables.items():
            if t_name.lower() in allowed_set:
                # Filter foreign keys so we don't reference tables outside this workspace
                filtered_fks = [
                    fk for fk in t_meta.foreign_keys
                    if fk.get("references", "").split(".")[0].lower() in allowed_set
                ]
                new_meta = TableMeta(
                    name=t_meta.name,
                    description=t_meta.description,
                    columns=[c.model_copy(deep=True) for c in t_meta.columns],
                    primary_keys=list(t_meta.primary_keys),
                    foreign_keys=[dict(fk) for fk in filtered_fks]
                )
                filtered_tables[t_name] = new_meta

        return DatabaseSchema(
            source_type=self.source_type,
            database_name=self.database_name,
            tables=filtered_tables
        )

    def describe_all_relationships(self) -> str:
        """
        Returns an analytical human-readable description of all table relationships.
        """
        rels = self.get_all_relationships()
        if not rels:
            return "No foreign key relationships defined in this schema."
        lines = []
        for r in rels:
            lines.append(f"• {r['source_table']}.{r['source_column']} -> {r['target_table']}.{r['target_column']} (Join condition: `{r['join_condition']}`)")
        return "\n".join(lines)


def get_default_sample_schema() -> DatabaseSchema:
    """
    Standard university & academic performance schema matching SRS Appendix A & Section 5.1:
    Students, Departments, Courses, Marks, Attendance.
    """
    tables = {
        "departments": TableMeta(
            name="departments",
            description="Academic departments",
            primary_keys=["id"],
            columns=[
                ColumnMeta(name="id", data_type="INTEGER", is_primary_key=True),
                ColumnMeta(name="name", data_type="VARCHAR(100)"),
                ColumnMeta(name="code", data_type="VARCHAR(10)")
            ]
        ),
        "students": TableMeta(
            name="students",
            description="Student demographics and department affiliation",
            primary_keys=["id"],
            foreign_keys=[{"column": "department_id", "references": "departments.id"}],
            columns=[
                ColumnMeta(name="id", data_type="INTEGER", is_primary_key=True),
                ColumnMeta(name="name", data_type="VARCHAR(100)"),
                ColumnMeta(name="email", data_type="VARCHAR(100)"),
                ColumnMeta(name="department_id", data_type="INTEGER", is_foreign_key=True, foreign_key_target="departments.id"),
                ColumnMeta(name="enrollment_year", data_type="INTEGER"),
                ColumnMeta(name="city", data_type="VARCHAR(100)"),
                ColumnMeta(name="attendance_percentage", data_type="NUMERIC(5,2)")
            ]
        ),
        "courses": TableMeta(
            name="courses",
            description="Available courses and credits",
            primary_keys=["id"],
            foreign_keys=[{"column": "department_id", "references": "departments.id"}],
            columns=[
                ColumnMeta(name="id", data_type="INTEGER", is_primary_key=True),
                ColumnMeta(name="title", data_type="VARCHAR(150)"),
                ColumnMeta(name="code", data_type="VARCHAR(20)"),
                ColumnMeta(name="department_id", data_type="INTEGER", is_foreign_key=True, foreign_key_target="departments.id"),
                ColumnMeta(name="credits", data_type="INTEGER")
            ]
        ),
        "marks": TableMeta(
            name="marks",
            description="Exam evaluations and subject marks for students",
            primary_keys=["id"],
            foreign_keys=[
                {"column": "student_id", "references": "students.id"},
                {"column": "course_id", "references": "courses.id"}
            ],
            columns=[
                ColumnMeta(name="id", data_type="INTEGER", is_primary_key=True),
                ColumnMeta(name="student_id", data_type="INTEGER", is_foreign_key=True, foreign_key_target="students.id"),
                ColumnMeta(name="course_id", data_type="INTEGER", is_foreign_key=True, foreign_key_target="courses.id"),
                ColumnMeta(name="semester", data_type="INTEGER"),
                ColumnMeta(name="score", data_type="NUMERIC(5,2)"),
                ColumnMeta(name="max_score", data_type="NUMERIC(5,2)"),
                ColumnMeta(name="grade", data_type="VARCHAR(2)")
            ]
        ),
        "sales": TableMeta(
            name="sales",
            description="Retail store sales transactions (for retail queries)",
            primary_keys=["transaction_id"],
            columns=[
                ColumnMeta(name="transaction_id", data_type="INTEGER", is_primary_key=True),
                ColumnMeta(name="store_city", data_type="VARCHAR(100)"),
                ColumnMeta(name="customer_city", data_type="VARCHAR(100)"),
                ColumnMeta(name="revenue", data_type="NUMERIC(10,2)"),
                ColumnMeta(name="units_sold", data_type="INTEGER"),
                ColumnMeta(name="transaction_date", data_type="DATE")
            ]
        ),
        "ipl": TableMeta(
            name="ipl",
            description="IPL Cricket tournament matches, scores, and player statistics",
            primary_keys=["match_id"],
            columns=[
                ColumnMeta(name="match_id", data_type="INTEGER", is_primary_key=True),
                ColumnMeta(name="season", data_type="INTEGER"),
                ColumnMeta(name="city", data_type="VARCHAR(100)"),
                ColumnMeta(name="team1", data_type="VARCHAR(100)"),
                ColumnMeta(name="team2", data_type="VARCHAR(100)"),
                ColumnMeta(name="toss_winner", data_type="VARCHAR(100)"),
                ColumnMeta(name="toss_decision", data_type="VARCHAR(50)"),
                ColumnMeta(name="match_winner", data_type="VARCHAR(100)"),
                ColumnMeta(name="result", data_type="VARCHAR(50)"),
                ColumnMeta(name="result_margin", data_type="INTEGER"),
                ColumnMeta(name="player_of_the_match", data_type="VARCHAR(100)"),
                ColumnMeta(name="venue", data_type="VARCHAR(150)"),
                ColumnMeta(name="top_scorer", data_type="VARCHAR(100)"),
                ColumnMeta(name="highscore", data_type="INTEGER"),
                ColumnMeta(name="best_bowling", data_type="VARCHAR(100)"),
                ColumnMeta(name="best_bowling_figure", data_type="VARCHAR(50)")
            ]
        ),
        "sarah_products": TableMeta(
            name="sarah_products",
            description="E-commerce and retail product catalog with prices and stock",
            primary_keys=["product_id"],
            columns=[
                ColumnMeta(name="product_id", data_type="INTEGER", is_primary_key=True),
                ColumnMeta(name="product_name", data_type="VARCHAR(150)"),
                ColumnMeta(name="category", data_type="VARCHAR(100)"),
                ColumnMeta(name="unit_price", data_type="NUMERIC(10,2)"),
                ColumnMeta(name="inventory_count", data_type="INTEGER")
            ]
        )
    }
    return DatabaseSchema(source_type="sample", database_name="academic_and_sales_sample", tables=tables)


def extract_postgresql_schema(conn) -> DatabaseSchema:
    """
    Introspects a real PostgreSQL database using information_schema and pg_catalog.
    """
    tables: Dict[str, TableMeta] = {}
    with conn.cursor() as cur:
        # 1. Fetch tables
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        table_rows = cur.fetchall()
        for (tbl_name,) in table_rows:
            tables[tbl_name] = TableMeta(name=tbl_name)

        # 2. Fetch columns
        cur.execute("""
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position;
        """)
        for tbl_name, col_name, data_type, is_null in cur.fetchall():
            if tbl_name in tables:
                tables[tbl_name].columns.append(
                    ColumnMeta(
                        name=col_name,
                        data_type=data_type.upper(),
                        is_nullable=(is_null == 'YES')
                    )
                )

        # 3. Fetch Primary Keys
        cur.execute("""
            SELECT kcu.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public';
        """)
        for tbl_name, col_name in cur.fetchall():
            if tbl_name in tables:
                tables[tbl_name].primary_keys.append(col_name)
                for col in tables[tbl_name].columns:
                    if col.name == col_name:
                        col.is_primary_key = True

        # 4. Fetch Foreign Keys
        cur.execute("""
            SELECT
                tc.table_name, 
                kcu.column_name, 
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name 
            FROM information_schema.table_constraints AS tc 
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public';
        """)
        for tbl_name, col_name, f_tbl, f_col in cur.fetchall():
            if tbl_name in tables:
                ref_target = f"{f_tbl}.{f_col}"
                tables[tbl_name].foreign_keys.append({
                    "column": col_name,
                    "references": ref_target
                })
                for col in tables[tbl_name].columns:
                    if col.name == col_name:
                        col.is_foreign_key = True
                        col.foreign_key_target = ref_target

    return DatabaseSchema(source_type="postgresql", database_name="postgresql_live", tables=tables)


def extract_sqlite_schema(conn) -> DatabaseSchema:
    """
    Introspects a live SQLite database including built-in sample tables and user-uploaded datasets.
    """
    default_schema = get_default_sample_schema()
    tables: Dict[str, TableMeta] = {}

    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    table_names = [row[0] for row in cur.fetchall()]

    for tbl_name in table_names:
        # If it's a known default sample table, start with its rich metadata
        if tbl_name in default_schema.tables:
            tables[tbl_name] = default_schema.tables[tbl_name].model_copy(deep=True)
            continue

        table_meta = TableMeta(name=tbl_name, description=f"Dataset '{tbl_name}'")

        # Introspect columns
        try:
            cur.execute(f'PRAGMA table_info("{tbl_name}");')
            col_rows = cur.fetchall()
            for row in col_rows:
                # PRAGMA table_info columns: (cid, name, type, notnull, dflt_value, pk)
                col_name = row[1]
                data_type = (row[2] or "TEXT").upper()
                notnull = bool(row[3])
                is_pk = bool(row[5])

                if is_pk:
                    table_meta.primary_keys.append(col_name)

                table_meta.columns.append(
                    ColumnMeta(
                        name=col_name,
                        data_type=data_type,
                        is_nullable=not notnull,
                        is_primary_key=is_pk
                    )
                )
        except Exception:
            pass

        # Introspect foreign keys
        try:
            cur.execute(f'PRAGMA foreign_key_list("{tbl_name}");')
            fk_rows = cur.fetchall()
            for row in fk_rows:
                # PRAGMA foreign_key_list: (id, seq, table, from, to, on_update, on_delete, match)
                target_table = row[2]
                from_col = row[3]
                to_col = row[4] or "id"
                ref_target = f"{target_table}.{to_col}"

                table_meta.foreign_keys.append({
                    "column": from_col,
                    "references": ref_target
                })
                for col in table_meta.columns:
                    if col.name == from_col:
                        col.is_foreign_key = True
                        col.foreign_key_target = ref_target
        except Exception:
            pass

        tables[tbl_name] = table_meta

    return DatabaseSchema(source_type="sample", database_name="academic_and_user_datasets", tables=tables)

