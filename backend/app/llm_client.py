from __future__ import annotations

import json
import logging
import os
import re
from time import perf_counter
from abc import ABC, abstractmethod
from typing import Any

from .intake_config import (
    DEFAULT_RECOMMENDED_FIELDS,
    EDITABLE_FIELDS,
    NEW_DASHBOARD_REQUIRED,
    question_spec,
    scenario_profile,
)
from .intake_workflow import has_value, utc_now
from .knowledge_base import KnowledgeBase
from .models import (
    ClarificationQuestion,
    FieldMetadata,
    FieldMetadataUpdate,
    IntakeData,
    LLMIntakeResult,
    LLMModelOutput,
    TranscriptMessage,
)


logger = logging.getLogger(__name__)


MINIMUM_GROUPS = list(NEW_DASHBOARD_REQUIRED)
RECOMMENDED_FIELDS = list(DEFAULT_RECOMMENDED_FIELDS)

ALLOWED_SCENARIOS = {
    "New Dashboard",
    "Ambiguous Request",
    "Existing Report Issue",
    "Enhancement Request",
    "Self-Service Access",
    "Unassigned",
}


def classify_scenario(message: str, intake: IntakeData) -> str:
    """Classify workflow shape separately from the requested deliverable type."""
    lower = message.lower()
    if re.search(r"\b(access|permission|permissions|credential|credentials|self[- ]service)\b", lower):
        return "Self-Service Access"
    if re.search(r"\b(broken|bug|error|incorrect|wrong|mismatch|not matching|stopped working|fails?)\b", lower):
        return "Existing Report Issue"
    if re.search(r"\b(enhance|enhancement|add|change|extend|modify|new filter|new metric)\b", lower) and re.search(
        r"\b(existing|current|dashboard|report)\b", lower
    ):
        return "Enhancement Request"
    current = intake.scenario_type
    if current in {"New Dashboard", "Existing Report Issue", "Enhancement Request", "Self-Service Access"}:
        return current
    if (
        re.search(r"\b(dashboard|report|data extract|analysis|power bi)\b", lower)
        or intake.request_type in {"dashboard", "report", "data extract", "metric analysis"}
    ):
        if len(message.split()) <= 4 or not (
            intake.why_report_necessary
            or intake.decisions_supported
            or intake.metrics_kpis_charts_maps
            or intake.required_fields
        ):
            return "Ambiguous Request"
        return "New Dashboard"
    if current == "Ambiguous Request" and intake.request_type and (
        intake.why_report_necessary
        or intake.decisions_supported
        or intake.metrics_kpis_charts_maps
        or intake.required_fields
    ):
        return "New Dashboard"
    if current in {"Ambiguous Request", "Unassigned"}:
        return current
    if len(message.split()) <= 5:
        return "Ambiguous Request"
    return "Unassigned"


def select_questions(intake: IntakeData, missing: list[str]) -> list[ClarificationQuestion]:
    """Return the highest-value unanswered business questions, never more than three."""
    missing_set = set(missing)
    profile = scenario_profile(intake.scenario_type)

    def unanswered(key: str) -> bool:
        if key == "request_type":
            return intake.scenario_type in {"Ambiguous Request", "Unassigned"} or not intake.request_type
        if key == "success_or_validator":
            return not (intake.success_definition or intake.accuracy_owner_or_validator)
        if key == "requester_or_owner":
            if intake.scenario_type == "Self-Service Access":
                return not (intake.armada_owner or intake.accuracy_owner_or_validator)
            return not (intake.requester or intake.armada_owner)
        if key == "requester_email":
            return not (intake.requester_email or intake.requester_email_unavailable)
        if key == "metrics_kpis_charts_maps":
            return not (intake.metrics_kpis_charts_maps or intake.required_fields)
        if key == "existing_report_to_mimic":
            return not (
                intake.existing_report_to_mimic
                or intake.report_name
                or intake.report_title
            )
        if key == "problems_addressed":
            return not (intake.problems_addressed or intake.why_report_necessary)
        if key in {"why_report_necessary", "recipients_or_access_roles", "data_sources", "display_format"}:
            return key in missing_set or not has_value(getattr(intake, key, None))
        return not has_value(getattr(intake, key, None))

    ordered_unanswered = [key for key in profile.question_order if unanswered(key)]
    required_keys = [
        key
        for key in ordered_unanswered
        if key in missing_set
        or (
            key == "request_type"
            and intake.scenario_type in {"Ambiguous Request", "Unassigned"}
        )
    ]
    optional_keys = [key for key in ordered_unanswered if key not in required_keys]
    return [
        question_spec(intake.scenario_type, key)
        for key in (required_keys + optional_keys)
    ][:3]


def metadata_for_changes(
    before: dict[str, Any],
    updated: IntakeData,
    message: str,
) -> dict[str, FieldMetadata]:
    """Attach auditable evidence to fields changed by deterministic extraction."""
    changes: dict[str, FieldMetadata] = {}
    now = utc_now()
    evidence = " ".join(message.strip().split())[:280]
    for field in EDITABLE_FIELDS:
        previous = before.get(field)
        value = getattr(updated, field, None)
        if previous == value or not has_value(value):
            continue
        if field in {"project_type_hint"}:
            source, confidence = "inferred", "medium"
        elif field == "scenario_type":
            source, confidence = (
                ("needs_confirmation", "low")
                if value in {"Ambiguous Request", "Unassigned"}
                else ("inferred", "medium")
            )
        elif field == "jira_issue_type" and value == "To be confirmed by Jira integration":
            source, confidence = "needs_confirmation", "low"
        elif field in {"metrics_kpis_charts_maps", "required_fields"} and (
            "definitions pending" in str(value).lower()
        ):
            source, confidence = "needs_confirmation", "low"
        elif field == "report_title" and not re.search(r"\b(title|named|called)\b", message, re.IGNORECASE):
            source, confidence = "inferred", "medium"
        else:
            source, confidence = "user_provided", "high"
        changes[field] = FieldMetadata(
            confidence=confidence,
            source=source,
            evidence=evidence,
            updated_at=now,
        )
    return changes


def _has_value(intake: IntakeData, fields: tuple[str, ...]) -> bool:
    return any(bool(getattr(intake, field, None)) for field in fields)


def score_intake(intake: IntakeData) -> tuple[int, list[str], bool]:
    profile = scenario_profile(intake.scenario_type)
    groups = profile.required_groups
    recommended = profile.recommended_fields
    missing_minimum = [label for label, fields in groups if not _has_value(intake, fields)]
    minimum_filled = len(groups) - len(missing_minimum)
    recommended_missing = [field for field in recommended if not getattr(intake, field)]
    score = round((minimum_filled / len(groups)) * 80) if groups else 80
    score += (
        round(((len(recommended) - len(recommended_missing)) / len(recommended)) * 20)
        if recommended
        else 20
    )
    ready = profile.can_generate_draft and not missing_minimum
    return min(score, 100), missing_minimum + recommended_missing, ready


