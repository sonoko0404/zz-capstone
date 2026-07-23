from __future__ import annotations

import os

from fastapi.testclient import TestClient


os.environ["OPENAI_API_KEY"] = ""
os.environ["DOTENV_OVERRIDE"] = "false"

from app.main import app


client = TestClient(app)


def _reset(session_id: str) -> None:
    response = client.post("/api/intake/reset", json={"session_id": session_id})
    assert response.status_code == 200


def test_api_guardrails_stop_live_and_multi_request_messages() -> None:
    live_session = "p0-api-live"
    _reset(live_session)
    live = client.post(
        "/api/intake/message",
        json={
            "session_id": live_session,
            "message": "Exactly how many open BIM tickets are assigned today?",
        },
    )
    assert live.status_code == 200
    live_payload = live.json()
    assert live_payload["mode"] == "context_answer"
    assert live_payload["llm_provider"] == "system"
    assert live_payload["intake"]["request_type"] is None
    assert live_payload["ticket_bundle_preview"] is None
    assert "cannot query live Power BI or Armada data" in live_payload["assistant_message"]

    multi_session = "p0-api-multi"
    _reset(multi_session)
    multi = client.post(
        "/api/intake/message",
        json={
            "session_id": multi_session,
            "message": (
                "Build a sales dashboard from Salesforce, and also fix the incorrect "
                "totals in our inventory report."
            ),
        },
    )
    assert multi.status_code == 200
    multi_payload = multi.json()
    assert multi_payload["ready_for_ticket"] is False
    assert multi_payload["intake"]["scenario_type"] == "Ambiguous Request"
    assert multi_payload["ticket_bundle_preview"] is None
    assert "two independent requests" in multi_payload["assistant_message"].lower()


def test_api_conflict_blocks_generation_until_resolved() -> None:
    session_id = "p0-api-conflict"
    _reset(session_id)
    complete = client.post(
        "/api/intake/message",
        json={
            "session_id": session_id,
            "message": (
                "Create a Power BI dashboard for sales managers to track units sold from Salesforce. "
                "Requester is Maya Chen, owner is Jordan Lee. Success is validated by Jordan Lee. "
                "Use daily refresh and no RLS."
            ),
        },
    )
    assert complete.status_code == 200
    assert complete.json()["ready_for_ticket"] is True

    conflict = client.post(
        "/api/intake/message",
        json={"session_id": session_id, "message": "Use Salesforce or SAP."},
    )
    assert conflict.status_code == 200
    conflict_payload = conflict.json()
    assert conflict_payload["ready_for_ticket"] is False
    assert conflict_payload["ticket_bundle_preview"] is None
    assert conflict_payload["field_metadata"]["data_sources"]["source"] == "needs_confirmation"

    blocked = client.post(
        "/api/intake/generate-ticket",
        json={"session_id": session_id},
    )
    assert blocked.status_code == 409
    assert "resolve conflicting" in blocked.json()["detail"]

    resolved = client.post(
        "/api/intake/message",
        json={"session_id": session_id, "message": "Use SAP."},
    )
    assert resolved.status_code == 200
    assert resolved.json()["intake"]["data_sources"] == "SAP"
    assert resolved.json()["ready_for_ticket"] is True

    generated = client.post(
        "/api/intake/generate-ticket",
        json={"session_id": session_id},
    )
    assert generated.status_code == 200
    assert generated.json()["status"] == "Draft Only"


def test_api_rls_rules_reach_structured_intake_and_ticket() -> None:
    session_id = "p0-api-rls"
    _reset(session_id)
    response = client.post(
        "/api/intake/message",
        json={
            "session_id": session_id,
            "message": (
                "Create a sales dashboard for regional managers and executives to track revenue from Salesforce. "
                "Managers only see their region; executives see all regions. "
                "Requester is Maya Chen, maya@example.com; owner is Jordan Lee. "
                "Success means Jordan validates accuracy. Daily refresh. High priority."
            ),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intake"]["row_level_security"].startswith("Required:")
    assert payload["intake"]["recipients_or_access_roles"] == "Regional managers and Executives"
    criteria = payload["ticket_preview"]["acceptance_criteria"]
    assert "Regional managers can view only their assigned region." in criteria
    assert "Executives can view all regions." in criteria
    assert "Role/group mappings are confirmed before release." in criteria
