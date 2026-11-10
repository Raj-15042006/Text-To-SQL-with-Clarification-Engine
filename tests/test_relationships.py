import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.modules.auth_manager import auth_manager
from backend.modules.relationship_manager import relationship_manager
from backend.modules.nlp_engine import local_nlp_engine
from backend.database.connection import db_manager
from backend.routers.schema import (
    get_current_schema,
    get_schema_relationships,
    create_schema_relationship,
    update_schema_relationship,
    delete_schema_relationship,
    inspect_relationship_cardinality,
    auto_detect_schema_relationships,
    save_diagram_layout,
    reset_diagram_layout,
    RelationshipCreateRequest,
    RelationshipUpdateRequest,
    CardinalityInspectRequest,
    AutoDetectRequest,
    DiagramLayoutRequest,
)


def _create_temp_user(username: str):
    for uid, u in list(auth_manager._users.items()):
        if u.get("username") == username:
            del auth_manager._users[uid]
    auth_manager._save()
    user, token, err = auth_manager.register(
        username=username,
        password="password123",
        display_name=username.title()
    )
    assert err is None
    return user, token


def _cleanup_user(user_id: str):
    keys_to_del = [k for k in list(relationship_manager._store.keys()) if k.startswith(f"{user_id}::")]
    for k in keys_to_del:
        del relationship_manager._store[k]
    relationship_manager._save()

    if user_id in auth_manager._users:
        del auth_manager._users[user_id]
        auth_manager._save()


def test_relationship_crud_and_nlp_join_integration():
    raj_user, raj_token, err = auth_manager.login("raj", "password123")
    assert err is None
    auth_header = f"Bearer {raj_token}"

    key = f"{raj_user['id']}::sample"
    orig_entry = relationship_manager._store.pop(key, None)
    relationship_manager._save()

    try:
        # 1. Fetch initial relationships (native university FKs)
        d0 = get_schema_relationships(authorization=auth_header)
        rels0 = d0["relationships"]
        assert any(r["source_table"] == "students" and r["target_table"] == "departments" for r in rels0)
        assert any(r["source_table"] == "marks" and r["target_table"] == "students" for r in rels0)

        # 2. Manually create a relationship between sales.store_city -> students.city
        res_create = create_schema_relationship(
            req=RelationshipCreateRequest(
                source_table="sales",
                source_column="store_city",
                target_table="students",
                target_column="city",
                cardinality="Many-to-Many",
                cross_filter_direction="Both",
                is_active=True
            ),
            authorization=auth_header
        )
        assert res_create["success"] is True
        created = res_create["relationship"]
        rel_id = created["id"]
        assert created["is_manual"] is True
        assert created["cardinality"] == "Many-to-Many"
        assert created["cross_filter_direction"] == "Both"

        # 3. Verify active schema & LocalNLPEngine pick up the manual relationship for JOIN path
        scoped_schema = get_current_schema(authorization=auth_header)
        joins = local_nlp_engine.resolve_join_path(["sales", "students"], scoped_schema)
        assert any("sales.store_city = students.city" in j for j in joins), f"Expected manual join in {joins}"

        # 4. Toggle relationship INACTIVE -> excluded from active JOINs, included in include_inactive=true
        res_upd = update_schema_relationship(
            rel_id=rel_id,
            req=RelationshipUpdateRequest(is_active=False, cardinality="Many-to-One"),
            authorization=auth_header
        )
        assert res_upd["success"] is True
        upd_rel = res_upd["relationship"]
        assert upd_rel["is_active"] is False
        assert upd_rel["cardinality"] == "Many-to-One"

        scoped_inactive = get_current_schema(authorization=auth_header)
        active_joins = local_nlp_engine.resolve_join_path(["sales", "students"], scoped_inactive)
        assert not any("sales.store_city = students.city" in j for j in active_joins)

        # Still visible in Model View list
        res_list = get_schema_relationships(include_inactive=True, authorization=auth_header)
        assert any(r["id"] == rel_id and r["is_active"] is False for r in res_list["relationships"])

        # 5. Cardinality detection inspection
        res_card = inspect_relationship_cardinality(
            req=CardinalityInspectRequest(
                source_table="marks",
                source_column="student_id",
                target_table="students",
                target_column="id"
            ),
            authorization=auth_header
        )
        assert res_card["suggested_cardinality"] == "Many-to-One"
        assert res_card["match_rate_pct"] == 100.0

        # 6. Diagram node layout persistence
        res_lay = save_diagram_layout(
            req=DiagramLayoutRequest(layouts={"students": {"x": 150, "y": 220}, "departments": {"x": 520, "y": 90}}),
            authorization=auth_header
        )
        assert res_lay["success"] is True
        res_check = get_schema_relationships(authorization=auth_header)
        assert res_check["layouts"]["students"] == {"x": 150.0, "y": 220.0}

        reset_res = reset_diagram_layout(authorization=auth_header)
        assert reset_res["success"] is True
        assert get_schema_relationships(authorization=auth_header)["layouts"] == {}

        # 7. Delete manual relationship
        res_del = delete_schema_relationship(rel_id=rel_id, authorization=auth_header)
        assert res_del["success"] is True
        assert not any(r["id"] == rel_id for r in res_del["relationships"])

    finally:
        if orig_entry is not None:
            relationship_manager._store[key] = orig_entry
        else:
            relationship_manager._store.pop(key, None)
        relationship_manager._save()


