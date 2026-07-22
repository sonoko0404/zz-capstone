from app.jira_adapter import JiraAdapter
from app.mock_jira import MockJiraAdapter
from app.models import TicketPayload


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


def test_mock_implements_adapter_contract_without_creation() -> None:
    adapter: JiraAdapter = MockJiraAdapter()
    result = adapter.create_ticket(payload())

    assert result.created is False
    assert result.ticket_key.startswith("DRAFT-BIM-")
    assert result.payload.title == "Test draft"

