import base64

from app.intake_engine import IntakeEngine
from app.knowledge_base import KnowledgeBase
from app.llm_client import DeterministicMockLLM
from app.mock_jira import MockJiraAdapter
from app.ticket_generator import TicketGenerator


def _engine() -> IntakeEngine:
    return IntakeEngine(DeterministicMockLLM(), KnowledgeBase(), TicketGenerator(MockJiraAdapter()))


def test_user_attachment_upload_and_remove() -> None:
    engine = _engine()
    session_id = "attach-test"
    payload = b"sku,units\nA,10\n"
    added = engine.add_user_attachment(
        session_id,
        filename="sample.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content=payload,
    )
    assert len(added.attachments) == 1
    assert added.attachments[0].filename == "sample.xlsx"
    assert added.attachments[0].content == ""
    assert added.attachments[0].source == "user"
    assert added.attachments[0].size_bytes == len(payload)

    state = engine.get_state(session_id)
    assert state.user_attachments[0].content_encoding == "base64"
    assert base64.b64decode(state.user_attachments[0].content) == payload

    removed = engine.remove_user_attachment(session_id, "sample.xlsx")
    assert removed.attachments == []
    assert engine.get_state(session_id).user_attachments == []


def test_user_attachments_included_in_bundle_payload() -> None:
    engine = _engine()
    session_id = "attach-bundle"
    engine.add_user_attachment(
        session_id,
        filename="mockup.png",
        content_type="image/png",
        content=b"\x89PNG\r\n\x1a\n",
    )
    state = engine.get_state(session_id)
    bundle = engine._tickets.build_bundle_payload(
        state.intake,
        state.transcript,
        state.validation_state,
        extra_attachments=state.user_attachments,
    )
    assert any(item.filename == "mockup.png" for item in bundle.ito_ticket.attachments)
    assert any(item.filename == "mockup.png" for item in bundle.bim_ticket.attachments)