def detect_risks(message: str, intake: IntakeData) -> list[str]:
    lower = message.lower()
    risks: list[str] = []
    if not intake.data_sources:
        risks.append("Data source is not yet defined.")
    if not (intake.requester or intake.armada_owner):
        risks.append("Requester or accountable owner is missing.")
    if not (intake.success_definition or intake.accuracy_owner_or_validator):
        risks.append("Success criteria or validation owner is missing.")
    if not intake.row_level_security:
        risks.append("Row-level security requirements are not yet defined.")
    if re.search(r"\b(dirty|noisy|duplicate|inconsistent|unreliable|mismatch)\w*\b", lower):
        risks.append("Potential dirty or inconsistent source data requires validation.")
    if "daily" in lower and re.search(r"(source|system|data).{0,35}(monthly|once a month)", lower):
        risks.append("Requested daily refresh conflicts with a source that updates monthly.")
    if re.search(r"\b(ssn|social security|patient|medical record|credit card|personal data|pii)\b", lower):
        risks.append("Potential sensitive data: use sanitized or aggregate data in this prototype.")
    if re.search(r"\b(whatever|just do it|you decide|don't care)\b", lower):
        risks.append("User intent is underspecified; confirmation is required before drafting.")
    return list(dict.fromkeys(risks))


class IntakeLLMClient(ABC):
    provider_name = "deterministic"
    model_name: str | None = None
    configured = False

    @abstractmethod
    def analyze(
        self,
        message: str,
        current: IntakeData,
        knowledge: KnowledgeBase,
        last_question_fields: list[str],
        field_metadata: dict[str, FieldMetadata] | None = None,
        recent_transcript: list[TranscriptMessage] | None = None,
        already_cited_context: list[str] | None = None,
    ) -> LLMIntakeResult:
        raise NotImplementedError


