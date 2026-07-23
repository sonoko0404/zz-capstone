from __future__ import annotations

from app.intake_engine import IntakeEngine
from app.knowledge_base import KnowledgeBase
from app.llm_client import DeterministicMockLLM, IntakeLLMClient
from app.mock_jira import MockJiraAdapter
from app.models import (
    ClarificationQuestion,
    FieldMetadata,
    IntakeData,
    LLMIntakeResult,
)
from app.ticket_generator import TicketGenerator


def make_engine(llm: IntakeLLMClient | None = None) -> IntakeEngine:
    return IntakeEngine(
        llm or DeterministicMockLLM(),
        KnowledgeBase(),
        TicketGenerator(MockJiraAdapter()),
    )


class GenericQuestionLLM(IntakeLLMClient):
    configured = True
    model_name = "scripted-openai"

    def __init__(self) -> None:
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
        result = self._delegate.analyze(
            message,
            current,
            knowledge,
            last_question_fields,
            field_metadata,
            recent_transcript,
            already_cited_context,
        )
        generic = [
            ClarificationQuestion(
                field="metrics_kpis_charts_maps",
                question="Which dashboard KPIs are required?",
                rationale="Generic model question.",
                suggested_replies=["Revenue"],
                priority=1,
            ),
            ClarificationQuestion(
                field="display_format",
                question="Which dashboard format is required?",
                rationale="Generic model question.",
                suggested_replies=["Power BI"],
                priority=2,
            ),
            ClarificationQuestion(
                field="refresh_frequency",
                question="How often should the dashboard refresh?",
                rationale="Generic model question.",
                suggested_replies=["Daily"],
                priority=3,
            ),
        ]
        return result.model_copy(update={
            "assistant_message": "Please answer three generic dashboard questions.",
            "next_questions": generic,
            "llm_provider": "openai",
            "llm_model": self.model_name,
            "llm_request_id": "chatcmpl-p1-scripted",
            "llm_latency_ms": 9,
        })


def test_tc001_ready_state_has_no_optional_chat_questions() -> None:
    response = make_engine().process_message(
        "p1-ready",
        (
            "Create a Power BI dashboard for sales managers to track units sold and revenue from Salesforce. "
            "Requester is Maya Chen, maya@example.com; owner is Jordan Lee. Daily refresh, no RLS, "
            "high priority, needed within two weeks. Success means Jordan validates accuracy and "
            "managers save two hours per week."
        ),
    )

    assert response.ready_for_ticket is True
    assert response.next_questions == []
    assert response.ticket_bundle_preview is not None
    assert "scope_criteria" in response.missing_fields
    assert "please clarify" not in response.assistant_message.lower()


def test_metric_noun_phrase_and_adjacent_owner_validator_are_extracted() -> None:
    response = make_engine().process_message(
        "p1-metric-noun-phrase",
        (
            "Create a Power BI dashboard using Salesforce units sold and revenue metrics. "
            "Owned by Jordan Lee and Finance validates totals."
        ),
    )

    assert response.intake.data_sources == "Salesforce"
    assert response.intake.metrics_kpis_charts_maps == "units sold and revenue"
    assert response.intake.required_fields == "units sold and revenue"
    assert response.intake.armada_owner == "Jordan Lee"
    assert response.intake.accuracy_owner_or_validator == "Finance"


def test_tc007_validator_and_cadence_conflict_allow_draft_but_block_validation() -> None:
    response = make_engine().process_message(
        "p1-cadence-conflict",
        (
            "Create a Power BI dashboard for finance leaders to track monthly margin from SAP. "
            "Requester is Alex Kim; alex@example.com. Finance validates totals. "
            "We require daily refresh, but the source data updates monthly. No RLS. High priority."
        ),
    )

    assert response.intake.accuracy_owner_or_validator == "Finance"
    assert response.intake.refresh_frequency == "Daily"
    assert response.intake.known_constraints == "Source update cadence is monthly."
    assert response.ready_for_ticket is True
    assert response.ticket_bundle_preview is not None
    assert response.next_questions == []
    assert response.validation_ready is False
    assert any("conflicts with a source" in risk.lower() for risk in response.risk_flags)


def test_tc008_metric_validator_and_dirty_data_are_structured() -> None:
    response = make_engine().process_message(
        "p1-dirty-data",
        (
            "Analyze BIM resolution time for BI-Reporting managers using E1_Tickets and E3_Change Log. "
            "Requester is Sam Ortiz; sam@example.com. The project labels are inconsistent and duplicate "
            "ticket records may exist. BI lead validates results. No RLS. Medium priority."
        ),
    )

    assert response.intake.request_type == "metric analysis"
    assert response.intake.metrics_kpis_charts_maps == "BIM resolution time"
    assert response.intake.accuracy_owner_or_validator == "BI lead"
    assert response.ready_for_ticket is True
    assert response.ticket_bundle_preview is not None
    assert response.validation_ready is False
    assert any("dirty or inconsistent" in risk.lower() for risk in response.risk_flags)


def test_concrete_scenarios_persist_and_choose_specific_questions() -> None:
    engine = make_engine()
    issue = engine.process_message(
        "p1-existing-issue",
        (
            "The weekly operations dashboard totals are wrong after the last refresh. "
            "Regional managers are seeing different numbers."
        ),
    )
    assert issue.intake.scenario_type == "Existing Report Issue"
    assert all(question.field not in {"metrics_kpis_charts_maps", "display_format"} for question in issue.next_questions)

    follow_up = engine.process_message("p1-existing-issue", "Salesforce.")
    assert follow_up.intake.scenario_type == "Existing Report Issue"

    enhancement = make_engine().process_message(
        "p1-enhancement",
        "Add a region filter and customer drilldown to our existing weekly operations dashboard.",
    )
    assert enhancement.intake.scenario_type == "Enhancement Request"
    assert all(question.field != "metrics_kpis_charts_maps" for question in enhancement.next_questions)


