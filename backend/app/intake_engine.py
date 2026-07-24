from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from .intake_config import EDITABLE_FIELDS
from .intake_workflow import (
    ambiguous_fields,
    build_requirements_matrix,
    derive_validation_state,
    empty_metadata,
    has_value,
    normalize_metadata,
    utc_now,
    validation_eligibility,
)
from .intake_reconciler import (
    RiskSignal,
    clear_risk_signals_for_field,
    detect_live_data_query,
    detect_multi_request,
    recalculate_risks,
    reconcile_turn,
    risk_signal,
    ticket_readiness,
    validation_blocking_risks,
)
from .knowledge_base import KnowledgeBase
from .llm_client import IntakeLLMClient, score_intake
from .models import (
    AttachmentDraft,
    AttachmentListResponse,
    ClarificationQuestion,
    FieldMetadata,
    IntakeData,
    IntakeMessageResponse,
    JiraTicketBundlePreview,
    LLMStatusResponse,
    TicketGenerationResponse,
    TicketPreview,
    TranscriptMessage,
)
from .ticket_generator import TicketGenerator, redact_bundle_preview


MAX_USER_ATTACHMENTS = 5
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


@dataclass
class SessionState:
    intake: IntakeData = field(default_factory=IntakeData)
    field_metadata: dict[str, FieldMetadata] = field(default_factory=empty_metadata)
    last_question_fields: list[str] = field(default_factory=list)
    transcript: list[TranscriptMessage] = field(default_factory=list)
    cited_context: list[str] = field(default_factory=list)
    ticket_preview: TicketPreview | None = None
    ticket_bundle_preview: JiraTicketBundlePreview | None = None
    user_attachments: list[AttachmentDraft] = field(default_factory=list)
    validation_state: str = "gathering"
    validator_name: str | None = None
    validated_at: str | None = None
    validation_note: str | None = None
    risk_signals: dict[str, RiskSignal] = field(default_factory=dict)


def _safe_filename(name: str) -> str:
    cleaned = PurePosixPath(name.replace("\\", "/")).name.strip()
    cleaned = re.sub(r"[^\w.\- ()+]+", "_", cleaned).strip(" ._")
    return (cleaned or "upload.bin")[:180]


def _unique_filename(desired: str, existing: list[str]) -> str:
    if desired not in existing:
        return desired
    stem, dot, suffix = desired.rpartition(".")
    if not dot:
        stem, suffix = desired, ""
    else:
        suffix = f".{suffix}"
    index = 2
    while True:
        candidate = f"{stem}-{index}{suffix}"
        if candidate not in existing:
            return candidate
        index += 1


