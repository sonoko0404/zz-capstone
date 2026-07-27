from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .intake_config import EDITABLE_FIELDS, FIELD_LABELS
from .intake_workflow import has_value, normalize_metadata, utc_now
from .llm_client import (
    classify_scenario,
    metadata_for_changes,
    score_intake,
    select_questions,
)
from .models import (
    ClarificationQuestion,
    FieldMetadata,
    FieldMetadataUpdate,
    IntakeData,
)


SOURCE_NAMES = (
    "Salesforce",
    "Snowflake",
    "SAP",
    "Oracle",
    "Jira",
    "OpenTickets",
    "E1_Tickets",
    "E2_Linked Tickets",
    "E3_Change Log",
    "WMS",
    "Red Prairie",
    "Excel",
    "CSV",
    "Microsoft Fabric",
    "Power BI semantic model",
    "ERP",
    "CRM",
    "Power BI Data Agent",
)

@dataclass
class ReconciliationResult:
    intake: IntakeData
    metadata: dict[str, FieldMetadata]
    changed_fields: dict[str, tuple[Any, Any]]
    rejected_changes: dict[str, Any]
    conflicting_fields: dict[str, list[str]]
    risk_signals: dict[str, RiskSignal]
    questions: list[ClarificationQuestion]
    score: int
    missing_fields: list[str]
    ready_for_ticket: bool
    assistant_message: str


@dataclass
class CorrectionPlan:
    updates: dict[str, Any] = field(default_factory=dict)
    explicit_fields: set[str] = field(default_factory=set)
    atomic_fields: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class RiskSignal:
    code: str
    message: str
    evidence: str = ""
    related_fields: tuple[str, ...] = ()
    blocking_validation: bool = False
    blocking_draft: bool = False


def risk_signal(
    code: str,
    message: str,
    *,
    evidence: str = "",
    related_fields: Iterable[str] = (),
    blocking_validation: bool = False,
    blocking_draft: bool = False,
) -> RiskSignal:
    return RiskSignal(
        code=code,
        message=message,
        evidence=_normalized(evidence)[:280],
        related_fields=tuple(related_fields),
        blocking_validation=blocking_validation,
        blocking_draft=blocking_draft,
    )


def detect_live_data_query(message: str) -> bool:
    """Detect explicit requests to query current enterprise facts."""
    lower = _normalized(message).lower()
    if re.search(
        r"\b(current fiscal year|current dashboard|daily refresh|"
        r"future power bi connection|use power bi as (?:the )?display format)\b",
        lower,
    ) or re.search(
        r"\b(create|build|develop|need|request)\b.{0,40}\bpower bi\b"
        r".{0,30}\b(report|dashboard)\b",
        lower,
    ):
        return False
    current_fact = re.search(
        r"\b(today|currently|live|right now|as of now|latest|"
        r"at this moment|exactly how many|current (?:count|backlog|tickets?))\b",
        lower,
    )
    query_intent = re.search(
        r"\b(how many|count|query|look up|retrieve|fetch|tell me|"
        r"show me|which assignee|who is assigned|busiest assignee)\b",
        lower,
    )
    enterprise_subject = re.search(
        r"\b(power bi data agent|data agent|opentickets|active backlog|"
        r"bim tickets?|jira tickets?|assignee|ticket counts?)\b",
        lower,
    )
    return bool(current_fact and query_intent and enterprise_subject)


def detect_multi_request(message: str) -> list[str]:
    """Return separate request summaries when a create request and a fix request coexist."""
    text = _normalized(message)
    lower = text.lower()
    has_separator = bool(re.search(r"\b(and also|also|as well as)\b|[,;]\s*and\b", lower))
    create_intent = bool(
        re.search(r"\b(build|create|develop|need|make)\b.{0,90}\b(dashboard|report|extract|analysis)\b", lower)
    )
    issue_intent = bool(
        re.search(
            r"\b(fix|correct|repair|investigate)\b.{0,100}"
            r"\b(incorrect|wrong|broken|bug|error|totals?|report|dashboard)\b",
            lower,
        )
        or re.search(
            r"\b(incorrect|wrong|broken|bug|error)\b.{0,80}\b(totals?|report|dashboard)\b",
            lower,
        )
    )
    if not (has_separator and create_intent and issue_intent):
        return []

    parts = [
        part.strip(" ,;")
        for part in re.split(r"\b(?:and also|also|as well as)\b|[,;]\s*and\b", text, flags=re.IGNORECASE)
        if part.strip(" ,;")
    ]
    return parts[:2] if len(parts) >= 2 else ["New BI deliverable", "Existing report issue"]


def detect_conflicting_values(message: str) -> dict[str, list[str]]:
    """Identify multiple unresolved values for the same canonical field."""
    text = _normalized(message)
    lower = text.lower()
    conflicts: dict[str, list[str]] = {}

    source_values = _mentioned_sources(text)
    if len(source_values) > 1 and re.search(r"\b(or|either|maybe)\b", lower):
        conflicts["data_sources"] = source_values

    format_values: list[str] = []
    if re.search(r"\bpower bi dashboard\b|\bdashboard\b", lower):
        format_values.append("Dashboard")
    if re.search(r"\breport\b", lower):
        format_values.append("Report")
    if re.search(r"\bexcel(?:\s+(?:extract|file|report))?\b", lower):
        format_values.append("Excel")
    format_values = _unique(format_values)
    if len(format_values) > 1 and (
        "/" in text or re.search(r"\b(or|maybe)\b", lower)
    ):
        conflicts["display_format"] = format_values
        conflicts["request_type"] = format_values

    cadence_pattern = r"(hourly|daily|weekly|monthly|quarterly|real[- ]time)"
    if re.search(r"\b(actually|maybe|or|either)\b|/", lower):
        cadence_matches = re.findall(rf"\b{cadence_pattern}\b", lower)
    else:
        cadence_matches = re.findall(
            rf"\b{cadence_pattern}\s+(?:data\s+)?(?:refresh|cadence)\b",
            lower,
        )
        cadence_matches.extend(re.findall(
            rf"\b(?:refresh|cadence)(?:ed|s)?\s+(?:is\s+)?{cadence_pattern}\b",
            lower,
        ))
    cadence_values = _unique(
        value.replace("-", " ").title() for value in cadence_matches
    )
    if len(cadence_values) > 1:
        conflicts["refresh_frequency"] = cadence_values
        conflicts["run_frequency"] = cadence_values
    return conflicts


