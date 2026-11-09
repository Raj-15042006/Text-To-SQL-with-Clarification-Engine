import io
import json
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_full_upload_pipeline():
    # 1. Health check
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"

    # 2. Upload CSV dataset
    csv_bytes = b"player_name,team,runs,balls_faced,strike_rate\nVirat Kohli,RCB,741,480,154.37\nSunil Narine,KKR,488,270,180.74\nTravis Head,SRH,567,296,191.55\n"
    res = client.post(
        "/api/upload",
        files={"file": ("sample_players.csv", io.BytesIO(csv_bytes), "text/csv")}
    )
    assert res.status_code == 200
    res_data = res.json()
    assert res_data.get("success") is True
    assert res_data.get("table_name") == "sample_players"
    assert res_data.get("row_count") == 3

    # 3. Check /api/schema for sample_players
    schema_res = client.get("/api/schema")
    assert schema_res.status_code == 200
    schema = schema_res.json()
    tables = list(schema.get("tables", {}).keys())
    assert "sample_players" in tables, "sample_players table NOT found in schema!"

    # 4. Query sample_players using natural language
    q_res = client.post(
        "/api/query",
        json={"query": "Show the player with the highest strike rate and their runs"}
    )
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert q_data.get("status") in ("executed", "success")
    assert q_data.get("execution", {}).get("success") is True

    # 5. Upload a JSON dataset (including nested fields)
    json_bytes = json.dumps([
        {"product_name": "UltraBook Pro", "category": "Laptops", "price": 1299.99, "stock": 45, "tags": ["premium", "pc"]},
        {"product_name": "SmartWatch X", "category": "Wearables", "price": 249.50, "stock": 120, "tags": ["fitness"]},
        {"product_name": "NoiseCancel 700", "category": "Audio", "price": 349.00, "stock": 80, "tags": ["audio"]}
    ]).encode("utf-8")

    res2 = client.post(
        "/api/upload",
        files={"file": ("products.json", io.BytesIO(json_bytes), "application/json")}
    )
    assert res2.status_code == 200
    res2_data = res2.json()
    assert res2_data.get("success") is True
    assert res2_data.get("table_name") == "products"

    schema2_res = client.get("/api/schema")
    tables2 = list(schema2_res.json().get("tables", {}).keys())
    assert "products" in tables2, "products table NOT found in schema!"

    # Clean up test tables
    client.delete("/api/upload/sample_players")
    client.delete("/api/upload/products")

if __name__ == "__main__":
    test_full_upload_pipeline()
    print("ALL VERIFICATIONS PASSED!")

