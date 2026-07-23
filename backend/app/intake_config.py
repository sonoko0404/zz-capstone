from __future__ import annotations

from dataclasses import dataclass

from .models import ClarificationQuestion


NODE_DEFINITIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("report_title", "Report Title", ("report_title", "report_name")),
    ("purpose", "Purpose", ("why_report_necessary", "problems_addressed", "why_requested_now", "related_customers_or_teams")),
    ("business_decision", "Business Decision", ("decisions_supported", "expected_metric_change_or_time_savings")),
    ("audience", "Audience", ("requester", "requester_email", "requester_email_unavailable", "armada_owner", "recipients_or_access_roles", "data_story_by_recipient_role")),
    ("reporting_frequency", "Reporting Frequency", ("run_frequency", "run_time_of_day", "deadline")),
    ("scope_filters", "Scope and Filters", ("scope_criteria", "filters_needed", "drilldowns_needed", "existing_report_to_mimic")),
    ("required_data", "Required Data Fields", ("data_sources", "required_fields", "mockup_or_sample_available")),
    ("calculations_metrics", "Calculations and Metrics", ("custom_calculations_needed", "metrics_kpis_charts_maps")),
    ("display_format", "Display Format", ("display_format",)),
    ("row_level_security", "Row-Level Security", ("row_level_security",)),
    ("refresh_frequency", "Refresh Frequency", ("refresh_frequency",)),
    ("success_criteria", "Success Criteria", ("success_definition", "accuracy_owner_or_validator", "expected_metric_change_or_time_savings")),
    ("risks_assumptions", "Risks and Assumptions", ("data_or_system_challenges", "assumptions_about_data_entry", "dependencies", "known_constraints")),
)


EDITABLE_FIELDS = frozenset({
    "report_title", "report_name", "request_type", "scenario_type",
    "why_report_necessary", "decisions_supported", "problems_addressed",
    "why_requested_now", "related_customers_or_teams", "requester",
    "requester_email", "requester_email_unavailable", "armada_owner",
    "recipients_or_access_roles", "data_story_by_recipient_role",
    "run_frequency", "run_time_of_day", "scope_criteria",
    "existing_report_to_mimic", "filters_needed", "drilldowns_needed",
    "required_fields", "mockup_or_sample_available",
    "custom_calculations_needed", "display_format", "row_level_security",
    "metrics_kpis_charts_maps", "refresh_frequency",
    "accuracy_owner_or_validator", "success_definition",
    "expected_metric_change_or_time_savings", "data_or_system_challenges",
    "assumptions_about_data_entry", "dependencies", "known_constraints",
    "priority", "deadline", "data_sources", "affected_business_unit",
    "project_type_hint", "linked_ticket_hint", "jira_issue_type",
    "jira_labels", "include_chat_attachment",
})


FIELD_LABELS = {
    field: field.replace("_", " ").title()
    for field in EDITABLE_FIELDS
}


QUESTION_ORDER = (
    "decisions_supported",
    "why_report_necessary",
    "recipients_or_access_roles",
    "data_sources",
    "metrics_kpis_charts_maps",
    "success_or_validator",
    "scope_criteria",
    "display_format",
    "row_level_security",
    "refresh_frequency",
    "requester_or_owner",
    "requester_email",
    "jira_issue_type",
    "priority",
)


@dataclass(frozen=True)
class ScenarioProfile:
    required_groups: tuple[tuple[str, tuple[str, ...]], ...]
    recommended_fields: tuple[str, ...]
    question_order: tuple[str, ...]
    not_applicable_nodes: frozenset[str] = frozenset()
    can_generate_draft: bool = True


NEW_DASHBOARD_REQUIRED = (
    ("request_type", ("request_type",)),
    ("why_report_necessary", ("why_report_necessary", "decisions_supported")),
    ("recipients_or_access_roles", ("recipients_or_access_roles",)),
    ("data_sources", ("data_sources",)),
    ("metrics_kpis_charts_maps", ("metrics_kpis_charts_maps", "required_fields")),
    ("display_format", ("display_format",)),
    ("requester_or_owner", ("requester", "armada_owner")),
    ("success_or_validator", ("success_definition", "accuracy_owner_or_validator")),
)

DEFAULT_RECOMMENDED_FIELDS = (
    "refresh_frequency",
    "row_level_security",
    "scope_criteria",
    "deadline",
    "data_or_system_challenges",
    "existing_report_to_mimic",
    "priority",
)

