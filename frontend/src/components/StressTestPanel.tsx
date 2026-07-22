import { AlertTriangle, Bot, CheckCircle2, FlaskConical, Play, TicketCheck, UserRound } from 'lucide-react'
import type { ScenarioSummary, StressTestResult } from '../types/intake'

interface StressTestPanelProps {
  scenarios: ScenarioSummary[]
  result: StressTestResult | null
  runningId: string | null
  error: string | null
  onRun: (scenarioId: string) => Promise<void>
}

export function StressTestPanel({
  scenarios,
  result,
  runningId,
  error,
  onRun,
}: StressTestPanelProps) {
  return (
    <section className="scenario-workspace" aria-labelledby="scenario-title">
      <div className="scenario-heading">
        <div>
          <div className="eyebrow"><FlaskConical size={13} /> Scenario lab</div>
          <h1 id="scenario-title">Test where the assistant holds the line.</h1>
          <p>Run repeatable demonstrations of clarification quality, data-risk detection, user fatigue, and the enterprise security boundary.</p>
        </div>
        <div className="scenario-stat"><strong>7</strong><span>repeatable scenarios</span></div>
      </div>

      <div className="scenario-grid">
        <aside className="panel scenario-list">
          <h2>Test library</h2>
          {scenarios.map((scenario, index) => (
            <button
              className={`scenario-button ${result?.scenario_id === scenario.scenario_id ? 'active' : ''}`}
              disabled={runningId !== null}
              key={scenario.scenario_id}
              onClick={() => void onRun(scenario.scenario_id)}
              type="button"
            >
              <span className="scenario-index">0{index + 1}</span>
              <span>{scenario.scenario_name}</span>
              <Play size={14} fill="currentColor" />
            </button>
          ))}
        </aside>

        <div className="panel scenario-result">
          {error && <div className="inline-error" role="alert">{error}</div>}
          {!result && !runningId && (
            <div className="empty-scenario">
              <FlaskConical size={34} />
              <h2>Choose a scenario to begin</h2>
              <p>Each run uses the same intake engine and mock Jira boundary as the live conversation.</p>
            </div>
          )}
          {runningId && (
            <div className="empty-scenario"><div className="spinner" /><h2>Running scenario…</h2></div>
          )}
          {result && !runningId && (
            <>
              <header className="result-header">
                <div><span>Run complete</span><h2>{result.scenario_name}</h2></div>
                <div className={`result-badge ${result.ticket_preview ? 'ticket' : ''}`}>
                  {result.ticket_preview ? <TicketCheck size={15} /> : <CheckCircle2 size={15} />}
                  {result.ticket_preview ? 'Draft produced' : 'Boundary held'}
                </div>
              </header>

              <div className="result-columns">
                <section>
                  <h3>Transcript</h3>
                  <div className="mini-transcript">
                    {result.transcript.map((message, index) => (
                      <div className={message.role} key={`${message.role}-${index}-${message.content.slice(0, 12)}`}>
                        <span>{message.role === 'user' ? <UserRound size={13} /> : <Bot size={13} />}</span>
                        <p>{message.content}</p>
                      </div>
                    ))}
                  </div>
                </section>
                <section>
                  <h3>Findings</h3>
                  <ul className="finding-list">
                    {result.findings.map((finding) => <li key={finding}><CheckCircle2 size={15} />{finding}</li>)}
                  </ul>
                  {result.risk_flags.length > 0 && (
                    <div className="result-risks">
                      <strong><AlertTriangle size={14} /> Risks surfaced</strong>
                      {result.risk_flags.map((risk) => <p key={risk}>{risk}</p>)}
                    </div>
                  )}
                </section>
              </div>
              <div className="scenario-evidence">
                <details open>
                  <summary>Final structured intake</summary>
                  <dl>
                    {Object.entries(result.final_intake)
                      .filter(([, value]) => typeof value === 'string' && value.length > 0)
                      .map(([field, value]) => (
                        <div key={field}>
                          <dt>{field.replaceAll('_', ' ')}</dt>
                          <dd>{String(value)}</dd>
                        </div>
                      ))}
                  </dl>
                </details>
                {result.ticket_preview && (
                  <div className="scenario-ticket-proof">
                    <span>{result.ticket_preview.status}</span>
                    <strong>{result.ticket_bundle_preview
                      ? `${result.ticket_bundle_preview.ito_ticket.draft_ticket_key} + ${result.ticket_bundle_preview.bim_ticket.draft_ticket_key}`
                      : result.ticket_preview.draft_ticket_key}</strong>
                    <p>{result.ticket_preview.title}</p>
                    <small>{result.ticket_bundle_preview
                      ? `${result.ticket_bundle_preview.proposed_relationship.direction} · no real link created`
                      : result.ticket_preview.disclaimer}</small>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  )
}