class DeterministicMockLLM(IntakeLLMClient):
    """Predictable keyword/rule engine used when no API key is configured."""

    SOURCE_NAMES = [
        "Salesforce", "Snowflake", "SAP", "Oracle", "Jira", "OpenTickets",
        "E1_Tickets", "E2_Linked Tickets", "E3_Change Log", "WMS", "Red Prairie",
        "Excel", "CSV", "Microsoft Fabric", "Power BI semantic model", "ERP", "CRM",
        "Power BI Data Agent",
    ]

    def __init__(self, fallback_reason: str | None = None) -> None:
        self.fallback_reason = fallback_reason

    def analyze(
        self,
        message: str,
        current: IntakeData,
        knowledge: KnowledgeBase,
        last_question_fields: list[str],
        field_metadata: dict[str, FieldMetadata] | None = None,
        recent_transcript: list[TranscriptMessage] | None = None,
        already_cited_context: list[str] | None = None,
    ) -> LLMIntakeResult:
        del field_metadata, recent_transcript, already_cited_context
        before = current.model_dump()
        updated = current.model_copy(deep=True)
        self._extract(message, updated, last_question_fields)
        updated.scenario_type = classify_scenario(message, updated)
        if updated.scenario_type == "Existing Report Issue":
            updated.request_type = "bug/fix"
        elif updated.scenario_type == "Self-Service Access":
            updated.request_type = "other"
            updated.project_type_hint = "BIM"
            updated.display_format = None
            updated.metrics_kpis_charts_maps = None
            updated.refresh_frequency = None
            updated.run_frequency = None
        elif updated.scenario_type == "Enhancement Request" and not updated.request_type:
            updated.request_type = "other"
        if not updated.jira_issue_type and updated.request_type:
            updated.jira_issue_type = "To be confirmed by Jira integration"
        score, missing, ready = score_intake(updated)
        risks = list(dict.fromkeys(current.risk_flags + detect_risks(message, updated)))
        updated.missing_fields = missing
        updated.risk_flags = risks
        updated.confidence_score = round(score / 100, 2)
        questions = select_questions(updated, missing)
        context_used = self._context_used(message, updated)
        metadata_changes = metadata_for_changes(before, updated, message)
        metadata_updates = [
            FieldMetadataUpdate(field=field, **metadata.model_dump())
            for field, metadata in metadata_changes.items()
        ]
        ambiguous = sorted(
            field for field, metadata in metadata_changes.items()
            if metadata.source == "needs_confirmation" or metadata.confidence == "low"
        )

        if ready:
            assistant = (
                "The minimum intake requirements are complete. I prepared a draft BIM ticket preview "
                "using the provided static context. No real Jira ticket was created."
            )
        else:
            known = self._known_summary(updated)
            prefix = f"I’ve captured {known}. " if known else "I can help structure this BI request. "
            assistant = prefix + "To complete the intake, please clarify:\n" + "\n".join(
                f"{index}. {question.question}" for index, question in enumerate(questions, start=1)
            )
        if any("sensitive data" in risk.lower() for risk in risks):
            assistant += "\nPlease use sanitized or aggregate data only; do not upload sensitive records to this prototype."

        return LLMIntakeResult(
            assistant_message=assistant,
            scenario_type=updated.scenario_type,
            updated_intake=updated,
            field_metadata_updates=metadata_updates,
            missing_fields=missing,
            ambiguous_fields=ambiguous,
            completion_score=score,
            ready_for_ticket=ready,
            risk_flags=risks,
            context_used=context_used,
            next_questions=questions,
            llm_provider="deterministic",
            fallback_reason=self.fallback_reason,
        )

    def _extract(self, message: str, intake: IntakeData, last_fields: list[str]) -> None:
        text = " ".join(message.strip().split())
        lower = text.lower()

        request_types = [
            ("bug", "bug/fix"), ("fix", "bug/fix"), ("data extract", "data extract"),
            ("extract", "data extract"), ("metric analysis", "metric analysis"),
            ("understand why", "metric analysis"), ("analy", "metric analysis"),
            ("dashboard", "dashboard"), ("report", "report"),
        ]
        for keyword, value in request_types:
            if keyword in lower:
                intake.request_type = intake.request_type or value
                break
        if intake.request_type == "metric analysis" and not intake.display_format:
            intake.display_format = "Metric analysis"

        if "power bi" in lower:
            intake.display_format = (
                "Power BI dashboard"
                if "dashboard" in lower or intake.request_type == "dashboard"
                else intake.display_format or "Power BI report"
            )
        elif "dashboard" in lower:
            intake.display_format = intake.display_format or "Dashboard"
        elif re.search(r"\bexcel\b", lower):
            intake.display_format = "Excel"
        elif "report" in lower:
            intake.display_format = intake.display_format or "Report"

        sources = [
            name
            for name in self.SOURCE_NAMES
            if re.search(
                rf"(?<!\w){re.escape(name.lower())}(?!\w)",
                lower,
            )
        ]
        if sources:
            intake.data_sources = ", ".join(dict.fromkeys(sources))

        audience_patterns = [
            r"\bfor\s+([^.,;]+?)(?=\s+to\s+|\s+so\s+|\s+using\s+|\s+within\s+|\s+by\s+|[.,;]|$)",
            r"\bused by\s+([^.,;]+)",
            r"\baudience(?: is|:)?\s+([^.,;]+)",
            r"(?:^|[.;]\s*)([A-Za-z][A-Za-z'& -]{1,50}?)\s+"
            r"(?:need|needs|require|requires)\s+(?:ongoing\s+|temporary\s+)?access\b",
        ]
        for pattern in audience_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                preceding = lower[max(0, match.start() - 30):match.start()]
                if (
                    re.fullmatch(r"(?:\d+|one|two|three|four|five|ten|twelve)\s+roles?", candidate, re.IGNORECASE)
                    and re.search(r"\brls\b|row[- ]level security", preceding)
                ):
                    continue
                if 1 <= len(candidate.split()) <= 12:
                    intake.recipients_or_access_roles = candidate
                    break

        metric_patterns = [
            r"\b(?:track|analy[sz]e|monitor|measure|compare|report on)\s+"
            r"(.+?)(?=\s+for\s+|\s+from\s+|\s+using\s+|\s+within\s+|[,.;]|$)",
            r"\bshow(?:ing)?\s+(.+?)(?=\s+for\s+|\s+from\s+|\s+using\s+|[,.;]|$)",
            r"\bunderstand\s+(.+?)(?=[.;]|$)",
            r"\b(?:using|include(?:s|d)?|including|with)\s+"
            r"(.+?)\s+(?:metrics?|kpis?)\b(?=[,.;]|$)",
            r"\bmetrics?(?: are| include|:)?\s+(.+?)(?=[.;]|$)",
            r"\bkpis?(?: are| include|:)?\s+(.+?)(?=[.;]|$)",
            r"\bfields?(?: are| include|:)?\s+(.+?)(?=[.;]|$)",
        ]
        for pattern in metric_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                metric = match.group(1).strip(" ,")
                for source_name in sorted(self.SOURCE_NAMES, key=len, reverse=True):
                    metric = re.sub(
                        rf"^{re.escape(source_name)}(?:\s+data)?\s+",
                        "",
                        metric,
                        flags=re.IGNORECASE,
                    )
                if (
                    "kpi" in match.group(0).lower()
                    and re.fullmatch(
                        r"\d+|one|two|three|four|five|ten|twenty|thirty",
                        metric,
                        re.IGNORECASE,
                    )
                ):
                    continue
                if metric:
                    intake.metrics_kpis_charts_maps = metric
                    intake.required_fields = intake.required_fields or metric
                    break
        kpi_count = re.search(
            r"\b(\d+|one|two|three|four|five|ten|twenty|thirty)\s+kpis?\b",
            lower,
        )
        if kpi_count and not intake.metrics_kpis_charts_maps:
            intake.metrics_kpis_charts_maps = (
                f"{kpi_count.group(1).title()} KPIs (definitions pending)"
            )
            intake.required_fields = intake.required_fields or intake.metrics_kpis_charts_maps

        deadline = re.search(
            r"\bwithin\s+(\d+|one|two|three|four)\s+"
            r"(business\s+)?(day|week|month)s?\b",
            lower,
        )
        if deadline:
            intake.deadline = deadline.group(0)
        relative_deadline = re.search(
            r"\b(?:by\s+)?(tomorrow|next\s+(?:monday|tuesday|wednesday|thursday|friday)|"
            r"eod|end of day|asap)\b",
            lower,
        )
        if relative_deadline:
            intake.deadline = relative_deadline.group(0)
        by_date = re.search(
            r"\bby\s+((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
            r"[a-z]*\s+\d{1,2}(?:,?\s+\d{4})?)",
            text,
            re.IGNORECASE,
        )
        if by_date:
            intake.deadline = f"by {by_date.group(1)}"

        cadence_pattern = r"(hourly|daily|weekly|monthly|quarterly|real[- ]time)"
        refresh = re.search(
            rf"\b{cadence_pattern}\s+(?:data\s+)?refresh\b",
            lower,
        )
        if refresh:
            intake.refresh_frequency = refresh.group(1).replace("-", " ").title()
            intake.run_frequency = intake.run_frequency or intake.refresh_frequency
        elif re.search(rf"\brefresh(?:ed)?\s+{cadence_pattern}\b", lower):
            value = re.search(rf"\brefresh(?:ed)?\s+{cadence_pattern}\b", lower)
            if value:
                intake.refresh_frequency = value.group(1).title()
                intake.run_frequency = intake.run_frequency or intake.refresh_frequency
        else:
            deliverable_cadence = re.search(
                rf"\b{cadence_pattern}\s+(?:\w+\s+)?"
                r"(?:dashboard|report|extract|analysis)\b",
                lower,
            )
            if deliverable_cadence:
                intake.refresh_frequency = (
                    deliverable_cadence.group(1).replace("-", " ").title()
                )
                intake.run_frequency = intake.run_frequency or intake.refresh_frequency
        if re.search(r"\bevery\s+morning\b", lower):
            intake.refresh_frequency = "Daily"
            intake.run_frequency = "Daily"
            intake.run_time_of_day = "Morning"
        if re.search(r"\bone[- ]time\s+(?:excel\s+)?extract\b", lower):
            intake.run_frequency = "One-time"
            intake.refresh_frequency = None

        if re.search(r"\b(no|without)\s+(row[- ]level security|rls)\b", lower):
            intake.row_level_security = "Not required"
        elif "row-level security" in lower or re.search(r"\brls\b", lower):
            role_count = re.search(r"\b(\d+)\s+roles?\b", lower)
            intake.row_level_security = (
                f"Required for {role_count.group(1)} roles; mappings need confirmation"
                if role_count
                else "Required; role rules need confirmation"
            )

        requester = re.search(
            r"\b(?:requester(?: is|:)?|requested by)\s+"
            r"([A-Z][A-Za-z' -]{1,40}?)"
            r"(?=\s+and\s+(?:the\s+)?(?:owner|validator|approver)\b|[,.;]|$)",
            text,
            re.IGNORECASE,
        )
        if requester:
            intake.requester = requester.group(1).strip()
        owner = re.search(
            r"\b(?:(?:business |armada |accountable )?owner(?: is|:)?|owned by)\s+"
            r"([A-Z][A-Za-z' -]{1,40}?)"
            r"(?=\s+and\s+[A-Za-z' -]{1,40}\s+(?:will\s+)?validates?\b|[,.;]|$)",
            text,
            re.IGNORECASE,
        )
        if owner:
            intake.armada_owner = owner.group(1).strip()
        approval_owner = re.search(
            r"\b(?:security|data)?\s*(?:approval owner|approver)"
            r"(?: is|:)?\s+([A-Z][A-Za-z' -]{1,40})(?=[,.;]|$)",
            text,
            re.IGNORECASE,
        )
        if approval_owner:
            intake.armada_owner = approval_owner.group(1).strip()
        if re.search(r"\bi(?:'m| am) the requester\b", lower):
            intake.requester = intake.requester or "Session user"

        email = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.IGNORECASE)
        if email:
            intake.requester_email = email.group(0)
            intake.requester_email_unavailable = False
        elif re.search(r"\b(email (?:is )?unavailable|no email|email unknown)\b", lower):
            intake.requester_email = None
            intake.requester_email_unavailable = True

        issue_type = re.search(r"\bjira issue type(?: is|:)?\s+([^,.;]+)", text, re.IGNORECASE)
        if issue_type:
            intake.jira_issue_type = issue_type.group(1).strip()
        labels = re.search(r"\b(?:jira )?labels?(?: are| include|:)?\s+([^.;]+)", text, re.IGNORECASE)
        if labels:
            intake.jira_labels = [part.strip() for part in re.split(r"[,;]", labels.group(1)) if part.strip()][:12]
        if re.search(r"\b(include|attach).{0,25}(chat|transcript)\b|\bchat\.txt\b", lower):
            intake.include_chat_attachment = True

        validator = re.search(
            r"\bvalidat(?:e|ed|ion)\s+(?:by|owner is)\s+([^.,;]+)",
            text,
            re.IGNORECASE,
        )
        if validator:
            intake.accuracy_owner_or_validator = validator.group(1).strip()
        role_validator = re.search(
            r"\b(BI lead|finance|data owner|business owner|report owner|owner)\s+"
            r"(?:will\s+)?validates?\b(?:\s+([^.;]+))?",
            text,
            re.IGNORECASE,
        )
        named_validator = re.search(
            r"\b([A-Z][a-z'&-]+(?:\s+[A-Z][a-z'&-]+){0,2})\s+"
            r"(?:will\s+)?validates?\b(?:\s+([^.;]+))?",
            text,
        )
        active_validator = role_validator or named_validator
        if active_validator:
            validator_name = active_validator.group(1).strip()
            validation_target = (active_validator.group(2) or "the result").strip()
            validation_statement = f"{validator_name} validates {validation_target}"
            if validator_name.lower() == "owner":
                intake.success_definition = intake.success_definition or validation_statement
            else:
                intake.accuracy_owner_or_validator = validator_name
                intake.success_definition = intake.success_definition or validation_statement
        success = re.search(r"\bsuccess(?: means| is|:)?\s+([^.;]+)", text, re.IGNORECASE)
        if success:
            intake.success_definition = success.group(1).strip()
        outcome = re.search(r"\b(reduce|save|improve|increase|decrease)\s+([^.;]+)", text, re.IGNORECASE)
        if outcome and not intake.success_definition:
            intake.success_definition = outcome.group(0).strip()
            intake.expected_metric_change_or_time_savings = outcome.group(0).strip()

        if "similar to" in lower or "mimic" in lower:
            mimic = re.search(r"(?:similar to|mimic)\s+(.+?)(?=[.;]|$)", text, re.IGNORECASE)
            intake.existing_report_to_mimic = mimic.group(1).strip() if mimic else text
        existing_report = re.search(
            r"\b(?:the|our)\s+((?:existing\s+|current\s+)?"
            r"[^.;]{0,70}?(?:dashboard|report))\b",
            text,
            re.IGNORECASE,
        )
        if existing_report and re.search(
            r"\b(existing|current|wrong|incorrect|broken|error|enhance|add|change|modify)\b",
            lower,
        ):
            intake.existing_report_to_mimic = (
                intake.existing_report_to_mimic
                or existing_report.group(1).strip()
            )
        if re.search(
            r"\b(broken|bug|error|incorrect|wrong|mismatch|not matching|"
            r"stopped working|fails?)\b",
            lower,
        ):
            intake.problems_addressed = intake.problems_addressed or text

        filter_match = re.search(r"\bfilter(?:ed|s)?\s+(?:by|to|for)\s+([^.;]+)", text, re.IGNORECASE)
        if filter_match:
            intake.filters_needed = filter_match.group(1).strip()
            intake.scope_criteria = intake.scope_criteria or f"Filtered by {filter_match.group(1).strip()}"
        data_scope = re.search(
            r"\b(?:data|access)\s+scope(?: is|:)?\s+([^.;]+)",
            text,
            re.IGNORECASE,
        )
        if data_scope:
            intake.scope_criteria = data_scope.group(1).strip()
        if "drilldown" in lower or "drill-down" in lower:
            drill = re.search(r"drill-?downs?\s+(?:by|to)?\s*([^.;]+)", text, re.IGNORECASE)
            intake.drilldowns_needed = drill.group(1).strip() if drill and drill.group(1) else "Required"

        priority = re.search(r"\b(urgent|high|medium|low)\s+priority\b", lower)
        if priority:
            intake.priority = priority.group(1).title()

        linked = re.findall(r"\b(?:SCP|ITO|BIM|CC)-\d+\b", text, re.IGNORECASE)
        if linked:
            intake.linked_ticket_hint = ", ".join(value.upper() for value in linked)

        if re.search(r"\b(dirty|noisy|duplicate|inconsistent|unreliable|mismatch)\w*\b", lower):
            intake.data_or_system_challenges = "Source data may be dirty, inconsistent, or require reconciliation."
        source_update = re.search(
            r"\bsource(?: data| system)?\s+"
            r"(?:updates?|refreshes?|is updated|supports?)\s+"
            r"(hourly|daily|weekly|monthly|quarterly|real[- ]time)\b",
            lower,
        )
        if source_update:
            source_cadence = source_update.group(1).replace("-", " ").title()
            intake.data_or_system_challenges = (
                f"Source data updates {source_cadence.lower()}."
            )
            known = re.sub(
                r"\s*Source update cadence is unknown\.\s*",
                " ",
                intake.known_constraints or "",
                flags=re.IGNORECASE,
            ).strip()
            intake.known_constraints = _append_detail(
                known or None,
                f"Source update cadence is {source_cadence.lower()}.",
            )
        if re.search(
            r"\b(?:do not|don't)\s+know\s+(?:how often|when)\s+"
            r"(?:the\s+)?source(?:\s+system)?\s+(?:updates|refreshes)\b",
            lower,
        ):
            intake.known_constraints = _append_detail(
                intake.known_constraints,
                "Source update cadence is unknown.",
            )
        source_count = re.search(
            r"\b(\d+|three|four|five|six|seven|eight|nine|ten)\s+"
            r"(?:source systems?|data sources?)\b",
            lower,
        )
        if source_count:
            intake.known_constraints = _append_detail(
                intake.known_constraints,
                f"{source_count.group(1).title()} source systems are required; "
                "specific systems are not yet identified.",
            )
        if "custom calculations" in lower:
            intake.custom_calculations_needed = "Required; definitions pending"
        if re.search(
            r"\b(mvp|phase[ds]?|phased delivery|reduced scope|"
            r"scope reduced|prioriti[sz]ed|staged delivery)\b",
            lower,
        ):
            intake.scope_criteria = _append_detail(
                intake.scope_criteria,
                f"Feasibility mitigation: {text}",
            )
        if "opentickets" in lower and re.search(
            r"\bresolved\b.{0,80}\b(open|active|opentickets)\b|"
            r"\b(open|active|opentickets)\b.{0,80}\bresolved\b",
            lower,
        ):
            intake.data_or_system_challenges = _append_detail(
                intake.data_or_system_challenges,
                "OpenTickets contains a Resolved versus active/open status inconsistency.",
            )
        if "opentickets" in lower and re.search(
            r"\bassigned groups?\b.{0,40}\b(blank|empty|missing)\b|"
            r"\b(blank|empty|missing)\b.{0,40}\bassigned groups?\b",
            lower,
        ):
            intake.data_or_system_challenges = _append_detail(
                intake.data_or_system_challenges,
                "Assigned group values are blank in some OpenTickets records.",
            )
        if re.search(
            r"\b(data quality|duplicates?|inconsisten(?:cy|cies)|reconciliation)\b"
            r".{0,60}\b(resolved|reconciled|removed|confirmed)\b",
            lower,
        ):
            intake.data_or_system_challenges = (
                "Data-quality reconciliation and validation approach confirmed."
            )
        if re.search(
            r"\b(active[- ]ticket definition|assigned[- ]group treatment)\b"
            r".{0,60}\b(validated|confirmed|resolved)\b",
            lower,
        ):
            intake.data_or_system_challenges = (
                "OpenTickets status and assigned-group reconciliation confirmed."
            )
        access_duration = re.search(
            r"\b(?:access\s+)?(?:for|lasting)\s+"
            r"(\d+\s+(?:days?|weeks?|months?)|ongoing|permanent(?:ly)?)\b",
            lower,
        )
        if not access_duration:
            access_duration = re.search(
                r"\b(ongoing|permanent|temporary)\s+access\b",
                lower,
            )
        if access_duration and (
            "access" in lower or intake.scenario_type == "Self-Service Access"
        ):
            intake.known_constraints = _append_detail(
                intake.known_constraints,
                f"Access duration: {access_duration.group(1)}.",
            )

        if not intake.why_report_necessary and len(text.split()) >= 5 and re.search(
            r"\b(need|build|create|understand|analy|track|show|access|monitor|measure)\w*\b",
            lower,
        ):
            intake.why_report_necessary = text
        if not intake.report_title and (intake.metrics_kpis_charts_maps or intake.request_type):
            core = intake.metrics_kpis_charts_maps or intake.request_type or "BI request"
            intake.report_title = (
                f"{intake.request_type.capitalize()} request"
                if core == intake.request_type
                else f"{core[:90].strip().capitalize()} — {intake.request_type or 'BI request'}"
            )
        if intake.request_type in {"dashboard", "report", "data extract", "metric analysis"}:
            intake.project_type_hint = "BIM"

        self._use_prompted_short_answer(text, lower, intake, last_fields)

    def _use_prompted_short_answer(self, text: str, lower: str, intake: IntakeData, fields: list[str]) -> None:
        if len(fields) != 1 or len(text.split()) > 18:
            return
        field = fields[0]
        if field == "data_sources" and not intake.data_sources:
            intake.data_sources = text
        elif field == "recipients_or_access_roles" and not intake.recipients_or_access_roles:
            intake.recipients_or_access_roles = text
        elif field == "metrics_kpis_charts_maps" and not intake.metrics_kpis_charts_maps:
            intake.metrics_kpis_charts_maps = text
            intake.required_fields = text
        elif field in {"requester_or_owner", "requester"} and not (
            intake.requester or intake.armada_owner
        ):
            intake.requester = text
        elif field == "armada_owner" and not intake.armada_owner:
            intake.armada_owner = text
        elif field in {"success_or_validator", "success_definition"} and not (
            intake.success_definition or intake.accuracy_owner_or_validator
        ):
            intake.success_definition = text
        elif field == "why_report_necessary" and not intake.why_report_necessary:
            intake.why_report_necessary = text
        elif field == "scope_criteria" and not intake.scope_criteria:
            intake.scope_criteria = text
        elif field == "known_constraints" and not intake.known_constraints:
            intake.known_constraints = (
                f"Access duration/constraint: {text}"
                if intake.scenario_type == "Self-Service Access"
                else text
            )
        elif field == "existing_report_to_mimic" and not intake.existing_report_to_mimic:
            intake.existing_report_to_mimic = text
        elif field == "problems_addressed" and not intake.problems_addressed:
            intake.problems_addressed = text
        elif field == "display_format" and not intake.display_format:
            intake.display_format = text
        elif field == "refresh_frequency" and not intake.refresh_frequency:
            cadence = re.search(
                r"\b(hourly|daily|weekly|monthly|quarterly|real[- ]time)\b",
                lower,
            )
            if cadence:
                intake.refresh_frequency = cadence.group(1).replace("-", " ").title()
                intake.run_frequency = intake.run_frequency or intake.refresh_frequency
        elif field == "request_type" and not intake.request_type:
            intake.request_type = lower

    def _context_used(self, message: str, intake: IntakeData) -> list[str]:
        lower = message.lower()
        context: list[str] = []
        # Only cite BIM when the turn is about delivery/reporting work, not on every reply.
        # Session-level dedupe in IntakeEngine still suppresses repeats across turns.
        if (
            intake.request_type
            or re.search(r"\bbi\b", lower)
            or any(token in lower for token in ("dashboard", "report", "power bi", "intake", "ticket", "jira"))
        ):
            context.append("BIM is the likely delivery category for BI/report work.")
        if "open" in lower or "backlog" in lower:
            context.append("OpenTickets is preferred for active backlog and ticket-age questions.")
        if "link" in lower or (
            intake.linked_ticket_hint and any(token in lower for token in ("link", "scp", "ito", "trace"))
        ):
            context.append("E2_Linked Tickets describes BIM → SCP/ITO traceability.")
        if "long" in lower or "bottleneck" in lower or "resolve" in lower:
            context.append("E3_Change Log supports workflow and bottleneck analysis.")
            context.append("E1_Tickets supports historical ticket-level analysis.")
        if "power bi data agent" in lower or "data agent" in lower:
            context.append("The user selected the provided static Power BI Data Agent context; no live connection is implied.")
        return context

    def _known_summary(self, intake: IntakeData) -> str:
        parts = []
        if intake.request_type:
            parts.append(f"a {intake.request_type} request")
        if intake.recipients_or_access_roles:
            parts.append(f"for {intake.recipients_or_access_roles}")
        if intake.data_sources:
            parts.append(f"using {intake.data_sources}")
        return " ".join(parts)