SCENARIO_PROFILES = {
    "New Dashboard": ScenarioProfile(
        required_groups=NEW_DASHBOARD_REQUIRED,
        recommended_fields=DEFAULT_RECOMMENDED_FIELDS,
        question_order=QUESTION_ORDER,
    ),
    "Existing Report Issue": ScenarioProfile(
        required_groups=(
            ("request_type", ("request_type",)),
            ("existing_report_to_mimic", ("existing_report_to_mimic", "report_name", "report_title")),
            ("problems_addressed", ("problems_addressed", "why_report_necessary")),
            ("recipients_or_access_roles", ("recipients_or_access_roles",)),
            ("data_sources", ("data_sources",)),
            ("requester_or_owner", ("requester", "armada_owner")),
            ("success_or_validator", ("success_definition", "accuracy_owner_or_validator")),
        ),
        recommended_fields=(
            "scope_criteria",
            "refresh_frequency",
            "mockup_or_sample_available",
            "row_level_security",
            "deadline",
            "priority",
        ),
        question_order=(
            "existing_report_to_mimic",
            "problems_addressed",
            "scope_criteria",
            "recipients_or_access_roles",
            "data_sources",
            "success_or_validator",
            "requester_or_owner",
            "row_level_security",
            "priority",
        ),
    ),
    "Enhancement Request": ScenarioProfile(
        required_groups=(
            ("request_type", ("request_type",)),
            ("existing_report_to_mimic", ("existing_report_to_mimic", "report_name", "report_title")),
            (
                "scope_criteria",
                (
                    "scope_criteria",
                    "filters_needed",
                    "drilldowns_needed",
                    "custom_calculations_needed",
                    "metrics_kpis_charts_maps",
                ),
            ),
            ("recipients_or_access_roles", ("recipients_or_access_roles",)),
            ("data_sources", ("data_sources",)),
            ("requester_or_owner", ("requester", "armada_owner")),
            ("success_or_validator", ("success_definition", "accuracy_owner_or_validator")),
        ),
        recommended_fields=(
            "row_level_security",
            "refresh_frequency",
            "deadline",
            "data_or_system_challenges",
            "priority",
        ),
        question_order=(
            "existing_report_to_mimic",
            "scope_criteria",
            "recipients_or_access_roles",
            "data_sources",
            "row_level_security",
            "success_or_validator",
            "requester_or_owner",
            "deadline",
            "priority",
        ),
    ),
    "Self-Service Access": ScenarioProfile(
        required_groups=(
            ("request_type", ("request_type",)),
            ("why_report_necessary", ("why_report_necessary",)),
            ("recipients_or_access_roles", ("recipients_or_access_roles", "requester")),
            ("data_sources", ("data_sources",)),
            ("scope_criteria", ("scope_criteria", "required_fields")),
            ("requester_or_owner", ("armada_owner", "accuracy_owner_or_validator")),
        ),
        recommended_fields=(
            "known_constraints",
            "row_level_security",
            "deadline",
            "priority",
        ),
        question_order=(
            "recipients_or_access_roles",
            "data_sources",
            "why_report_necessary",
            "scope_criteria",
            "requester_or_owner",
            "known_constraints",
            "row_level_security",
            "priority",
        ),
        not_applicable_nodes=frozenset({
            "calculations_metrics",
            "display_format",
            "refresh_frequency",
        }),
    ),
    "Ambiguous Request": ScenarioProfile(
        required_groups=NEW_DASHBOARD_REQUIRED,
        recommended_fields=DEFAULT_RECOMMENDED_FIELDS,
        question_order=(
            "request_type",
            "why_report_necessary",
            "recipients_or_access_roles",
            "data_sources",
            "metrics_kpis_charts_maps",
            "requester_or_owner",
            "success_or_validator",
        ),
        can_generate_draft=False,
    ),
    "Unassigned": ScenarioProfile(
        required_groups=NEW_DASHBOARD_REQUIRED,
        recommended_fields=DEFAULT_RECOMMENDED_FIELDS,
        question_order=("request_type",),
        can_generate_draft=False,
    ),
}


def scenario_profile(scenario_type: str | None) -> ScenarioProfile:
    return SCENARIO_PROFILES.get(
        scenario_type or "Unassigned",
        SCENARIO_PROFILES["Unassigned"],
    )


