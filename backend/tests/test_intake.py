from app.knowledge_base import KnowledgeBase
from app.llm_client import DeterministicMockLLM
from app.models import IntakeData


def test_extracts_complete_dashboard_request() -> None:
    client = DeterministicMockLLM()
    result = client.analyze(
        (
            "Create a Power BI dashboard for sales managers to track units sold from Salesforce. "
            "Requester is Maya Chen, owner is Jordan Lee. Success is validated by Jordan Lee. "
            "Use daily refresh and no RLS."
        ),
        IntakeData(),
        KnowledgeBase(),
        [],
    )

    assert result.updated_intake.request_type == "dashboard"
    assert result.updated_intake.data_sources == "Salesforce"
    assert result.updated_intake.recipients_or_access_roles == "sales managers"
    assert result.updated_intake.metrics_kpis_charts_maps == "units sold"
    assert result.updated_intake.requester == "Maya Chen"
    assert result.ready_for_ticket is True
    assert result.completion_score >= 80


def test_vague_request_asks_limited_questions() -> None:
    result = DeterministicMockLLM().analyze(
        "I need a dashboard.", IntakeData(), KnowledgeBase(), []
    )

    assert result.ready_for_ticket is False
    assert 1 <= len(result.next_questions) <= 3
    assert "data_sources" in result.missing_fields


def test_power_bi_data_agent_is_captured_as_static_context_source() -> None:
    result = DeterministicMockLLM().analyze(
        "You can use data from Power BI Data Agent.",
        IntakeData(request_type="dashboard", display_format="Power BI dashboard"),
        KnowledgeBase(),
        [],
    )

    assert result.updated_intake.data_sources == "Power BI Data Agent"
    assert result.updated_intake.display_format == "Power BI dashboard"
    assert any("no live connection" in item.lower() for item in result.context_used)