class OpenAIIntakeLLM(IntakeLLMClient):
    """OpenAI-compatible structured-output client with safe deterministic fallback."""

    provider_name = "openai"
    configured = True

    def __init__(self, api_key: str, model: str, fallback: DeterministicMockLLM) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.model_name = model
        self._fallback = fallback

    def analyze(
        self,
        message: str,
        current: IntakeData,
        knowledge: KnowledgeBase,
        last_question_fields: list[str],
        field_metadata: dict[str, FieldMetadata] | None = None,
        recent_transcript: list[TranscriptMessage] | None = None,
        already_cited_context: list[str] | None = None,
    ) -> LLMIntakeResult:
        # Seed obvious fields deterministically before the model call. This keeps
        # multi-turn state stable while the OpenAI model handles interpretation,
        # concise acknowledgement, and context-aware question selection.
        preprocessed_result = self._fallback.analyze(
            message,
            current,
            knowledge,
            last_question_fields,
            field_metadata,
            recent_transcript,
            already_cited_context,
        )
        preprocessed = preprocessed_result.updated_intake
        already_cited = already_cited_context or []
        active_profile = scenario_profile(preprocessed.scenario_type)
        profile_required = [
            {"label": label, "fields": list(fields)}
            for label, fields in active_profile.required_groups
        ]
        system = f"""You are a concise guided intake assistant for BI, report, dashboard, data extract, and metric-analysis requests.
Return a response that strictly matches the provided structured-output schema.

Rules:
- Extract only information explicitly supplied or safely implied by the requested deliverable.
- The current_intake includes server-side pre-extraction. Preserve its non-null fields unless the user explicitly corrects them.
- Preserve fields marked user_confirmed in field_metadata unless the user clearly corrects them.
- Classify scenario_type independently from request_type using exactly one of: New Dashboard, Ambiguous Request, Existing Report Issue, Enhancement Request, Self-Service Access, Unassigned.
- For each field you add or change, return field_metadata_updates with confidence, source, short evidence from the user message, and updated_at. Inferences must not be marked user_provided.
- Ask only the most important 1-3 missing questions; prioritize source, audience, metrics, owner, and success/validation.
- Each next_questions item must include field, plain-language question, why it matters, up to 4 suggested replies, and priority.
- Acknowledge what was newly captured before asking the next questions.
- Speak naturally to the business user. Do not mention confidence scores, raw field names, project_type_hint, extraction mechanics, or JSON.
- "Power BI Data Agent" means the provided static semantic-model context. It may be recorded as a data source/context descriptor, but never describe it as a live connection.
- BIM is normally the delivery category for BI work. E2 links may suggest BIM to SCP/ITO traceability.
- context_used must list only newly relevant static-context notes for THIS turn. Do not repeat items from already_cited_context. If nothing new applies, return an empty list.
- Never claim live access to or action in Armada, Jira, Power BI, Fabric, Azure, or Copilot Studio.
- Never claim a real ticket was created. Recommend sanitized/aggregate data for sensitive requests.
- Do not invent Jira project configuration, Jira Issue Type values, relationship types, Armada policies, source fields, or ticket IDs. Use "To be confirmed by Jira integration" for unknown Jira configuration.
- Treat the following as static context, not live facts:
{knowledge.prompt_context()}

Active scenario: {preprocessed.scenario_type or "Unassigned"}
Server-owned required groups for this scenario: {json.dumps(profile_required)}
Server-owned question order: {json.dumps(active_profile.question_order)}
Do not ask dashboard KPI, display-format, or refresh questions for Self-Service Access.
"""
        user_payload: dict[str, Any] = {
            "message": message,
            "current_intake": preprocessed.model_dump(),
            "last_question_fields": last_question_fields,
            "already_cited_context": already_cited,
            "field_metadata": {
                key: value.model_dump() for key, value in (field_metadata or {}).items()
            },
            "recent_transcript": [
                entry.model_dump() for entry in (recent_transcript or [])[-6:]
            ],
        }
        started_at = perf_counter()
        try:
            # Newer SDKs expose chat.completions.parse directly; the pinned SDK
            # exposes the same Structured Outputs helper under beta.chat.
            parse = getattr(self._client.chat.completions, "parse", None)
            if parse is None:
                parse = self._client.beta.chat.completions.parse
            response = parse(
                model=self._model,
                temperature=0.1,
                response_format=LLMModelOutput,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(user_payload)},
                ],
            )
            parsed = response.choices[0].message.parsed
            if parsed is None:
                refusal = response.choices[0].message.refusal or "The model returned no parsed output."
                raise ValueError(refusal)
            result = LLMIntakeResult(
                **parsed.model_dump(),
                llm_provider="openai",
                llm_model=response.model or self._model,
                llm_request_id=response.id,
                llm_latency_ms=round((perf_counter() - started_at) * 1000),
            )
            # Recompute hard safety/scoring fields server-side instead of trusting
            # a model to decide when ticket generation is allowed.
            merged = preprocessed.model_copy(update={
                key: value
                for key, value in result.updated_intake.model_dump().items()
                if value not in (None, "", [], {})
            })
            scenario = result.scenario_type if result.scenario_type in ALLOWED_SCENARIOS else preprocessed.scenario_type
            merged.scenario_type = scenario or classify_scenario(message, merged)
            score, missing, ready = score_intake(merged)
            risks = list(dict.fromkeys(result.risk_flags + detect_risks(message, merged)))
            assistant_message = result.assistant_message
            questions = result.next_questions[:3]
            if not questions and not ready:
                questions = select_questions(merged, missing)
            if questions and not ready and not any(question.question in assistant_message for question in questions):
                assistant_message = assistant_message.rstrip() + "\n" + "\n".join(
                    f"{index}. {question.question}"
                    for index, question in enumerate(questions, start=1)
                )
            if ready or re.search(
                r"\b(created|submitted|sent|pushed|connected)\b.{0,50}\b(real\s+)?(jira|ticket|power bi|fabric|azure|copilot)",
                assistant_message,
                re.IGNORECASE,
            ):
                assistant_message = (
                    "The minimum intake requirements are complete. I prepared a local draft ticket preview. "
                    "No real Jira ticket was created and no enterprise system was accessed."
                    if ready
                    else "This prototype can structure the request and prepare a local draft only; it did not access or write to an enterprise system."
                )
            if any("sensitive data" in risk.lower() for risk in risks):
                assistant_message += " Please use sanitized or aggregate data only."
            merged.missing_fields = missing
            merged.risk_flags = risks
            merged.confidence_score = round(score / 100, 2)
            metadata_updates_by_field = {
                item.field: item for item in preprocessed_result.field_metadata_updates
            }
            metadata_updates_by_field.update({
                item.field: item for item in result.field_metadata_updates
                if item.field in EDITABLE_FIELDS
            })
            metadata_updates = list(metadata_updates_by_field.values())
            ambiguous = sorted(set(result.ambiguous_fields) | {
                item.field for item in metadata_updates
                if item.source in {"inferred", "needs_confirmation"} or item.confidence == "low"
            })
            return result.model_copy(update={
                "assistant_message": assistant_message,
                "scenario_type": merged.scenario_type,
                "updated_intake": merged,
                "field_metadata_updates": metadata_updates,
                "missing_fields": missing,
                "ambiguous_fields": ambiguous,
                "completion_score": score,
                "ready_for_ticket": ready,
                "risk_flags": risks,
                "next_questions": questions,
            })
        except Exception as exc:
            # Preserve the original product requirement to fall back safely, but
            # make the transition observable in logs and in the API response.
            reason = _fallback_reason(exc)
            logger.warning(
                "OpenAI intake failed; using deterministic fallback (%s)",
                reason,
                exc_info=True,
            )
            fallback = self._fallback.analyze(
                message,
                current,
                knowledge,
                last_question_fields,
                field_metadata,
                recent_transcript,
                already_cited_context,
            )
            return fallback.model_copy(update={
                "llm_model": self._model,
                "llm_latency_ms": round((perf_counter() - started_at) * 1000),
                "fallback_reason": reason,
            })


