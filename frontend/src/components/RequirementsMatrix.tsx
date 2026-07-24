import { Check, Edit3, Filter, Info, Search, ShieldQuestion, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { FieldMetadata, IntakeData, RequirementNode } from '../types/intake'

interface RequirementsMatrixProps {
  intake: IntakeData | null
  metadata: Record<string, FieldMetadata>
  nodes: RequirementNode[]
  ambiguousFields: string[]
  saving: boolean
  onEdit: (field: string, value: string | boolean | string[] | null) => Promise<void>
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
  onEdit,
}: RequirementsMatrixProps) {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('All')
  const [editingField, setEditingField] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [editError, setEditError] = useState<string | null>(null)

  const visibleNodes = useMemo(() => nodes.filter((node) => {
    const matchesStatus = status === 'All' || node.status === status
    const query = search.trim().toLowerCase()
    const matchesSearch = !query || `${node.display_name} ${node.summary} ${node.fields.join(' ')}`.toLowerCase().includes(query)
    return matchesStatus && matchesSearch
  }), [nodes, search, status])

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

  return (
    <section className="panel requirements-panel" aria-labelledby="requirements-title">
      <header className="matrix-header">
        <div>
          <div className="eyebrow"><ShieldQuestion size={13} /> Explainable requirements</div>
          <h2 id="requirements-title">Requirements Matrix</h2>
          <p>13 PRD nodes · values, confidence, evidence, and confirmation status</p>
        </div>
        <span className="matrix-count">{nodes.filter((node) => node.status === 'Filled').length}/{nodes.length} filled</span>
      </header>

      <div className="matrix-toolbar">
        <label><Search size={14} /><input onChange={(event) => setSearch(event.target.value)} placeholder="Search requirements" value={search} /></label>
        <label><Filter size={14} /><select onChange={(event) => setStatus(event.target.value)} value={status}>
          <option>All</option><option>Filled</option><option>Missing</option><option>Needs Confirmation</option><option>N/A</option>
        </select></label>
      </div>

      <div className="matrix-list">
        {visibleNodes.map((node) => (
          <details className="matrix-node" key={node.key}>
            <summary>
              <span className={`node-status ${node.status.toLowerCase().replaceAll(' ', '-')}`}>
                {node.status === 'Filled' ? <Check size={12} /> : node.status === 'Needs Confirmation' ? '!' : '—'}
              </span>
              <span className="node-heading"><strong>{node.display_name}</strong><small>{node.summary}</small></span>
              <span className={`confidence-pill ${node.confidence}`}>{node.confidence}</span>
              <span className="source-pill">{node.source.replaceAll('_', ' ')}</span>
            </summary>
            <div className="node-fields">
              {node.fields.map((field) => {
                const value = intake?.[field as keyof IntakeData]
                const fieldMeta = metadata[field]
                const ambiguous = ambiguousFields.includes(field)
                return (
                  <div className={ambiguous ? 'ambiguous' : ''} key={field}>
                    <div><strong>{labelFor(field)}</strong><span>{displayValue(value)}</span></div>
                    <div className="field-evidence">
                      {fieldMeta?.source && <span>{fieldMeta.source.replaceAll('_', ' ')} · {fieldMeta.confidence}</span>}
                      {fieldMeta?.evidence && <q>{fieldMeta.evidence}</q>}
                    </div>
                    <button aria-label={`Edit ${labelFor(field)}`} onClick={() => openEditor(field)} type="button"><Edit3 size={13} /> Edit</button>
                  </div>
                )
              })}
            </div>
          </details>
        ))}
        {visibleNodes.length === 0 && <p className="matrix-empty">No requirements match this view.</p>}
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

      {editingField && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setEditingField(null)
        }}>
          <div aria-labelledby="edit-field-title" aria-modal="true" className="field-modal" role="dialog">
            <header><div><span>Manual confirmation</span><h3 id="edit-field-title">{labelFor(editingField)}</h3></div><button onClick={() => setEditingField(null)} type="button"><X size={16} /></button></header>
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