def reconcile_turn(
    *,
    message: str,
    previous: IntakeData,
    candidate: IntakeData,
    existing_metadata: dict[str, FieldMetadata],
    model_metadata_updates: Iterable[FieldMetadataUpdate],
    model_questions: list[ClarificationQuestion],
    risk_signals: dict[str, RiskSignal],
) -> ReconciliationResult:
    """Make the server-owned canonical decision for a completed LLM turn."""
    # The model proposes a delta. Canonical state starts from the previous
    # session and accepts only non-empty, non-ambiguous candidate changes.
    final = previous.model_copy(deep=True)
    model_updates = list(model_metadata_updates)
    updates_by_field = {
        update.field: update
        for update in model_updates
        if update.field in EDITABLE_FIELDS
    }
    for field_name in EDITABLE_FIELDS:
        candidate_value = getattr(candidate, field_name, None)
        previous_value = getattr(previous, field_name, None)
        if candidate_value == previous_value or not has_value(candidate_value):
            continue
        update = updates_by_field.get(field_name)
        if update is None:
            # A structured value without per-field evidence is only an LLM
            # guess. Deterministic extraction and compliant cloud responses
            # both provide metadata for every proposed change.
            continue
        # Low-confidence/inferred candidates may fill a blank slot so the UI
        # can surface them for confirmation, but may never replace a stable
        # existing fact. Explicit user-provided values can replace an
        # unconfirmed value; user-confirmed protection is applied below.
        if (
            has_value(previous_value)
            and (
                update.source in {"inferred", "needs_confirmation"}
                or update.confidence == "low"
            )
        ):
            continue
        if (
            has_value(previous_value)
            and update.source == "user_provided"
            and not _candidate_change_is_evidenced(field_name, candidate_value, message)
        ):
            continue
        setattr(final, field_name, candidate_value)
    signals = dict(risk_signals)
    signals.pop("live_data_boundary", None)
    signals.pop("multi_request", None)

    correction = build_correction_plan(message, previous, final)
    for field_name, value in correction.updates.items():
        setattr(final, field_name, value)

    scenario_basis = final.model_copy(update={"scenario_type": previous.scenario_type})
    final.scenario_type = classify_scenario(message, scenario_basis)
    if final.scenario_type == "Existing Report Issue":
        final.request_type = "bug/fix"
    elif final.scenario_type == "Self-Service Access":
        final.request_type = "other"
        final.project_type_hint = "BIM"
        _apply_self_service_rules(message, final, correction)
        final.display_format = "Not applicable — self-service access"
        final.metrics_kpis_charts_maps = "Not applicable — self-service access"
        final.refresh_frequency = "Not applicable — self-service access"
        final.run_frequency = "Not applicable — self-service access"
    elif final.scenario_type == "Enhancement Request" and not final.request_type:
        final.request_type = "other"

    _apply_rls_role_rules(message, final, correction)
    _sanitize_deliverable_sources(message, previous, final)
    detected_conflicts = detect_conflicting_values(message)
    rejected_changes: dict[str, Any] = {}

    protected_atomic_change = any(
        existing_metadata.get(field_name, FieldMetadata()).source == "user_confirmed"
        and getattr(final, field_name, None) != getattr(previous, field_name, None)
        for field_name in correction.atomic_fields
    )
    if protected_atomic_change:
        for field_name in correction.atomic_fields:
            attempted = getattr(final, field_name, None)
            previous_value = getattr(previous, field_name, None)
            if attempted != previous_value:
                rejected_changes[field_name] = attempted
            setattr(final, field_name, previous_value)

    for field_name, metadata in existing_metadata.items():
        if metadata.source != "user_confirmed" or field_name not in EDITABLE_FIELDS:
            continue
        previous_value = getattr(previous, field_name, None)
        candidate_value = getattr(final, field_name, None)
        if candidate_value != previous_value:
            rejected_changes[field_name] = candidate_value
            setattr(final, field_name, previous_value)

    conflicts: dict[str, list[str]] = {}
    for field_name, values in detected_conflicts.items():
        if existing_metadata.get(field_name, FieldMetadata()).source == "user_confirmed":
            rejected_changes.setdefault(field_name, " / ".join(values))
        else:
            conflicts[field_name] = values

    for field_name in conflicts:
        if field_name not in EDITABLE_FIELDS:
            continue
        setattr(final, field_name, getattr(previous, field_name, None))
        signals[f"conflict:{field_name}"] = risk_signal(
            f"conflict:{field_name}",
            f"Conflicting {FIELD_LABELS[field_name].lower()} values require confirmation: "
            + ", ".join(conflicts[field_name])
            + ".",
            evidence=message,
            related_fields=(field_name,),
            blocking_validation=True,
            blocking_draft=True,
        )

    for field_name in correction.explicit_fields:
        if field_name not in conflicts and field_name not in rejected_changes:
            signals.pop(f"conflict:{field_name}", None)

    model_update_fields = {
        update.field
        for update in model_updates
        if update.source == "user_provided" and update.confidence == "high"
    }
    for signal_key in list(signals):
        if not signal_key.startswith("conflict:"):
            continue
        field_name = signal_key.removeprefix("conflict:")
        if field_name in conflicts:
            continue
        final_value = getattr(final, field_name, None)
        if (
            has_value(final_value)
            and (
                final_value != getattr(previous, field_name, None)
                or field_name in correction.explicit_fields
                or field_name in model_update_fields
            )
        ):
            signals.pop(signal_key, None)

    # A correction to a deliverable should not erase the stable scenario
    # classification unless the message explicitly introduces another scenario.
    if correction.explicit_fields and previous.scenario_type and final.scenario_type in {None, "Unassigned"}:
        final.scenario_type = previous.scenario_type

    changed_fields = {
        field_name: (getattr(previous, field_name, None), getattr(final, field_name, None))
        for field_name in EDITABLE_FIELDS
        if getattr(previous, field_name, None) != getattr(final, field_name, None)
    }

    metadata = _reconcile_metadata(
        message=message,
        previous=previous,
        final=final,
        existing=existing_metadata,
        model_updates=model_updates,
        changed_fields=changed_fields,
        correction_fields=correction.explicit_fields,
        conflicts=conflicts,
    )
    signals = update_persistent_risk_signals(message, final, metadata, signals)
    risks = recalculate_risks(final, metadata, signals, message)
    final.risk_flags = risks

    score, missing, ready = ticket_readiness(final, signals)
    final.missing_fields = missing
    final.confidence_score = round(score / 100, 2)

    questions = _select_reconciled_questions(
        final=final,
        missing=missing,
        ready=ready,
        conflicts=conflicts,
        model_questions=model_questions,
        metadata=metadata,
        signals=signals,
    )
    assistant_message = render_assistant_message(
        final=final,
        changed_fields=changed_fields,
        rejected_changes=rejected_changes,
        conflicts=conflicts,
        questions=questions,
        ready=ready,
        risks=risks,
        blocking_validation_risks=validation_blocking_risks(signals),
        atomic_rejected_fields=correction.atomic_fields if protected_atomic_change else set(),
        protected_fields={
            field_name
            for field_name, metadata in existing_metadata.items()
            if metadata.source == "user_confirmed"
        },
    )
    return ReconciliationResult(
        intake=final,
        metadata=metadata,
        changed_fields=changed_fields,
        rejected_changes=rejected_changes,
        conflicting_fields=conflicts,
        risk_signals=signals,
        questions=questions,
        score=score,
        missing_fields=missing,
        ready_for_ticket=ready,
        assistant_message=assistant_message,
    )