QUESTION_SPECS = {
    "request_type": ClarificationQuestion(
        field="request_type",
        question="Is this a new deliverable, an issue with an existing report, an enhancement, or an access request?",
        rationale="The workflow type determines which requirements are relevant and prevents unrelated questions.",
        suggested_replies=[
            "New dashboard or report",
            "Existing report issue",
            "Enhancement request",
            "Self-service access",
        ],
        priority=1,
    ),
    "decisions_supported": ClarificationQuestion(
        field="decisions_supported",
        question="What business decision should this request help someone make?",
        rationale="The decision defines which insights matter and prevents a dashboard that only displays data.",
        suggested_replies=["Prioritize follow-up actions", "Compare performance across teams", "I’m not sure — help me define the decision"],
        priority=1,
    ),
    "why_report_necessary": ClarificationQuestion(
        field="why_report_necessary",
        question="What business problem or outcome makes this request necessary?",
        rationale="A clear purpose anchors scope, acceptance criteria, and delivery priority.",
        suggested_replies=["Reduce manual reporting", "Identify operational exceptions", "I’m not sure — help me frame the purpose"],
        priority=2,
    ),
    "recipients_or_access_roles": ClarificationQuestion(
        field="recipients_or_access_roles",
        question="Who will use this deliverable, and do different roles need different views?",
        rationale="Audience and access roles shape the data story, usability, and security design.",
        suggested_replies=["Managers", "Analysts and managers", "I’m not sure — help me identify the audience"],
        priority=3,
    ),
    "data_sources": ClarificationQuestion(
        field="data_sources",
        question="Which source system or dataset should provide the data?",
        rationale="The source determines field availability, ownership, data quality, and feasible refresh cadence.",
        suggested_replies=["Salesforce", "Power BI Data Agent context", "I’m not sure — help me identify it"],
        priority=4,
    ),
    "metrics_kpis_charts_maps": ClarificationQuestion(
        field="metrics_kpis_charts_maps",
        question="Which metrics, KPIs, or data fields must be included?",
        rationale="Required measures make scope testable and drive the eventual acceptance criteria.",
        suggested_replies=["Volume and trend", "Cycle time and exceptions", "I’m not sure — propose a starter set"],
        priority=5,
    ),
    "success_or_validator": ClarificationQuestion(
        field="success_definition",
        question="How will success be measured, or who should validate the result?",
        rationale="A measurable outcome or named validator is needed for acceptance and release readiness.",
        suggested_replies=["The business owner validates accuracy", "Reduce weekly manual effort", "I’m not sure — define this during review"],
        priority=6,
    ),
    "scope_criteria": ClarificationQuestion(
        field="scope_criteria",
        question="What scope, filters, or drilldowns should be included?",
        rationale="Scope boundaries prevent hidden requirements and make delivery estimates more reliable.",
        suggested_replies=["Filter by region and customer", "Current fiscal year only", "I’m not sure — confirm during refinement"],
        priority=7,
    ),
    "display_format": ClarificationQuestion(
        field="display_format",
        question="What output format do you need?",
        rationale="The delivery format affects interaction design, export behavior, and implementation effort.",
        suggested_replies=["Power BI dashboard", "Scheduled report", "Excel extract"],
        priority=8,
    ),
    "row_level_security": ClarificationQuestion(
        field="row_level_security",
        question="Are row-level security rules required?",
        rationale="Access rules must be explicit before data is exposed to different audiences.",
        suggested_replies=["Not required", "Required by business unit", "I’m not sure — needs security review"],
        priority=9,
    ),
    "refresh_frequency": ClarificationQuestion(
        field="refresh_frequency",
        question="How often should the data refresh?",
        rationale="Refresh cadence must align with source availability and business decision timing.",
        suggested_replies=["Daily", "Weekly", "Match the source system cadence"],
        priority=10,
    ),
    "requester_or_owner": ClarificationQuestion(
        field="requester",
        question="Who is the requester or accountable business owner?",
        rationale="A named owner is required for decisions, validation, and future Jira traceability.",
        suggested_replies=["I am the requester", "A business owner will be assigned", "I’m not sure — confirm later"],
        priority=11,
    ),
    "requester_email": ClarificationQuestion(
        field="requester_email",
        question="What requester email should appear in the draft descriptions?",
        rationale="The confirmed Jira handoff requires requester name and email in both ticket descriptions.",
        suggested_replies=["I’ll provide a sanitized demo email", "Email unavailable", "I’m not sure — confirm before validation"],
        priority=12,
    ),
    "jira_issue_type": ClarificationQuestion(
        field="jira_issue_type",
        question="Is a Jira Issue Type known for this request?",
        rationale="Issue Type is required for the future BIM ticket, but valid values are not yet confirmed.",
        suggested_replies=["To be confirmed by Jira integration", "I’ll provide a confirmed value", "I’m not sure"],
        priority=13,
    ),
    "priority": ClarificationQuestion(
        field="priority",
        question="What priority should the draft propose?",
        rationale="Priority is one of the confirmed required BIM Jira fields.",
        suggested_replies=["Low", "Medium", "High"],
        priority=14,
    ),
    "deadline": ClarificationQuestion(
        field="deadline",
        question="When is this request needed?",
        rationale="A requested date supports prioritization and feasibility review without promising delivery.",
        suggested_replies=[
            "Within two weeks",
            "By the next business review",
            "No fixed deadline",
        ],
        priority=14,
    ),
    "existing_report_to_mimic": ClarificationQuestion(
        field="existing_report_to_mimic",
        question="Which existing report or dashboard is affected?",
        rationale="A clear report identity is required to investigate or enhance the correct deliverable.",
        suggested_replies=[
            "Weekly operations dashboard",
            "I’ll provide the report name",
            "The report identifier is not yet known",
        ],
        priority=1,
    ),
    "problems_addressed": ClarificationQuestion(
        field="problems_addressed",
        question="What is the actual behavior, and what result did you expect instead?",
        rationale="Expected-versus-actual behavior makes an existing-report issue reproducible and testable.",
        suggested_replies=[
            "Totals differ from the source",
            "The latest refresh is missing",
            "I’ll provide a sanitized example",
        ],
        priority=2,
    ),
    "known_constraints": ClarificationQuestion(
        field="known_constraints",
        question="How long is access needed, and are there any known access constraints?",
        rationale="Access duration and constraints are needed for a reviewable self-service request.",
        suggested_replies=[
            "Ongoing access",
            "Temporary access for 90 days",
            "Duration to be confirmed",
        ],
        priority=6,
    ),
}