def test_relationship_autodetect_and_tenant_isolation():
    user_a, tok_a = _create_temp_user("rel_user_a")
    user_b, tok_b = _create_temp_user("rel_user_b")

    try:
        cur = db_manager._sample_sqlite_conn.cursor()
        cur.executescript("""
            DROP TABLE IF EXISTS test_rel_customers;
            DROP TABLE IF EXISTS test_rel_orders;
            CREATE TABLE test_rel_customers (id INTEGER PRIMARY KEY, name TEXT);
            INSERT INTO test_rel_customers VALUES (1, 'Alice'), (2, 'Bob');
            CREATE TABLE test_rel_orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL);
            INSERT INTO test_rel_orders VALUES (10, 1, 99.5), (11, 1, 45.0), (12, 2, 120.0);
        """)
        db_manager._sample_sqlite_conn.commit()
        db_manager.get_schema(force_refresh=True)

        auth_manager.record_uploaded_table(user_a["id"], {
            "table_name": "test_rel_customers",
            "filename": "customers.csv",
            "row_count": 2,
            "column_count": 2,
            "columns": ["id", "name"]
        })
        auth_manager.record_uploaded_table(user_a["id"], {
            "table_name": "test_rel_orders",
            "filename": "orders.csv",
            "row_count": 3,
            "column_count": 3,
            "columns": ["order_id", "customer_id", "amount"]
        })

        auth_a = f"Bearer {tok_a}"
        auth_b = f"Bearer {tok_b}"

        # 1. Auto-detect should find test_rel_orders.customer_id -> test_rel_customers.id
        res_ad = auto_detect_schema_relationships(req=AutoDetectRequest(apply=False), authorization=auth_a)
        cands = res_ad["candidates"]
        assert any(
            c["source_table"] == "test_rel_orders"
            and c["source_column"] == "customer_id"
            and c["target_table"] == "test_rel_customers"
            and c["target_column"] == "id"
            for c in cands
        ), f"Expected auto-detected candidate, got {cands}"

        # 2. Apply detected candidate
        res_apply = auto_detect_schema_relationships(req=AutoDetectRequest(apply=True), authorization=auth_a)
        assert res_apply["applied_count"] >= 1

        # 3. Verify User B does NOT see User A's tables or relationships
        res_b = get_schema_relationships(authorization=auth_b)
        assert res_b["relationships"] == []

    finally:
        try:
            cur = db_manager._sample_sqlite_conn.cursor()
            cur.executescript("DROP TABLE IF EXISTS test_rel_orders; DROP TABLE IF EXISTS test_rel_customers;")
            db_manager._sample_sqlite_conn.commit()
            db_manager.get_schema(force_refresh=True)
        except Exception:
            pass
        _cleanup_user(user_a["id"])
        _cleanup_user(user_b["id"])