def build_correction_plan(message: str, previous: IntakeData, candidate: IntakeData) -> CorrectionPlan:
    text = _normalized(message)
    lower = text.lower()
    plan = CorrectionPlan()
    correction_language = bool(
        re.search(r"\b(correction|instead(?: of)?|actually|only need|change(?: it)? to|switch(?: it)? to)\b", lower)
    )
    if not correction_language:
        return plan

    if re.search(r"\b(one[- ]time\s+)?excel\s+(extract|file)\b", lower):
        plan.updates.update({
            "request_type": "data extract",
            "display_format": "Excel",
            "run_frequency": "One-time",
            "refresh_frequency": None,
            "data_sources": previous.data_sources,
        })
        plan.explicit_fields.update(plan.updates)
        plan.atomic_fields.update({
            "request_type",
            "display_format",
            "run_frequency",
            "refresh_frequency",
        })

    sources = [
        source for source in _mentioned_sources(text)
        if source not in {"Excel", "CSV"}
    ]
    if sources:
        target = sources[0]
        if "instead of" in lower and len(sources) > 1:
            target = sources[0]
        plan.updates["data_sources"] = target
        plan.explicit_fields.add("data_sources")

    return plan


def update_persistent_risk_signals(
    message: str,
    intake: IntakeData,
    metadata: dict[str, FieldMetadata],
    current: dict[str, RiskSignal],
) -> dict[str, RiskSignal]:
    signals = dict(current)
    lower = _normalized(message).lower()
    evidence = _normalized(message)
    challenges = " ".join(
        filter(None, [intake.data_or_system_challenges, intake.known_constraints])
    ).lower()

    quality_resolved = bool(re.search(
        r"\b(data quality|duplicates?|inconsisten(?:cy|cies)|reconciliation)\b"
        r".{0,60}\b(resolved|reconciled|removed|confirmed)\b",
        f"{lower} {challenges}",
    ))
    if quality_resolved:
        signals.pop("dirty_data", None)
    elif re.search(
        r"\b(dirty|noisy|duplicate|inconsistent|unreliable|mismatch)\w*\b",
        f"{lower} {challenges}",
    ):
        signals["dirty_data"] = risk_signal(
            "dirty_data",
            "Potential dirty or inconsistent source data requires validation.",
            evidence=evidence,
            related_fields=("data_or_system_challenges", "accuracy_owner_or_validator"),
            blocking_validation=True,
        )
    if re.search(r"\b(ssn|social security|patient|medical record|credit card|personal data|pii)\b", lower):
        signals["sensitive_data"] = risk_signal(
            "sensitive_data",
            "Potential sensitive data: use sanitized or aggregate data in this prototype.",
            evidence=evidence,
            related_fields=("scope_criteria", "row_level_security"),
            blocking_validation=True,
        )
    if re.search(r"\b(whatever|just do it|you decide|don't care)\b", lower):
        signals["user_fatigue"] = risk_signal(
            "user_fatigue",
            "User intent is underspecified; confirmation is required before validation.",
            evidence=evidence,
            blocking_validation=True,
        )

    requested_cadence = (intake.refresh_frequency or intake.run_frequency or "").lower()
    source_cadence = _source_cadence(challenges)
    source_unknown = "source update cadence is unknown" in challenges
    if requested_cadence in {"hourly", "daily", "real time"} and source_unknown:
        signals["source_cadence_unknown"] = risk_signal(
            "source_cadence_unknown",
            f"Requested {requested_cadence.title()} refresh feasibility is unknown because source cadence is not confirmed.",
            evidence=evidence,
            related_fields=("refresh_frequency", "known_constraints", "data_sources"),
            blocking_validation=True,
        )
    else:
        signals.pop("source_cadence_unknown", None)

    if (
        source_cadence
        and requested_cadence
        and _cadence_rank(requested_cadence) > _cadence_rank(source_cadence)
    ):
        signals["cadence_conflict"] = risk_signal(
            "cadence_conflict",
            f"Requested {requested_cadence.title()} refresh conflicts with a source that updates {source_cadence}.",
            evidence=evidence,
            related_fields=("refresh_frequency", "known_constraints", "data_sources"),
            blocking_validation=True,
        )
    else:
        signals.pop("cadence_conflict", None)

    complexity_score = _complexity_score(intake)
    mitigation_text = " ".join(filter(None, [
        intake.scope_criteria,
        intake.dependencies,
        intake.known_constraints,
    ])).lower()
    mitigation_captured = bool(
        re.search(
            r"\b(mvp|phase[ds]?|phased delivery|reduced scope|scope reduced|"
            r"prioriti[sz]ed|staged delivery)\b",
            mitigation_text,
        )
    )
    if complexity_score >= 3 and not mitigation_captured:
        signals["high_complexity"] = risk_signal(
            "high_complexity",
            "High request complexity requires MVP prioritization, dependencies, or phased delivery before validation.",
            evidence=evidence,
            related_fields=("scope_criteria", "dependencies", "known_constraints"),
            blocking_validation=True,
        )
    else:
        signals.pop("high_complexity", None)

    deadline = (intake.deadline or "").lower()
    aggressive_deadline = bool(
        re.search(
            r"\b(tomorrow|next business day|within (?:one|1|two|2) "
            r"(?:business )?days?|eod|end of day)\b",
            deadline,
        )
    )
    if complexity_score >= 3 and aggressive_deadline and not mitigation_captured:
        signals["deadline_feasibility"] = risk_signal(
            "deadline_feasibility",
            "The requested deadline is not credible for the stated complexity without an agreed MVP or phased plan.",
            evidence=evidence,
            related_fields=("deadline", "scope_criteria", "dependencies"),
            blocking_validation=True,
        )
    else:
        signals.pop("deadline_feasibility", None)

    open_tickets_text = f"{lower} {challenges}"
    open_tickets_reconciled = (
        "opentickets" in challenges and "reconciliation confirmed" in challenges
    )
    if open_tickets_reconciled:
        signals.pop("open_tickets_status_quality", None)
    elif "opentickets" in open_tickets_text and re.search(
        r"\bresolved\b.{0,80}\b(open|active|opentickets)\b|"
        r"\b(open|active|opentickets)\b.{0,80}\bresolved\b",
        open_tickets_text,
    ):
        signals["open_tickets_status_quality"] = risk_signal(
            "open_tickets_status_quality",
            "OpenTickets contains an open/active versus Resolved status inconsistency; the active-ticket definition requires owner validation.",
            evidence=evidence,
            related_fields=("data_or_system_challenges", "accuracy_owner_or_validator"),
            blocking_validation=True,
        )
    if open_tickets_reconciled:
        signals.pop("open_tickets_assignment_quality", None)
    elif "opentickets" in open_tickets_text and re.search(
        r"\bassigned groups?\b.{0,40}\b(blank|empty|missing)\b|"
        r"\b(blank|empty|missing)\b.{0,40}\bassigned groups?\b",
        open_tickets_text,
    ):
        signals["open_tickets_assignment_quality"] = risk_signal(
            "open_tickets_assignment_quality",
            "Assigned group may be blank in OpenTickets; blank values must not be assumed to mean unassigned.",
            evidence=evidence,
            related_fields=("data_or_system_challenges", "accuracy_owner_or_validator"),
            blocking_validation=True,
        )

    rls_value = (intake.row_level_security or "").lower()
    rls_metadata = metadata.get("row_level_security", FieldMetadata())
    if rls_value.startswith("required") and rls_metadata.source != "user_confirmed":
        signals["rls_mapping"] = risk_signal(
            "rls_mapping",
            "RLS role/group mappings require confirmation before release.",
            evidence=evidence,
            related_fields=("row_level_security", "data_story_by_recipient_role"),
            blocking_validation=True,
        )
    elif rls_metadata.source == "user_confirmed" or not rls_value:
        signals.pop("rls_mapping", None)
    return signals


