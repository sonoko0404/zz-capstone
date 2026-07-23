from __future__ import annotations

import pytest

from app.intake_engine import IntakeEngine
from app.knowledge_base import KnowledgeBase
from app.llm_client import DeterministicMockLLM, IntakeLLMClient
from app.mock_jira import MockJiraAdapter
from app.models import FieldMetadata, IntakeData, LLMIntakeResult
from app.ticket_generator import TicketGenerator


def make_engine(llm: IntakeLLMClient | None = None) -> IntakeEngine:
    return IntakeEngine(
        llm or DeterministicMockLLM(),
        KnowledgeBase(),
        TicketGenerator(MockJiraAdapter()),
    )


class MisleadingOpenAILLM(IntakeLLMClient):
    configured = True
    model_name = "test-openai-model"

    def __init__(self) -> None:
        self.calls = 0
        self._deterministic = DeterministicMockLLM()

    def analyze(
        self,
        message: str,
        current: IntakeData,
        knowledge: KnowledgeBase,
        last_question_fields: list[str],
        field_metadata: dict[str, FieldMetadata] | None = None,
        recent_transcript: list | None = None,
        already_cited_context: list[str] | None = None,
    ) -> LLMIntakeResult:
        self.calls += 1
        base = self._deterministic.analyze(
            message,
            current,
            knowledge,
            last_question_fields,
            field_metadata,
            recent_transcript,
            already_cited_context,
        )
        return base.model_copy(update={
            "assistant_message": "I updated the confirmed source to SAP.",
            "risk_flags": [
                "Data source is not yet defined.",
                "This stale model risk must not survive reconciliation.",
            ],
            "llm_provider": "openai",
            "llm_model": self.model_name,
            "llm_request_id": f"chatcmpl-test-{self.calls}",
            "llm_latency_ms": 12,
        })


class CountingLLM(IntakeLLMClient):
    model_name = "counting-model"

    def __init__(self) -> None:
        self.calls = 0
        self._delegate = DeterministicMockLLM()

    def analyze(
        self,
        message: str,
        current: IntakeData,
        knowledge: KnowledgeBase,
        last_question_fields: list[str],
        field_metadata: dict[str, FieldMetadata] | None = None,
        recent_transcript: list | None = None,
        already_cited_context: list[str] | None = None,
    ) -> LLMIntakeResult:
        self.calls += 1
        return self._delegate.analyze(
            message,
            current,
            knowledge,
            last_question_fields,
            field_metadata,
            recent_transcript,
            already_cited_context,
        )


def test_data_agent_source_removes_stale_missing_risk_and_question() -> None:
    engine = make_engine()
    session_id = "data-agent-reconciliation"
    engine.process_message(session_id, "I need a dashboard.")
    response = engine.process_message(
        session_id,
        "You can use data from the Power BI Data Agent context.",
    )

    assert response.intake.data_sources == "Power BI Data Agent"
    assert "Power BI Data Agent" in response.assistant_message
    assert "data_sources" not in response.missing_fields
    assert all("data source is not yet defined" not in risk.lower() for risk in response.risk_flags)
    assert all(question.field != "data_sources" for question in response.next_questions)


def test_confirmed_field_is_protected_and_reply_describes_actual_state() -> None:
    llm = MisleadingOpenAILLM()
    engine = make_engine(llm)
    session_id = "confirmed-reply-reconciliation"
    engine.process_message(session_id, "Build a dashboard using Salesforce data.")
    engine.update_field(session_id, "data_sources", "Salesforce")

    response = engine.process_message(session_id, "Use SAP instead.")

    assert response.intake.data_sources == "Salesforce"
    assert response.field_metadata["data_sources"].source == "user_confirmed"
    assert "remains the manually confirmed value" in response.assistant_message
    assert "did not change it to “SAP”" in response.assistant_message
    assert "stale model risk" not in " ".join(response.risk_flags).lower()
    assert response.llm_provider == "openai"
    assert response.llm_request_id == "chatcmpl-test-2"


