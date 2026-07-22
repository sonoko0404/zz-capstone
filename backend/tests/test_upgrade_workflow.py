from openai.lib._pydantic import to_strict_json_schema

from app.intake_engine import IntakeEngine
from app.knowledge_base import KnowledgeBase
from app.llm_client import DeterministicMockLLM
from app.mock_jira import MockJiraAdapter
from app.models import LLMModelOutput
from app.ticket_generator import TicketGenerator


def make_engine() -> IntakeEngine:
    return IntakeEngine(
        DeterministicMockLLM(),
        KnowledgeBase(),
        TicketGenerator(MockJiraAdapter()),
    )


def complete_message() -> str:
    return (
        "Create a Power BI dashboard for sales managers to track units sold from Salesforce. "
        "Requester is Maya Chen, owner is Jordan Lee. Success is validated by Jordan Lee. "
        "Use daily refresh and no RLS. High priority. Include the sanitized chat transcript."
    )


def test_strict_openai_schema_has_no_dynamic_objects() -> None:
    schema = to_strict_json_schema(LLMModelOutput)
    problems: list[str] = []

    def visit(value: object, path: str = "root") -> None:
        if isinstance(value, dict):
            if value.get("type") == "object" and value.get("additionalProperties") is not False:
                problems.append(path)
            for key, child in value.items():
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(schema)
    assert not problems
    assert set(schema["required"]) == set(schema["properties"])


def test_requirements_matrix_manual_confirmation_and_validation_flow() -> None:
    engine = make_engine()
    session_id = "workflow-test"
    response = engine.process_message(session_id, complete_message())

    assert response.ready_for_ticket is True
    assert len(response.requirements_matrix) == 13
    assert response.intake.scenario_type == "New Dashboard"
    assert response.validation_ready is False
    assert "email" in (response.validation_note or "").lower()

    response = engine.update_field(session_id, "requester_email", "maya@example.com")
    assert response.field_metadata["requester_email"].source == "user_confirmed"
    assert response.validation_ready is True

    response = engine.submit_for_validation(session_id, "Jordan Lee", None)
    assert response.validation_state == "pending_validation"
    response = engine.validate(session_id, "Jordan Lee", "Validated for prototype review")
    assert response.validation_state == "validated"
    assert response.validated_at is not None


def test_mock_bundle_contains_traceability_and_sanitized_attachment() -> None:
    engine = make_engine()
    session_id = "bundle-test"
    engine.process_message(session_id, complete_message())
    engine.update_field(session_id, "requester_email", "maya@example.com")
    generated = engine.generate_ticket(session_id)
    bundle = generated.ticket_bundle_preview

    assert bundle.created is False
    assert bundle.ito_ticket.draft_ticket_key.startswith("DRAFT-ITO-")
    assert bundle.bim_ticket.draft_ticket_key.startswith("DRAFT-BIM-")
    assert bundle.proposed_relationship.created is False
    assert "Maya Chen" in bundle.ito_ticket.description
    assert "maya@example.com" in bundle.bim_ticket.description
    assert bundle.bim_ticket.issue_type == "To be confirmed by Jira integration"
    assert bundle.ito_ticket.attachments[0].filename == "chat.txt"
    assert "maya@example.com" not in bundle.ito_ticket.attachments[0].content


def test_confirmed_matrix_value_is_not_overwritten_by_later_model_extraction() -> None:
    engine = make_engine()
    session_id = "confirmed-field-test"
    engine.process_message(session_id, "I need a dashboard using Salesforce data.")
    engine.update_field(session_id, "data_sources", "Salesforce")
    response = engine.process_message(session_id, "Use SAP instead.")

    assert response.intake.data_sources == "Salesforce"
    assert response.field_metadata["data_sources"].source == "user_confirmed"
