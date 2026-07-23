from __future__ import annotations

import re
from dataclasses import dataclass, field
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
from .knowledge_base import KnowledgeBase
from .llm_client import IntakeLLMClient, score_intake
from .models import (
    FieldMetadata,
    IntakeData,
    IntakeMessageResponse,
    JiraTicketBundlePreview,
    LLMStatusResponse,
    TicketGenerationResponse,
    TicketPreview,
    TranscriptMessage,
)
from .ticket_generator import TicketGenerator


@dataclass
class SessionState:
    intake: IntakeData = field(default_factory=IntakeData)
    field_metadata: dict[str, FieldMetadata] = field(default_factory=empty_metadata)
    last_question_fields: list[str] = field(default_factory=list)
    transcript: list[TranscriptMessage] = field(default_factory=list)
    cited_context: list[str] = field(default_factory=list)
    ticket_preview: TicketPreview | None = None
    ticket_bundle_preview: JiraTicketBundlePreview | None = None
    validation_state: str = "gathering"
    validator_name: str | None = None
    validated_at: str | None = None
    validation_note: str | None = None


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
        provider = "openai" if configured else "deterministic"
        return LLMStatusResponse(
            configured=configured,
            provider=provider,
            model=self._llm.model_name,
            message=(
                "OpenAI is configured. Each response reports provider, model, request ID, and latency."
                if configured
                else "No OpenAI key is active; deterministic fallback mode is in use."
            ),
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
        updated = result.updated_intake.model_copy(deep=True)

        # A model may not silently replace manually confirmed values. Explicit
        # corrections are applied through PATCH /api/intake/field.
        for field_name, metadata in state.field_metadata.items():
            if metadata.source == "user_confirmed" and field_name in EDITABLE_FIELDS:
                setattr(updated, field_name, getattr(previous, field_name))

        metadata = dict(state.field_metadata)
        for change in result.field_metadata_updates:
            field_name = change.field
            if field_name not in EDITABLE_FIELDS:
                continue
            if metadata.get(field_name, FieldMetadata()).source == "user_confirmed":
                continue
            metadata[field_name] = FieldMetadata(
                **change.model_dump(exclude={"field", "updated_at"}),
                updated_at=change.updated_at or utc_now(),
            )
        state.intake = updated
        state.field_metadata = normalize_metadata(updated, metadata)
        state.last_question_fields = [question.field for question in result.next_questions]
        state.validation_state = derive_validation_state(state.validation_state, result.ready_for_ticket)
        if state.validation_state in {"validated", "rejected"}:
            state.validation_state = "draft_ready" if result.ready_for_ticket else "gathering"
            state.validator_name = None
            state.validated_at = None
            state.validation_note = None

        state.transcript.append(TranscriptMessage(
            role="assistant",
            content=result.assistant_message,
            timestamp=utc_now(),
            questions=result.next_questions,
        ))
        self._refresh_ticket_drafts(state, result.ready_for_ticket)
        return self._response(
            session_id,
            state,
            assistant_message=result.assistant_message,
            context_used=self._novel_context(state, result.context_used),
            mode="draft_ticket" if result.ready_for_ticket else "clarify",
            provider=result.llm_provider,
            model=result.llm_model,
            request_id=result.llm_request_id,
            latency_ms=result.llm_latency_ms,
            fallback_reason=result.fallback_reason,
            next_questions=result.next_questions,
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
        state.validation_state = "draft_ready" if score_intake(state.intake)[2] else "gathering"
        state.validator_name = None
        state.validated_at = None
        state.validation_note = None
        score, missing, ready = score_intake(state.intake)
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
        score, _, ready = score_intake(state.intake)
        ambiguous = ambiguous_fields(state.field_metadata, state.intake)
        eligible, blockers = validation_eligibility(state.intake, score, ready, ambiguous, state.intake.risk_flags)
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
        self._refresh_ticket_drafts(state, score_intake(state.intake)[2])
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
        score, missing, ready = score_intake(state.intake)
        state.intake.confidence_score = score / 100
        state.intake.missing_fields = missing
        if not ready:
            raise ValueError("Complete the minimum intake fields before generating a draft: " + ", ".join(missing[:8]))
        self._refresh_ticket_drafts(state, True, force=True)
        assert state.ticket_preview is not None and state.ticket_bundle_preview is not None
        return TicketGenerationResponse(
            **state.ticket_preview.model_dump(),
            ticket_preview=state.ticket_preview,
            ticket_bundle_preview=state.ticket_bundle_preview,
        )

    def _refresh_ticket_drafts(self, state: SessionState, ready: bool, force: bool = False) -> None:
        if not ready:
            state.ticket_preview = None
            state.ticket_bundle_preview = None
            return
        if force or state.ticket_bundle_preview is None:
            state.ticket_bundle_preview = self._tickets.generate_bundle(
                state.intake,
                state.transcript,
                state.validation_state,
            )
        else:
            # Rebuild content after field edits while keeping stable mock keys.
            payload = self._tickets.build_bundle_payload(state.intake, state.transcript, state.validation_state)
            state.ticket_bundle_preview = state.ticket_bundle_preview.model_copy(update={
                "ito_ticket": state.ticket_bundle_preview.ito_ticket.model_copy(update=payload.ito_ticket.model_dump()),
                "bim_ticket": state.ticket_bundle_preview.bim_ticket.model_copy(update=payload.bim_ticket.model_dump()),
                "proposed_relationship": payload.proposed_relationship,
                "validation_state": state.validation_state,
            })
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
        score, missing, ready = score_intake(state.intake)
        state.intake.missing_fields = missing
        state.intake.confidence_score = score / 100
        ambiguous = ambiguous_fields(state.field_metadata, state.intake)
        validation_ready, validation_blockers = validation_eligibility(
            state.intake,
            score,
            ready,
            ambiguous,
            state.intake.risk_flags,
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
        external_action = re.search(
            r"\b(connect|access|create|submit|send|write|push|log in|login)\b.{0,70}\b(real|live|armada|internal)\b.{0,50}\b(jira|power bi|fabric|azure|copilot)",
            lower,
        ) or re.search(
            r"\b(real|live|armada|internal)\b.{0,50}\b(jira|power bi|fabric|azure|copilot)\b",
            lower,
        )
        if external_action:
            risk = "External enterprise system access is blocked in this standalone prototype."
            state.intake.risk_flags = list(dict.fromkeys(state.intake.risk_flags + [risk]))
            return self._response(
                session_id,
                state,
                assistant_message=(
                    "This standalone prototype cannot connect to or write to real Armada Jira, Power BI, "
                    "Fabric, Azure, or Copilot Studio. I can structure the request and prepare local ITO/BIM "
                    "drafts only; no external action will be taken."
                ),
                context_used=self._novel_context(
                    state,
                    ["Static context only; no live enterprise connection."],
                ),
                mode="context_answer",
                provider="system",
                model=self._llm.model_name,
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
