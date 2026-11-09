import uuid
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.modules.auth_manager import auth_manager

client = TestClient(app)

TEST_USER = f"sarah_{uuid.uuid4().hex[:6]}"

def test_auth_system_registration_and_login():
    """Verify account creation, login, and profile retrieval."""
    # Register new account
    reg_resp = client.post("/api/auth/register", json={
        "username": TEST_USER,
        "display_name": "Sarah Analyst",
        "email": f"{TEST_USER}@company.com",
        "password": "securepassword123"
    })
    assert reg_resp.status_code == 200
    data = reg_resp.json()
    assert data["success"] is True
    assert data["user"]["username"] == TEST_USER
    assert data["token"] is not None
    token = data["token"]

    # Verify profile endpoint with token
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["display_name"] == "Sarah Analyst"

    # Verify login
    login_resp = client.post("/api/auth/login", json={
        "username": TEST_USER,
        "password": "securepassword123"
    })
    assert login_resp.status_code == 200
    assert login_resp.json()["success"] is True

def test_account_saved_chats_isolation():
    """Verify that saved chats belong strictly to the authenticated account."""
    # 1. Login as raj
    raj_login = client.post("/api/auth/login", json={"username": "raj", "password": "password123"}).json()
    raj_token = raj_login["token"]

    # 2. Login as TEST_USER
    sarah_login = client.post("/api/auth/login", json={"username": TEST_USER, "password": "securepassword123"}).json()
    sarah_token = sarah_login["token"]

    # Sarah creates a conversation
    conv_resp = client.post("/api/conversations", json={"title": "Sarah Financial Model"}, headers={"Authorization": f"Bearer {sarah_token}"})
    assert conv_resp.status_code == 200
    sarah_conv_id = conv_resp.json()["id"]

    # List conversations for Sarah -> should contain her chat
    sarah_chats = client.get("/api/conversations", headers={"Authorization": f"Bearer {sarah_token}"}).json()
    assert any(c["id"] == sarah_conv_id for c in sarah_chats)

    # List conversations for Raj -> should NOT contain Sarah's private chat
    raj_chats = client.get("/api/conversations", headers={"Authorization": f"Bearer {raj_token}"}).json()
    assert not any(c["id"] == sarah_conv_id for c in raj_chats)

def test_account_saved_uploads_isolation():
    """Verify that uploaded datasets are saved and tagged to the user's account."""
    sarah_login = client.post("/api/auth/login", json={"username": TEST_USER, "password": "securepassword123"}).json()
    sarah_token = sarah_login["token"]

    csv_data = b"product_id,product_name,category,unit_price,inventory_count\n1,Alpha Widget,Hardware,25.50,140\n2,Beta Drone,Robotics,450.00,22\n3,Gamma Sensor,IoT,15.20,500\n"
    
    files = {"file": ("products_catalog.csv", csv_data, "text/csv")}
    upload_resp = client.post(
        "/api/upload",
        files=files,
        data={"custom_table_name": "sarah_products"},
        headers={"Authorization": f"Bearer {sarah_token}"}
    )
    assert upload_resp.status_code == 200
    data = upload_resp.json()
    assert data["success"] is True
    assert data.get("account_saved") is True

    # Sarah inspects her uploaded tables
    my_tables_resp = client.get("/api/auth/my-tables", headers={"Authorization": f"Bearer {sarah_token}"})
    assert my_tables_resp.status_code == 200
    my_tables = my_tables_resp.json()
    assert any(t["table_name"] == "sarah_products" for t in my_tables)

    # Raj inspects his uploaded tables -> sarah_products should not be in Raj's personal upload list
    raj_login = client.post("/api/auth/login", json={"username": "raj", "password": "password123"}).json()
    raj_tables = client.get("/api/auth/my-tables", headers={"Authorization": f"Bearer {raj_login['token']}"}).json()
    assert not any(t["table_name"] == "sarah_products" for t in raj_tables)

def test_universal_domain_formulas_non_table_calculations():
    """Verify that multi-domain formulas (Finance, Healthcare, Supply Chain, Physics) work directly."""
    # Finance: Compound Interest
    res1 = client.post("/api/query", json={"query": "Calculate compound interest on 10000 at 5% for 3 years"})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "executed"
    assert data1["execution"]["success"] is True
    assert len(data1["execution"]["rows"]) == 1

    # Healthcare: BMI Calculation
    res2 = client.post("/api/query", json={"query": "Calculate BMI for weight 70 kg and height 1.75 meters"})
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "executed"
    assert data2["execution"]["success"] is True
    # BMI is around 22.86
    val = list(data2["execution"]["rows"][0].values())[0]
    assert 22.0 <= float(val) <= 23.5

    # Supply Chain: Economic Order Quantity (EOQ)
    res3 = client.post("/api/query", json={"query": "Calculate EOQ for annual demand 10000, order cost $50, holding cost $2"})
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["status"] == "executed"
    assert data3["execution"]["success"] is True
    # EOQ = sqrt((2 * 10000 * 50) / 2) = sqrt(500000) ~ 707.1
    val3 = list(data3["execution"]["rows"][0].values())[0]
    assert 700 <= float(val3) <= 715

    # STEM / Physics: Kinetic Energy
    res4 = client.post("/api/query", json={"query": "Calculate kinetic energy for 1000 kg mass moving at 20 m/s"})
    assert res4.status_code == 200
    data4 = res4.json()
    assert data4["status"] == "executed"
    assert data4["execution"]["success"] is True
    # KE = 0.5 * 1000 * 400 = 200000
    val4 = list(data4["execution"]["rows"][0].values())[0]
    assert float(val4) == 200000.0 or float(val4) == 200000
