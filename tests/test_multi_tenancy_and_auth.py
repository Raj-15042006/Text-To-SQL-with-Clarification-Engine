import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.modules.auth_manager import auth_manager
from backend.modules.conversation_manager import conversation_manager
from backend.database.connection import db_manager
from backend.routers.schema import get_current_schema
from backend.routers.query import submit_query, QueryRequest
from backend.routers.conversations import list_conversations

def test_multi_tenancy_and_account_isolation():
    # 1. Login as existing default user 'raj'
    raj_user, raj_token, err = auth_manager.login("raj", "password123")
    assert err is None
    assert raj_user is not None
    assert raj_token is not None
    assert raj_user["username"] == "raj"

    # Verify raj sees all previous datasets and 17 previous conversations
    raj_auth = f"Bearer {raj_token}"
    raj_schema = get_current_schema(authorization=raj_auth)
    assert len(raj_schema.tables) >= 5
    assert "students" in raj_schema.tables
    assert "sales" in raj_schema.tables

    raj_convs = list_conversations(authorization=raj_auth)
    assert len(raj_convs) >= 15

    # 2. Register a brand-new user account
    new_username = "flagship_user_test"
    # Ensure fresh test state
    for uid, u in list(auth_manager._users.items()):
        if u.get("username") == new_username:
            del auth_manager._users[uid]
            auth_manager._save()

    new_user, new_token, reg_err = auth_manager.register(
        username=new_username,
        password="securepass123",
        display_name="Flagship Explorer",
        email="explorer@flagship.io"
    )
    assert reg_err is None
    assert new_user is not None
    assert new_token is not None
    assert new_user["username"] == new_username
    assert new_user["uploaded_tables_count"] == 0

    new_auth = f"Bearer {new_token}"

    # Verify new account starts with ZERO datasets
    new_schema = get_current_schema(authorization=new_auth)
    assert len(new_schema.tables) == 0, f"New user must have 0 tables, got {list(new_schema.tables.keys())}"

    # Verify new account starts with ZERO prior conversations
    new_convs = list_conversations(authorization=new_auth)
    assert len(new_convs) == 0, f"New user must have 0 conversations, got {len(new_convs)}"

    # 3. New account queries a database table -> Graceful no_dataset status without crash or error
    db_query_req = QueryRequest(query="Show all students and departments")
    db_res = submit_query(req=db_query_req, authorization=new_auth)
    assert db_res.status == "no_dataset"
    assert "No database tables found in your workspace" in db_res.natural_explanation
    assert db_res.execution is None

    # 4. New account queries a mathematical formula -> Executes cleanly even with 0 tables!
    math_query_req = QueryRequest(query="calculate EMI for 500000 at 8.5% for 5 years")
    math_res = submit_query(req=math_query_req, authorization=new_auth)
    assert math_res.status == "executed"
    assert math_res.execution is not None
    assert math_res.execution.success is True
    assert math_res.execution.row_count == 1
    assert "monthly_emi" in math_res.execution.rows[0]

    # 5. New account uploads a dataset
    table_meta = {
        "table_name": "explorer_metrics",
        "filename": "metrics.csv",
        "row_count": 5,
        "column_count": 3,
        "columns": ["metric_name", "metric_value", "region"]
    }
    auth_manager.record_uploaded_table(new_user["id"], table_meta)

    # Now new user has 1 dataset!
    updated_tables = auth_manager.get_user_uploaded_tables(new_user["id"])
    assert len(updated_tables) == 1
    assert updated_tables[0]["table_name"] == "explorer_metrics"

    # Clean up test user
    del auth_manager._users[new_user["id"]]
    auth_manager._save()
