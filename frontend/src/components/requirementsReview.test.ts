import { describe, expect, it } from 'vitest'
import type { IntakeData, RequirementNode } from '../types/intake'
import {
  buildAiSummary,
  deriveReviewMilestone,
  groupRequirementNodes,
  messageMatchesEvidence,
} from './requirementsReview'

function node(overrides: Partial<RequirementNode> & Pick<RequirementNode, 'key' | 'display_name'>): RequirementNode {
  return {
    fields: [],
    summary: 'No information captured yet',
    status: 'Missing',
    requirement_level: 'optional',
    required_fields: [],
    confidence: 'n/a',
    source: 'not_provided',
    filled_fields: 0,
    total_fields: 1,
    ...overrides,
  }
}

function intake(overrides: Partial<IntakeData> = {}): IntakeData {
  return {
    report_title: null,
    report_name: null,
    request_type: null,
    scenario_type: 'New Dashboard',
    why_report_necessary: null,
    decisions_supported: null,
    problems_addressed: null,
    why_requested_now: null,
    related_customers_or_teams: null,
    requester: null,
    requester_email: null,
    requester_email_unavailable: false,
    armada_owner: null,
    recipients_or_access_roles: null,
    data_story_by_recipient_role: null,
    run_frequency: null,
    run_time_of_day: null,
    scope_criteria: null,
    existing_report_to_mimic: null,
    filters_needed: null,
    drilldowns_needed: null,
    required_fields: null,
    mockup_or_sample_available: null,
    custom_calculations_needed: null,
    display_format: null,
    row_level_security: null,
    metrics_kpis_charts_maps: null,
    refresh_frequency: null,
    accuracy_owner_or_validator: null,
    success_definition: null,
    expected_metric_change_or_time_savings: null,
    data_or_system_challenges: null,
    assumptions_about_data_entry: null,
    dependencies: null,
    known_constraints: null,
    priority: null,
    deadline: null,
    data_sources: null,
    affected_business_unit: null,
    project_type_hint: null,
    linked_ticket_hint: null,
    jira_issue_type: null,
    jira_labels: [],
    include_chat_attachment: false,
    confidence_score: 0,
    missing_fields: [],
    risk_flags: [],
    ...overrides,
  }
}

describe('groupRequirementNodes', () => {
  it('puts unresolved required sections before confirmed sections', () => {
    const sections = groupRequirementNodes([
      node({
        key: 'purpose',
        display_name: 'Purpose',
        fields: ['why_report_necessary'],
        status: 'Filled',
        requirement_level: 'required',
        filled_fields: 1,
      }),
      node({
        key: 'audience',
        display_name: 'Audience',
        fields: ['recipients_or_access_roles'],
        status: 'Needs Confirmation',
        requirement_level: 'required',
        required_fields: ['recipients_or_access_roles'],
      }),
    ], intake({ recipients_or_access_roles: 'Sales managers' }), {}, ['recipients_or_access_roles'])

    expect(sections[0].label).toBe('Audience')
    expect(sections[0].needsAttention).toBe(true)
    expect(sections.find((section) => section.label === 'Purpose')?.needsAttention).toBe(false)
  })
})

describe('buildAiSummary', () => {
  it('summarizes the request and names the most important review gaps', () => {
    const summary = buildAiSummary(
      intake({
        recipients_or_access_roles: 'Sales managers',
        display_format: 'Power BI dashboard',
        metrics_kpis_charts_maps: 'weekly unit sales',
        data_sources: 'Salesforce',
      }),
      ['Frequency', 'Success Criteria'],
    )

    expect(summary).toContain('Sales managers')
    expect(summary).toContain('weekly unit sales')
    expect(summary).toContain('Salesforce')
    expect(summary).toContain('Frequency and Success Criteria')
  })
})

describe('deriveReviewMilestone', () => {
  it('shows an AI draft awaiting BI validation when a draft exists', () => {
    expect(deriveReviewMilestone({
      hasIntake: true,
      completionScore: 82,
      readyForTicket: true,
      validationReady: false,
      validationState: 'draft_ready',
      hasDraft: true,
    })).toEqual({
      title: 'AI Draft Complete',
      detail: 'Awaiting BI validation',
    })
  })

  it('shows ready for BI review when validation requirements are met', () => {
    expect(deriveReviewMilestone({
      hasIntake: true,
      completionScore: 92,
      readyForTicket: true,
      validationReady: true,
      validationState: 'draft_ready',
      hasDraft: true,
    }).title).toBe('Ready for BI Review')
  })
})

describe('messageMatchesEvidence', () => {
  it('matches evidence despite case and whitespace differences', () => {
    expect(messageMatchesEvidence(
      'Sales managers need visibility into weekly unit sales.',
      'sales managers   need visibility',
    )).toBe(true)
  })

  it('does not match unrelated conversation text', () => {
    expect(messageMatchesEvidence(
      'The dashboard should refresh daily.',
      'Sales managers need visibility.',
    )).toBe(false)
  })
})
