from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IntakeData(BaseModel):
    """The canonical PRD-shaped state collected during an intake session."""

    model_config = ConfigDict(extra="ignore")

    report_title: str | None = None
    report_name: str | None = None
    request_type: str | None = None
    scenario_type: str | None = None
    why_report_necessary: str | None = None
    decisions_supported: str | None = None
    problems_addressed: str | None = None
    why_requested_now: str | None = None
    related_customers_or_teams: str | None = None
    requester: str | None = None
    requester_email: str | None = None
    requester_email_unavailable: bool = False
    armada_owner: str | None = None
    recipients_or_access_roles: str | None = None
    data_story_by_recipient_role: str | None = None
    run_frequency: str | None = None
    run_time_of_day: str | None = None
    scope_criteria: str | None = None
    existing_report_to_mimic: str | None = None
    filters_needed: str | None = None
    drilldowns_needed: str | None = None
    required_fields: str | None = None
    mockup_or_sample_available: str | None = None
    custom_calculations_needed: str | None = None
    display_format: str | None = None
    row_level_security: str | None = None
    metrics_kpis_charts_maps: str | None = None
    refresh_frequency: str | None = None
    accuracy_owner_or_validator: str | None = None
    success_definition: str | None = None
    expected_metric_change_or_time_savings: str | None = None
    data_or_system_challenges: str | None = None
    assumptions_about_data_entry: str | None = None
    dependencies: str | None = None
    known_constraints: str | None = None
    priority: str | None = None
    deadline: str | None = None
    data_sources: str | None = None
    affected_business_unit: str | None = None
    project_type_hint: str | None = None
    linked_ticket_hint: str | None = None
    jira_issue_type: str | None = None
    jira_labels: list[str] = Field(default_factory=list)
    include_chat_attachment: bool = False
    confidence_score: float = 0.0
    missing_fields: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class FieldMetadata(BaseModel):
    confidence: Literal["high", "medium", "low", "n/a"] = "n/a"
    source: Literal[
        "user_provided",
        "inferred",
        "needs_confirmation",
        "not_provided",
        "user_confirmed",
    ] = "not_provided"
    evidence: str | None = None
    updated_at: str | None = None


class FieldMetadataUpdate(FieldMetadata):
    """Strict-output-safe list item; dynamic-key objects are not OpenAI strict schemas."""

    field: str


class ClarificationQuestion(BaseModel):
    field: str
    question: str
    rationale: str
    suggested_replies: list[str] = Field(default_factory=list, max_length=4)
    priority: int = Field(ge=1, le=20)


class RequirementNode(BaseModel):
    key: str
    display_name: str
    fields: list[str]
    summary: str
    status: Literal["Filled", "Missing", "Needs Confirmation", "N/A"]
    confidence: Literal["high", "medium", "low", "n/a"]
    source: Literal[
        "user_provided",
        "inferred",
        "needs_confirmation",
        "not_provided",
        "user_confirmed",
    ]
    filled_fields: int
    total_fields: int


class LLMModelOutput(BaseModel):
    """Strict structured-output schema returned by the configured model."""

    assistant_message: str
    scenario_type: str | None = None
    updated_intake: IntakeData
    field_metadata_updates: list[FieldMetadataUpdate] = Field(default_factory=list)
    missing_fields: list[str]
    ambiguous_fields: list[str] = Field(default_factory=list)
    completion_score: int = Field(ge=0, le=100)
    ready_for_ticket: bool
    validation_ready: bool = False
    risk_flags: list[str] = Field(default_factory=list)
    context_used: list[str] = Field(default_factory=list)
    next_questions: list[ClarificationQuestion] = Field(default_factory=list, max_length=3)

    @field_validator("next_questions", mode="before")
    @classmethod
    def normalize_legacy_questions(cls, value: object) -> object:
        """Accept old deterministic fixtures while publishing an object schema."""
        if not isinstance(value, list):
            return value
        return [
            {
                "field": "unknown",
                "question": item,
                "rationale": "Additional clarification is needed.",
                "suggested_replies": [],
                "priority": min(index + 1, 20),
            }
            if isinstance(item, str) else item
            for index, item in enumerate(value)
        ]


class LLMIntakeResult(LLMModelOutput):
    """Model output plus server-owned runtime provenance."""

    llm_provider: Literal["openai", "claude", "deterministic"] = "deterministic"
    llm_model: str | None = None
    llm_request_id: str | None = None
    llm_latency_ms: int | None = None
    fallback_reason: str | None = None


class TicketPayload(BaseModel):
    """Adapter-neutral Jira ticket payload. See README for the handoff contract."""

    title: str
    project_category: str = "BIM"
    source_request_category: str = "unknown"
    summary: str
    business_purpose: str
    requester: str
    owner: str
    audience: str
    data_sources: list[str]
    metrics_or_kpis: list[str]
    display_format: str
    refresh_frequency: str
    scope: str
    acceptance_criteria: list[str]
    success_criteria: list[str]
    risks_and_assumptions: list[str]
    suggested_priority: str
    linked_ticket_suggestion: str
    implementation_notes: list[str]
    created_by: str = "AI Intake Prototype"


class TicketPreview(TicketPayload):
    draft_ticket_key: str
    status: str = "Draft Only"
    disclaimer: str = "No real Jira ticket was created."


