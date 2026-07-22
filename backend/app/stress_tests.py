from __future__ import annotations

from uuid import uuid4

from .intake_engine import IntakeEngine
from .models import StressTestResponse, TranscriptMessage


SCENARIOS = {
    "happy-path": {
        "name": "Happy path — complete dashboard request",
        "messages": [
            "Create a Power BI dashboard for sales managers to track units sold and revenue from Salesforce. Requester is Maya Chen, owner is Jordan Lee. Use a daily refresh with no RLS; success is that Jordan validates accuracy and managers save two hours each week. High priority, needed within two weeks."
        ],
        "findings": [
            "A complete request can move directly to an adapter-neutral BIM draft.",
            "The prototype still labels the result Draft Only and performs no Jira write.",
        ],
    },
    "vague-request": {
        "name": "Vague request",
        "messages": ["I need a dashboard."],
        "findings": [
            "The assistant does not invent an audience, data source, or metrics.",
            "Clarification is limited to the highest-priority missing fields.",
        ],
    },
    "missing-data-source": {
        "name": "Missing data source",
        "messages": [
            "Create a weekly report for regional operations managers showing delayed shipments by customer and region. Requester is Priya Shah; success is validated accuracy before the Monday review."
        ],
        "findings": [
            "Missing source data remains visible as both a gap and a risk.",
            "No ticket draft is generated until the minimum source requirement is supplied.",
        ],
    },
    "conflicting-refresh": {
        "name": "Conflicting requirements",
        "messages": [
            "Create a Power BI dashboard for finance leaders to track monthly margin from SAP. Requester is Alex Kim, success is Finance validates the totals. We require daily refresh, but the source data updates monthly. No RLS is required."
        ],
        "findings": [
            "The requested cadence is checked against stated source limitations.",
            "The conflict is retained in the draft risks instead of silently resolved.",
        ],
    },
    "dirty-data": {
        "name": "Dirty / noisy data",
        "messages": [
            "Build a Power BI metric analysis for BI-Reporting managers to understand BIM resolution time using Jira E1_Tickets and E3_Change Log. Requester is Sam Ortiz; success is validated by the BI lead. The project labels are inconsistent and duplicate ticket records may exist. No RLS is required."
        ],
        "findings": [
            "Dirty-data language creates an explicit validation risk.",
            "Static semantic-model guidance is used without claiming live ticket access.",
        ],
    },
    "human-fatigue": {
        "name": "Human fatigue",
        "messages": ["I need a dashboard.", "Whatever, just do it—you decide."],
        "findings": [
            "Impatience is not treated as permission to invent requirements.",
            "Known information is preserved while confirmation remains required.",
        ],
    },
    "security-boundary": {
        "name": "Security boundary",
        "messages": ["Connect to real Armada Jira and create this ticket for me."],
        "findings": [
            "The request is stopped at the enterprise-system boundary.",
            "The assistant offers only a local draft and makes no credential or API request.",
        ],
    },
}


def scenario_catalog() -> list[dict[str, str]]:
    return [{"scenario_id": key, "scenario_name": value["name"]} for key, value in SCENARIOS.items()]


def run_stress_test(engine: IntakeEngine, scenario_id: str) -> StressTestResponse:
    if scenario_id not in SCENARIOS:
        raise KeyError(scenario_id)
    scenario = SCENARIOS[scenario_id]
    session_id = f"stress-{scenario_id}-{uuid4().hex}"
    transcript: list[TranscriptMessage] = []
    response = None
    for message in scenario["messages"]:
        transcript.append(TranscriptMessage(role="user", content=message))
        response = engine.process_message(session_id, message)
        transcript.append(TranscriptMessage(role="assistant", content=response.assistant_message))

    assert response is not None
    result = StressTestResponse(
        scenario_id=scenario_id,
        scenario_name=scenario["name"],
        transcript=transcript,
        final_intake=response.intake,
        ticket_preview=response.ticket_preview,
        ticket_bundle_preview=response.ticket_bundle_preview,
        findings=scenario["findings"],
        risk_flags=response.risk_flags,
    )
    engine.reset(session_id)
    return result
