import { PanelRightClose, PanelRightOpen, ShieldQuestion, Ticket } from 'lucide-react'
import type { ReactNode } from 'react'

interface InsightSidebarProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  children: ReactNode
}

export function InsightSidebar({ open, onOpenChange, children }: InsightSidebarProps) {
  function openAndScroll(targetId: string) {
    const scrollToTarget = () => {
      document.getElementById(targetId)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }

    if (open) {
      scrollToTarget()
      return
    }

    onOpenChange(true)
    window.setTimeout(scrollToTarget, 60)
  }

  return (
    <aside className={`insight-sidebar ${open ? 'open' : 'collapsed'}`} id="insight-column">
      <div className="insight-rail" aria-label="Requirements sidebar">
        <button
          aria-expanded={open}
          aria-label={open ? 'Close sidebar' : 'Open sidebar'}
          className={`rail-icon-button ${open ? 'active' : ''}`}
          data-tooltip={open ? 'Close sidebar' : 'Open sidebar'}
          onClick={() => onOpenChange(!open)}
          type="button"
        >
          {open ? <PanelRightClose aria-hidden="true" size={16} /> : <PanelRightOpen aria-hidden="true" size={16} />}
        </button>

        <div className="rail-divider" aria-hidden="true" />

        <button
          aria-label="Requirements review"
          className="rail-icon-button"
          data-tooltip="Requirements review"
          onClick={() => openAndScroll('explainable-requirements')}
          type="button"
        >
          <ShieldQuestion aria-hidden="true" size={16} />
        </button>

        <button
          aria-label="Ticket draft"
          className="rail-icon-button"
          data-tooltip="Ticket draft"
          onClick={() => openAndScroll('ticket-draft')}
          type="button"
        >
          <Ticket aria-hidden="true" size={16} />
        </button>
      </div>

      {open ? <div className="insight-panels">{children}</div> : null}
    </aside>
  )
}