def recalculate_risks(
    intake: IntakeData,
    metadata: dict[str, FieldMetadata],
    risk_signals: dict[str, RiskSignal],
    message: str = "",
) -> list[str]:
    """Rebuild risks from final state; never retain stale missing-field strings."""
    del metadata, message
    risks: list[str] = []
    if not intake.data_sources:
        risks.append("Data source is not yet defined.")
    if intake.scenario_type == "Self-Service Access":
        if not (intake.armada_owner or intake.accuracy_owner_or_validator):
            risks.append("Security or data approval owner is missing.")
    else:
        if not (intake.requester or intake.armada_owner):
            risks.append("Requester or accountable owner is missing.")
        if not (intake.success_definition or intake.accuracy_owner_or_validator):
            risks.append("Success criteria or validation owner is missing.")
        if not intake.row_level_security:
            risks.append("Row-level security requirements are not yet defined.")
    risks.extend(signal.message for signal in risk_signals.values())
    return _unique(risks)


def ticket_readiness(
    intake: IntakeData,
    risk_signals: dict[str, RiskSignal],
) -> tuple[int, list[str], bool]:
    """Return draft readiness from canonical fields plus unresolved turn signals."""
    score, missing, minimum_ready = score_intake(intake)
    has_blocking_signal = any(
        signal.blocking_draft for signal in risk_signals.values()
    )
    return score, missing, minimum_ready and not has_blocking_signal


def validation_blocking_risks(
    risk_signals: dict[str, RiskSignal],
) -> list[str]:
    return [
        signal.message
        for signal in risk_signals.values()
        if signal.blocking_validation
    ]


