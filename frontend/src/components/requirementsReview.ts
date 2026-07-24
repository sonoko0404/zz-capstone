import type {
  FieldMetadata,
  IntakeData,
  RequirementNode,
  ValidationState,
} from '../types/intake'

export type ReviewFilter = 'all' | 'attention' | 'required' | 'optional'
export type ReviewFieldState = 'complete' | 'missing' | 'needs-confirmation' | 'n/a'

export interface ReviewField {
  field: string
  node: RequirementNode
  value: unknown
  metadata: FieldMetadata | undefined
  required: boolean
  state: ReviewFieldState
  needsAttention: boolean
}

export interface ReviewSection {
  key: string
  label: string
  nodes: RequirementNode[]
  fields: ReviewField[]
  summaryLines: string[]
  needsAttention: boolean
  blockingCount: number
  attentionCount: number
  completedCount: number
  applicableCount: number
}

export interface ReviewWorkflowState {
  hasIntake: boolean
  completionScore: number
  readyForTicket: boolean
  validationReady: boolean
  validationState: ValidationState
  hasDraft: boolean
}

export interface ReviewMilestone {
  title: string
  detail: string
}

const SECTION_DEFINITIONS = [
  { key: 'purpose', label: 'Purpose', nodeKeys: ['purpose', 'business_decision'] },
  { key: 'audience', label: 'Audience', nodeKeys: ['audience'] },
  { key: 'frequency', label: 'Frequency', nodeKeys: ['reporting_frequency', 'refresh_frequency'] },
  { key: 'scope', label: 'Scope', nodeKeys: ['scope_filters', 'row_level_security'] },
  { key: 'data', label: 'Data Requirements', nodeKeys: ['required_data'] },
  { key: 'report', label: 'Report Requirements', nodeKeys: ['report_title', 'calculations_metrics', 'display_format'] },
  { key: 'success', label: 'Success Criteria', nodeKeys: ['success_criteria'] },
  { key: 'risks', label: 'Risks & Assumptions', nodeKeys: ['risks_assumptions'] },
] as const

function hasValue(value: unknown) {
  if (typeof value === 'boolean') return true
  if (Array.isArray(value)) return value.length > 0
  return value !== null && value !== undefined && String(value).trim().length > 0
}

function fieldState(
  node: RequirementNode,
  value: unknown,
  fieldMetadata: FieldMetadata | undefined,
  ambiguous: boolean,
): ReviewFieldState {
  if (node.status === 'N/A' || node.requirement_level === 'n/a') return 'n/a'
  if (!hasValue(value)) return 'missing'
  if (
    ambiguous
    || fieldMetadata?.source === 'needs_confirmation'
    || fieldMetadata?.source === 'inferred'
    || fieldMetadata?.confidence === 'low'
    || fieldMetadata?.confidence === 'medium'
  ) {
    return 'needs-confirmation'
  }
  return 'complete'
}

function usefulSummary(summary: string) {
  return summary
    && summary !== 'No information captured yet'
    && !summary.startsWith('Not applicable for')
    && summary !== 'Conflicting values require confirmation'
}