class IntakeEngine:
    def __init__(
        self,
        llm_client: IntakeLLMClient,
        knowledge: KnowledgeBase,
        ticket_generator: TicketGenerator,
    ) -> None:
        self._llm = llm_client
        self._knowledge = knowledge
        self._tickets = ticket_generator
        self._sessions: dict[str, SessionState] = {}

    def get_state(self, session_id: str) -> SessionState:
        return self._sessions.setdefault(session_id, SessionState())

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def llm_status(self) -> LLMStatusResponse:
        configured = bool(self._llm.configured)
        provider_name = getattr(self._llm, "provider_name", "deterministic")
        if configured and provider_name in {"openai", "claude"}:
            provider = provider_name  # type: ignore[assignment]
        else:
            provider = "deterministic"
        labels = {
            "openai": "OpenAI is configured. Each response reports provider, model, request ID, and latency.",
            "claude": (
                "Anthropic Claude is configured "
                f"({self._llm.model_name or 'model pending'}). "
                "Each response reports provider, model, request ID, and latency."
            ),
            "deterministic": "No cloud LLM key is active; deterministic fallback mode is in use.",
        }
        return LLMStatusResponse(
            configured=configured and provider != "deterministic",
            provider=provider,  # type: ignore[arg-type]
            model=self._llm.model_name,
            message=labels.get(provider, labels["deterministic"]),
        )

    def process_message(self, session_id: str, message: str) -> IntakeMessageResponse:
        state = self.get_state(session_id)
        state.transcript.append(TranscriptMessage(role="user", content=message, timestamp=utc_now()))
        boundary = self._boundary_response(session_id, message, state)
        if boundary:
            state.transcript.append(TranscriptMessage(
                role="assistant",
                content=boundary.assistant_message,
                timestamp=utc_now(),
            ))
            return boundary

        previous = state.intake.model_copy(deep=True)
        result = self._llm.analyze(
            message=message,
            current=state.intake,
            knowledge=self._knowledge,
            last_question_fields=state.last_question_fields,
            field_metadata=state.field_metadata,
            recent_transcript=state.transcript,
            already_cited_context=state.cited_context,
        )
        reconciled = reconcile_turn(
            message=message,
            previous=previous,
            candidate=result.updated_intake,
            existing_metadata=state.field_metadata,
            model_metadata_updates=result.field_metadata_updates,
            model_questions=result.next_questions,
            risk_signals=state.risk_signals,
        )
        state.intake = reconciled.intake
        state.field_metadata = reconciled.metadata
        state.risk_signals = reconciled.risk_signals
        state.last_question_fields = [question.field for question in reconciled.questions]
        state.validation_state = derive_validation_state(
            state.validation_state,
            reconciled.ready_for_ticket,
        )
        if state.validation_state in {"validated", "rejected"}:
            state.validation_state = "draft_ready" if reconciled.ready_for_ticket else "gathering"
            state.validator_name = None
            state.validated_at = None
            state.validation_note = None

        state.transcript.append(TranscriptMessage(
            role="assistant",
            content=reconciled.assistant_message,
            timestamp=utc_now(),
            questions=reconciled.questions,
        ))
        self._refresh_ticket_drafts(state, reconciled.ready_for_ticket)
        return self._response(
            session_id,
            state,
            assistant_message=reconciled.assistant_message,
            context_used=self._novel_context(state, result.context_used),
            mode="draft_ticket" if reconciled.ready_for_ticket else "clarify",
            provider=result.llm_provider,
            model=result.llm_model,
            request_id=result.llm_request_id,
            latency_ms=result.llm_latency_ms,
            fallback_reason=result.fallback_reason,
            next_questions=reconciled.questions,
        )

    def update_field(
        self,
        session_id: str,
        field_name: str,
        value: Any,
        confirmed: bool = True,
    ) -> IntakeMessageResponse:
        if field_name not in EDITABLE_FIELDS:
            raise ValueError(f"Field is not editable: {field_name}")
        state = self.get_state(session_id)
        value = self._coerce_field_value(field_name, value)
        payload = state.intake.model_dump()
        payload[field_name] = value
        state.intake = IntakeData.model_validate(payload)
        if has_value(value) or (isinstance(value, bool) and value):
            state.field_metadata[field_name] = FieldMetadata(
                confidence="high" if confirmed else "medium",
                source="user_confirmed" if confirmed else "user_provided",
                evidence="Edited in the Requirements Matrix",
                updated_at=utc_now(),
            )
        else:
            state.field_metadata[field_name] = FieldMetadata()
        if field_name == "requester_email" and has_value(value):
            state.intake.requester_email_unavailable = False
        if field_name == "requester_email_unavailable" and value:
            state.intake.requester_email = None
        state.field_metadata = normalize_metadata(state.intake, state.field_metadata)
        state.risk_signals = clear_risk_signals_for_field(
            field_name,
            value,
            confirmed,
            state.risk_signals,
        )
        state.intake.risk_flags = recalculate_risks(
            state.intake,
            state.field_metadata,
            state.risk_signals,
        )
        score, missing, ready = ticket_readiness(state.intake, state.risk_signals)
        state.validation_state = "draft_ready" if ready else "gathering"
        state.validator_name = None
        state.validated_at = None
        state.validation_note = None
        state.intake.missing_fields = missing
        state.intake.confidence_score = score / 100
        self._refresh_ticket_drafts(state, ready)
        return self._response(
            session_id,
            state,
            assistant_message=f"{field_name.replace('_', ' ').title()} was updated and marked {'confirmed' if confirmed else 'provided'}.",
            context_used=[],
            mode="draft_ticket" if ready else "clarify",
            provider="system",
        )

    def submit_for_validation(self, session_id: str, validator_name: str | None, note: str | None) -> IntakeMessageResponse:
        state = self.get_state(session_id)
        score, _, ready = ticket_readiness(state.intake, state.risk_signals)
        ambiguous = ambiguous_fields(state.field_metadata, state.intake)
        eligible, blockers = validation_eligibility(
            state.intake,
            score,
            ready,
            ambiguous,
            state.intake.risk_flags,
            validation_blocking_risks(state.risk_signals),
        )
        if not eligible:
            raise ValueError("Cannot submit for validation: " + " ".join(blockers))
        state.validation_state = "pending_validation"
        state.validator_name = validator_name or state.intake.accuracy_owner_or_validator
        state.validation_note = note
        self._refresh_ticket_drafts(state, ready)
        return self._response(
            session_id,
            state,
            assistant_message="The requirements are pending human validation. This still has not created any real Jira ticket.",
            context_used=[],
            mode="draft_ticket",
            provider="system",
        )

    def validate(self, session_id: str, validator_name: str | None, note: str | None) -> IntakeMessageResponse:
        state = self.get_state(session_id)
        if state.validation_state != "pending_validation":
            raise ValueError("Submit the intake for validation before approving it.")
        state.validation_state = "validated"
        state.validator_name = validator_name or state.validator_name or state.intake.accuracy_owner_or_validator or "Human validator"
        state.validation_note = note or state.validation_note
        state.validated_at = utc_now()
        self._refresh_ticket_drafts(state, True)
        return self._response(
            session_id,
            state,
            assistant_message="The draft requirements were marked validated by a human. No real Jira ticket was created.",
            context_used=[],
            mode="draft_ticket",
            provider="system",
        )

    def reject(self, session_id: str, validator_name: str | None, note: str | None) -> IntakeMessageResponse:
        state = self.get_state(session_id)
        if state.validation_state not in {"pending_validation", "validated"}:
            raise ValueError("Only a pending or validated intake can be rejected for revision.")
        state.validation_state = "rejected"
        state.validator_name = validator_name or state.validator_name
        state.validation_note = note or "Revision requested"
        state.validated_at = utc_now()
        self._refresh_ticket_drafts(
            state,
            ticket_readiness(state.intake, state.risk_signals)[2],
        )
        return self._response(
            session_id,
            state,
            assistant_message="The draft was returned for revision. Confirm or edit the flagged requirements before resubmitting.",
            context_used=[],
            mode="clarify",
            provider="system",
        )

    def generate_ticket(self, session_id: str) -> TicketGenerationResponse:
        state = self.get_state(session_id)
        score, missing, ready = ticket_readiness(state.intake, state.risk_signals)
        state.intake.confidence_score = score / 100
        state.intake.missing_fields = missing
        if not ready:
            minimum_ready = score_intake(state.intake)[2]
            details = (
                "resolve conflicting or combined requests first"
                if minimum_ready
                else ", ".join(missing[:8])
            )
            raise ValueError("Complete the intake before generating a draft: " + details)
        self._refresh_ticket_drafts(state, True, force=True)
        assert state.ticket_preview is not None and state.ticket_bundle_preview is not None
        return TicketGenerationResponse(
            **state.ticket_preview.model_dump(),
            ticket_preview=state.ticket_preview,
            ticket_bundle_preview=state.ticket_bundle_preview,
            pending_attachments=[item.public_view() for item in state.user_attachments],
        )

    def add_user_attachment(
        self,
        session_id: str,
        *,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> AttachmentListResponse:
        state = self.get_state(session_id)
        if len(state.user_attachments) >= MAX_USER_ATTACHMENTS:
            raise ValueError(f"At most {MAX_USER_ATTACHMENTS} optional files can be attached.")
        if len(content) == 0:
            raise ValueError("Empty files cannot be attached.")
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise ValueError(f"Each file must be {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB or smaller.")

        safe_name = _unique_filename(
            _safe_filename(filename),
            [item.filename for item in state.user_attachments],
        )
        state.user_attachments.append(AttachmentDraft(
            filename=safe_name,
            content_type=(content_type or "application/octet-stream").strip() or "application/octet-stream",
            content=base64.b64encode(content).decode("ascii"),
            included=True,
            uploaded=False,
            content_encoding="base64",
            size_bytes=len(content),
            source="user",
        ))
        if state.ticket_bundle_preview is not None:
            self._refresh_ticket_drafts(state, True, force=False)
        return self._attachment_response(session_id, state)

    def remove_user_attachment(self, session_id: str, filename: str) -> AttachmentListResponse:
        state = self.get_state(session_id)
        before = len(state.user_attachments)
        state.user_attachments = [
            item for item in state.user_attachments if item.filename != filename
        ]
        if len(state.user_attachments) == before:
            raise ValueError(f"No pending attachment named {filename!r}.")
        if state.ticket_bundle_preview is not None:
            self._refresh_ticket_drafts(state, True, force=False)
        return self._attachment_response(session_id, state)

    def _attachment_response(self, session_id: str, state: SessionState) -> AttachmentListResponse:
        return AttachmentListResponse(
            session_id=session_id,
            attachments=[item.public_view() for item in state.user_attachments],
            ticket_preview=state.ticket_preview,
            ticket_bundle_preview=state.ticket_bundle_preview,
        )

    def _refresh_ticket_drafts(self, state: SessionState, ready: bool, force: bool = False) -> None:
        if not ready:
            state.ticket_preview = None
            state.ticket_bundle_preview = None
            return
        extras = list(state.user_attachments)
        if force:
            # Explicit generate-ticket action: may create real Jira issues.
            state.ticket_bundle_preview = self._tickets.generate_bundle(
                state.intake,
                state.transcript,
                state.validation_state,
                extra_attachments=extras,
            )
        elif state.ticket_bundle_preview is None:
            # Chat/auto-preview must stay local. Never write to Jira mid-conversation.
            from .mock_jira import MockJiraAdapter
            from .ticket_generator import TicketGenerator

            previewer = TicketGenerator(MockJiraAdapter())
            state.ticket_bundle_preview = previewer.generate_bundle(
                state.intake,
                state.transcript,
                state.validation_state,
                extra_attachments=extras,
            )
        else:
            # Rebuild content after field edits while keeping stable draft keys.
            payload = self._tickets.build_bundle_payload(
                state.intake,
                state.transcript,
                state.validation_state,
                extra_attachments=extras,
            )
            public_ito = {
                **payload.ito_ticket.model_dump(),
                "attachments": [item.public_view() for item in payload.ito_ticket.attachments],
            }
            public_bim = {
                **payload.bim_ticket.model_dump(),
                "attachments": [item.public_view() for item in payload.bim_ticket.attachments],
            }
            state.ticket_bundle_preview = state.ticket_bundle_preview.model_copy(update={
                "ito_ticket": state.ticket_bundle_preview.ito_ticket.model_copy(update=public_ito),
                "bim_ticket": state.ticket_bundle_preview.bim_ticket.model_copy(update=public_bim),
                "proposed_relationship": payload.proposed_relationship,
                "validation_state": state.validation_state,
            })
            state.ticket_bundle_preview = redact_bundle_preview(state.ticket_bundle_preview)
        state.ticket_preview = self._tickets.legacy_preview_from_bundle(state.intake, state.ticket_bundle_preview)

    def _response(
        self,
        session_id: str,
        state: SessionState,
        *,
        assistant_message: str,
        context_used: list[str],
        mode: str,
        provider: str,
        model: str | None = None,
        request_id: str | None = None,
        latency_ms: int | None = None,
        fallback_reason: str | None = None,
        next_questions: list | None = None,
    ) -> IntakeMessageResponse:
        score, missing, ready = ticket_readiness(state.intake, state.risk_signals)
        state.intake.missing_fields = missing
        state.intake.confidence_score = score / 100
        ambiguous = ambiguous_fields(state.field_metadata, state.intake)
        validation_ready, validation_blockers = validation_eligibility(
            state.intake,
            score,
            ready,
            ambiguous,
            state.intake.risk_flags,
            validation_blocking_risks(state.risk_signals),
        )
        # Blockers are available as risk-style UI guidance without mutating the
        # canonical AI risk list or claiming they came from OpenAI.
        validation_note = state.validation_note
        if not validation_ready and not validation_note:
            validation_note = " ".join(validation_blockers)
        return IntakeMessageResponse(
            session_id=session_id,
            assistant_message=assistant_message,
            intake=state.intake,
            missing_fields=missing,
            completion_score=score,
            ready_for_ticket=ready,
            ticket_preview=state.ticket_preview,
            ticket_bundle_preview=state.ticket_bundle_preview,
            pending_attachments=[item.public_view() for item in state.user_attachments],
            field_metadata=state.field_metadata,
            ambiguous_fields=ambiguous,
            next_questions=next_questions or [],
            requirements_matrix=build_requirements_matrix(state.intake, state.field_metadata),
            validation_ready=validation_ready,
            validation_state=state.validation_state,
            validator_name=state.validator_name,
            validated_at=state.validated_at,
            validation_note=validation_note,
            risk_flags=state.intake.risk_flags,
            context_used=context_used,
            mode=mode,
            llm_provider=provider,
            llm_model=model,
            llm_request_id=request_id,
            llm_latency_ms=latency_ms,
            fallback_reason=fallback_reason,
        )

    def _boundary_response(
        self,
        session_id: str,
        message: str,
        state: SessionState,
    ) -> IntakeMessageResponse | None:
        lower = message.lower()
        if detect_live_data_query(message):
            risk = "Live-data access is unavailable; this prototype uses static context only."
            state.risk_signals["live_data_boundary"] = risk_signal(
                "live_data_boundary",
                risk,
                evidence=message,
            )
            state.intake.risk_flags = recalculate_risks(
                state.intake,
                state.field_metadata,
                state.risk_signals,
            )
            return self._response(
                session_id,
                state,
                assistant_message=(
                    "I cannot query live Power BI or Armada data. I only have static context descriptions. "
                    "I can help turn this question into a BI intake request, but I did not query or change "
                    "any enterprise system."
                ),
                context_used=["Static context only; no live enterprise connection."],
                mode="context_answer",
                provider="system",
                model=self._llm.model_name,
            )

        external_action = re.search(
            r"\b(connect|access|create|submit|send|write|push|log in|login)\b.{0,70}\b(real|live|armada|internal)\b.{0,50}\b(jira|power bi|fabric|azure|copilot)",
            lower,
        ) or re.search(
            r"\b(real|live|armada|internal)\b.{0,50}\b(jira|power bi|fabric|azure|copilot)\b",
            lower,
        )
        if external_action:
            state.risk_signals["external_system_boundary"] = risk_signal(
                "external_system_boundary",
                "External actions are blocked in chat; Jira creation requires the explicit ticket action.",
                evidence=message,
            )
            state.intake.risk_flags = recalculate_risks(
                state.intake,
                state.field_metadata,
                state.risk_signals,
            )
            return self._response(
                session_id,
                state,
                assistant_message=(
                    "This chat cannot connect to or write to external systems directly. I can structure "
                    "the request and prepare local ITO/BIM drafts; if Real Jira is enabled, a user must "
                    "select the explicit Create in Jira action after the intake is complete. I did not "
                    "query or change Jira, Power BI, Fabric, Azure, or Copilot Studio in this chat turn."
                ),
                context_used=self._novel_context(
                    state,
                    ["Static context only; no live enterprise connection."],
                ),
                mode="context_answer",
                provider="system",
                model=self._llm.model_name,
            )

        separate_requests = detect_multi_request(message)
        if separate_requests:
            state.intake.scenario_type = "Ambiguous Request"
            state.field_metadata["scenario_type"] = FieldMetadata(
                confidence="low",
                source="needs_confirmation",
                evidence=" ".join(message.split())[:280],
                updated_at=utc_now(),
            )
            state.risk_signals["multi_request"] = risk_signal(
                "multi_request",
                "Multiple independent requests were detected; split them before drafting.",
                evidence=message,
                related_fields=("request_type", "scenario_type"),
                blocking_validation=True,
                blocking_draft=True,
            )
            state.intake.risk_flags = recalculate_risks(
                state.intake,
                state.field_metadata,
                state.risk_signals,
            )
            state.validation_state = "gathering"
            state.ticket_preview = None
            state.ticket_bundle_preview = None
            summaries = "\n".join(
                f"{index}. {summary}" for index, summary in enumerate(separate_requests, start=1)
            )
            question = ClarificationQuestion(
                field="request_type",
                question="Please create separate intake sessions for these requests; which one will you submit first?",
                rationale="Independent delivery and defect work should not be merged into one Jira draft.",
                suggested_replies=["Start with the new BI deliverable", "Start with the existing report issue"],
                priority=1,
            )
            state.last_question_fields = ["request_type"]
            return self._response(
                session_id,
                state,
                assistant_message=(
                    "I detected two independent requests and did not merge them into one intake:\n"
                    f"{summaries}\nPlease use New intake to submit each request separately; no draft was generated."
                ),
                context_used=[],
                mode="clarify",
                provider="system",
                model=self._llm.model_name,
                next_questions=[question],
            )

        if re.search(r"\b(what|which)\b.{0,30}\b(table|semantic model|context)\b", lower):
            return self._response(
                session_id,
                state,
                assistant_message=(
                    "The static context includes E1_Tickets for historical ticket detail, OpenTickets for active "
                    "backlog and aging, E2_Linked Tickets for BIM → SCP/ITO traceability, and E3_Change Log for "
                    "status or assignment history. These are descriptions only—not a live Power BI connection."
                ),
                context_used=self._novel_context(
                    state,
                    ["Static semantic model table descriptions."],
                ),
                mode="context_answer",
                provider="system",
                model=self._llm.model_name,
            )
        return None

    @staticmethod
    def _novel_context(state: SessionState, candidates: list[str]) -> list[str]:
        """Return only citations not already shown in this session, then record them."""
        seen = {item.casefold() for item in state.cited_context}
        novel: list[str] = []
        for item in candidates:
            text = " ".join(item.split())
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            novel.append(text)
        state.cited_context.extend(novel)
        return novel

    @staticmethod
    def _coerce_field_value(field_name: str, value: Any) -> Any:
        if field_name in {"requester_email_unavailable", "include_chat_attachment"}:
            if isinstance(value, str):
                return value.strip().lower() in {"true", "1", "yes", "on"}
            return bool(value)
        if field_name == "jira_labels":
            if value is None:
                return []
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            return [part.strip() for part in re.split(r"[,;]", str(value)) if part.strip()]
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None