def test_tc019_self_service_overrides_generic_llm_questions_and_generates_bundle() -> None:
    engine = make_engine(GenericQuestionLLM())
    first = engine.process_message(
        "p1-self-service",
        "I need access to the Power BI semantic model so I can build my own report.",
    )

    assert first.intake.scenario_type == "Self-Service Access"
    assert first.llm_provider == "openai"
    assert {question.field for question in first.next_questions} == {
        "recipients_or_access_roles",
        "scope_criteria",
        "armada_owner",
    }
    assert all(
        question.field not in {
            "metrics_kpis_charts_maps",
            "display_format",
            "refresh_frequency",
        }
        for question in first.next_questions
    )
    assert {
        node.key: node.status for node in first.requirements_matrix
    }["display_format"] == "N/A"

    complete = engine.process_message(
        "p1-self-service",
        (
            "Regional analysts need ongoing access. Data scope is Northeast sales data. "
            "Approval owner is Dana Lee."
        ),
    )
    assert complete.ready_for_ticket is True
    assert complete.next_questions == []
    assert complete.ticket_preview is not None
    assert complete.ticket_preview.display_format == "Not applicable — self-service access"
    assert complete.ticket_preview.refresh_frequency == "Not applicable — self-service access"
    assert complete.ticket_bundle_preview is not None
    assert "SELF-SERVICE ACCESS REQUEST" in complete.ticket_bundle_preview.ito_ticket.description
    assert "BI ENABLEMENT AND SECURITY REVIEW" in complete.ticket_bundle_preview.bim_ticket.description
    assert "No permission is granted by this prototype" in "\n".join(
        complete.ticket_preview.acceptance_criteria
    )


def test_tc026_requested_and_source_cadence_are_kept_separate_and_resolvable() -> None:
    engine = make_engine()
    first = engine.process_message(
        "p1-source-cadence",
        "We need an hourly operations dashboard, but I do not know how often the source system updates.",
    )

    assert first.intake.refresh_frequency == "Hourly"
    assert "unknown" in (first.intake.known_constraints or "").lower()
    assert any("feasibility is unknown" in risk.lower() for risk in first.risk_flags)
    assert first.next_questions[0].field == "known_constraints"

    confirmed = engine.process_message(
        "p1-source-cadence",
        "The source supports daily updates.",
    )
    assert "daily" in (confirmed.intake.known_constraints or "").lower()
    assert all("feasibility is unknown" not in risk.lower() for risk in confirmed.risk_flags)
    assert any("conflicts with a source" in risk.lower() for risk in confirmed.risk_flags)

    aligned = engine.process_message("p1-source-cadence", "Refresh daily.")
    assert aligned.intake.refresh_frequency == "Daily"
    assert all("conflicts with a source" not in risk.lower() for risk in aligned.risk_flags)


def test_tc027_complexity_deadline_and_generic_sources_are_safe_and_mitigatable() -> None:
    engine = make_engine()
    response = engine.process_message(
        "p1-complexity",
        (
            "Build an enterprise Power BI dashboard with 30 KPIs, five source systems, "
            "custom calculations, and RLS for 12 roles by tomorrow."
        ),
    )

    assert response.intake.data_sources is None
    assert "ERP" not in (response.intake.data_sources or "")
    assert response.intake.metrics_kpis_charts_maps == "30 KPIs (definitions pending)"
    assert "Five source systems" in (response.intake.known_constraints or "")
    assert response.intake.custom_calculations_needed == "Required; definitions pending"
    assert "12 roles" in (response.intake.row_level_security or "")
    assert response.intake.deadline == "by tomorrow"
    assert any("high request complexity" in risk.lower() for risk in response.risk_flags)
    assert any("deadline is not credible" in risk.lower() for risk in response.risk_flags)
    assert response.next_questions[0].field == "scope_criteria"

    mitigated = engine.process_message(
        "p1-complexity",
        "Use an MVP with five KPIs and phased delivery over six weeks.",
    )
    assert "MVP" in (mitigated.intake.scope_criteria or "")
    assert all("high request complexity" not in risk.lower() for risk in mitigated.risk_flags)
    assert all("deadline is not credible" not in risk.lower() for risk in mitigated.risk_flags)


def test_tc033_open_tickets_quality_warnings_are_structured() -> None:
    engine = make_engine()
    response = engine.process_message(
        "p1-open-tickets-quality",
        (
            "Analyze active BIM backlog, but our sample has tickets marked Resolved in OpenTickets "
            "and some assigned groups are blank."
        ),
    )

    assert response.intake.data_sources == "OpenTickets"
    assert response.intake.metrics_kpis_charts_maps == "active BIM backlog"
    assert "Resolved versus active/open" in (response.intake.data_or_system_challenges or "")
    assert any("active-ticket definition" in risk.lower() for risk in response.risk_flags)
    assert any("must not be assumed to mean unassigned" in risk.lower() for risk in response.risk_flags)
    assert response.next_questions[0].field == "data_or_system_challenges"

    resolved = engine.process_message(
        "p1-open-tickets-quality",
        "The active-ticket definition is confirmed and the assigned-group treatment is resolved.",
    )
    assert all("active-ticket definition" not in risk.lower() for risk in resolved.risk_flags)
    assert all("must not be assumed to mean unassigned" not in risk.lower() for risk in resolved.risk_flags)
