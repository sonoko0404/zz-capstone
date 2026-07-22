import os

from fastapi.testclient import TestClient

os.environ["OPENAI_API_KEY"] = ""
os.environ["DOTENV_OVERRIDE"] = "false"

from app.main import app


client = TestClient(app)


def test_reference_endpoints() -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert len(client.get("/api/context/summary").json()["tables"]) == 4
    assert len(client.get("/api/sample-requests").json()["requests"]) == 5
    assert len(client.get("/api/stress-test/scenarios").json()["scenarios"]) == 7
    llm_status = client.get("/api/llm/status").json()
    assert llm_status["provider"] == "deterministic"
    assert llm_status["configured"] is False


def test_message_generate_and_reset_flow() -> None:
    session_id = "api-contract-test"
    message = (
        "Create a Power BI dashboard for sales managers to track units sold from Salesforce. "
        "Requester is Maya Chen, owner is Jordan Lee. Success is validated by Jordan Lee. "
        "Use daily refresh and no RLS."
    )
    response = client.post(
        "/api/intake/message",
        json={"session_id": session_id, "message": message},
    )
    assert response.status_code == 200
    assert response.json()["ready_for_ticket"] is True
    assert response.json()["ticket_preview"]["status"] == "Draft Only"
    assert response.json()["ticket_bundle_preview"]["ito_ticket"]["created"] is False
    assert len(response.json()["requirements_matrix"]) == 13
    assert response.json()["llm_provider"] == "deterministic"
    assert response.json()["fallback_reason"]

    draft = client.post("/api/intake/generate-ticket", json={"session_id": session_id})
    assert draft.status_code == 200
    assert draft.json()["draft_ticket_key"].startswith("DRAFT-BIM-")
    assert draft.json()["ticket_bundle_preview"]["ito_ticket"]["draft_ticket_key"].startswith("DRAFT-ITO-")

    field_update = client.patch(
        "/api/intake/field",
        json={"session_id": session_id, "field": "requester_email", "value": "maya@example.com"},
    )
    assert field_update.status_code == 200
    assert field_update.json()["field_metadata"]["requester_email"]["source"] == "user_confirmed"

    reset = client.post("/api/intake/reset", json={"session_id": session_id})
    assert reset.json() == {"session_id": session_id, "status": "reset"}
