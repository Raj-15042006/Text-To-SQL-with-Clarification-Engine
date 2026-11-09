import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_full_pipeline():
    print("--- 0. Ensuring Sample Data Source for E2E Test ---")
    resp0 = client.post("/api/schema/switch-source", json={"source": "sample"})
    assert resp0.status_code == 200

    print("\n--- 1. Testing Ambiguous Query: 'Show the highest sales' ---")
    res_resp = client.post("/api/query", json={"query": "Show the highest sales"})
    assert res_resp.status_code == 200
    res = res_resp.json()
    print(f"Query Status: {res.get('status')}")
    if res.get("status") == "error":
        print(f"Error Message: {res.get('error_message')}")
    assert res["status"] == "awaiting_clarification", f"Expected awaiting_clarification, got {res['status']}: {res.get('error_message')}"
    assert res["analysis"]["is_ambiguous"] is True
    print(f"Detected Ambiguity Category: {res['analysis']['ambiguity_type']}")
    print(f"Clarification Question: {res['analysis']['clarification']['question']}")
    
    options = res["analysis"]["clarification"]["options"]
    assert len(options) >= 2, "Expected at least 2 clarification options"
    for opt in options:
        print(f"  • [{opt['id']}] {opt['label']}")

    # Pick the first option to clarify
    selected_opt = options[0]["id"]
    print(f"\n--- 2. Submitting Clarification: '{selected_opt}' ---")
    session_id = res["session_id"]
    clarify_resp = client.post(f"/api/query/{session_id}/clarify", json={"option_id": selected_opt})
    assert clarify_resp.status_code == 200
    clarify_res = clarify_resp.json()
    
    assert clarify_res["status"] == "executed", f"Expected executed, got {clarify_res['status']}"
    print(f"Generated SQL: {clarify_res['generated_sql']}")
    print(f"SQLGlot Validation: is_valid={clarify_res['validation']['is_valid']}")
    assert clarify_res["validation"]["is_valid"] is True
    assert clarify_res["execution"]["success"] is True
    print(f"Rows Returned: {clarify_res['execution']['row_count']}")
    print(f"Sample Data: {clarify_res['execution']['rows'][:2]}")
    print(f"Plain-English Explanation: {clarify_res['natural_explanation']}")

    print("\n--- 3. Testing Direct/Unambiguous Query: 'How many students are enrolled?' ---")
    direct_resp = client.post("/api/query", json={"query": "How many students are enrolled?"})
    assert direct_resp.status_code == 200
    direct_res = direct_resp.json()
    assert direct_res["status"] == "executed"
    print(f"Generated SQL: {direct_res['generated_sql']}")
    print(f"SQLGlot Validation: is_valid={direct_res['validation']['is_valid']}")
    assert direct_res["validation"]["is_valid"] is True
    print(f"Rows Returned: {direct_res['execution']['row_count']}")
    print(f"Result: {direct_res['execution']['rows']}")
    print(f"Explanation: {direct_res['natural_explanation']}")

    print("\n[SUCCESS] ALL END-TO-END PIPELINE TESTS PASSED!")

if __name__ == "__main__":
    test_full_pipeline()

