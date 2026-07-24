from unittest.mock import patch

import httpx
import pytest

from app.jira_adapter import JiraAdapter
from app.mock_jira import MockJiraAdapter
from app.models import (
    AttachmentDraft,
    JiraTicketBundlePayload,
    JiraTicketDraftPayload,
    TicketPayload,
    TicketRelationshipDraft,
)
from app.real_jira import RealJiraAdapter, build_jira_adapter, plain_text_to_adf


def payload() -> TicketPayload:
    return TicketPayload(
        title="Test draft",
        summary="Test",
        business_purpose="Test the adapter boundary",
        requester="Tester",
        owner="Owner",
        audience="Analysts",
        data_sources=["Sanitized sample"],
        metrics_or_kpis=["Count"],
        display_format="Dashboard",
        refresh_frequency="Weekly",
        scope="Prototype",
        acceptance_criteria=["Draft renders"],
        success_criteria=["Contract passes"],
        risks_and_assumptions=["Mock only"],
        suggested_priority="Low",
        linked_ticket_suggestion="None",
        implementation_notes=["No external write"],
    )


def bundle_payload() -> JiraTicketBundlePayload:
    return JiraTicketBundlePayload(
        ito_ticket=JiraTicketDraftPayload(
            project_category="ITO",
            issue_type="To be confirmed by Jira integration",
            summary="BI request intake: Sales dashboard",
            description="REQUEST INTAKE (DRAFT)\nRequester: Maya\nAudience: managers",
            priority="High",
            attachments=[
                AttachmentDraft(content="user: hello\nassistant: hi", included=True),
            ],
        ),
        bim_ticket=JiraTicketDraftPayload(
            project_category="BIM",
            issue_type="To be confirmed by Jira integration",
            summary="Sales dashboard",
            description="BI DELIVERY REQUIREMENTS (DRAFT)\nData sources: Salesforce",
            priority="High",
        ),
        proposed_relationship=TicketRelationshipDraft(),
        validation_state="draft_ready",
    )


def test_mock_implements_adapter_contract_without_creation() -> None:
    adapter: JiraAdapter = MockJiraAdapter()
    result = adapter.create_ticket(payload())

    assert result.created is False
    assert result.ticket_key.startswith("DRAFT-BIM-")
    assert result.payload.title == "Test draft"


def test_plain_text_to_adf_builds_document() -> None:
    doc = plain_text_to_adf("REQUEST INTAKE (DRAFT)\n\nRequester: Maya")
    assert doc["type"] == "doc"
    assert doc["version"] == 1
    assert any(block["type"] == "heading" for block in doc["content"])
    assert any(block["type"] == "paragraph" for block in doc["content"])


def test_build_jira_adapter_defaults_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_REAL_JIRA", raising=False)
    assert isinstance(build_jira_adapter(), MockJiraAdapter)


def test_build_jira_adapter_falls_back_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_REAL_JIRA", "true")
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    assert isinstance(build_jira_adapter(), MockJiraAdapter)


def test_real_jira_bundle_creates_and_links() -> None:
    adapter = RealJiraAdapter(
        base_url="https://example.atlassian.net",
        email="bot@example.com",
        api_token="token",
        ito_issue_type="Task",
        bim_issue_type="Story",
        link_type="Relates",
    )

    responses = [
        httpx.Response(201, json={"key": "ITO-101", "id": "1"}),
        httpx.Response(201, json={"key": "BIM-202", "id": "2"}),
        httpx.Response(201, json={}),
        httpx.Response(200, json=[{"filename": "chat.txt"}]),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    transport = httpx.MockTransport(handler)
    fake_client = httpx.Client(transport=transport, headers=adapter._auth_headers())

    with patch.object(adapter, "_client", return_value=fake_client):
        result = adapter.create_ticket_bundle(bundle_payload())

    assert result.created is True
    assert result.ito_ticket_key == "ITO-101"
    assert result.bim_ticket_key == "BIM-202"
    assert result.status == "Created in Jira"
    assert result.payload.proposed_relationship.created is True
    assert result.payload.proposed_relationship.relationship_type == "Relates"
    assert result.payload.ito_ticket.issue_type == "Task"
    assert result.payload.bim_ticket.issue_type == "Story"
    assert "ITO-101" in result.message
    assert not responses


def test_real_jira_create_failure_raises() -> None:
    adapter = RealJiraAdapter(
        base_url="https://example.atlassian.net",
        email="bot@example.com",
        api_token="token",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(400, text='{"errorMessages":["bad project"]}')
    )
    fake_client = httpx.Client(transport=transport, headers=adapter._auth_headers())

    with patch.object(adapter, "_client", return_value=fake_client):
        with pytest.raises(RuntimeError, match="ITO ticket creation failed"):
            adapter.create_ticket_bundle(bundle_payload())
