import {
  AlertCircle,
  Check,
  ChevronDown,
  Circle,
  Edit3,
  Eye,
  Info,
  RefreshCw,
  Search,
  Sparkles,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type {
  FieldMetadata,
  IntakeData,
  RequirementNode,
  ValidationState,
} from '../types/intake'
import {
  buildAiSummary,
  deriveReviewMilestone,
  groupRequirementNodes,
  type ReviewField,
  type ReviewFilter,
} from './requirementsReview'

interface RequirementsMatrixProps {
  intake: IntakeData | null
  metadata: Record<string, FieldMetadata>
  nodes: RequirementNode[]
  ambiguousFields: string[]
  saving: boolean
  completionScore: number
  readyForTicket: boolean
  validationReady: boolean
  validationState: ValidationState
  hasDraft: boolean
  onEdit: (field: string, value: string | boolean | string[] | null) => Promise<void>
  onViewEvidence?: (evidence: string) => void
}

const BOOLEAN_FIELDS = new Set(['requester_email_unavailable', 'include_chat_attachment'])

/** Common Jira Cloud issue types for ITO / BIM handoff. */
const JIRA_ISSUE_TYPES = ['Epic', 'Story', 'Task', 'Bug', 'Sub-task'] as const

/** Jira Cloud default priority names. */
const JIRA_PRIORITIES = ['Highest', 'High', 'Medium', 'Low', 'Lowest'] as const

const SELECT_FIELDS: Record<string, readonly string[]> = {
  jira_issue_type: JIRA_ISSUE_TYPES,
  priority: JIRA_PRIORITIES,
}

function labelFor(field: string) {
  const labels: Record<string, string> = {
    why_report_necessary: 'Business problem',
    decisions_supported: 'Decision supported',
    recipients_or_access_roles: 'Audience and access roles',
    data_story_by_recipient_role: 'Role-specific views',
    run_frequency: 'Reporting frequency',
    run_time_of_day: 'Delivery time',
    scope_criteria: 'Scope boundaries',
    existing_report_to_mimic: 'Existing report',
    required_fields: 'Required data fields',
    mockup_or_sample_available: 'Sample or mockup',
    custom_calculations_needed: 'Custom calculations',
    metrics_kpis_charts_maps: 'Metrics and visual requirements',
    row_level_security: 'Row-level security',
    accuracy_owner_or_validator: 'Business validator',
    success_definition: 'Definition of success',
    data_or_system_challenges: 'Data or system risks',
    assumptions_about_data_entry: 'Data assumptions',
    known_constraints: 'Known constraints',
  }
  if (labels[field]) return labels[field]
  return field.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function selectValue(field: string, raw: string | null | undefined) {
  const options = SELECT_FIELDS[field]
  if (!options || !raw) return ''
  const match = options.find((option) => option.toLowerCase() === raw.toLowerCase())
  return match ?? ''
}

function displayValue(value: unknown) {
  if (Array.isArray(value)) return value.join(', ') || 'Not provided'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return value ? String(value) : 'Not provided'
}

export function RequirementsMatrix({
  intake,
  metadata,
  nodes,
  ambiguousFields,
  saving,
  completionScore,
  readyForTicket,
  validationReady,
  validationState,
  hasDraft,
  onEdit,
  onViewEvidence,
}: RequirementsMatrixProps) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<ReviewFilter>('attention')
  const [openSections, setOpenSections] = useState<Set<string>>(new Set())
  const [editingField, setEditingField] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [editError, setEditError] = useState<string | null>(null)
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({})

  const sections = useMemo(
    () => groupRequirementNodes(nodes, intake, metadata, ambiguousFields),
    [ambiguousFields, intake, metadata, nodes],
  )
  const attentionSections = useMemo(
    () => sections.filter((section) => section.needsAttention),
    [sections],
  )
  const activeFilter = filter === 'attention' && attentionSections.length === 0 ? 'all' : filter
  const visibleSections = useMemo(() => sections.filter((section) => {
    const query = search.trim().toLowerCase()
    const matchesSearch = !query || [
      section.label,
      ...section.summaryLines,
      ...section.fields.flatMap((field) => [
        labelFor(field.field),
        displayValue(field.value),
        field.metadata?.evidence ?? '',
      ]),
    ].join(' ').toLowerCase().includes(query)
    const matchesFilter = activeFilter === 'all'
      || (activeFilter === 'attention' && section.needsAttention)
      || (activeFilter === 'required' && section.fields.some((field) => field.required))
      || (activeFilter === 'optional' && section.fields.some((field) => !field.required && field.state !== 'n/a'))
    return matchesSearch && matchesFilter
  }), [activeFilter, search, sections])
  const milestone = deriveReviewMilestone({
    hasIntake: Boolean(intake),
    completionScore,
    readyForTicket,
    validationReady,
    validationState,
    hasDraft,
  })
  const blockingCount = sections.reduce((total, section) => total + section.blockingCount, 0)
  const aiSummary = buildAiSummary(intake, attentionSections.map((section) => section.label))

  useEffect(() => {
    setOpenSections(new Set(attentionSections.map((section) => section.key)))
  }, [attentionSections.map((section) => section.key).join('|')])

  function filteredFields(fields: ReviewField[]) {
    if (activeFilter === 'required') return fields.filter((field) => field.required)
    if (activeFilter === 'optional') return fields.filter((field) => !field.required && field.state !== 'n/a')
    if (activeFilter === 'attention') return fields.filter((field) => field.needsAttention)
    return fields
  }

  function toggleSection(key: string) {
    setOpenSections((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function focusSection(key: string) {
    setOpenSections((current) => new Set(current).add(key))
    requestAnimationFrame(() => {
      sectionRefs.current[key]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    })
  }

  function openEditor(field: string) {
    const value = intake?.[field as keyof IntakeData]
    setEditingField(field)
    setDraft(Array.isArray(value) ? value.join(', ') : typeof value === 'boolean' ? String(value) : String(value ?? ''))
    setEditError(null)
  }

  async function saveEdit() {
    if (!editingField) return
    try {
      const value = BOOLEAN_FIELDS.has(editingField)
        ? draft === 'true'
        : editingField === 'jira_labels'
          ? draft.split(',').map((item) => item.trim()).filter(Boolean)
          : draft.trim() || null
      await onEdit(editingField, value)
      setEditingField(null)
    } catch (error) {
      setEditError(error instanceof Error ? error.message : 'Could not update this field.')
    }
  }

  function confirmField(field: ReviewField) {
    const value = field.value
    if (value === null || value === undefined) return
    void onEdit(
      field.field,
      Array.isArray(value)
        ? value.map(String)
        : typeof value === 'boolean'
          ? value
          : String(value),
    ).catch(() => undefined)
  }

  return (
    <section className="panel requirements-panel" aria-labelledby="requirements-title">
      <header className="review-header">
        <div className="review-title-row">
          <div>
            <div className="eyebrow">BI request review</div>
            <h2 id="requirements-title">Requirements Review</h2>
          </div>
          <span className="review-progress" aria-label={`${completionScore}% review progress`}>
            {Math.round(completionScore)}%
          </span>
        </div>
        <div className="review-milestone">
          <strong>{milestone.title}</strong>
          <span>
            {blockingCount > 0
              ? `${blockingCount} required item${blockingCount === 1 ? '' : 's'} need attention`
              : milestone.detail}
          </span>
        </div>
      </header>

      <div className="ai-review-summary">
        <div><Sparkles size={14} /><span>AI Summary</span></div>
        <p>{aiSummary}</p>
      </div>

      {attentionSections.length > 0 && (
        <div className="attention-index" aria-label="Requirements needing attention">
          <span>Needs attention</span>
          <div>
            {attentionSections.map((section) => (
              <button key={section.key} onClick={() => focusSection(section.key)} type="button">
                {section.label}
                <span>{section.attentionCount}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="review-toolbar">
        <label className="review-search">
          <Search size={14} />
          <input
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search requirements"
            value={search}
          />
        </label>
        <div className="review-filters" aria-label="Filter requirements">
          {([
            ['all', 'All'],
            ['attention', 'Needs attention'],
            ['required', 'Required'],
            ['optional', 'Optional'],
          ] as const).map(([value, label]) => (
            <button
              aria-pressed={activeFilter === value}
              className={activeFilter === value ? 'active' : ''}
              key={value}
              onClick={() => setFilter(value)}
              type="button"
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="review-ledger">
        {visibleSections.map((section) => {
          const open = openSections.has(section.key)
          const fields = filteredFields(section.fields)
          return (
            <article
              className={`review-section${section.needsAttention ? ' needs-attention' : ' complete'}`}
              key={section.key}
              ref={(element) => {
                sectionRefs.current[section.key] = element
              }}
            >
              <button
                aria-expanded={open}
                className="review-section-toggle"
                onClick={() => toggleSection(section.key)}
                type="button"
              >
                <span className="review-section-status" aria-hidden="true">
                  {section.needsAttention
                    ? <AlertCircle size={16} />
                    : section.completedCount > 0
                      ? <Check size={15} />
                      : <Circle size={13} />}
                </span>
                <span className="review-section-heading">
                  <strong>{section.label}</strong>
                  <small>
                    {section.summaryLines.length > 0
                      ? section.summaryLines.join(' · ')
                      : section.nodes.map((node) => node.display_name).join(' · ')}
                  </small>
                </span>
                {section.attentionCount > 0 && (
                  <span className="review-section-count">{section.attentionCount} to review</span>
                )}
                {section.attentionCount === 0 && section.applicableCount > 0 && (
                  <span className="review-section-count quiet">
                    {section.completedCount}/{section.applicableCount}
                  </span>
                )}
                <ChevronDown className="review-chevron" size={15} />
              </button>

              {open && (
                <div className="review-fields">
                  {fields.map((field) => {
                    const confirmed = field.metadata?.source === 'user_confirmed'
                    const hasEvidence = Boolean(field.metadata?.evidence || field.metadata?.source)
                    return (
                      <div
                        className={`review-field ${field.state}${field.required ? ' required' : ' optional'}`}
                        key={`${field.node.key}-${field.field}`}
                      >
                        <div className="review-field-main">
                          <div className="review-field-copy">
                            <div className="review-field-label">
                              <strong>{labelFor(field.field)}</strong>
                              <span>{field.required ? 'Required' : field.state === 'n/a' ? 'Not applicable' : 'Optional'}</span>
                            </div>
                            <p>{displayValue(field.value)}</p>
                            {field.needsAttention && (
                              <small className="review-field-alert">
                                {field.state === 'missing' ? 'Missing' : 'Needs confirmation'}
                              </small>
                            )}
                            {confirmed && <small className="review-field-confirmed"><Check size={11} /> Confirmed</small>}
                          </div>
                          <div className="review-field-actions">
                            {!confirmed && field.state !== 'missing' && field.state !== 'n/a' && (
                              <button
                                aria-label={`Confirm ${labelFor(field.field)}`}
                                disabled={saving}
                                onClick={() => confirmField(field)}
                                title="Confirm"
                                type="button"
                              >
                                <Check size={14} />
                              </button>
                            )}
                            <button
                              aria-label={`Edit ${labelFor(field.field)}`}
                              disabled={field.state === 'n/a'}
                              onClick={() => openEditor(field.field)}
                              title="Edit"
                              type="button"
                            >
                              <Edit3 size={13} />
                            </button>
                            <button
                              aria-label={`Re-extract ${labelFor(field.field)} — future capability`}
                              disabled
                              title="Re-extract — future capability"
                              type="button"
                            >
                              <RefreshCw size={13} />
                            </button>
                          </div>
                        </div>

                        {hasEvidence && field.state !== 'n/a' && (
                          <details className="review-evidence">
                            <summary><Eye size={12} /> Evidence</summary>
                            <div>
                              {field.metadata?.evidence && <q>{field.metadata.evidence}</q>}
                              <span>
                                {field.metadata?.source
                                  ? field.metadata.source.replaceAll('_', ' ')
                                  : 'Source unavailable'}
                              </span>
                              {field.metadata?.evidence && onViewEvidence && (
                                <button onClick={() => onViewEvidence(field.metadata?.evidence ?? '')} type="button">
                                  View in conversation
                                </button>
                              )}
                            </div>
                          </details>
                        )}
                      </div>
                    )
                  })}
                  {fields.length === 0 && (
                    <p className="review-section-empty">No requirements in this section match the current filter.</p>
                  )}
                </div>
              )}
            </article>
          )
        })}
        {visibleSections.length === 0 && (
          <div className="review-empty">
            <p>No requirements match this view.</p>
            <button onClick={() => { setFilter('all'); setSearch('') }} type="button">Show all requirements</button>
          </div>
        )}
      </div>

      <div className="review-handoff">
        <div className="review-handoff-heading">
          <strong>Jira draft settings</strong>
          <span>Applied when the reviewed request moves to Jira</span>
        </div>
        <div className="handoff-options">
        <label className="handoff-select">
          <span>Jira Issue Type</span>
          <select
            aria-label="Jira issue type"
            disabled={saving}
            onChange={(event) => void onEdit('jira_issue_type', event.target.value || null)}
            value={selectValue('jira_issue_type', intake?.jira_issue_type)}
          >
            <option value="">Select issue type…</option>
            {JIRA_ISSUE_TYPES.map((type) => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </label>
        <label className="handoff-select">
          <span>Priority</span>
          <select
            aria-label="Priority"
            disabled={saving}
            onChange={(event) => void onEdit('priority', event.target.value || null)}
            value={selectValue('priority', intake?.priority)}
          >
            <option value="">Select priority…</option>
            {JIRA_PRIORITIES.map((level) => (
              <option key={level} value={level}>{level}</option>
            ))}
          </select>
        </label>
        <label className="handoff-chat-attach">
          <input
            checked={intake?.include_chat_attachment ?? false}
            onChange={(event) => void onEdit('include_chat_attachment', event.target.checked)}
            type="checkbox"
          />
          <span>Attach Chat Transcript</span>
          <button
            aria-label="Required for file upload"
            className="info-tooltip"
            data-tooltip="Required for file upload"
            onClick={(event) => event.preventDefault()}
            type="button"
          >
            <Info size={13} />
          </button>
        </label>
        </div>
      </div>

      {editingField && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setEditingField(null)
        }}>
          <div aria-labelledby="edit-field-title" aria-modal="true" className="field-modal" role="dialog">
            <header><div><span>Review requirement</span><h3 id="edit-field-title">{labelFor(editingField)}</h3></div><button aria-label="Close editor" onClick={() => setEditingField(null)} type="button"><X size={16} /></button></header>
            <p>Manual edits are marked <strong>user confirmed</strong> and protected from later model overwrites.</p>
            {BOOLEAN_FIELDS.has(editingField) ? (
              <select onChange={(event) => setDraft(event.target.value)} value={draft || 'false'}><option value="false">No</option><option value="true">Yes</option></select>
            ) : editingField in SELECT_FIELDS ? (
              <select autoFocus onChange={(event) => setDraft(event.target.value)} value={selectValue(editingField, draft) || draft}>
                <option value="">Select…</option>
                {SELECT_FIELDS[editingField].map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            ) : (
              <textarea autoFocus onChange={(event) => setDraft(event.target.value)} rows={5} value={draft} />
            )}
            {editError && <div className="inline-error">{editError}</div>}
            <footer><button className="secondary-button" onClick={() => setEditingField(null)} type="button">Cancel</button><button className="primary-button" disabled={saving} onClick={() => void saveEdit()} type="button"><Check size={14} /> {saving ? 'Saving…' : 'Save & confirm'}</button></footer>
          </div>
        </div>
      )}
    </section>
  )
}
