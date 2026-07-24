import { Check, Clipboard, Download, FileText, Link2, Paperclip, Send, ShieldAlert, Upload, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { AttachmentDraft, JiraTicketBundlePreview, JiraTicketDraftPreview, TicketPreview } from '../types/intake'

interface TicketPreviewCardProps {
  ticket: TicketPreview | null
  bundle: JiraTicketBundlePreview | null
  pendingAttachments?: AttachmentDraft[]
  jiraProvider?: 'mock' | 'real'
  creating?: boolean
  uploading?: boolean
  onCreateInJira?: () => Promise<void>
  onUploadFiles?: (files: FileList | File[]) => Promise<void>
  onRemoveAttachment?: (filename: string) => Promise<void>
}

function formatBytes(size?: number) {
  if (!size || size <= 0) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
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
        <span><small>Created</small>{draft.created ? 'Yes — in Jira' : 'No — preview only'}</span>
      </div>
      <details>
        <summary><FileText size={13} /> View description blueprint</summary>
        <pre>{draft.description}</pre>
      </details>
      {draft.labels.length > 0 && <div className="ticket-chip-row">{draft.labels.map((label) => <span key={label}>{label}</span>)}</div>}
      {draft.attachments.map((attachment) => (
        <div className="attachment-draft" key={`${draft.project_category}-${attachment.filename}`}>
          <Paperclip size={13} />
          <span>{attachment.filename}</span>
          <small>
            {attachment.source === 'user' ? 'user upload' : 'sanitized chat'}
            {' · '}
            {attachment.uploaded ? 'uploaded' : 'pending'}
          </small>
        </div>
      ))}
    </article>
  )
}

function OptionalAttachments({
  attachments,
  uploading,
  disabled,
  onUploadFiles,
  onRemoveAttachment,
}: {
  attachments: AttachmentDraft[]
  uploading?: boolean
  disabled?: boolean
  onUploadFiles?: (files: FileList | File[]) => Promise<void>
  onRemoveAttachment?: (filename: string) => Promise<void>
}) {
  const inputRef = useRef<HTMLInputElement | null>(null)

  if (!onUploadFiles) return null

  return (
    <div className="optional-attachments">
      <div className="optional-attachments-header">
        <div>
          <strong><Paperclip size={14} /> Optional attachments</strong>
          <p>Add Excel, images, PDFs, or other evidence. Files upload to both ITO and BIM tickets when you create in Jira.</p>
        </div>
        <button
          className="secondary-button attachment-upload-button"
          disabled={disabled || uploading}
          onClick={() => inputRef.current?.click()}
          type="button"
        >
          <Upload size={14} />
          {uploading ? 'Uploading…' : 'Add files'}
        </button>
        <input
          accept=".xlsx,.xls,.csv,.pdf,.png,.jpg,.jpeg,.gif,.webp,.txt,.doc,.docx"
          hidden
          multiple
          onChange={(event) => {
            const files = event.target.files
            if (files?.length) void onUploadFiles(files)
            event.target.value = ''
          }}
          ref={inputRef}
          type="file"
        />
      </div>
      {attachments.length > 0 ? (
        <ul className="optional-attachment-list">
          {attachments.map((attachment) => (
            <li key={attachment.filename}>
              <Paperclip size={13} />
              <div>
                <span>{attachment.filename}</span>
                <small>
                  {attachment.content_type || 'file'}
                  {attachment.size_bytes ? ` · ${formatBytes(attachment.size_bytes)}` : ''}
                  {attachment.uploaded ? ' · uploaded' : ' · ready for Jira'}
                </small>
              </div>
              {onRemoveAttachment && !attachment.uploaded && (
                <button
                  aria-label={`Remove ${attachment.filename}`}
                  disabled={disabled || uploading}
                  onClick={() => void onRemoveAttachment(attachment.filename)}
                  type="button"
                >
                  <X size={14} />
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="optional-attachments-empty">No extra files yet — mockups, sample Excel, or screenshots are optional.</p>
      )}
    </div>
  )
}

export function TicketPreviewCard({
  ticket,
  bundle,
  pendingAttachments = [],
  jiraProvider = 'mock',
  creating = false,
  uploading = false,
  onCreateInJira,
  onUploadFiles,
  onRemoveAttachment,
}: TicketPreviewCardProps) {
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

  const attachmentPanel = (
    <OptionalAttachments
      attachments={pendingAttachments}
      disabled={creating || bundle?.created}
      onRemoveAttachment={onRemoveAttachment}
      onUploadFiles={onUploadFiles}
      uploading={uploading}
    />
  )

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
          <p>Once the minimum fields are present, a local ITO + BIM draft preview appears here. Creating real Jira tickets is a separate step.</p>
        </div>
        <div className="boundary-note"><ShieldAlert size={15} /> Preview only until you create in Jira</div>
      </section>
    )
  }

  return (
    <section className="panel ticket-panel bundle-panel" aria-labelledby="ticket-title">
      <header className="ticket-topbar">
        <div><div className="eyebrow">Jira handoff blueprint</div><h2 id="ticket-title">Dual-ticket draft bundle</h2></div>
        <div className="ticket-actions">
          {onCreateInJira && !bundle.created && (
            <button
              className="primary-button create-jira-button"
              disabled={creating}
              onClick={() => void onCreateInJira()}
              type="button"
            >
              <Send size={14} />
              {creating
                ? jiraProvider === 'real' ? 'Creating in Jira…' : 'Generating preview…'
                : jiraProvider === 'real' ? 'Create in Jira' : 'Generate Jira preview'}
            </button>
          )}
          <button aria-label="Copy bundle JSON" className="icon-button" onClick={() => void copyTicket()} type="button">{copied ? <Check size={16} /> : <Clipboard size={16} />}</button>
          <button aria-label="Export bundle JSON" className="icon-button" onClick={exportTicket} type="button"><Download size={16} /></button>
        </div>
      </header>
      {attachmentPanel}
      <div className="bundle-content">
        <DraftTicket draft={bundle.ito_ticket} />
        <div className="relationship-blueprint">
          <span><Link2 size={14} /></span>
          <div>
            <strong>{bundle.proposed_relationship.direction}</strong>
            <small>
              {bundle.proposed_relationship.relationship_type}
              {bundle.proposed_relationship.created ? ' · link created' : ' · no link created'}
            </small>
          </div>
        </div>
        <DraftTicket draft={bundle.bim_ticket} />
      </div>
      <footer className="draft-disclaimer"><ShieldAlert size={14} /> {bundle.disclaimer}</footer>
    </section>
  )
}