def test_unconfirmed_source_correction_replaces_prior_value() -> None:
    engine = make_engine()
    session_id = "source-correction"
    engine.process_message(session_id, "Build a sales dashboard using Salesforce.")

    response = engine.process_message(
        session_id,
        "Correction: use SAP instead of Salesforce.",
    )

    assert response.intake.data_sources == "SAP"
    assert "Salesforce, SAP" not in response.intake.data_sources
    assert "changed from “Salesforce” to “SAP”" in response.assistant_message


def test_scope_change_updates_deliverable_atomically_and_preserves_source() -> None:
    engine = make_engine()
    session_id = "scope-change"
    engine.process_message(
        session_id,
        "Build a Power BI dashboard for operations managers using Salesforce.",
    )

    response = engine.process_message(
        session_id,
        "Actually, we only need a one-time Excel extract.",
    )

    assert response.intake.request_type == "data extract"
    assert response.intake.display_format == "Excel"
    assert response.intake.run_frequency == "One-time"
    assert response.intake.refresh_frequency is None
    assert response.intake.data_sources == "Salesforce"


def test_scope_change_is_atomically_rejected_when_scope_field_is_confirmed() -> None:
    engine = make_engine()
    session_id = "protected-scope-change"
    engine.process_message(
        session_id,
        (
            "Create a Power BI dashboard for sales managers to track units sold from Salesforce. "
            "Requester is Maya Chen, owner is Jordan Lee. Success is validated by Jordan Lee. "
            "Use daily refresh and no RLS."
        ),
    )
    engine.update_field(session_id, "request_type", "dashboard")

    response = engine.process_message(
        session_id,
        "Actually, we only need a one-time Excel extract.",
    )

    assert response.intake.request_type == "dashboard"
    assert response.intake.display_format == "Power BI dashboard"
    assert response.intake.run_frequency == "Daily"
    assert response.intake.refresh_frequency == "Daily"
    assert "did not apply the scope change" in response.assistant_message
    assert "Request Type is manually confirmed" in response.assistant_message


def test_multi_request_is_stopped_before_llm_or_ticket_generation() -> None:
    llm = CountingLLM()
    engine = make_engine(llm)

    response = engine.process_message(
        "multi-request",
        "Build a sales dashboard from Salesforce, and also fix the incorrect totals in our inventory report.",
    )

    assert llm.calls == 0
    assert response.intake.scenario_type == "Ambiguous Request"
    assert response.intake.request_type is None
    assert response.intake.data_sources is None
    assert response.ticket_bundle_preview is None
    assert "two independent requests" in response.assistant_message.lower()
    assert any("split" in risk.lower() for risk in response.risk_flags)


def test_conflicting_values_remain_unconfirmed_and_block_draft() -> None:
    engine = make_engine()
    response = engine.process_message(
        "conflicts",
        (
            "I need a daily—actually weekly—maybe real-time dashboard/report/Excel file "
            "using Salesforce or SAP."
        ),
    )

    assert response.intake.data_sources is None
    assert response.intake.display_format is None
    assert response.intake.refresh_frequency is None
    assert response.field_metadata["data_sources"].source == "needs_confirmation"
    assert response.field_metadata["data_sources"].confidence == "low"
    assert "data_sources" in response.ambiguous_fields
    assert response.ready_for_ticket is False
    assert response.ticket_bundle_preview is None
    assert {question.field for question in response.next_questions} == {
        "data_sources",
        "display_format",
        "refresh_frequency",
    }


def test_conflict_blocks_complete_intake_until_chat_confirmation() -> None:
    engine = make_engine()
    session_id = "complete-intake-conflict"
    engine.process_message(
        session_id,
        (
            "Create a Power BI dashboard for sales managers to track units sold from Salesforce. "
            "Requester is Maya Chen, owner is Jordan Lee. Success is validated by Jordan Lee. "
            "Use daily refresh and no RLS."
        ),
    )

    conflicted = engine.process_message(session_id, "Use Salesforce or SAP.")
    assert conflicted.completion_score >= 80
    assert conflicted.ready_for_ticket is False
    assert conflicted.ticket_bundle_preview is None
    with pytest.raises(ValueError, match="resolve conflicting"):
        engine.generate_ticket(session_id)

    resolved = engine.process_message(session_id, "Use SAP.")
    assert resolved.intake.data_sources == "SAP"
    assert resolved.ready_for_ticket is True
    assert all("conflicting data source" not in risk.lower() for risk in resolved.risk_flags)
    assert resolved.ticket_bundle_preview is not None