class ClaudeIntakeLLM(IntakeLLMClient):
    """Anthropic Claude client with tool-enforced JSON and deterministic fallback."""

    provider_name = "claude"
    configured = True

    def __init__(
        self,
        api_key: str,
        model: str,
        fallback: DeterministicMockLLM,
        *,
        timeout: float = 120.0,
    ) -> None:
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key, timeout=timeout)
        self._model = model
        self.model_name = model
        self._fallback = fallback

    def analyze(
        self,
        message: str,
        current: IntakeData,
        knowledge: KnowledgeBase,
        last_question_fields: list[str],
        field_metadata: dict[str, FieldMetadata] | None = None,
        recent_transcript: list[TranscriptMessage] | None = None,
        already_cited_context: list[str] | None = None,
    ) -> LLMIntakeResult:
        preprocessed_result = self._fallback.analyze(
            message,
            current,
            knowledge,
            last_question_fields,
            field_metadata,
            recent_transcript,
            already_cited_context,
        )
        preprocessed = preprocessed_result.updated_intake
        already_cited = already_cited_context or []
        system = f"""You are a concise guided intake assistant for BI, report, dashboard, data extract, and metric-analysis requests.
Call the submit_intake_result tool with a complete intake analysis for this turn.

Rules:
- Extract only information explicitly supplied or safely implied by the requested deliverable.
- The current_intake includes server-side pre-extraction. Preserve its non-null fields unless the user explicitly corrects them.
- Preserve fields marked user_confirmed in field_metadata unless the user clearly corrects them.
- Classify scenario_type independently from request_type using exactly one of: New Dashboard, Ambiguous Request, Existing Report Issue, Enhancement Request, Self-Service Access, Unassigned.
- For each field you add or change, return field_metadata_updates with confidence, source, short evidence from the user message, and updated_at. Inferences must not be marked user_provided.
- Ask only the most important 1-3 missing questions; prioritize source, audience, metrics, owner, and success/validation.
- Each next_questions item must include field, plain-language question, why it matters, up to 4 suggested replies, and priority.
- Acknowledge what was newly captured before asking the next questions.
- Speak naturally to the business user. Do not mention confidence scores, raw field names, project_type_hint, extraction mechanics, or JSON.
- "Power BI Data Agent" means the provided static semantic-model context. It may be recorded as a data source/context descriptor, but never describe it as a live connection.
- BIM is normally the delivery category for BI work. E2 links may suggest BIM to SCP/ITO traceability.
- context_used must list only newly relevant static-context notes for THIS turn. Do not repeat items from already_cited_context. If nothing new applies, return an empty list.
- Never claim live access to or action in Armada, Jira, Power BI, Fabric, Azure, or Copilot Studio.
- Never claim a real ticket was created. Recommend sanitized/aggregate data for sensitive requests.
- Do not invent Jira project configuration, Jira Issue Type values, relationship types, Armada policies, source fields, or ticket IDs. Use "To be confirmed by Jira integration" for unknown Jira configuration.
- Treat the following as static context, not live facts:
{knowledge.prompt_context()}
"""
        user_payload: dict[str, Any] = {
            "message": message,
            "current_intake": preprocessed.model_dump(),
            "last_question_fields": last_question_fields,
            "already_cited_context": already_cited,
            "field_metadata": {
                key: value.model_dump() for key, value in (field_metadata or {}).items()
            },
            "recent_transcript": [
                {"role": entry.role, "content": entry.content}
                for entry in (recent_transcript or [])[-6:]
            ],
        }
        started_at = perf_counter()
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                temperature=0.2,
                system=system,
                tools=[
                    {
                        "name": "submit_intake_result",
                        "description": "Submit the structured BI intake analysis for this conversation turn.",
                        "input_schema": _claude_tool_schema(),
                    }
                ],
                tool_choice={"type": "tool", "name": "submit_intake_result"},
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Analyze this intake turn and call submit_intake_result.\n"
                            + json.dumps(user_payload, ensure_ascii=False)
                        ),
                    }
                ],
            )
            tool_input: dict[str, Any] | None = None
            for block in response.content:
                if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "submit_intake_result":
                    tool_input = dict(block.input)
                    break
            if tool_input is None:
                # Fallback: try parsing plain text JSON if the model ignored tools.
                text = "".join(
                    getattr(block, "text", "")
                    for block in response.content
                    if getattr(block, "type", None) == "text"
                ).strip()
                if not text:
                    raise ValueError("Claude returned no tool payload and no text content.")
                tool_input = json.loads(_extract_json_payload(text))

            parsed = LLMModelOutput.model_validate(tool_input)
            result = LLMIntakeResult(
                **parsed.model_dump(),
                llm_provider="claude",
                llm_model=response.model or self._model,
                llm_request_id=response.id,
                llm_latency_ms=round((perf_counter() - started_at) * 1000),
            )
            return _finalize_cloud_result(
                message=message,
                preprocessed=preprocessed,
                preprocessed_result=preprocessed_result,
                result=result,
            )
        except Exception as exc:
            reason = _fallback_reason(exc)
            logger.warning(
                "Claude intake failed; using deterministic fallback (%s)",
                reason,
                exc_info=True,
            )
            fallback = self._fallback.analyze(
                message,
                current,
                knowledge,
                last_question_fields,
                field_metadata,
                recent_transcript,
                already_cited_context,
            )
            return fallback.model_copy(update={
                "llm_provider": "deterministic",
                "llm_model": self._model,
                "llm_latency_ms": round((perf_counter() - started_at) * 1000),
                "fallback_reason": reason,
            })


