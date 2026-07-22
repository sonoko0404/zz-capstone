import { AlertTriangle, BookOpen, Database, X } from 'lucide-react'
import type { ContextSummary } from '../types/intake'

interface ContextPanelProps {
  context: ContextSummary | null
  open: boolean
  onClose: () => void
}

export function ContextPanel({ context, open, onClose }: ContextPanelProps) {
  if (!open) return null

  return (
    <>
      <button
        aria-label="Close business context"
        className="drawer-backdrop open"
        onClick={onClose}
        type="button"
      />
      <aside className="context-drawer open">
        <header>
          <div>
            <div className="eyebrow"><BookOpen size={13} /> Static knowledge</div>
            <h2>Business context</h2>
          </div>
          <button aria-label="Close context panel" className="icon-button" onClick={onClose} type="button"><X size={18} /></button>
        </header>

        <div className="drawer-content">
          <div className="static-context-note">
            <Database size={16} />
            <p><strong>Reference-only context</strong><br />No live Power BI or Jira connection is active.</p>
          </div>

          <section>
            <h3>Semantic model tables</h3>
            <div className="context-table-list">
              {context?.tables.map((table) => (
                <article key={table.name}>
                  <strong>{table.name}</strong>
                  <p>{table.description}</p>
                  <small>Use for: {table.use_when}</small>
                </article>
              ))}
            </div>
          </section>

          <section>
            <h3>Working terminology</h3>
            <dl className="terminology-list">
              {Object.entries(context?.terminology ?? {}).map(([term, definition]) => (
                <div key={term}><dt>{term.replace('_', ' ')}</dt><dd>{definition}</dd></div>
              ))}
            </dl>
          </section>

          <section>
            <h3>Known quality warnings</h3>
            <ul className="warning-list">
              {context?.data_quality_warnings.map((warning) => <li key={warning}><AlertTriangle size={14} />{warning}</li>)}
            </ul>
          </section>
        </div>
      </aside>
    </>
  )
}
