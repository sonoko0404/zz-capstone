from __future__ import annotations

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


QUESTION_SPECS = {
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
}
