import pytest

from app.intake_engine import IntakeEngine
from app.knowledge_base import KnowledgeBase
from app.llm_client import DeterministicMockLLM
from app.mock_jira import MockJiraAdapter
from app.stress_tests import run_stress_test
from app.ticket_generator import TicketGenerator


def make_engine() -> IntakeEngine:
    return IntakeEngine(
        DeterministicMockLLM(),
        KnowledgeBase(),
        TicketGenerator(MockJiraAdapter()),
    )


def test_security_scenario_blocks_external_action() -> None:
    result = run_stress_test(make_engine(), "security-boundary")

    assert result.ticket_preview is None
    assert any("blocked" in risk.lower() for risk in result.risk_flags)
    assert "cannot connect" in result.transcript[-1].content.lower()


def test_conflict_scenario_flags_refresh_mismatch() -> None:
    result = run_stress_test(make_engine(), "conflicting-refresh")

    assert any("conflicts" in risk.lower() for risk in result.risk_flags)


@pytest.mark.parametrize(
    "scenario_id",
    [
        "happy-path",
        "vague-request",
        "missing-data-source",
        "conflicting-refresh",
        "dirty-data",
        "human-fatigue",
        "security-boundary",
    ],
)
def test_every_demo_scenario_returns_evidence(scenario_id: str) -> None:
    result = run_stress_test(make_engine(), scenario_id)

    assert result.transcript
    assert result.findings
    assert result.final_intake is not None
