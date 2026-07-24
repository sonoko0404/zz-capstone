export interface IntakeData {
  report_title: string | null
  report_name: string | null
  request_type: string | null
  scenario_type: string | null
  why_report_necessary: string | null
  decisions_supported: string | null
  problems_addressed: string | null
  why_requested_now: string | null
  related_customers_or_teams: string | null
  requester: string | null
  requester_email: string | null
  requester_email_unavailable: boolean
  armada_owner: string | null
  recipients_or_access_roles: string | null
  data_story_by_recipient_role: string | null
  run_frequency: string | null
  run_time_of_day: string | null
  scope_criteria: string | null
  existing_report_to_mimic: string | null
  filters_needed: string | null
  drilldowns_needed: string | null
  required_fields: string | null
  mockup_or_sample_available: string | null
  custom_calculations_needed: string | null
  display_format: string | null
  row_level_security: string | null
  metrics_kpis_charts_maps: string | null
  refresh_frequency: string | null
  accuracy_owner_or_validator: string | null
  success_definition: string | null
  expected_metric_change_or_time_savings: string | null
  data_or_system_challenges: string | null
  assumptions_about_data_entry: string | null
  dependencies: string | null
  known_constraints: string | null
  priority: string | null
  deadline: string | null
  data_sources: string | null
  affected_business_unit: string | null
  project_type_hint: string | null
  linked_ticket_hint: string | null
  jira_issue_type: string | null
  jira_labels: string[]
  include_chat_attachment: boolean
  confidence_score: number
  missing_fields: string[]
  risk_flags: string[]
}

export type EditableIntakeField = Exclude<keyof IntakeData, 'confidence_score' | 'missing_fields' | 'risk_flags'>
export type FieldSource = 'user_provided' | 'inferred' | 'needs_confirmation' | 'not_provided' | 'user_confirmed'
export type FieldConfidence = 'high' | 'medium' | 'low' | 'n/a'

export interface FieldMetadata {
  confidence: FieldConfidence
  source: FieldSource
  evidence: string | null
  updated_at: string | null
}

export interface ClarificationQuestion {
  field: string
  question: string
  rationale: string
  suggested_replies: string[]
  priority: number
}

export interface RequirementNode {
  key: string
  display_name: string
  fields: string[]
  summary: string
  status: 'Filled' | 'Missing' | 'Needs Confirmation' | 'N/A'
  confidence: FieldConfidence
  source: FieldSource
  filled_fields: number
  total_fields: number
}

export interface TicketPreview {
  draft_ticket_key: string
  title: string
  project_category: string
  source_request_category: string
  summary: string
  business_purpose: string
  requester: string
  owner: string
  audience: string
  data_sources: string[]
  metrics_or_kpis: string[]
  display_format: string
  refresh_frequency: string
  scope: string
  acceptance_criteria: string[]
  success_criteria: string[]
  risks_and_assumptions: string[]
  suggested_priority: string
  linked_ticket_suggestion: string
  implementation_notes: string[]
  created_by: string
  status: string
  disclaimer: string
}

export interface AttachmentDraft {
  filename: string
  content_type: string
  content: string
  included: boolean
  uploaded: boolean
  content_encoding?: 'utf-8' | 'base64'
  size_bytes?: number
  source?: 'chat' | 'user'
}

export interface AttachmentListResponse {
  session_id: string
  attachments: AttachmentDraft[]
  ticket_preview: TicketPreview | null
  ticket_bundle_preview: JiraTicketBundlePreview | null
}

export interface JiraTicketDraftPreview {
  draft_ticket_key: string
  project_category: 'ITO' | 'BIM'
  issue_type: string
  summary: string
  description: string
  priority: string
  labels: string[]
  attachments: AttachmentDraft[]
  created: boolean
  status: string
  disclaimer: string
}

export interface JiraTicketBundlePreview {
  ito_ticket: JiraTicketDraftPreview
  bim_ticket: JiraTicketDraftPreview
  proposed_relationship: {
    source_ticket_category: string
    delivery_ticket_category: string
    direction: string
    relationship_type: string
    created: boolean
  }
  created_by: string
  validation_state: ValidationState
  created: boolean
  status: string
  disclaimer: string
}

export interface TicketGenerationResponse extends TicketPreview {
  ticket_preview: TicketPreview
  ticket_bundle_preview: JiraTicketBundlePreview
  pending_attachments?: AttachmentDraft[]
}

export type ResponseMode = 'clarify' | 'draft_ticket' | 'context_answer' | 'error'
export type LLMProvider = 'openai' | 'claude' | 'deterministic' | 'system'
export type ValidationState = 'gathering' | 'draft_ready' | 'pending_validation' | 'validated' | 'rejected'

export interface LLMRuntimeStatus {
  configured: boolean
  provider: 'openai' | 'claude' | 'deterministic'
  model: string | null
  message: string
}

export interface JiraRuntimeStatus {
  configured: boolean
  provider: 'mock' | 'real'
  message: string
}

export interface IntakeResponse {
  session_id: string
  assistant_message: string
  intake: IntakeData
  missing_fields: string[]
  completion_score: number
  ready_for_ticket: boolean
  ticket_preview: TicketPreview | null
  ticket_bundle_preview: JiraTicketBundlePreview | null
  pending_attachments?: AttachmentDraft[]
  field_metadata: Record<string, FieldMetadata>
  ambiguous_fields: string[]
  next_questions: ClarificationQuestion[]
  requirements_matrix: RequirementNode[]
  validation_ready: boolean
  validation_state: ValidationState
  validator_name: string | null
  validated_at: string | null
  validation_note: string | null
  risk_flags: string[]
  context_used: string[]
  mode: ResponseMode
  llm_provider: LLMProvider
  llm_model: string | null
  llm_request_id: string | null
  llm_latency_ms: number | null
  fallback_reason: string | null
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  mode?: ResponseMode
  contextUsed?: string[]
  questions?: ClarificationQuestion[]
  llmProvider?: LLMProvider
  llmModel?: string | null
  llmRequestId?: string | null
  llmLatencyMs?: number | null
  fallbackReason?: string | null
}

export interface ContextTable {
  name: string
  description: string
  use_when: string
}

export interface ContextSummary {
  source: string
  live_connection: boolean
  tables: ContextTable[]
  terminology: Record<string, string>
  data_quality_warnings: string[]
  usage_note: string
}

export interface ScenarioSummary {
  scenario_id: string
  scenario_name: string
}

export interface StressTestResult {
  scenario_id: string
  scenario_name: string
  transcript: Array<{ role: 'user' | 'assistant'; content: string }>
  final_intake: IntakeData
  ticket_preview: TicketPreview | null
  ticket_bundle_preview: JiraTicketBundlePreview | null
  findings: string[]
  risk_flags: string[]
}
