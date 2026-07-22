from types import SimpleNamespace
from unittest.mock import patch

from app.knowledge_base import KnowledgeBase
from app.llm_client import DeterministicMockLLM, OpenAIIntakeLLM
from app.models import IntakeData, LLMModelOutput


def model_output() -> LLMModelOutput:
    return LLMModelOutput(
        assistant_message="Which metrics should the dashboard include?",
        updated_intake=IntakeData(
            request_type="dashboard",
            display_format="Power BI dashboard",
        ),
        missing_fields=["metrics_kpis_charts_maps"],
        completion_score=20,
        ready_for_ticket=False,
        risk_flags=[],
        context_used=[],
        next_questions=["Which metrics should the dashboard include?"],
    )


def test_openai_success_returns_request_provenance() -> None:
    client = OpenAIIntakeLLM("test-key", "gpt-4o-mini", DeterministicMockLLM())
    response = SimpleNamespace(
        id="chatcmpl-test123",
        model="gpt-4o-mini-2024-07-18",
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=model_output(), refusal=None))],
    )

    with patch.object(client._client.beta.chat.completions, "parse", return_value=response):
        result = client.analyze("I need a dashboard", IntakeData(), KnowledgeBase(), [])

    assert result.llm_provider == "openai"
    assert result.llm_request_id == "chatcmpl-test123"
    assert result.llm_model == "gpt-4o-mini-2024-07-18"
    assert result.fallback_reason is None


def test_openai_failure_exposes_fallback_reason() -> None:
    client = OpenAIIntakeLLM("test-key", "gpt-4o-mini", DeterministicMockLLM())

    with patch.object(
        client._client.beta.chat.completions,
        "parse",
        side_effect=RuntimeError("simulated structured-output failure"),
    ):
        result = client.analyze("I need a dashboard", IntakeData(), KnowledgeBase(), [])

    assert result.llm_provider == "deterministic"
    assert result.llm_model == "gpt-4o-mini"
    assert "simulated structured-output failure" in (result.fallback_reason or "")