export function groupRequirementNodes(
  nodes: RequirementNode[],
  intake: IntakeData | null,
  metadata: Record<string, FieldMetadata>,
  ambiguousFields: string[],
): ReviewSection[] {
  const nodeByKey = new Map(nodes.map((node) => [node.key, node]))

  const sections = SECTION_DEFINITIONS.map((definition) => {
    const sectionNodes = definition.nodeKeys
      .map((key) => nodeByKey.get(key))
      .filter((node): node is RequirementNode => Boolean(node))
    const fields = sectionNodes.flatMap((node) => node.fields.map((field): ReviewField => {
      const value = intake?.[field as keyof IntakeData]
      const required = (node.required_fields ?? []).includes(field)
      const state = fieldState(
        node,
        value,
        metadata[field],
        ambiguousFields.includes(field),
      )
      const needsAttention = state === 'needs-confirmation' || (required && state === 'missing')
      return {
        field,
        node,
        value,
        metadata: metadata[field],
        required,
        state,
        needsAttention,
      }
    }))
    const applicableFields = fields.filter((field) => field.state !== 'n/a')
    const summaryLines = sectionNodes
      .map((node) => node.summary)
      .filter(usefulSummary)
      .slice(0, 2)

    return {
      key: definition.key,
      label: definition.label,
      nodes: sectionNodes,
      fields,
      summaryLines,
      needsAttention: fields.some((field) => field.needsAttention),
      blockingCount: fields.filter((field) => field.required && field.needsAttention).length,
      attentionCount: fields.filter((field) => field.needsAttention).length,
      completedCount: applicableFields.filter((field) => field.state === 'complete').length,
      applicableCount: applicableFields.length,
    }
  }).filter((section) => section.nodes.length > 0)

  return sections
    .map((section, index) => ({ section, index }))
    .sort((left, right) => (
      Number(right.section.needsAttention) - Number(left.section.needsAttention)
      || left.index - right.index
    ))
    .map(({ section }) => section)
}

function joinLabels(labels: string[]) {
  if (labels.length === 0) return ''
  if (labels.length === 1) return labels[0]
  return `${labels[0]} and ${labels[1]}`
}

export function buildAiSummary(
  intake: IntakeData | null,
  attentionSections: string[],
) {
  if (!intake) {
    return 'Describe the business need in the conversation. The review will organize requirements and surface what needs attention.'
  }

  const audience = intake.recipients_or_access_roles || 'The business team'
  const output = intake.display_format || intake.request_type || 'a BI deliverable'
  const metric = intake.metrics_kpis_charts_maps || intake.required_fields
  const source = intake.data_sources
  const purpose = intake.why_report_necessary || intake.decisions_supported
  const request = [
    `${audience} need ${output.toLowerCase()}`,
    metric ? `tracking ${metric}` : null,
    source ? `from ${source}` : null,
    purpose ? `to ${purpose.replace(/[.!]+$/, '').replace(/^to\s+/i, '')}` : null,
  ].filter(Boolean).join(' ')
  const gapLabels = joinLabels(attentionSections.slice(0, 2))
  const gap = gapLabels
    ? ` The request still needs ${gapLabels} before BI review.`
    : ' The request has the information needed for BI review.'

  return `${request.replace(/\s+/g, ' ').trim().replace(/[.!]+$/, '')}.${gap}`
}

export function deriveReviewMilestone(state: ReviewWorkflowState): ReviewMilestone {
  if (!state.hasIntake) {
    return { title: 'Start the request', detail: 'Requirements will appear as the conversation develops' }
  }
  if (state.validationState === 'validated') {
    return { title: 'BI Validation Complete', detail: 'Ready for submission' }
  }
  if (state.validationState === 'pending_validation') {
    return { title: 'BI Review in Progress', detail: 'Awaiting reviewer decision' }
  }
  if (state.validationReady) {
    return { title: 'Ready for BI Review', detail: 'Required information is complete' }
  }
  if (state.hasDraft) {
    return { title: 'AI Draft Complete', detail: 'Awaiting BI validation' }
  }
  if (state.readyForTicket) {
    return { title: 'Ready to Generate Draft', detail: 'Minimum requirements are complete' }
  }
  return {
    title: 'AI Intake in Progress',
    detail: `${Math.max(0, Math.round(state.completionScore))}% review progress`,
  }
}

function normalizeEvidence(value: string) {
  return value
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
    .replace(/\s+/g, ' ')
}

export function messageMatchesEvidence(message: string, evidence: string) {
  const normalizedMessage = normalizeEvidence(message)
  const normalizedEvidence = normalizeEvidence(evidence)
  if (normalizedEvidence.length < 12 || normalizedMessage.length < 12) return false
  return (
    normalizedMessage.includes(normalizedEvidence)
    || normalizedEvidence.includes(normalizedMessage)
  )
}