SCENARIO_QUESTION_OVERRIDES = {
    "Existing Report Issue": {
        "scope_criteria": ClarificationQuestion(
            field="scope_criteria",
            question="Which users, dates, regions, or refresh runs are affected, and can the issue be reproduced safely?",
            rationale="Affected scope and reproducibility help distinguish a localized data issue from a broader defect.",
            suggested_replies=[
                "All users after the latest refresh",
                "One region only",
                "I’ll provide a sanitized reproduction",
            ],
            priority=3,
        ),
    },
    "Enhancement Request": {
        "scope_criteria": ClarificationQuestion(
            field="scope_criteria",
            question="What exact change should be added, and what should remain unchanged?",
            rationale="A bounded enhancement scope prevents an existing dashboard change from becoming an unplanned rebuild.",
            suggested_replies=[
                "Add one filter only",
                "Add a drilldown without changing metrics",
                "I’ll define the acceptance scope",
            ],
            priority=2,
        ),
        "data_sources": ClarificationQuestion(
            field="data_sources",
            question="Will the enhancement use the current data source, or require a new source?",
            rationale="Source impact determines whether the change is a visual enhancement or new data engineering work.",
            suggested_replies=[
                "Use the current source",
                "A new source is required",
                "Source impact is unknown",
            ],
            priority=4,
        ),
    },
    "Self-Service Access": {
        "recipients_or_access_roles": ClarificationQuestion(
            field="recipients_or_access_roles",
            question="Which user or role needs access?",
            rationale="Access must be tied to a specific user population or business role.",
            suggested_replies=[
                "Business analysts",
                "Regional managers",
                "I’ll provide the requester and role",
            ],
            priority=1,
        ),
        "data_sources": ClarificationQuestion(
            field="data_sources",
            question="Which dataset or Power BI semantic model is requested?",
            rationale="The requested data asset determines ownership and the required access review.",
            suggested_replies=[
                "Power BI semantic model",
                "A named certified dataset",
                "The dataset name is not yet known",
            ],
            priority=2,
        ),
        "why_report_necessary": ClarificationQuestion(
            field="why_report_necessary",
            question="What business purpose requires this self-service access?",
            rationale="A documented business purpose is needed before a data-access request can be reviewed.",
            suggested_replies=[
                "Build a team report",
                "Perform approved ad hoc analysis",
                "Support a recurring business review",
            ],
            priority=3,
        ),
        "scope_criteria": ClarificationQuestion(
            field="scope_criteria",
            question="What data scope should the user be allowed to access?",
            rationale="The approved scope should be no broader than the stated business need.",
            suggested_replies=[
                "One business unit",
                "Assigned regions only",
                "Scope requires security review",
            ],
            priority=4,
        ),
        "requester_or_owner": ClarificationQuestion(
            field="armada_owner",
            question="Who is the security or data owner responsible for approving access?",
            rationale="A named approval owner is required for a controlled access request.",
            suggested_replies=[
                "The dataset owner",
                "The business data steward",
                "Approval owner to be confirmed",
            ],
            priority=5,
        ),
    },
}


def question_spec(scenario_type: str | None, key: str) -> ClarificationQuestion:
    override = SCENARIO_QUESTION_OVERRIDES.get(scenario_type or "", {}).get(key)
    return (override or QUESTION_SPECS[key]).model_copy(deep=True)
