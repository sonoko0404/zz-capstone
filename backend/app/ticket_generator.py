from __future__ import annotations

import re

from .intake_workflow import sanitized_transcript_text
from .jira_adapter import JiraAdapter
from .models import (
    AttachmentDraft,
    IntakeData,
    JiraTicketBundlePayload,
    JiraTicketBundlePreview,
    JiraTicketDraftPayload,
    JiraTicketDraftPreview,
    TicketPayload,
    TicketPreview,
    TicketRelationshipDraft,
    TranscriptMessage,
)


def _items(value: str | None, fallback: str = "To be confirmed") -> list[str]:
    if not value:
        return [fallback]
    parts = [part.strip(" .") for part in re.split(r"[,;\n]", value) if part.strip(" .")]
    return parts or [fallback]


class TicketGenerator:
    """Builds adapter-neutral payloads, then delegates ticket creation behavior."""

    def __init__(self, jira_adapter: JiraAdapter) -> None:
        self._jira_adapter = jira_adapter

    def build_payload(self, intake: IntakeData) -> TicketPayload:
        audience = intake.recipients_or_access_roles or "Audience to be confirmed"
        metric = intake.metrics_kpis_charts_maps or intake.required_fields or "BI requirements"
        display = intake.display_format or "BI deliverable"
        project = (intake.project_type_hint or "BIM").upper()
        if project not in {"BIM", "SCP", "ITO", "CC"}:
            project = "BIM"

        linked = intake.linked_ticket_hint or "No source ticket supplied; consider linking an SCP or ITO request for traceability."
        source_category = "unknown"
        if intake.linked_ticket_hint and re.search(r"\bSCP-?\d*\b", intake.linked_ticket_hint, re.IGNORECASE):
            source_category = "SCP"
        elif intake.linked_ticket_hint and re.search(r"\bITO-?\d*\b", intake.linked_ticket_hint, re.IGNORECASE):
            source_category = "ITO"

        title = (
            intake.report_title
            or intake.report_name
            or f"{display}: {metric} for {audience}"
        )
        title = re.sub(r"\s+", " ", title).strip()[:160]

        validation_owner = intake.accuracy_owner_or_validator or intake.armada_owner or intake.requester
        acceptance_criteria = [
            f"The {display.lower()} displays the agreed metrics or fields for {audience}.",
            f"Data is filtered according to the agreed scope: {intake.scope_criteria or 'scope to be confirmed during refinement'}.",
            f"{validation_owner or 'A designated report owner'} validates data accuracy before release.",
            f"Row-level security is documented as: {intake.row_level_security or 'decision pending'}.",
            f"Refresh cadence is configured as: {intake.refresh_frequency or intake.run_frequency or 'cadence pending'}.",
        ]

        risks = list(dict.fromkeys(intake.risk_flags + _items(intake.data_or_system_challenges, "No additional data risks supplied.")))
        if not intake.row_level_security:
            risks.append("Row-level security requirements require confirmation.")
        if not intake.linked_ticket_hint:
            risks.append("No SCP/ITO source ticket was supplied for traceability.")

        notes = [
            "Treat BIM as the proposed BI delivery category; a Jira administrator should validate project mapping before any future submission.",
            "Use only sanitized or approved data during prototype review.",
            "Validate source availability, field definitions, and refresh feasibility during technical refinement.",
        ]
        if "ticket" in (intake.data_sources or "").lower() or "jira" in (intake.data_sources or "").lower():
            notes.append("Use E1_Tickets for historical ticket-level analysis and E3_Change Log for workflow/bottleneck analysis.")

        return TicketPayload(
            title=title,
            project_category=project,
            source_request_category=source_category,
            summary=(intake.problems_addressed or intake.why_report_necessary or title),
            business_purpose=intake.why_report_necessary or "Business purpose to be confirmed",
            requester=intake.requester or "Not supplied",
            owner=intake.armada_owner or intake.requester or "Not supplied",
            audience=audience,
            data_sources=_items(intake.data_sources),
            metrics_or_kpis=_items(intake.metrics_kpis_charts_maps or intake.required_fields),
            display_format=display,
            refresh_frequency=intake.refresh_frequency or intake.run_frequency or "To be confirmed",
            scope=intake.scope_criteria or intake.filters_needed or "Scope to be confirmed",
            acceptance_criteria=acceptance_criteria,
            success_criteria=_items(intake.success_definition or intake.expected_metric_change_or_time_savings),
            risks_and_assumptions=risks,
            suggested_priority=intake.priority or "Medium",
            linked_ticket_suggestion=linked,
            implementation_notes=notes,
        )

    def generate(self, intake: IntakeData) -> TicketPreview:
        payload = self.build_payload(intake)
        result = self._jira_adapter.create_ticket(payload)
        # The adapter owns external-system behavior. The generator only maps the
        # stable result into the frontend's stable draft preview contract.
        return TicketPreview(
            **result.payload.model_dump(),
            draft_ticket_key=result.ticket_key,
            status=result.status,
            disclaimer=result.message,
        )

    def build_bundle_payload(
        self,
        intake: IntakeData,
        transcript: list[TranscriptMessage],
        validation_state: str,
    ) -> JiraTicketBundlePayload:
        """Build the stable, adapter-neutral ITO intake + BIM delivery blueprint."""
        title = self.build_payload(intake).title
        requester = intake.requester or "To be confirmed"
        requester_email = (
            intake.requester_email
            or ("Unavailable — explicitly marked by requester" if intake.requester_email_unavailable else "To be confirmed")
        )
        issue_type = intake.jira_issue_type or "To be confirmed by Jira integration"
        priority = intake.priority or "To be confirmed"
        labels = list(dict.fromkeys(intake.jira_labels))
        attachments: list[AttachmentDraft] = []
        if intake.include_chat_attachment:
            attachments.append(AttachmentDraft(
                content=sanitized_transcript_text(transcript),
                included=True,
                uploaded=False,
            ))

        ito_description = "\n".join([
            "REQUEST INTAKE (DRAFT)",
            f"Requester: {requester}",
            f"Requester email: {requester_email}",
            f"Scenario classification: {intake.scenario_type or 'Unassigned'}",
            f"Business request: {intake.why_report_necessary or 'To be confirmed'}",
            f"Decision supported: {intake.decisions_supported or 'To be confirmed'}",
            f"Audience: {intake.recipients_or_access_roles or 'To be confirmed'}",
            f"Desired output: {intake.display_format or 'To be confirmed'}",
            f"Requested deadline: {intake.deadline or 'To be confirmed'}",
            f"Source/request ticket hint: {intake.linked_ticket_hint or 'None supplied'}",
            "",
            "Known constraints and assumptions:",
            f"- {intake.known_constraints or 'To be confirmed'}",
            f"- {intake.assumptions_about_data_entry or 'To be confirmed'}",
            "",
            "Prototype note: static context only; no Armada system was queried or changed.",
        ])
        acceptance = self.build_payload(intake).acceptance_criteria
        bim_description = "\n".join([
            "BI DELIVERY REQUIREMENTS (DRAFT)",
            f"Requester: {requester}",
            f"Requester email: {requester_email}",
            f"Business purpose: {intake.why_report_necessary or 'To be confirmed'}",
            f"Business decision: {intake.decisions_supported or 'To be confirmed'}",
            f"Audience/access roles: {intake.recipients_or_access_roles or 'To be confirmed'}",
            f"Data sources: {intake.data_sources or 'To be confirmed'}",
            f"Required fields: {intake.required_fields or 'To be confirmed'}",
            f"Metrics/KPIs: {intake.metrics_kpis_charts_maps or 'To be confirmed'}",
            f"Display format: {intake.display_format or 'To be confirmed'}",
            f"Scope/filters: {intake.scope_criteria or intake.filters_needed or 'To be confirmed'}",
            f"Row-level security: {intake.row_level_security or 'To be confirmed'}",
            f"Refresh frequency: {intake.refresh_frequency or intake.run_frequency or 'To be confirmed'}",
            f"Success/validator: {intake.success_definition or intake.accuracy_owner_or_validator or 'To be confirmed'}",
            f"Risks: {'; '.join(intake.risk_flags) or 'No additional risks supplied'}",
            "",
            "Acceptance criteria:",
            *[f"- {criterion}" for criterion in acceptance],
            "",
            "Jira configuration note: project keys, Issue Type values, and relationship types must be confirmed by the future Jira integration owner.",
        ])

        return JiraTicketBundlePayload(
            ito_ticket=JiraTicketDraftPayload(
                project_category="ITO",
                issue_type="To be confirmed by Jira integration",
                summary=f"BI request intake: {title}"[:255],
                description=ito_description,
                priority=priority,
                labels=labels,
                attachments=[item.model_copy(deep=True) for item in attachments],
            ),
            bim_ticket=JiraTicketDraftPayload(
                project_category="BIM",
                issue_type=issue_type,
                summary=title[:255],
                description=bim_description,
                priority=priority,
                labels=labels,
                attachments=[item.model_copy(deep=True) for item in attachments],
            ),
            proposed_relationship=TicketRelationshipDraft(),
            validation_state=validation_state,
        )

    def generate_bundle(
        self,
        intake: IntakeData,
        transcript: list[TranscriptMessage],
        validation_state: str,
    ) -> JiraTicketBundlePreview:
        payload = self.build_bundle_payload(intake, transcript, validation_state)
        result = self._jira_adapter.create_ticket_bundle(payload)
        return JiraTicketBundlePreview(
            ito_ticket=JiraTicketDraftPreview(
                **result.payload.ito_ticket.model_dump(),
                draft_ticket_key=result.ito_ticket_key,
                status=result.status,
                disclaimer=result.message,
            ),
            bim_ticket=JiraTicketDraftPreview(
                **result.payload.bim_ticket.model_dump(),
                draft_ticket_key=result.bim_ticket_key,
                status=result.status,
                disclaimer=result.message,
            ),
            proposed_relationship=result.payload.proposed_relationship,
            validation_state=result.payload.validation_state,
            created=result.created,
            status=result.status,
            disclaimer=result.message,
        )

    def legacy_preview_from_bundle(
        self,
        intake: IntakeData,
        bundle: JiraTicketBundlePreview,
    ) -> TicketPreview:
        """Keep the existing frontend/API shape while the bundle becomes primary."""
        payload = self.build_payload(intake)
        return TicketPreview(
            **payload.model_dump(),
            draft_ticket_key=bundle.bim_ticket.draft_ticket_key,
            status=bundle.status,
            disclaimer=bundle.disclaimer,
        )
