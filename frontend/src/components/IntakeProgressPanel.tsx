import { AlertTriangle, Check, Circle, FileText, Send, ShieldCheck, X } from 'lucide-react'
import type { IntakeData, ValidationState } from '../types/intake'

interface IntakeProgressPanelProps {
  intake: IntakeData | null
  completionScore: number
  missingFields: string[]
  riskFlags: string[]
  readyForTicket: boolean
  hasTicket: boolean
  generating: boolean
  onGenerate: () => Promise<void>
  validationReady: boolean
  validationState: ValidationState
  validationNote: string | null
  onValidation: (action: 'submit' | 'approve' | 'reject') => Promise<void>
}

const SECTIONS = [
  { label: 'Purpose', fields: ['why_report_necessary', 'decisions_supported', 'problems_addressed'] },
  { label: 'Audience', fields: ['requester', 'armada_owner', 'recipients_or_access_roles'] },
  { label: 'Data', fields: ['data_sources', 'required_fields', 'metrics_kpis_charts_maps'] },
  { label: 'Delivery', fields: ['display_format', 'refresh_frequency', 'deadline'] },
  { label: 'Success', fields: ['success_definition', 'accuracy_owner_or_validator'] },
] as const

const LABELS: Record<string, string> = {
  request_type: 'Request type',
  why_report_necessary: 'Business purpose',
  recipients_or_access_roles: 'Audience / access roles',
  data_sources: 'Data source',
  metrics_kpis_charts_maps: 'Metrics or fields',
  display_format: 'Output format',
  requester_or_owner: 'Requester or owner',
  success_or_validator: 'Success measure or validator',
  refresh_frequency: 'Refresh cadence',
  row_level_security: 'Row-level security',
  scope_criteria: 'Scope and filters',
  deadline: 'Deadline',
  data_or_system_challenges: 'Data risks',
  existing_report_to_mimic: 'Related report',
  priority: 'Priority',
}

export function IntakeProgressPanel({
  intake,
  completionScore,
  missingFields,
  riskFlags,
  readyForTicket,
  hasTicket,
  generating,
  onGenerate,
  validationReady,
  validationState,
  validationNote,
  onValidation,
}: IntakeProgressPanelProps) {
  const coreMissing = missingFields.slice(0, 5)

  return (
    <section className="panel progress-panel" aria-labelledby="progress-title">
      <header className="panel-header compact-header">
        <div>
          <div className="eyebrow"><FileText size={13} /> Live PRD</div>
          <h2 id="progress-title">Intake readiness</h2>
        </div>
        <div className="score-ring" style={{ '--score': `${completionScore * 3.6}deg` } as React.CSSProperties}>
          <span>{completionScore}%</span>
        </div>
      </header>

      <div className="readiness-state">
        <span className={`readiness-icon ${readyForTicket ? 'ready' : ''}`}>
          {readyForTicket ? <Check size={15} /> : <Circle size={12} />}
        </span>
        <div>
          <strong>{readyForTicket ? 'Minimum requirements complete' : 'Clarification in progress'}</strong>
          <p>{readyForTicket ? 'Ready to prepare an adapter-neutral draft.' : 'The assistant is prioritizing the most important gaps.'}</p>
        </div>
      </div>

      <div className="scenario-strip">
        <span>Scenario</span><strong>{intake?.scenario_type ?? 'Unassigned'}</strong>
        <small>Classified separately from request type: {intake?.request_type ?? 'unknown'}</small>
      </div>

      <div className="section-checks" aria-label="PRD section progress">
        {SECTIONS.map((section) => {
          const filled = section.fields.filter((field) => Boolean(intake?.[field])).length
          const complete = filled === section.fields.length
          return (
            <div className={`section-check ${complete ? 'complete' : ''}`} key={section.label}>
              <span>{complete ? <Check size={13} /> : filled}</span>
              <div>
                <strong>{section.label}</strong>
                <small>{filled}/{section.fields.length} captured</small>
              </div>
            </div>
          )
        })}
      </div>

      {coreMissing.length > 0 && (
        <div className="progress-list">
          <h3>Needs attention</h3>
          <div className="tag-list">
            {coreMissing.map((field) => <span className="missing-tag" key={field}>{LABELS[field] ?? field.replaceAll('_', ' ')}</span>)}
          </div>
        </div>
      )}

      {riskFlags.length > 0 && (
        <div className="risk-callout">
          <AlertTriangle aria-hidden="true" size={16} />
          <div>
            <strong>{riskFlags.length} risk{riskFlags.length === 1 ? '' : 's'} surfaced</strong>
            <p>{riskFlags[0]}</p>
          </div>
        </div>
      )}

      <button
        className="primary-button full-width"
        disabled={!readyForTicket || generating}
        onClick={() => void onGenerate()}
        type="button"
      >
        <ShieldCheck aria-hidden="true" size={16} />
        {generating ? 'Preparing draft…' : hasTicket ? 'Regenerate draft ticket' : 'Generate draft ticket'}
      </button>
      <p className="button-disclaimer">Preview only — MockJiraAdapter performs no external write.</p>

      <div className="validation-workflow">
        <div className="validation-heading"><strong>Human validation</strong><span>{validationState.replaceAll('_', ' ')}</span></div>
        <div className="validation-steps" aria-label="Validation workflow">
          {(['gathering', 'draft_ready', 'pending_validation', 'validated'] as const).map((step, index) => {
            const order = ['gathering', 'draft_ready', 'pending_validation', 'validated']
            const current = validationState === 'rejected' ? 1 : order.indexOf(validationState)
            return <span className={index <= current ? 'complete' : ''} key={step}>{index + 1}</span>
          })}
        </div>
        {validationNote && validationState !== 'validated' && <p>{validationNote}</p>}
        <div className="validation-actions">
          {validationState !== 'pending_validation' && validationState !== 'validated' && (
            <button disabled={!validationReady} onClick={() => void onValidation('submit')} type="button"><Send size={13} /> Submit</button>
          )}
          {validationState === 'pending_validation' && <button onClick={() => void onValidation('approve')} type="button"><Check size={13} /> Approve</button>}
          {(validationState === 'pending_validation' || validationState === 'validated') && <button className="reject" onClick={() => void onValidation('reject')} type="button"><X size={13} /> Revise</button>}
        </div>
      </div>
    </section>
  )
}
