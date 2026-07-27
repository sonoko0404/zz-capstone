import { Check, LockKeyhole, RotateCcw, Send, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ValidationState } from '../types/intake'

interface ValidationWorkflowPanelProps {
  ready: boolean
  state: ValidationState
  validatorName: string | null
  validatedAt: string | null
  note: string | null
  onAction: (
    action: 'submit' | 'approve' | 'reject',
    validatorName?: string,
    note?: string,
  ) => Promise<void>
}

const ORDER: ValidationState[] = [
  'gathering',
  'draft_ready',
  'pending_validation',
  'validated',
]

export function ValidationWorkflowPanel({
  ready,
  state,
  validatorName,
  validatedAt,
  note,
  onAction,
}: ValidationWorkflowPanelProps) {
  const [name, setName] = useState(validatorName ?? '')
  const [reviewNote, setReviewNote] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const current = state === 'rejected' ? 1 : Math.max(0, ORDER.indexOf(state))
  const locked = state === 'pending_validation' || state === 'validated'

  useEffect(() => {
    setName(validatorName ?? '')
    if (state === 'gathering' || state === 'draft_ready') {
      setReviewNote('')
      setError(null)
    }
  }, [state, validatorName])

  async function act(action: 'submit' | 'approve' | 'reject') {
    setLoading(true)
    setError(null)
    try {
      await onAction(action, name.trim() || undefined, reviewNote.trim() || undefined)
      setReviewNote('')
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Validation action failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className={`panel validation-panel ${locked ? 'locked' : ''}`} aria-labelledby="validation-title">
      <header className="validation-panel-header">
        <div>
          <span>Human review gate</span>
          <h2 id="validation-title">Human Validation</h2>
        </div>
        <strong>{state.replaceAll('_', ' ')}</strong>
      </header>

      <div className="validation-steps" aria-label="Validation workflow progress">
        {ORDER.map((step, index) => (
          <span className={index <= current ? 'complete' : ''} key={step}>{index + 1}</span>
        ))}
      </div>

      {locked && (
        <p className="validation-lock-note">
          <LockKeyhole size={13} />
          {state === 'validated'
            ? 'Requirements are locked after approval. Return the intake for revision to edit them.'
            : 'Requirements are locked while human review is pending.'}
        </p>
      )}

      {state !== 'validated' && (
        <div className="validation-inputs">
          <label>
            <span>Reviewer</span>
            <input
              disabled={loading}
              onChange={(event) => setName(event.target.value)}
              placeholder="Reviewer name or role"
              value={name}
            />
          </label>
          <label>
            <span>Review note</span>
            <textarea
              disabled={loading}
              onChange={(event) => setReviewNote(event.target.value)}
              placeholder={state === 'pending_validation' ? 'Approval or revision note' : 'Optional handoff note'}
              rows={2}
              value={reviewNote}
            />
          </label>
        </div>
      )}

      {note && <p className="validation-status-note">{note}</p>}
      {validatedAt && state === 'validated' && (
        <p className="validation-status-note">
          Validated by {validatorName ?? 'human reviewer'} · {new Date(validatedAt).toLocaleString()}
        </p>
      )}
      {error && <p className="validation-error" role="alert"><X size={12} /> {error}</p>}

      <div className="validation-actions">
        {!locked && (
          <button disabled={!ready || loading} onClick={() => void act('submit')} type="button">
            <Send size={13} /> {loading ? 'Submitting…' : 'Submit for review'}
          </button>
        )}
        {state === 'pending_validation' && (
          <button disabled={loading} onClick={() => void act('approve')} type="button">
            <Check size={13} /> {loading ? 'Saving…' : 'Approve'}
          </button>
        )}
        {(state === 'pending_validation' || state === 'validated') && (
          <button className="reject" disabled={loading} onClick={() => void act('reject')} type="button">
            <RotateCcw size={13} /> Return for revision
          </button>
        )}
      </div>
    </section>
  )
}
