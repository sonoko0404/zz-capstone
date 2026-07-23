from __future__ import annotations

import os

from fastapi.testclient import TestClient


os.environ["OPENAI_API_KEY"] = ""
os.environ["DOTENV_OVERRIDE"] = "false"

from app.main import app


client = TestClient(app)


def _reset(session_id: str) -> None:
    assert client.post(
        "/api/intake/reset",
        json={"session_id": session_id},
    ).status_code == 200


def test_api_ready_state_suppresses_optional_questions() -> None:
    session_id = "p1-api-ready"
    _reset(session_id)
    response = client.post(
        "/api/intake/message",
        json={
            "session_id": session_id,
            "message": (
                "Create a Power BI dashboard for sales managers to track units sold from Salesforce. "
                "Requester is Maya Chen, maya@example.com; owner is Jordan Lee. Daily refresh, no RLS, "
                "high priority. Success means Jordan validates accuracy."
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready_for_ticket"] is True
    assert payload["next_questions"] == []
    assert payload["missing_fields"]
    assert payload["ticket_bundle_preview"]["created"] is False


def test_api_self_service_bundle_and_feasibility_validation_gate() -> None:
    access_session = "p1-api-self-service"
    _reset(access_session)
    access = client.post(
        "/api/intake/message",
        json={
            "session_id": access_session,
            "message": (
                "Regional analysts need ongoing access to the Power BI semantic model to build approved reports. "
                "Data scope is Northeast sales data. Approval owner is Dana Lee."
            ),
        },
    )
    assert access.status_code == 200
    access_payload = access.json()
    assert access_payload["intake"]["scenario_type"] == "Self-Service Access"
    assert access_payload["ready_for_ticket"] is True
    assert access_payload["next_questions"] == []
    assert "SELF-SERVICE ACCESS REQUEST" in (
        access_payload["ticket_bundle_preview"]["ito_ticket"]["description"]
    )
    assert access_payload["ticket_preview"]["display_format"] == (
        "Not applicable — self-service access"
    )

    conflict_session = "p1-api-feasibility"
    _reset(conflict_session)
    conflict = client.post(
        "/api/intake/message",
        json={
            "session_id": conflict_session,
            "message": (
                "Create a Power BI dashboard for finance leaders to track monthly margin from SAP. "
                "Requester is Alex Kim; alex@example.com. Finance validates totals. "
                "Daily refresh, but the source data updates monthly. No RLS. High priority."
            ),
        },
    )
    assert conflict.status_code == 200
    conflict_payload = conflict.json()
    assert conflict_payload["ready_for_ticket"] is True
    assert conflict_payload["validation_ready"] is False
    blocked = client.post(
        "/api/intake/validation/submit",
        json={"session_id": conflict_session, "validator_name": "Finance"},
    )
    assert blocked.status_code == 409
    assert "feasibility risks" in blocked.json()["detail"]
