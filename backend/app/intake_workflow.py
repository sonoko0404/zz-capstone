from __future__ import annotations

import re
from datetime import UTC, datetime

from .intake_config import (
    EDITABLE_FIELDS,
    NODE_DEFINITIONS,
    scenario_profile,
)
from .models import FieldMetadata, IntakeData, RequirementNode, TranscriptMessage


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return bool(value)


def empty_metadata() -> dict[str, FieldMetadata]:
    return {field: FieldMetadata() for field in EDITABLE_FIELDS}


def normalize_metadata(
    intake: IntakeData,
    existing: dict[str, FieldMetadata],
) -> dict[str, FieldMetadata]:
    normalized = {field: metadata.model_copy(deep=True) for field, metadata in existing.items() if field in EDITABLE_FIELDS}
    for field in EDITABLE_FIELDS:
        value = getattr(intake, field, None)
        metadata = normalized.get(field)
        if metadata is None:
            metadata = FieldMetadata()
        if (
            not has_value(value)
            and field not in {"requester_email_unavailable", "include_chat_attachment"}
            and metadata.source != "needs_confirmation"
        ):
            metadata = FieldMetadata(confidence="n/a", source="not_provided")
        normalized[field] = metadata
    return normalized


def build_requirements_matrix(
    intake: IntakeData,
    metadata: dict[str, FieldMetadata],
) -> list[RequirementNode]:
    nodes: list[RequirementNode] = []
    profile = scenario_profile(intake.scenario_type)
    for key, display_name, fields in NODE_DEFINITIONS:
        if key in profile.not_applicable_nodes:
            nodes.append(RequirementNode(
                key=key,
                display_name=display_name,
                fields=list(fields),
                summary=f"Not applicable for {intake.scenario_type}",
                status="N/A",
                confidence="n/a",
                source="not_provided",
                filled_fields=0,
                total_fields=len(fields),
            ))
            continue
        filled = [field for field in fields if has_value(getattr(intake, field, None))]
        field_metadata = [metadata.get(field, FieldMetadata()) for field in filled]
        if not filled:
            unresolved = [
                metadata.get(field, FieldMetadata())
                for field in fields
                if metadata.get(field, FieldMetadata()).source == "needs_confirmation"
            ]
            if unresolved:
                status = "Needs Confirmation"
                confidence = "low"
                source = "needs_confirmation"
                summary = "Conflicting values require confirmation"
            else:
                status = "Missing"
                confidence = "n/a"
                source = "not_provided"
                summary = "No information captured yet"
        else:
            needs_confirmation = any(
                item.source in {"inferred", "needs_confirmation"} or item.confidence in {"low", "medium"}
                for item in field_metadata
            )
            status = "Needs Confirmation" if needs_confirmation else "Filled"
            confidence = _aggregate_confidence(field_metadata)
            source = _aggregate_source(field_metadata)
            parts = [
                str(getattr(intake, field)).strip()
                for field in filled
                if not isinstance(getattr(intake, field), bool)
            ]
            summary = " · ".join(parts[:3])[:260] or "Captured"
        nodes.append(RequirementNode(
            key=key,
            display_name=display_name,
            fields=list(fields),
            summary=summary,
            status=status,
            confidence=confidence,
            source=source,
            filled_fields=len(filled),
            total_fields=len(fields),
        ))
    return nodes


def _aggregate_confidence(items: list[FieldMetadata]) -> str:
    levels = {item.confidence for item in items}
    if "low" in levels:
        return "low"
    if "medium" in levels:
        return "medium"
    if "high" in levels:
        return "high"
    return "n/a"


def _aggregate_source(items: list[FieldMetadata]) -> str:
    sources = {item.source for item in items}
    for source in ("needs_confirmation", "inferred", "user_confirmed", "user_provided"):
        if source in sources:
            return source
    return "not_provided"


def ambiguous_fields(metadata: dict[str, FieldMetadata], intake: IntakeData) -> list[str]:
    return sorted(
        field
        for field, item in metadata.items()
        if (
            item.source == "needs_confirmation"
            or (
                has_value(getattr(intake, field, None))
                and (item.source == "inferred" or item.confidence == "low")
            )
        )
    )


def validation_eligibility(
    intake: IntakeData,
    completion_score: int,
    minimum_complete: bool,
    ambiguous: list[str],
    risks: list[str],
    blocking_risks: list[str] | None = None,
) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if completion_score < 70:
        blockers.append("Completion score must be at least 70%.")
    if not minimum_complete:
        blockers.append("Minimum intake requirements are incomplete.")
    if not (intake.requester or intake.armada_owner):
        blockers.append("Requester or owner is required.")
    if not (intake.requester_email or intake.requester_email_unavailable):
        blockers.append("Requester email is required or must be marked unavailable.")
    if not intake.jira_issue_type:
        blockers.append("Jira Issue Type is required or must be marked To be confirmed.")
    if not intake.priority:
        blockers.append("Priority is required.")

    profile = scenario_profile(intake.scenario_type)
    blocking_fields = {
        field
        for _, fields in profile.required_groups
        for field in fields
    }
    blocking_ambiguity = sorted(set(ambiguous) & blocking_fields)
    if blocking_ambiguity:
        blockers.append("Required fields need confirmation: " + ", ".join(blocking_ambiguity))

    if blocking_risks is None:
        blocking_risks = [
            risk for risk in risks
            if any(
                token in risk.lower()
                for token in (
                    "sensitive",
                    "conflict",
                    "dirty",
                    "inconsistent",
                    "blocked",
                    "rls",
                    "feasibility",
                    "complexity",
                )
            )
        ]
    if blocking_risks:
        blockers.append(
            "Resolve blocking security, data-quality, or feasibility risks before validation."
        )
    return not blockers, blockers


def derive_validation_state(current: str, ready_for_ticket: bool) -> str:
    if current in {"pending_validation", "validated", "rejected"}:
        return current
    return "draft_ready" if ready_for_ticket else "gathering"


def sanitized_transcript_text(transcript: list[TranscriptMessage]) -> str:
    lines = [
        "AI BI Intake Assistant — sanitized conversation draft",
        "Draft only. Do not include sensitive or internal records.",
        "",
    ]
    for entry in transcript:
        content = _sanitize_text(entry.content)
        stamp = f" [{entry.timestamp}]" if entry.timestamp else ""
        lines.append(f"{entry.role.upper()}{stamp}: {content}")
    return "\n".join(lines).strip() + "\n"


def _sanitize_text(value: str) -> str:
    value = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED SSN]", value)
    value = re.sub(r"\b(?:\d[ -]*?){13,16}\b", "[REDACTED CARD NUMBER]", value)
    value = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[EMAIL STORED IN STRUCTURED INTAKE]", value, flags=re.IGNORECASE)
    return value[:10_000]