def clear_risk_signals_for_field(
    field_name: str,
    value: Any,
    confirmed: bool,
    risk_signals: dict[str, RiskSignal],
) -> dict[str, RiskSignal]:
    signals = dict(risk_signals)
    signals.pop(f"conflict:{field_name}", None)
    if field_name in {"request_type", "display_format"}:
        signals.pop("conflict:request_type", None)
        signals.pop("conflict:display_format", None)
    if field_name in {"run_frequency", "refresh_frequency"}:
        signals.pop("conflict:run_frequency", None)
        signals.pop("conflict:refresh_frequency", None)
        if confirmed:
            signals.pop("cadence_conflict", None)
            signals.pop("source_cadence_unknown", None)
    if field_name in {"row_level_security", "data_story_by_recipient_role"} and confirmed:
        signals.pop("rls_mapping", None)
    if field_name == "data_or_system_challenges" and confirmed:
        normalized = str(value or "").lower()
        if any(token in normalized for token in ("none", "clean", "resolved", "no known")):
            signals.pop("dirty_data", None)
            signals.pop("open_tickets_status_quality", None)
            signals.pop("open_tickets_assignment_quality", None)
    if field_name == "known_constraints" and confirmed:
        normalized = str(value or "").lower()
        if "unknown" not in normalized and re.search(
            r"\b(hourly|daily|weekly|monthly|quarterly|real[- ]time)\b",
            normalized,
        ):
            signals.pop("source_cadence_unknown", None)
        if re.search(r"\b(mvp|phase[ds]?|reduced scope|prioriti[sz]ed)\b", normalized):
            signals.pop("high_complexity", None)
            signals.pop("deadline_feasibility", None)
    if field_name in {"scope_criteria", "dependencies"} and confirmed:
        normalized = str(value or "").lower()
        if re.search(r"\b(mvp|phase[ds]?|reduced scope|prioriti[sz]ed)\b", normalized):
            signals.pop("high_complexity", None)
            signals.pop("deadline_feasibility", None)
    if field_name == "deadline" and confirmed:
        normalized = str(value or "").lower()
        if not re.search(
            r"\b(tomorrow|next business day|within (?:one|1|two|2) "
            r"(?:business )?days?|eod|end of day)\b",
            normalized,
        ):
            signals.pop("deadline_feasibility", None)
    return signals


def render_assistant_message(
    *,
    final: IntakeData,
    changed_fields: dict[str, tuple[Any, Any]],
    rejected_changes: dict[str, Any],
    conflicts: dict[str, list[str]],
    questions: list[ClarificationQuestion],
    ready: bool,
    risks: list[str],
    blocking_validation_risks: list[str],
    atomic_rejected_fields: set[str],
    protected_fields: set[str],
) -> str:
    parts: list[str] = []
    if atomic_rejected_fields:
        protected_labels = [
            FIELD_LABELS[field_name]
            for field_name in atomic_rejected_fields
            if field_name in protected_fields
        ]
        parts.append(
            "I did not apply the scope change because it must update the deliverable type, format, "
            f"and cadence together, while {', '.join(protected_labels)} is manually confirmed. "
            "Edit and confirm the scope fields in the Requirements Matrix if this change is intended."
        )
    for field_name, attempted in rejected_changes.items():
        if field_name in atomic_rejected_fields:
            continue
        current = getattr(final, field_name, None)
        parts.append(
            f"{FIELD_LABELS[field_name]} remains the manually confirmed value “{current}”. "
            f"I did not change it to “{attempted}”; edit and confirm it in the Requirements Matrix if needed."
        )

    if conflicts:
        for field_name, values in conflicts.items():
            if field_name in {"request_type", "run_frequency"}:
                continue
            parts.append(
                f"I detected conflicting {FIELD_LABELS[field_name].lower()} values "
                f"({', '.join(values)}), so I did not choose one."
            )
    elif changed_fields and not rejected_changes:
        has_replacement = any(before is not None for before, _ in changed_fields.values())
        if has_replacement:
            preferred_order = (
                "request_type",
                "display_format",
                "data_sources",
                "run_frequency",
                "refresh_frequency",
                "recipients_or_access_roles",
                "row_level_security",
                "metrics_kpis_charts_maps",
                "success_definition",
            )
            ordered_fields = [
                field_name for field_name in preferred_order if field_name in changed_fields
            ]
            ordered_fields.extend(
                field_name for field_name in changed_fields if field_name not in ordered_fields
            )
            rendered_changes: list[str] = []
            for field_name in ordered_fields[:5]:
                before, after = changed_fields[field_name]
                if before is None:
                    rendered_changes.append(
                        f"{FIELD_LABELS[field_name]} captured as “{after}”"
                    )
                else:
                    rendered_changes.append(
                        f"{FIELD_LABELS[field_name]} changed from “{before}” to “{after}”"
                    )
            rendered = "; ".join(rendered_changes)
            parts.append(rendered + ".")
        else:
            summary = _known_summary(final)
            parts.append(f"I’ve captured {summary}." if summary else "I’ve updated the intake.")

    if ready:
        parts.append(
            "The minimum intake requirements are complete. I prepared a local draft ticket preview. "
            "No real Jira ticket was created and no enterprise system was accessed."
        )
        if blocking_validation_risks:
            parts.append(
                "The draft can be reviewed, but human validation remains blocked until the surfaced "
                "security, data-quality, or feasibility risks are resolved."
            )
    elif questions:
        parts.append("To continue, please clarify:\n" + "\n".join(
            f"{index}. {question.question}" for index, question in enumerate(questions, start=1)
        ))
    else:
        parts.append("The intake remains incomplete; no draft ticket was generated.")

    if any("sensitive data" in risk.lower() for risk in risks):
        parts.append("Please use sanitized or aggregate data only.")
    return "\n".join(parts)


