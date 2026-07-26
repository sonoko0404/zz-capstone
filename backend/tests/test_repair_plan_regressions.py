from __future__ import annotations

import pytest

from app.intake_engine import IntakeEngine
from app.knowledge_base import KnowledgeBase
from app.llm_client import DeterministicMockLLM, IntakeLLMClient
from app.mock_jira import MockJiraAdapter
from app.models import (
    FieldMetadataUpdate,
    IntakeData,
    LLMIntakeResult,
    TranscriptMessage,
)
from app.ticket_generator import TicketGenerator


def make_engine(llm: IntakeLLMClient | None = None) -> IntakeEngine:
    return IntakeEngine(
        llm or DeterministicMockLLM(),
        KnowledgeBase(),
        TicketGenerator(MockJiraAdapter()),
    )


class SparseSecondTurnLLM(IntakeLLMClient):
    """Simulate a cloud model that omits established fields on turn two."""

    def __init__(self) -> None:
        self.calls = 0
        self.delegate = DeterministicMockLLM()

    def analyze(self, *args, **kwargs) -> LLMIntakeResult:  # type: ignore[no-untyped-def]
        self.calls += 1
        result = self.delegate.analyze(*args, **kwargs)
        if self.calls == 1:
            return result
        sparse = IntakeData(
            armada_owner=result.updated_intake.armada_owner,
            success_definition=result.updated_intake.success_definition,
            data_sources="SAP",
        )
        updates = list(result.field_metadata_updates) + [
            FieldMetadataUpdate(
                field="data_sources",
                confidence="high",
                source="user_provided",
                evidence="Owner is Jordan Lee. Success means Jordan validates the totals.",
            )
        ]
        return result.model_copy(update={
            "updated_intake": sparse,
            "field_metadata_updates": updates,
        })


class CountingLLM(IntakeLLMClient):
    def __init__(self) -> None:
        self.calls = 0
        self.delegate = DeterministicMockLLM()

    def analyze(self, *args, **kwargs) -> LLMIntakeResult:  # type: ignore[no-untyped-def]
        self.calls += 1
        return self.delegate.analyze(*args, **kwargs)


