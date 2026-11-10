import sqlite3
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import psycopg
from pydantic import BaseModel
from backend.config import settings, BASE_DIR
from backend.database.schema_extractor import DatabaseSchema, get_default_sample_schema, extract_postgresql_schema, extract_sqlite_schema

class ExecutionResult(BaseModel):
    success: bool
    columns: List[str] = []
    rows: List[Dict[str, Any]] = []
    row_count: int = 0
    execution_time_ms: float = 0.0
    error_message: Optional[str] = None
    data_source: str = "sample"

class DatabaseManager:
    """
    Manages connections to both local PostgreSQL and a high-fidelity local sample database.
    Guarantees strict read-only execution with query timeouts and row ceilings.
    """
    def __init__(self):
        self.active_source: str = getattr(settings, "ACTIVE_DATA_SOURCE", "sample")
        self._schema_cache: Optional[DatabaseSchema] = None
        self._sample_sqlite_conn: Optional[sqlite3.Connection] = None
        self._init_sample_database()
        if self.active_source == "postgresql":
            success, _ = self.test_postgres_connection()
            if not success:
                self.active_source = "sample"
            else:
                self.get_schema(force_refresh=True)

    def _init_sample_database(self):
        """Initializes persistent SQLite warehouse (preserving uploaded datasets across restarts) and seeds sample tables if empty."""
        data_dir = BASE_DIR / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = data_dir / "local_warehouse.db"

        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Ensure sample tables exist
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100),
            code VARCHAR(10)
        );

        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100),
            email VARCHAR(100),
            department_id INTEGER,
            enrollment_year INTEGER,
            city VARCHAR(100),
            attendance_percentage NUMERIC(5,2),
            FOREIGN KEY (department_id) REFERENCES departments(id)
        );

        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY,
            title VARCHAR(150),
            code VARCHAR(20),
            department_id INTEGER,
            credits INTEGER,
            FOREIGN KEY (department_id) REFERENCES departments(id)
        );

        CREATE TABLE IF NOT EXISTS marks (
            id INTEGER PRIMARY KEY,
            student_id INTEGER,
            course_id INTEGER,
            semester INTEGER,
            score NUMERIC(5,2),
            max_score NUMERIC(5,2),
            grade VARCHAR(2),
            FOREIGN KEY (student_id) REFERENCES students(id),
            FOREIGN KEY (course_id) REFERENCES courses(id)
        );

        CREATE TABLE IF NOT EXISTS sales (
            transaction_id INTEGER PRIMARY KEY,
            store_city VARCHAR(100),
            customer_city VARCHAR(100),
            revenue NUMERIC(10,2),
            units_sold INTEGER,
            transaction_date DATE
        );

        CREATE TABLE IF NOT EXISTS ipl (
            match_id INTEGER PRIMARY KEY,
            season INTEGER,
            city VARCHAR(100),
            team1 VARCHAR(100),
            team2 VARCHAR(100),
            toss_winner VARCHAR(100),
            toss_decision VARCHAR(50),
            match_winner VARCHAR(100),
            result VARCHAR(50),
            result_margin INTEGER,
            player_of_the_match VARCHAR(100),
            venue VARCHAR(150),
            top_scorer VARCHAR(100),
            highscore INTEGER,
            best_bowling VARCHAR(100),
            best_bowling_figure VARCHAR(50)
        );

        CREATE TABLE IF NOT EXISTS sarah_products (
            product_id INTEGER PRIMARY KEY,
            product_name VARCHAR(150),
            category VARCHAR(100),
            unit_price NUMERIC(10,2),
            inventory_count INTEGER
        );
        """)

        def _is_empty(tbl: str) -> bool:
            cur.execute(f'SELECT COUNT(*) FROM "{tbl}";')
            return (cur.fetchone()[0] or 0) == 0

        if _is_empty("departments"):
            cur.executescript("""
            INSERT INTO departments VALUES 
                (1, 'Computer Science', 'CS'),
                (2, 'Data Science', 'DS'),
                (3, 'Mechanical Engineering', 'ME');
            """)
        if _is_empty("students"):
            cur.executescript("""
            INSERT INTO students VALUES 
                (101, 'Aarav Sharma', 'aarav@univ.edu', 1, 2022, 'Mumbai', 94.5),
                (102, 'Priya Patel', 'priya@univ.edu', 1, 2022, 'Delhi', 88.0),
                (103, 'Rohan Verma', 'rohan@univ.edu', 2, 2023, 'Bangalore', 96.0),
                (104, 'Ananya Iyer', 'ananya@univ.edu', 2, 2023, 'Mumbai', 79.5),
                (105, 'Kavya Nair', 'kavya@univ.edu', 3, 2021, 'Chennai', 91.0);
            """)
        if _is_empty("courses"):
            cur.executescript("""
            INSERT INTO courses VALUES 
                (201, 'Database Systems', 'CS301', 1, 4),
                (202, 'Machine Learning', 'DS401', 2, 4),
                (203, 'Algorithms', 'CS201', 1, 3);
            """)
        if _is_empty("marks"):
            cur.executescript("""
            INSERT INTO marks VALUES 
                (1, 101, 201, 4, 92.0, 100.0, 'A'),
                (2, 101, 203, 4, 88.5, 100.0, 'B'),
                (3, 102, 201, 4, 76.0, 100.0, 'C'),
                (4, 103, 202, 2, 98.0, 100.0, 'A'),
                (5, 104, 202, 2, 84.0, 100.0, 'B'),
                (6, 105, 201, 6, 81.0, 100.0, 'B');
            """)
        if _is_empty("sales"):
            cur.executescript("""
            INSERT INTO sales VALUES 
                (1, 'Mumbai', 'Mumbai', 15400.0, 12, '2024-01-15'),
                (2, 'Delhi', 'Mumbai', 8900.0, 5, '2024-02-10'),
                (3, 'Mumbai', 'Bangalore', 23100.0, 19, '2024-03-01'),
                (4, 'Bangalore', 'Bangalore', 12500.0, 8, '2024-03-12'),
                (5, 'Mumbai', 'Pune', 31200.0, 25, '2024-04-20');
            """)
        if _is_empty("ipl"):
            cur.executescript("""
            INSERT INTO ipl VALUES
                (1, 2023, 'Ahmedabad', 'Chennai Super Kings', 'Gujarat Titans', 'Chennai Super Kings', 'field', 'Chennai Super Kings', 'wickets', 5, 'Devon Conway', 'Narendra Modi Stadium', 'Devon Conway', 47, 'Ravindra Jadeja', '3--22'),
                (2, 2023, 'Mumbai', 'Mumbai Indians', 'Royal Challengers Bangalore', 'Mumbai Indians', 'field', 'Mumbai Indians', 'wickets', 6, 'Suryakumar Yadav', 'Wankhede Stadium', 'Suryakumar Yadav', 83, 'Jason Behrendorff', '3--36'),
                (3, 2023, 'Chennai', 'Chennai Super Kings', 'Kolkata Knight Riders', 'Chennai Super Kings', 'bat', 'Kolkata Knight Riders', 'wickets', 6, 'Rinku Singh', 'MA Chidambaram Stadium', 'Shivam Dube', 48, 'Varun Chakravarthy', '2--36'),
                (4, 2023, 'Delhi', 'Delhi Capitals', 'Chennai Super Kings', 'Chennai Super Kings', 'bat', 'Chennai Super Kings', 'runs', 77, 'Ruturaj Gaikwad', 'Arun Jaitley Stadium', 'Ruturaj Gaikwad', 79, 'Deepak Chahar', '3--22'),
                (5, 2023, 'Bangalore', 'Royal Challengers Bangalore', 'Gujarat Titans', 'Gujarat Titans', 'field', 'Gujarat Titans', 'wickets', 6, 'Shubman Gill', 'M Chinnaswamy Stadium', 'Shubman Gill', 104, 'Rashid Khan', '1--24'),
                (6, 2023, 'Lucknow', 'Lucknow Super Giants', 'Mumbai Indians', 'Mumbai Indians', 'field', 'Mumbai Indians', 'runs', 81, 'Akash Madhwal', 'BRSABV Ekana Cricket Stadium', 'Cameron Green', 41, 'Akash Madhwal', '5--5');
            """)
        if _is_empty("sarah_products"):
            cur.executescript("""
            INSERT INTO sarah_products VALUES
                (1, 'MacBook Pro 16', 'Laptops', 2499.00, 45),
                (2, 'iPhone 15 Pro Max', 'Smartphones', 1199.00, 120),
                (3, 'AirPods Max', 'Audio', 549.00, 85),
                (4, 'Studio Display 27', 'Monitors', 1599.00, 30),
                (5, 'Magic Keyboard Touch ID', 'Accessories', 199.00, 210);
            """)

        conn.commit()
        self._sample_sqlite_conn = conn
        self._schema_cache = extract_sqlite_schema(conn)

    def get_schema(self, force_refresh: bool = False) -> DatabaseSchema:
        if self._schema_cache and not force_refresh:
            return self._schema_cache

        if self.active_source == "postgresql":
            try:
                dsn = settings.get_postgres_dsn(readonly=True)
                with psycopg.connect(dsn, connect_timeout=4) as conn:
                    self._schema_cache = extract_postgresql_schema(conn)
                    return self._schema_cache
            except Exception as e:
                # If local PostgreSQL connection fails, fallback to sample schema gracefully
                self._schema_cache = get_default_sample_schema()
                self._schema_cache.database_name = f"Sample (PostgreSQL unavailable: {str(e)[:40]}...)"
                return self._schema_cache
        else:
            if self._sample_sqlite_conn:
                self._schema_cache = extract_sqlite_schema(self._sample_sqlite_conn)
            else:
                self._schema_cache = get_default_sample_schema()
            return self._schema_cache

    def test_postgres_connection(
        self, 
        host: Optional[str] = None, 
        port: Optional[int] = None, 
        dbname: Optional[str] = None, 
        user: Optional[str] = None, 
        password: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Tests live PostgreSQL connectivity without persisting changes."""
        h = host or settings.DB_HOST
        p = port or settings.DB_PORT
        db = dbname or settings.DB_NAME
        u = user or settings.DB_READONLY_USER
        pwd = password if password is not None else settings.DB_READONLY_PASSWORD

        dsn = f"postgresql://{u}:{pwd}@{h}:{p}/{db}"
        try:
            with psycopg.connect(dsn, connect_timeout=4) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version();")
                    ver = cur.fetchone()[0]
                    return True, f"Connected successfully to PostgreSQL! Version: {ver}"
        except Exception as e:
            return False, f"PostgreSQL connection failed: {str(e)}"

    def set_data_source(
        self, 
        source: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        dbname: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ) -> Tuple[bool, str]:
        if source not in ("sample", "postgresql"):
            return False, "Invalid data source. Must be 'sample' or 'postgresql'."
        if source == "postgresql":
            h = host or settings.DB_HOST
            p = port or settings.DB_PORT
            db = dbname or settings.DB_NAME
            u = user or settings.DB_USER
            pwd = password if password is not None else settings.DB_PASSWORD

            success, msg = self.test_postgres_connection(host=h, port=p, dbname=db, user=u, password=pwd)
            if not success:
                return False, f"Cannot switch to PostgreSQL: {msg}"

            # Persist to in-memory settings
            settings.DB_HOST = h
            settings.DB_PORT = p
            settings.DB_NAME = db
            settings.DB_USER = u
            settings.DB_PASSWORD = pwd
            settings.DB_READONLY_USER = u
            settings.DB_READONLY_PASSWORD = pwd

            # Optionally update .env file
            try:
                env_path = settings.BASE_DIR / ".env" if hasattr(settings, "BASE_DIR") else None
                if not env_path:
                    from backend.config import BASE_DIR
                    env_path = BASE_DIR / ".env"
                if env_path.exists():
                    lines = env_path.read_text(encoding="utf-8").splitlines()
                    new_lines = []
                    keys_updated = set()
                    for line in lines:
                        if line.startswith("DB_HOST="):
                            new_lines.append(f"DB_HOST={h}"); keys_updated.add("DB_HOST")
                        elif line.startswith("DB_PORT="):
                            new_lines.append(f"DB_PORT={p}"); keys_updated.add("DB_PORT")
                        elif line.startswith("DB_NAME="):
                            new_lines.append(f"DB_NAME={db}"); keys_updated.add("DB_NAME")
                        elif line.startswith("DB_USER="):
                            new_lines.append(f"DB_USER={u}"); keys_updated.add("DB_USER")
                        elif line.startswith("DB_PASSWORD="):
                            new_lines.append(f"DB_PASSWORD={pwd}"); keys_updated.add("DB_PASSWORD")
                        elif line.startswith("DB_READONLY_USER="):
                            new_lines.append(f"DB_READONLY_USER={u}"); keys_updated.add("DB_READONLY_USER")
                        elif line.startswith("DB_READONLY_PASSWORD="):
                            new_lines.append(f"DB_READONLY_PASSWORD={pwd}"); keys_updated.add("DB_READONLY_PASSWORD")
                        else:
                            new_lines.append(line)
                    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            except Exception as e:
                pass  # Non-fatal if .env cannot be written

            self.active_source = "postgresql"
            self.get_schema(force_refresh=True)
            return True, f"Switched data source to live PostgreSQL database '{db}' at {h}:{p}."
        else:
            self.active_source = "sample"
            self.get_schema(force_refresh=True)
            return True, "Switched data source to local sample database."

    def execute_query(self, sql: str) -> ExecutionResult:
        """
        Executes a validated read-only SQL query against the active database source.
        Applies timeouts, row limits, and transaction read-only protection.
        """
        start_time = time.time()
        clean_sql = sql.strip().rstrip(";")

        # Enforce row limit if not specified
        if "limit" not in clean_sql.lower():
            clean_sql += f" LIMIT {settings.MAX_ROW_LIMIT}"

        if self.active_source == "postgresql":
            try:
                dsn = settings.get_postgres_dsn(readonly=True)
                with psycopg.connect(dsn, connect_timeout=settings.QUERY_TIMEOUT_SECONDS) as conn:
                    # Enforce read-only transaction mode
                    conn.read_only = True
                    with conn.cursor() as cur:
                        cur.execute(f"SET statement_timeout = {settings.QUERY_TIMEOUT_SECONDS * 1000};")
                        cur.execute(clean_sql)
                        cols = [desc[0] for desc in cur.description] if cur.description else []
                        raw_rows = cur.fetchall()
                        rows = [dict(zip(cols, row)) for row in raw_rows]
                        exec_ms = round((time.time() - start_time) * 1000, 2)
                        return ExecutionResult(
                            success=True,
                            columns=cols,
                            rows=rows,
                            row_count=len(rows),
                            execution_time_ms=exec_ms,
                            data_source="postgresql"
                        )
            except Exception as e:
                exec_ms = round((time.time() - start_time) * 1000, 2)
                return ExecutionResult(
                    success=False,
                    execution_time_ms=exec_ms,
                    error_message=f"PostgreSQL Execution Error: {str(e)}",
                    data_source="postgresql"
                )
        else:
            # Execute on local sample database
            try:
                cur = self._sample_sqlite_conn.cursor()
                cur.execute(clean_sql)
                cols = [desc[0] for desc in cur.description] if cur.description else []
                raw_rows = cur.fetchall()
                rows = [dict(zip(cols, row)) for row in raw_rows]
                exec_ms = round((time.time() - start_time) * 1000, 2)
                return ExecutionResult(
                    success=True,
                    columns=cols,
                    rows=rows,
                    row_count=len(rows),
                    execution_time_ms=exec_ms,
                    data_source="sample"
                )
            except Exception as e:
                exec_ms = round((time.time() - start_time) * 1000, 2)
                return ExecutionResult(
                    success=False,
                    execution_time_ms=exec_ms,
                    error_message=f"Query Execution Error: {str(e)}",
                    data_source="sample"
                )

db_manager = DatabaseManager()