def _reconcile_metadata(
    *,
    message: str,
    previous: IntakeData,
    final: IntakeData,
    existing: dict[str, FieldMetadata],
    model_updates: Iterable[FieldMetadataUpdate],
    changed_fields: dict[str, tuple[Any, Any]],
    correction_fields: set[str],
    conflicts: dict[str, list[str]],
) -> dict[str, FieldMetadata]:
    metadata = {key: value.model_copy(deep=True) for key, value in existing.items()}
    deterministic = metadata_for_changes(previous.model_dump(), final, message)
    updates = {item.field: item for item in model_updates if item.field in EDITABLE_FIELDS}
    now = utc_now()
    evidence = _normalized(message)[:280]
    for field_name in changed_fields:
        if metadata.get(field_name, FieldMetadata()).source == "user_confirmed":
            continue
        update = updates.get(field_name)
        if update:
            metadata[field_name] = FieldMetadata(
                **update.model_dump(exclude={"field", "updated_at"}),
                updated_at=update.updated_at or now,
            )
        elif field_name in deterministic:
            metadata[field_name] = deterministic[field_name]
    for field_name in correction_fields:
        if field_name in changed_fields and metadata.get(field_name, FieldMetadata()).source != "user_confirmed":
            metadata[field_name] = FieldMetadata(
                confidence="high",
                source="user_provided",
                evidence=evidence,
                updated_at=now,
            )
    for field_name in conflicts:
        if field_name in EDITABLE_FIELDS:
            metadata[field_name] = FieldMetadata(
                confidence="low",
                source="needs_confirmation",
                evidence=evidence,
                updated_at=now,
            )
    return normalize_metadata(final, metadata)


def _select_reconciled_questions(
    *,
    final: IntakeData,
    missing: list[str],
    ready: bool,
    conflicts: dict[str, list[str]],
    model_questions: list[ClarificationQuestion],
    metadata: dict[str, FieldMetadata],
    signals: dict[str, RiskSignal],
) -> list[ClarificationQuestion]:
    del model_questions
    if conflicts:
        questions: list[ClarificationQuestion] = []
        for field_name, values in conflicts.items():
            if field_name in {"request_type", "run_frequency"}:
                continue
            questions.append(ClarificationQuestion(
                field=field_name,
                question=f"Which {FIELD_LABELS[field_name].lower()} should be used: {', '.join(values)}?",
                rationale="The request contains conflicting values, so confirmation is required before drafting.",
                suggested_replies=values[:4],
                priority=len(questions) + 1,
            ))
        return questions[:3]

    if ready:
        return []

    questions = _risk_questions(signals)
    questions.extend(
        question
        for question in select_questions(final, missing)
        if question.field not in {item.field for item in questions}
    )

    if "rls_mapping" in signals and metadata.get("row_level_security", FieldMetadata()).source != "user_confirmed":
        rls_question = ClarificationQuestion(
            field="row_level_security",
            question=(
                "Who owns the role/group mapping, and are the regional-manager "
                "and executive access rules confirmed?"
            ),
            rationale="Role-specific access must be confirmed before release.",
            suggested_replies=[
                "The business owner will confirm the role mapping",
                "Security review is required",
                "I will confirm it in the Requirements Matrix",
            ],
            priority=1,
        )
        questions = [
            question for question in questions if question.field != "row_level_security"
        ] + [rls_question]
    return questions[:3]


def _risk_questions(
    signals: dict[str, RiskSignal],
) -> list[ClarificationQuestion]:
    questions: list[ClarificationQuestion] = []
    if "source_cadence_unknown" in signals:
        questions.append(ClarificationQuestion(
            field="known_constraints",
            question="Who owns the source system, and what refresh cadence can it actually support?",
            rationale="Requested cadence must be separated from confirmed source capability.",
            suggested_replies=[
                "The source supports hourly updates",
                "The source supports daily updates",
                "The source owner must confirm",
            ],
            priority=1,
        ))
    if "cadence_conflict" in signals:
        questions.append(ClarificationQuestion(
            field="refresh_frequency",
            question="Should the request match the source cadence, use another source, or accept stale refreshes?",
            rationale="A faster report refresh cannot create newer data than the source provides.",
            suggested_replies=[
                "Match the source cadence",
                "Find an alternate source",
                "Accept the source data latency",
            ],
            priority=1,
        ))
    if "deadline_feasibility" in signals or "high_complexity" in signals:
        questions.append(ClarificationQuestion(
            field="scope_criteria",
            question="Which KPIs, sources, or roles belong in an MVP, and can delivery be phased?",
            rationale="A prioritized MVP or phased plan is required before the deadline can be validated.",
            suggested_replies=[
                "Start with an MVP",
                "Phase sources and KPIs",
                "Reduce roles and calculations",
            ],
            priority=1,
        ))
    if (
        "open_tickets_status_quality" in signals
        or "open_tickets_assignment_quality" in signals
    ):
        questions.append(ClarificationQuestion(
            field="data_or_system_challenges",
            question="Who will validate the active-ticket definition and treatment of blank assigned groups?",
            rationale="OpenTickets status and assignment inconsistencies must be reconciled before analysis.",
            suggested_replies=[
                "The BI owner will validate definitions",
                "Exclude inconsistent records pending review",
                "Document a reconciliation rule",
            ],
            priority=1,
        ))
    return questions


def _question_is_answered(field_name: str, intake: IntakeData) -> bool:
    if field_name in {"success_or_validator", "success_definition"}:
        return bool(intake.success_definition or intake.accuracy_owner_or_validator)
    if field_name in {"requester_or_owner", "requester"}:
        return bool(intake.requester or intake.armada_owner)
    if field_name == "requester_email":
        return bool(intake.requester_email or intake.requester_email_unavailable)
    if field_name == "metrics_kpis_charts_maps":
        return bool(intake.metrics_kpis_charts_maps or intake.required_fields)
    return has_value(getattr(intake, field_name, None))