class CapturingAdapter(MockJiraAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.bundle_payload = None

    def create_ticket_bundle(self, ticket_bundle):  # type: ignore[no-untyped-def]
        self.bundle_payload = ticket_bundle
        return super().create_ticket_bundle(ticket_bundle)


def test_sparse_llm_candidate_cannot_regress_canonical_state() -> None:
    engine = make_engine(SparseSecondTurnLLM())
    session_id = "canonical-monotonic"
    first = engine.process_message(
        session_id,
        (
            "Create a Power BI dashboard for sales managers to track revenue from Salesforce. "
            "Requester is Maya Chen. Daily refresh and no RLS."
        ),
    )
    second = engine.process_message(
        session_id,
        "Owner is Jordan Lee. Success means Jordan validates the totals.",
    )

    assert second.intake.data_sources == first.intake.data_sources == "Salesforce"
    assert second.intake.metrics_kpis_charts_maps == first.intake.metrics_kpis_charts_maps == "revenue"
    assert second.intake.recipients_or_access_roles == first.intake.recipients_or_access_roles
    assert second.intake.display_format == first.intake.display_format
    assert second.intake.refresh_frequency == "Daily"
    assert second.intake.armada_owner == "Jordan Lee"
    assert second.intake.success_definition == "Jordan validates the totals"


def test_live_guardrail_does_not_block_normal_power_bi_requirements() -> None:
    llm = CountingLLM()
    engine = make_engine(llm)
    normal_requirements = (
        "Create a Power BI report for the current fiscal year to identify underperforming regions.",
        "Build a current dashboard from Salesforce with a daily refresh.",
        "Use Power BI as the display format for a future reporting solution.",
    )
    for index, message in enumerate(normal_requirements):
        response = engine.process_message(f"not-live-{index}", message)
        assert response.mode != "context_answer"

    assert llm.calls == len(normal_requirements)


def test_self_service_complete_request_maps_once_and_generates_dual_draft() -> None:
    response = make_engine().process_message(
        "self-service-one-turn",
        (
            "Regional analysts need ongoing read-only access to the Finance Certified semantic model "
            "so they can analyze Northeast sales. Data scope is Northeast region. "
            "Security approver is Dana Lee."
        ),
    )

    assert response.intake.scenario_type == "Self-Service Access"
    assert response.intake.recipients_or_access_roles == "Regional analysts"
    assert response.intake.data_sources == "Finance Certified semantic model"
    assert response.intake.why_report_necessary == "analyze Northeast sales"
    assert response.intake.scope_criteria == "Northeast region"
    assert response.intake.armada_owner == "Dana Lee"
    assert "ongoing" in (response.intake.known_constraints or "").lower()
    assert "read-only" in (response.intake.row_level_security or "").lower()
    assert response.intake.display_format == "Not applicable — self-service access"
    assert response.intake.metrics_kpis_charts_maps == "Not applicable — self-service access"
    assert response.intake.refresh_frequency == "Not applicable — self-service access"
    assert response.ready_for_ticket is True
    assert response.next_questions == []
    assert response.ticket_bundle_preview is not None
    assert response.ticket_bundle_preview.ito_ticket.project_category == "ITO"
    assert response.ticket_bundle_preview.bim_ticket.project_category == "BIM"


def test_source_cadence_synonyms_remain_separate_from_requested_cadence() -> None:
    response = make_engine().process_message(
        "cadence-synonyms",
        (
            "Build an hourly operations dashboard for dispatch managers to monitor late orders "
            "from Salesforce. The source is only refreshed monthly."
        ),
    )

    assert response.intake.refresh_frequency == "Hourly"
    assert response.intake.run_frequency == "Hourly"
    assert "monthly" in (response.intake.known_constraints or "").lower()
    assert any("conflicts with a source" in risk.lower() for risk in response.risk_flags)


def test_requester_owner_synonyms_enter_canonical_fields() -> None:
    response = make_engine().process_message(
        "requester-owner-synonyms",
        (
            "Create a report from Salesforce to track revenue for finance. "
            "The request comes from Priya Shah; the delivery is accountable to Jordan Lee."
        ),
    )
    assert response.intake.requester == "Priya Shah"
    assert response.intake.armada_owner == "Jordan Lee"


def test_ticket_and_adapter_payloads_are_sanitized_before_projection() -> None:
    adapter = CapturingAdapter()
    generator = TicketGenerator(adapter)
    intake = IntakeData(
        scenario_type="New Dashboard",
        request_type="dashboard",
        why_report_necessary=(
            "Contact maya@example.com; password=super-secret; "
            "employee id=EMP-991; SSN 123-45-6789."
        ),
        requester="Maya Chen",
        requester_email="maya@example.com",
        armada_owner="Jordan Lee",
        recipients_or_access_roles="Sales managers",
        data_sources="Salesforce",
        required_fields="Revenue",
        metrics_kpis_charts_maps="Revenue",
        display_format="Power BI dashboard",
        success_definition="Jordan validates totals",
        include_chat_attachment=True,
    )
    preview = generator.generate_bundle(
        intake,
        [
            TranscriptMessage(
                role="user",
                content="Email maya@example.com and token=abc123; card 4111 1111 1111 1111.",
            )
        ],
        "draft_ready",
    )

    assert adapter.bundle_payload is not None
    serialized_adapter = adapter.bundle_payload.model_dump_json()
    serialized_preview = preview.model_dump_json()
    for serialized in (serialized_adapter, serialized_preview):
        assert "maya@example.com" not in serialized
        assert "super-secret" not in serialized
        assert "EMP-991" not in serialized
        assert "123-45-6789" not in serialized
        assert "4111 1111 1111 1111" not in serialized
    assert "[REDACTED EMAIL]" in serialized_adapter
    assert "[REDACTED SECRET]" in serialized_adapter


def test_requirements_matrix_publishes_required_and_na_contract() -> None:
    response = make_engine().process_message(
        "matrix-contract",
        "I need self-service access to the Power BI semantic model.",
    )
    by_key = {node.key: node for node in response.requirements_matrix}

    assert by_key["required_data"].requirement_level == "required"
    assert ["data_sources"] in by_key["required_data"].required_groups
    assert by_key["display_format"].requirement_level == "n/a"
    assert by_key["display_format"].required_groups == []


def test_pending_and_validated_intakes_are_locked_until_revision() -> None:
    engine = make_engine()
    session_id = "validation-lock"
    response = engine.process_message(
        session_id,
        (
            "Create a Power BI dashboard for sales managers to track revenue from Salesforce. "
            "Requester is Maya Chen, email unavailable; owner is Jordan Lee. "
            "Finance validates totals. Daily refresh, no RLS. High priority. "
            "Jira issue type is Story."
        ),
    )
    assert response.validation_ready is True
    pending = engine.submit_for_validation(session_id, "Jordan Lee", "Reviewing")
    assert pending.validation_state == "pending_validation"

    locked_chat = engine.process_message(session_id, "Use SAP instead.")
    assert locked_chat.validation_state == "pending_validation"
    assert locked_chat.intake.data_sources == "Salesforce"
    assert locked_chat.llm_provider == "system"
    assert "locked" in locked_chat.assistant_message.lower()
    with pytest.raises(ValueError, match="Return the intake for revision"):
        engine.update_field(session_id, "data_sources", "SAP")

    approved = engine.validate(session_id, "Jordan Lee", "Approved")
    assert approved.validation_state == "validated"
    locked_after_approval = engine.process_message(session_id, "Use SAP instead.")
    assert locked_after_approval.validation_state == "validated"
    assert locked_after_approval.intake.data_sources == "Salesforce"