class JiraAdapterResult(BaseModel):
    ticket_key: str
    status: str
    created: bool
    message: str
    payload: TicketPayload


class AttachmentDraft(BaseModel):
    filename: str = "chat.txt"
    content_type: str = "text/plain"
    content: str
    included: bool = False
    uploaded: bool = False
    content_encoding: Literal["utf-8", "base64"] = "utf-8"
    size_bytes: int = 0
    source: Literal["chat", "user"] = "chat"

    def public_view(self) -> "AttachmentDraft":
        """Metadata-only copy — never send file bodies to the browser."""
        return self.model_copy(update={"content": ""})


class JiraTicketDraftPayload(BaseModel):
    project_category: Literal["ITO", "BIM"]
    issue_type: str
    summary: str
    description: str
    priority: str
    labels: list[str] = Field(default_factory=list)
    attachments: list[AttachmentDraft] = Field(default_factory=list)


class TicketRelationshipDraft(BaseModel):
    source_ticket_category: str = "ITO"
    delivery_ticket_category: str = "BIM"
    direction: str = "Proposed BIM → ITO traceability relationship"
    relationship_type: str = "To be confirmed by Jira integration"
    created: bool = False


class JiraTicketBundlePayload(BaseModel):
    ito_ticket: JiraTicketDraftPayload
    bim_ticket: JiraTicketDraftPayload
    proposed_relationship: TicketRelationshipDraft
    created_by: str = "AI Intake Prototype"
    validation_state: Literal["gathering", "draft_ready", "pending_validation", "validated", "rejected"]


class JiraTicketBundleAdapterResult(BaseModel):
    ito_ticket_key: str
    bim_ticket_key: str
    status: str = "Draft Only"
    created: bool = False
    message: str = "No real Jira ticket was created. This is a prototype draft."
    payload: JiraTicketBundlePayload


class JiraTicketDraftPreview(JiraTicketDraftPayload):
    draft_ticket_key: str
    created: bool = False
    status: str = "Draft Only"
    disclaimer: str = "No real Jira ticket was created."


class JiraTicketBundlePreview(BaseModel):
    ito_ticket: JiraTicketDraftPreview
    bim_ticket: JiraTicketDraftPreview
    proposed_relationship: TicketRelationshipDraft
    created_by: str = "AI Intake Prototype"
    validation_state: str
    created: bool = False
    status: str = "Draft Only"
    disclaimer: str = "No real Jira ticket was created."


class RemoveAttachmentRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)
    filename: str = Field(min_length=1, max_length=255)


class AttachmentListResponse(BaseModel):
    session_id: str
    attachments: list[AttachmentDraft] = Field(default_factory=list)
    ticket_preview: TicketPreview | None = None
    ticket_bundle_preview: JiraTicketBundlePreview | None = None


class TicketGenerationResponse(TicketPreview):
    """Bundle response with legacy BIM preview fields preserved at top level."""

    ticket_preview: TicketPreview
    ticket_bundle_preview: JiraTicketBundlePreview
    pending_attachments: list[AttachmentDraft] = Field(default_factory=list)


class MessageRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=10_000)


class ResetRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)


class GenerateTicketRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)


class FieldPatchRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)
    field: str
    value: str | bool | list[str] | None = None
    confirmed: bool = True


class ValidationActionRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)
    validator_name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class IntakeMessageResponse(BaseModel):
    session_id: str
    assistant_message: str
    intake: IntakeData
    missing_fields: list[str]
    completion_score: int
    ready_for_ticket: bool
    ticket_preview: TicketPreview | None = None
    ticket_bundle_preview: JiraTicketBundlePreview | None = None
    pending_attachments: list[AttachmentDraft] = Field(default_factory=list)
    field_metadata: dict[str, FieldMetadata] = Field(default_factory=dict)
    ambiguous_fields: list[str] = Field(default_factory=list)
    next_questions: list[ClarificationQuestion] = Field(default_factory=list)
    requirements_matrix: list[RequirementNode] = Field(default_factory=list)
    validation_ready: bool = False
    validation_state: Literal["gathering", "draft_ready", "pending_validation", "validated", "rejected"] = "gathering"
    validator_name: str | None = None
    validated_at: str | None = None
    validation_note: str | None = None
    risk_flags: list[str]
    context_used: list[str]
    mode: Literal["clarify", "draft_ticket", "context_answer", "error"]
    llm_provider: Literal["openai", "claude", "deterministic", "system"]
    llm_model: str | None = None
    llm_request_id: str | None = None
    llm_latency_ms: int | None = None
    fallback_reason: str | None = None


class LLMStatusResponse(BaseModel):
    configured: bool
    provider: Literal["openai", "claude", "deterministic"]
    model: str | None = None
    message: str


class TranscriptMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: str | None = None
    questions: list[ClarificationQuestion] = Field(default_factory=list)


class StressTestRequest(BaseModel):
    scenario_id: str


class StressTestResponse(BaseModel):
    scenario_id: str
    scenario_name: str
    transcript: list[TranscriptMessage]
    final_intake: IntakeData
    ticket_preview: TicketPreview | None = None
    ticket_bundle_preview: JiraTicketBundlePreview | None = None
    findings: list[str]
    risk_flags: list[str]
