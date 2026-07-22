import { Check, Clipboard, Download, FileText, Link2, Paperclip, ShieldAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { JiraTicketBundlePreview, JiraTicketDraftPreview, TicketPreview } from '../types/intake'

interface TicketPreviewCardProps {
  ticket: TicketPreview | null
  bundle: JiraTicketBundlePreview | null
}

function DraftTicket({ draft }: { draft: JiraTicketDraftPreview }) {
  return (
    <article className={`blueprint-ticket ${draft.project_category.toLowerCase()}`}>
      <header>
        <span className="project-avatar">{draft.project_category}</span>
        <div><code>{draft.draft_ticket_key}</code><strong>{draft.summary}</strong></div>
        <span className="draft-badge">{draft.status}</span>
      </header>
      <div className="blueprint-meta">
        <span><small>Issue type</small>{draft.issue_type}</span>
        <span><small>Priority</small>{draft.priority}</span>
        <span><small>Created</small>No — preview only</span>
      </div>
      <details>
        <summary><FileText size={13} /> View description blueprint</summary>
        <pre>{draft.description}</pre>
      </details>
      {draft.labels.length > 0 && <div className="ticket-chip-row">{draft.labels.map((label) => <span key={label}>{label}</span>)}</div>}
      {draft.attachments.map((attachment) => (
        <div className="attachment-draft" key={attachment.filename}><Paperclip size={13} /><span>{attachment.filename}</span><small>sanitized · not uploaded</small></div>
      ))}
    </article>
  )
}

export function TicketPreviewCard({ ticket, bundle }: TicketPreviewCardProps) {
  const [copied, setCopied] = useState(false)
  const copyTimer = useRef<number | null>(null)

  useEffect(() => () => {
    if (copyTimer.current !== null) window.clearTimeout(copyTimer.current)
  }, [])

  async function copyTicket() {
    const payload = bundle ?? ticket
    if (!payload) return
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
    setCopied(true)
    if (copyTimer.current !== null) window.clearTimeout(copyTimer.current)
    copyTimer.current = window.setTimeout(() => setCopied(false), 1800)
  }

  function exportTicket() {
    const payload = bundle ?? ticket
    if (!payload) return
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = bundle ? 'draft-jira-ticket-bundle.json' : `${ticket?.draft_ticket_key ?? 'draft-ticket'}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  if (!ticket || !bundle) {
    return (
      <section className="panel ticket-panel empty-ticket" aria-labelledby="ticket-title">
        <div className="empty-ticket-visual" aria-hidden="true">
          <div className="ticket-sheet sheet-back" />
          <div className="ticket-sheet sheet-front"><span>ITO + BIM</span><i /><i /><i /></div>
        </div>
        <div>
          <div className="eyebrow">Jira blueprint</div>
          <h2 id="ticket-title">Your dual-ticket draft will appear here</h2>
          <p>Once the minimum fields are present, the mock adapter prepares an ITO request draft and a linked BIM delivery draft.</p>
        </div>
        <div className="boundary-note"><ShieldAlert size={15} /> No real Jira connection</div>
      </section>
    )
  }

  return (
    <section className="panel ticket-panel bundle-panel" aria-labelledby="ticket-title">
      <header className="ticket-topbar">
        <div><div className="eyebrow">Jira handoff blueprint</div><h2 id="ticket-title">Dual-ticket draft bundle</h2></div>
        <div className="ticket-actions">
          <button aria-label="Copy bundle JSON" className="icon-button" onClick={() => void copyTicket()} type="button">{copied ? <Check size={16} /> : <Clipboard size={16} />}</button>
          <button aria-label="Export bundle JSON" className="icon-button" onClick={exportTicket} type="button"><Download size={16} /></button>
        </div>
      </header>
      <div className="bundle-content">
        <DraftTicket draft={bundle.ito_ticket} />
        <div className="relationship-blueprint">
          <span><Link2 size={14} /></span>
          <div><strong>{bundle.proposed_relationship.direction}</strong><small>{bundle.proposed_relationship.relationship_type} · no link created</small></div>
        </div>
        <DraftTicket draft={bundle.bim_ticket} />
      </div>
      <footer className="draft-disclaimer"><ShieldAlert size={14} /> {bundle.disclaimer}</footer>
    </section>
  )
}