def _claude_tool_schema() -> dict[str, Any]:
    """JSON Schema for Claude tool_use, derived from the intake response model."""
    schema = LLMModelOutput.model_json_schema()
    # Anthropic expects a root object schema; keep $defs for $ref resolution.
    if schema.get("type") != "object":
        return {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
            "additionalProperties": False,
        }
    schema.setdefault("additionalProperties", False)
    return schema


def _extract_json_payload(text: str) -> str:
    """Pull the first JSON object from a model reply."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = cleaned.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("No JSON object found in model response.")
    return cleaned[start : end + 1]


def _finalize_cloud_result(
    *,
    message: str,
    preprocessed: IntakeData,
    preprocessed_result: LLMIntakeResult,
    result: LLMIntakeResult,
) -> LLMIntakeResult:
    """Recompute scoring/safety fields server-side for any cloud LLM provider."""
    merged = preprocessed.model_copy(update={
        key: value
        for key, value in result.updated_intake.model_dump().items()
        if value not in (None, "", [], {})
    })
    scenario = result.scenario_type if result.scenario_type in ALLOWED_SCENARIOS else preprocessed.scenario_type
    merged.scenario_type = scenario or classify_scenario(message, merged)
    score, missing, ready = score_intake(merged)
    risks = list(dict.fromkeys(result.risk_flags + detect_risks(message, merged)))
    assistant_message = result.assistant_message
    questions = result.next_questions[:3]
    if not questions and not ready:
        questions = select_questions(merged, missing)
    if questions and not ready and not any(question.question in assistant_message for question in questions):
        assistant_message = assistant_message.rstrip() + "\n" + "\n".join(
            f"{index}. {question.question}"
            for index, question in enumerate(questions, start=1)
        )
    if ready or re.search(
        r"\b(created|submitted|sent|pushed|connected)\b.{0,50}\b(real\s+)?(jira|ticket|power bi|fabric|azure|copilot)",
        assistant_message,
        re.IGNORECASE,
    ):
        assistant_message = (
            "The minimum intake requirements are complete. I prepared a local draft ticket preview. "
            "No real Jira ticket was created and no enterprise system was accessed."
            if ready
            else "This prototype can structure the request and prepare a local draft only; it did not access or write to an enterprise system."
        )
    if any("sensitive data" in risk.lower() for risk in risks):
        assistant_message += " Please use sanitized or aggregate data only."
    merged.missing_fields = missing
    merged.risk_flags = risks
    merged.confidence_score = round(score / 100, 2)
    metadata_updates_by_field = {
        item.field: item for item in preprocessed_result.field_metadata_updates
    }
    metadata_updates_by_field.update({
        item.field: item for item in result.field_metadata_updates
        if item.field in EDITABLE_FIELDS
    })
    metadata_updates = list(metadata_updates_by_field.values())
    ambiguous = sorted(set(result.ambiguous_fields) | {
        item.field for item in metadata_updates
        if item.source in {"inferred", "needs_confirmation"} or item.confidence == "low"
    })
    return result.model_copy(update={
        "assistant_message": assistant_message,
        "scenario_type": merged.scenario_type,
        "updated_intake": merged,
        "field_metadata_updates": metadata_updates,
        "missing_fields": missing,
        "ambiguous_fields": ambiguous,
        "completion_score": score,
        "ready_for_ticket": ready,
        "risk_flags": risks,
        "next_questions": questions,
    })


def _fallback_reason(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    details = " ".join(str(exc).split())[:240]
    parts = [type(exc).__name__]
    if status:
        parts.append(f"HTTP {status}")
    if code:
        parts.append(str(code))
    if details:
        parts.append(details)
    return ": ".join(parts)


def _append_detail(existing: str | None, detail: str) -> str:
    if not existing:
        return detail
    if detail.lower() in existing.lower():
        return existing
    return f"{existing.rstrip()} {detail}"


def create_llm_client() -> IntakeLLMClient:
    fallback = DeterministicMockLLM()
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    anthropic_key = (
        os.getenv("ANTHROPIC_API_KEY", "").strip()
        or os.getenv("CLAUDE_API_KEY", "").strip()
    )
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    use_claude = provider in {"claude", "anthropic"}
    if not provider and anthropic_key and not openai_key:
        use_claude = True

    if use_claude:
        if not anthropic_key:
            return DeterministicMockLLM(
                "LLM_PROVIDER=claude but ANTHROPIC_API_KEY is not configured in backend/.env"
            )
        model = os.getenv("ANTHROPIC_MODEL", os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")).strip()
        return ClaudeIntakeLLM(anthropic_key, model, fallback)

    if not openai_key:
        return DeterministicMockLLM("OPENAI_API_KEY is not configured in backend/.env")
    return OpenAIIntakeLLM(
        api_key=openai_key,
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        fallback=fallback,
    )