def _apply_rls_role_rules(message: str, intake: IntakeData, correction: CorrectionPlan) -> None:
    text = _normalized(message)
    lower = text.lower()
    regional = bool(
        re.search(
            r"\b(?:regional\s+)?managers?\b.{0,80}\b(?:only\s+)?see\b"
            r".{0,50}\b(?:their|own|assigned)\b.{0,20}\bregion\b",
            lower,
        )
    )
    executives = bool(
        re.search(r"\bexecutives?\b.{0,60}\bsee\b.{0,30}\ball\s+regions?\b", lower)
    )
    if not (regional or executives):
        return
    roles: list[str] = []
    rules: list[str] = []
    if regional:
        roles.append("Regional managers")
        rules.append("regional managers limited to their assigned region")
    if executives:
        roles.append("Executives")
        rules.append("executives have all-region access")
    intake.recipients_or_access_roles = " and ".join(roles)
    intake.data_story_by_recipient_role = "; ".join(rules)
    intake.row_level_security = "Required: " + "; ".join(rules) + "."
    correction.explicit_fields.update({
        "recipients_or_access_roles",
        "data_story_by_recipient_role",
        "row_level_security",
    })


def _apply_self_service_rules(
    message: str,
    intake: IntakeData,
    correction: CorrectionPlan,
) -> None:
    """Map access-request language into the existing public intake schema."""
    text = _normalized(message)
    lower = text.lower()

    role_match = re.search(
        r"(?:^|[.;]\s*)([A-Za-z][A-Za-z0-9 &'/-]{1,70}?)\s+"
        r"(?:need|needs|require|requires)\s+"
        r"(?:(?:ongoing|temporary|permanent|read[- ]only)\s+)*access\b",
        text,
        re.IGNORECASE,
    )
    if not role_match:
        role_match = re.search(
            r"\baccess\s+(?:for|to be granted to)\s+([^.;,]+)",
            text,
            re.IGNORECASE,
        )
    if role_match:
        intake.recipients_or_access_roles = role_match.group(1).strip()
        correction.explicit_fields.add("recipients_or_access_roles")

    dataset_match = re.search(
        r"\b(?:access\s+to|dataset(?: is|:)?|semantic model(?: is|:)?)\s+"
        r"(?:the\s+)?([^.;,]{2,90}?(?:semantic model|dataset))\b",
        text,
        re.IGNORECASE,
    )
    if dataset_match:
        value = dataset_match.group(1).strip()
        if value.lower() not in {"power bi semantic model", "semantic model", "dataset"}:
            intake.data_sources = value
        elif not intake.data_sources:
            intake.data_sources = value
        correction.explicit_fields.add("data_sources")

    purpose_match = re.search(
        r"\b(?:business purpose(?: is|:)?|so (?:i|we|they) can|in order to)\s+"
        r"([^.;]+)",
        text,
        re.IGNORECASE,
    )
    if purpose_match:
        intake.why_report_necessary = purpose_match.group(1).strip()
        correction.explicit_fields.add("why_report_necessary")

    scope_match = re.search(
        r"\b(?:data|access)\s+scope(?: is|:)?\s+([^.;]+)",
        text,
        re.IGNORECASE,
    )
    if scope_match:
        intake.scope_criteria = scope_match.group(1).strip()
        correction.explicit_fields.add("scope_criteria")

    approver_match = re.search(
        r"\b(?:security|data)?\s*(?:approval owner|approver)"
        r"(?: is|:)?\s+([A-Z][A-Za-z' -]{1,60})(?=[,.;]|$)",
        text,
        re.IGNORECASE,
    )
    if approver_match:
        intake.armada_owner = approver_match.group(1).strip()
        intake.accuracy_owner_or_validator = (
            intake.accuracy_owner_or_validator or approver_match.group(1).strip()
        )
        correction.explicit_fields.update({
            "armada_owner",
            "accuracy_owner_or_validator",
        })

    duration_match = re.search(
        r"\b(?:access\s+)?(?:for|lasting)\s+"
        r"(\d+\s+(?:days?|weeks?|months?)|ongoing|permanent(?:ly)?)\b",
        lower,
    ) or re.search(
        r"\b(ongoing|permanent|temporary)(?:\s+read[- ]only)?\s+access\b",
        lower,
    )
    if duration_match:
        duration = duration_match.group(1)
        detail = f"Access duration: {duration}."
        if detail.lower() not in (intake.known_constraints or "").lower():
            intake.known_constraints = "; ".join(
                filter(None, [intake.known_constraints, detail])
            )
        correction.explicit_fields.add("known_constraints")

    if re.search(r"\bread[- ]only\b", lower):
        intake.row_level_security = "Required: read-only access for the approved role."
        correction.explicit_fields.add("row_level_security")


def _sanitize_deliverable_sources(message: str, previous: IntakeData, intake: IntakeData) -> None:
    if not intake.data_sources:
        return
    lower = _normalized(message).lower()
    generic_source_count = re.search(
        r"\b(\d+|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?:source systems?|data sources?)\b",
        lower,
    )
    explicitly_named = _mentioned_sources(message)
    if generic_source_count and not explicitly_named:
        intake.data_sources = previous.data_sources
        return
    sources = [part.strip() for part in intake.data_sources.split(",") if part.strip()]
    cleaned: list[str] = []
    for source in sources:
        normalized = source.lower()
        if normalized in {"excel", "csv"}:
            explicit_data_source = bool(re.search(
                rf"\b(from|using)\s+{re.escape(normalized)}\b|"
                rf"\b{re.escape(normalized)}\s+data\b",
                lower,
            ))
            if not explicit_data_source:
                continue
        if normalized == "jira":
            explicit_jira_source = bool(re.search(r"\b(from|using)\s+jira\b|\bjira\s+(data|tickets?)\b", lower))
            if not explicit_jira_source:
                continue
        cleaned.append(source)
    intake.data_sources = ", ".join(_unique(cleaned)) or previous.data_sources