def test_conflict_does_not_downgrade_manually_confirmed_source() -> None:
    engine = make_engine()
    session_id = "confirmed-source-conflict"
    engine.process_message(session_id, "Build a dashboard using Salesforce data.")
    engine.update_field(session_id, "data_sources", "Salesforce")

    response = engine.process_message(session_id, "Use Salesforce or SAP.")

    assert response.intake.data_sources == "Salesforce"
    assert response.field_metadata["data_sources"].source == "user_confirmed"
    assert "remains the manually confirmed value" in response.assistant_message
    assert all("conflicting data source" not in risk.lower() for risk in response.risk_flags)


def test_rls_role_rules_are_structured_and_added_to_ticket_acceptance() -> None:
    engine = make_engine()
    response = engine.process_message(
        "rls-rules",
        (
            "Create a sales dashboard for regional managers and executives to track revenue from Salesforce. "
            "Managers should only see their own region; executives see all regions. "
            "Requester is Maya Chen, maya@example.com; owner is Jordan Lee. "
            "Success means Jordan validates accuracy. Daily refresh. High priority."
        ),
    )

    assert response.intake.row_level_security == (
        "Required: regional managers limited to their assigned region; "
        "executives have all-region access."
    )
    assert response.intake.data_story_by_recipient_role == (
        "regional managers limited to their assigned region; executives have all-region access"
    )
    assert response.intake.recipients_or_access_roles == "Regional managers and Executives"
    assert all(
        "row-level security requirements are not yet defined" not in risk.lower()
        for risk in response.risk_flags
    )
    assert any("rls role/group mappings" in risk.lower() for risk in response.risk_flags)
    assert response.ticket_bundle_preview is not None
    description = response.ticket_bundle_preview.bim_ticket.description
    assert "Regional managers can view only their assigned region." in description
    assert "Executives can view all regions." in description
    assert "Role/group mappings are confirmed before release." in description

    confirmed = engine.update_field(
        "rls-rules",
        "row_level_security",
        response.intake.row_level_security,
    )
    assert all("rls role/group mappings" not in risk.lower() for risk in confirmed.risk_flags)


def test_live_data_questions_use_system_guardrail_without_llm_call() -> None:
    for message in (
        "Exactly how many open BIM tickets are assigned to BI-Reporting today?",
        "Use the Power BI Data Agent to query today's live backlog and identify the busiest assignee.",
    ):
        llm = CountingLLM()
        engine = make_engine(llm)
        response = engine.process_message(f"live-{llm.calls}-{len(message)}", message)

        assert llm.calls == 0
        assert response.mode == "context_answer"
        assert response.llm_provider == "system"
        assert response.intake.request_type is None
        assert response.intake.data_sources is None
        assert response.ticket_bundle_preview is None
        assert "cannot query live Power BI or Armada data" in response.assistant_message


def test_daily_refresh_requirement_is_not_mistaken_for_live_query() -> None:
    llm = CountingLLM()
    engine = make_engine(llm)

    response = engine.process_message(
        "daily-refresh-requirement",
        "Build a Power BI dashboard from Salesforce with a daily refresh.",
    )

    assert llm.calls == 1
    assert response.mode != "context_answer"
    assert response.intake.refresh_frequency == "Daily"


def test_manual_field_updates_remove_all_stale_missing_risks() -> None:
    engine = make_engine()
    session_id = "stale-risk-cleanup"
    response = engine.process_message(session_id, "I need a dashboard.")
    assert any("data source" in risk.lower() for risk in response.risk_flags)

    response = engine.update_field(session_id, "data_sources", "Salesforce")
    assert all("data source is not yet defined" not in risk.lower() for risk in response.risk_flags)
    response = engine.update_field(session_id, "armada_owner", "Jordan Lee")
    assert all("requester or accountable owner" not in risk.lower() for risk in response.risk_flags)
    response = engine.update_field(session_id, "success_definition", "Jordan validates accuracy")
    assert all("success criteria or validation owner" not in risk.lower() for risk in response.risk_flags)
    response = engine.update_field(session_id, "row_level_security", "Not required")
    assert all("row-level security requirements" not in risk.lower() for risk in response.risk_flags)
