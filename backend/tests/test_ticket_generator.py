from app.mock_jira import MockJiraAdapter
from app.models import IntakeData
from app.ticket_generator import TicketGenerator


def complete_intake() -> IntakeData:
    return IntakeData(
        report_title="Sales performance dashboard",
        request_type="dashboard",
        why_report_necessary="Help managers identify sales gaps.",
        recipients_or_access_roles="Sales managers",
        data_sources="Salesforce",
        metrics_kpis_charts_maps="Units sold, revenue",
        display_format="Power BI dashboard",
        requester="Maya Chen",
        armada_owner="Jordan Lee",
        success_definition="Managers can identify underperforming regions weekly.",
        accuracy_owner_or_validator="Jordan Lee",
        project_type_hint="BIM",
        risk_flags=[],
    )


def test_ticket_generation_is_draft_only() -> None:
    preview = TicketGenerator(MockJiraAdapter()).generate(complete_intake())

    assert preview.draft_ticket_key == "DRAFT-BIM-1001"
    assert preview.status == "Draft Only"
    assert preview.disclaimer == "No real Jira ticket was created. This is a prototype draft."
    assert preview.project_category == "BIM"
    assert preview.source_request_category == "unknown"
    assert len(preview.acceptance_criteria) >= 5
