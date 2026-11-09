import io
import json
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_csv_upload_and_query():
    csv_data = b"""item_name,category,price,qty,in_stock
Laptop,Electronics,1200.50,15,True
Chair,Furniture,150.00,40,False
Headphones,Electronics,89.99,100,True
Desk,Furniture,350.00,10,True
"""
    res = client.post(
        "/api/upload",
        files={"file": ("office_supplies.csv", io.BytesIO(csv_data), "text/csv")}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["table_name"] == "office_supplies"
    assert data["row_count"] == 4
    assert "item_name" in data["columns"]

    # Verify query works on newly uploaded table
    q_res = client.post("/api/query", json={"query": "Show all items in Electronics category"})
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert q_data["status"] == "executed"
    assert q_data["execution"]["success"] is True

    # Cleanup
    del_res = client.delete("/api/upload/office_supplies")
    assert del_res.status_code == 200

def test_tsv_and_semicolon_delimited_upload():
    tsv_data = b"emp_id\temp_name\tdepartment\tsalary\n101\tAlice\tEng\t110000\n102\tBob\tSales\t95000\n"
    res = client.post(
        "/api/upload",
        files={"file": ("team_roster.tsv", io.BytesIO(tsv_data), "text/tab-separated-values")}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["table_name"] == "team_roster"
    assert len(data["columns"]) == 4

    client.delete("/api/upload/team_roster")

def test_json_upload_with_nested_structures():
    nested_json = json.dumps([
        {
            "id": 1,
            "title": "Quantum Computing",
            "tags": ["physics", "computing", "advanced"],
            "metadata": {"author": "Dr. Smith", "reviewed": True}
        },
        {
            "id": 2,
            "title": "Relational Databases",
            "tags": ["sql", "storage"],
            "metadata": {"author": "Dr. Stone", "reviewed": False}
        }
    ]).encode("utf-8")

    res = client.post(
        "/api/upload",
        files={"file": ("research_papers.json", io.BytesIO(nested_json), "application/json")}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["table_name"] == "research_papers"
    assert data["row_count"] == 2

    # Cleanup
    client.delete("/api/upload/research_papers")

def test_upload_reserved_keyword_table_name():
    csv_data = b"order_id,user_id,amount\n1,10,50.0\n2,20,75.0\n"
    res = client.post(
        "/api/upload",
        files={"file": ("order.csv", io.BytesIO(csv_data), "text/csv")}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    # Should sanitize reserved keyword "order" to "tbl_order"
    assert data["table_name"] == "tbl_order"

    client.delete(f"/api/upload/{data['table_name']}")

def test_empty_file_rejected():
    res = client.post(
        "/api/upload",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    )
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()

def test_unsupported_file_extension_rejected():
    res = client.post(
        "/api/upload",
        files={"file": ("malicious.exe", io.BytesIO(b"binary"), "application/octet-stream")}
    )
    assert res.status_code == 400
    assert "unsupported" in res.json()["detail"].lower()