def _mentioned_sources(message: str) -> list[str]:
    lower = message.lower()
    found: list[tuple[int, str]] = []
    for source in SOURCE_NAMES:
        match = re.search(
            rf"(?<!\w){re.escape(source.lower())}(?!\w)",
            lower,
        )
        if not match:
            continue
        position = match.start()
        normalized = source.lower()
        if normalized in {"excel", "csv"} and not re.search(
            rf"\b(from|using)\s+{re.escape(normalized)}\b|\b{re.escape(normalized)}\s+data\b",
            lower,
        ):
            continue
        if normalized == "jira" and not re.search(
            r"\b(from|using)\s+jira\b|\bjira\s+(data|tickets?)\b",
            lower,
        ):
            continue
        found.append((position, source))
    return _unique(source for _, source in sorted(found))


def _known_summary(intake: IntakeData) -> str:
    parts: list[str] = []
    if intake.request_type:
        parts.append(f"a {intake.request_type} request")
    if intake.recipients_or_access_roles:
        parts.append(f"for {intake.recipients_or_access_roles}")
    if intake.data_sources:
        parts.append(f"using {intake.data_sources}")
    return " ".join(parts)


def _source_cadence(challenges: str) -> str | None:
    match = re.search(
        r"\bsource(?: data)?(?: update cadence is| updates?| refreshes?)\s+"
        r"(hourly|daily|weekly|monthly|quarterly|real[- ]time)\b",
        challenges,
    )
    return match.group(1).replace("-", " ") if match else None


def _candidate_change_is_evidenced(
    field_name: str,
    candidate_value: Any,
    message: str,
) -> bool:
    """Require current-turn evidence before replacing an established fact."""
    lower = _normalized(message).lower()
    if re.search(
        r"\b(correction|instead(?: of)?|actually|only need|change(?: it)? to|"
        r"switch(?: it)? to)\b",
        lower,
    ):
        return True
    if isinstance(candidate_value, bool):
        if field_name == "requester_email_unavailable":
            return bool(re.search(r"\b(email unavailable|no email|email unknown)\b", lower))
        if field_name == "include_chat_attachment":
            return bool(re.search(r"\b(include|attach).{0,25}(chat|transcript)\b", lower))
        return False
    if isinstance(candidate_value, list):
        return all(str(item).lower() in lower for item in candidate_value)

    value = _normalized(str(candidate_value)).lower().strip(" .")
    if value and value in lower:
        return True
    if field_name == "data_sources":
        sources = [
            part.strip().lower()
            for part in re.split(r"[,;]", value)
            if part.strip()
        ]
        return bool(sources) and all(source in lower for source in sources)
    if field_name in {"refresh_frequency", "run_frequency"}:
        cadence = value.replace("-", " ")
        return cadence in lower or (
            cadence == "daily" and "every morning" in lower
        )
    if field_name == "request_type":
        aliases = {
            "data extract": ("extract", "excel file"),
            "metric analysis": ("analyze", "analyse", "understand why"),
            "bug/fix": ("bug", "fix", "broken", "incorrect", "wrong"),
        }
        return any(alias in lower for alias in aliases.get(value, (value,)))
    if field_name == "display_format":
        return any(
            token in lower
            for token in ("power bi", "dashboard", "report", "excel", "extract")
        )
    if field_name == "row_level_security":
        return bool(re.search(r"\b(row[- ]level security|rls|access rules?|read[- ]only)\b", lower))
    if field_name in {"known_constraints", "data_or_system_challenges"}:
        return bool(re.search(
            r"\b(source|upstream|cadence|refresh|constraint|dirty|duplicate|"
            r"inconsistent|opentickets|assigned group|resolved|reconciliation)\b",
            lower,
        ))
    if field_name in {"scope_criteria", "dependencies"}:
        return bool(re.search(
            r"\b(scope|filter|region|mvp|phase|dependency|data scope|access scope)\b",
            lower,
        ))
    return False


def _cadence_rank(value: str) -> int:
    return {
        "quarterly": 1,
        "monthly": 2,
        "weekly": 3,
        "daily": 4,
        "hourly": 5,
        "real time": 6,
    }.get(value.replace("-", " ").lower(), 0)


def _complexity_score(intake: IntakeData) -> int:
    score = 0
    metrics = f"{intake.metrics_kpis_charts_maps or ''} {intake.required_fields or ''}"
    kpi_count = _stated_count(metrics, r"\b({number})\s+kpis?\b")
    if kpi_count >= 20:
        score += 2

    named_sources = [
        part.strip()
        for part in re.split(r"[,;]", intake.data_sources or "")
        if part.strip()
    ]
    constraint_count = _stated_count(
        intake.known_constraints or "",
        r"\b({number})\s+(?:source systems?|data sources?)\b",
    )
    if max(len(named_sources), constraint_count) >= 3:
        score += 2

    if has_value(intake.custom_calculations_needed):
        score += 1

    rls_count = _stated_count(
        intake.row_level_security or "",
        r"\b({number})\s+roles?\b",
    )
    if rls_count >= 5:
        score += 2

    scope_text = " ".join(filter(None, [
        intake.scope_criteria,
        intake.why_report_necessary,
        intake.affected_business_unit,
    ])).lower()
    if re.search(r"\b(enterprise|global|company[- ]wide|all business units)\b", scope_text):
        score += 1
    return score


def _stated_count(text: str, pattern: str) -> int:
    number_pattern = (
        r"\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"twenty|thirty"
    )
    match = re.search(pattern.format(number=number_pattern), text, re.IGNORECASE)
    if not match:
        return 0
    value = match.group(1).lower()
    if value.isdigit():
        return int(value)
    return {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "twenty": 20,
        "thirty": 30,
    }.get(value, 0)


def _normalized(value: str) -> str:
    return " ".join(value.strip().split())


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
