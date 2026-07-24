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
  /** Compact field labels shown while the section is collapsed. */
  previewLabels: string[]
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

const FIELD_PREVIEW_LABELS: Record<string, string> = {
  why_report_necessary: 'Business problem',
  decisions_supported: 'Decision supported',
  problems_addressed: 'Problem addressed',
  recipients_or_access_roles: 'Audience',
  requester: 'Requester',
  armada_owner: 'Owner',
  run_frequency: 'Reporting frequency',
  refresh_frequency: 'Refresh frequency',
  deadline: 'Deadline',
  scope_criteria: 'Scope',
  filters_needed: 'Filters',
  existing_report_to_mimic: 'Existing report',
  row_level_security: 'Row-level security',
  data_sources: 'Data source',
  required_fields: 'Required fields',
  metrics_kpis_charts_maps: 'Metrics',
  display_format: 'Output format',
  report_title: 'Report title',
  success_definition: 'Success criteria',
  accuracy_owner_or_validator: 'Validator',
  data_or_system_challenges: 'Risks',
  assumptions_about_data_entry: 'Assumptions',
  known_constraints: 'Constraints',
}

function previewLabelFor(field: string) {
  return FIELD_PREVIEW_LABELS[field]
    ?? field.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function sectionPreviewLabels(fields: ReviewField[]) {
  const ranked = [...fields]
    .filter((field) => field.state !== 'n/a')
    .sort((left, right) => (
      Number(right.needsAttention) - Number(left.needsAttention)
      || Number(right.required) - Number(left.required)
      || Number(hasValue(right.value)) - Number(hasValue(left.value))
    ))
  const labels: string[] = []
  for (const field of ranked) {
    const label = previewLabelFor(field.field)
    if (!labels.includes(label)) labels.push(label)
    if (labels.length >= 2) break
  }
  return labels
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
      const requiredGroups = (node.required_groups ?? [])
        .filter((group) => group.includes(field))
      const required = requiredGroups.length > 0
      const hasUnsatisfiedRequiredGroup = requiredGroups.some((group) => (
        !group.some((groupField) => hasValue(intake?.[groupField as keyof IntakeData]))
      ))
      const state = fieldState(
        node,
        value,
        metadata[field],
        ambiguousFields.includes(field),
      )
      const needsAttention = (
        state === 'needs-confirmation'
        || (state === 'missing' && hasUnsatisfiedRequiredGroup)
      )
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
    const requiredGroups = Array.from(new Map(
      sectionNodes
        .flatMap((node) => node.required_groups ?? [])
        .map((group) => [JSON.stringify(group), group] as const),
    ).values())
    const blockingGroups = requiredGroups.filter((group) => (
      !group.some((field) => hasValue(intake?.[field as keyof IntakeData]))
    ))

    return {
      key: definition.key,
      label: definition.label,
      nodes: sectionNodes,
      fields,
      previewLabels: sectionPreviewLabels(fields),
      needsAttention: fields.some((field) => field.needsAttention),
      blockingCount: blockingGroups.length,
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
    return 'Describe the business need in the conversation. Requirements will appear here as they are extracted, with gaps called out for review.'
  }

  const audience = intake.recipients_or_access_roles
  const output = intake.display_format || 'dashboard'
  const metric = intake.metrics_kpis_charts_maps || intake.required_fields
  const source = intake.data_sources
  const cadence = intake.refresh_frequency || intake.run_frequency
  const purpose = intake.why_report_necessary || intake.decisions_supported

  let request: string
  if (audience && metric && source) {
    request = `${audience} need a ${output.toLowerCase()} tracking ${metric} from ${source}`
  } else if (audience && purpose) {
    request = `${audience} need a ${output.toLowerCase()} to ${purpose.replace(/[.!]+$/, '').replace(/^to\s+/i, '')}`
  } else if (purpose) {
    request = `This request is for a ${output.toLowerCase()} to ${purpose.replace(/[.!]+$/, '').replace(/^to\s+/i, '')}`
  } else if (audience) {
    request = `${audience} need a ${output.toLowerCase()}`
  } else {
    request = `This request is for a ${output.toLowerCase()}`
  }
  if (cadence && !attentionSections.includes('Frequency')) {
    request += ` with ${cadence.toLowerCase()} refresh`
  }

  const gapLabels = joinLabels(attentionSections.slice(0, 2))
  const gap = gapLabels
    ? ` The request is missing ${gapLabels.toLowerCase()} before it can move to BI review.`
    : ' The request looks ready for BI review.'

  return `${request.replace(/\s+/g, ' ').trim().replace(/[.!]+$/, '')}.${gap}`
}

export function deriveReviewMilestone(state: ReviewWorkflowState): ReviewMilestone {
  if (!state.hasIntake) {
    return { title: 'Start the request', detail: 'Requirements will appear as the conversation develops' }
  }
  if (state.validationState === 'validated') {
    return { title: 'BI Validation Complete', detail: 'Ready for submission' }
  }
  if (state.validationState === 'rejected') {
    return {
      title: 'Revision Required',
      detail: 'Address the reviewer feedback before resubmitting',
    }
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

export function canConfirmRequirement(validationState: ValidationState) {
  return validationState !== 'pending_validation' && validationState !== 'validated'
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
