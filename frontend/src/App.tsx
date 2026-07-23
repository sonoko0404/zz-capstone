import { useEffect, useState } from 'react'
import { BookOpen, BrainCircuit, FlaskConical, MessageSquareText, ShieldCheck } from 'lucide-react'
import { api } from './api/client'
import { ChatPanel } from './components/ChatPanel'
import { ContextPanel } from './components/ContextPanel'
import { InsightSidebar } from './components/InsightSidebar'
import { RequirementsMatrix } from './components/RequirementsMatrix'
import { StressTestPanel } from './components/StressTestPanel'
import { TicketPreviewCard } from './components/TicketPreviewCard'
import type {
  ChatMessage,
  ContextSummary,
  IntakeData,
  IntakeResponse,
  FieldMetadata,
  JiraTicketBundlePreview,
  LLMRuntimeStatus,
  ScenarioSummary,
  StressTestResult,
  TicketPreview,
  RequirementNode,
} from './types/intake'

const GREETING: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content:
    'Tell me what BI decision or reporting need you’re working on. I’ll capture what you already know, then ask only the highest-value follow-up questions.',
}

type WorkspaceView = 'intake' | 'scenarios'

export function App() {
  const [sessionId] = useState(() => crypto.randomUUID())
  const [view, setView] = useState<WorkspaceView>('intake')
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING])
  const [intake, setIntake] = useState<IntakeData | null>(null)
  const [ticket, setTicket] = useState<TicketPreview | null>(null)
  const [ticketBundle, setTicketBundle] = useState<JiraTicketBundlePreview | null>(null)
  const [fieldMetadata, setFieldMetadata] = useState<Record<string, FieldMetadata>>({})
  const [requirements, setRequirements] = useState<RequirementNode[]>([])
  const [ambiguousFields, setAmbiguousFields] = useState<string[]>([])
  const [samples, setSamples] = useState<string[]>([])
  const [context, setContext] = useState<ContextSummary | null>(null)
  const [llmStatus, setLlmStatus] = useState<LLMRuntimeStatus | null>(null)
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([])
  const [stressResult, setStressResult] = useState<StressTestResult | null>(null)
  const [contextOpen, setContextOpen] = useState(false)
  const [insightsOpen, setInsightsOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [savingField, setSavingField] = useState(false)
  const [runningId, setRunningId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stressError, setStressError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([api.samples(), api.context(), api.scenarios(), api.llmStatus()])
      .then(([sampleData, contextData, scenarioData, statusData]) => {
        if (controller.signal.aborted) return
        setSamples(sampleData)
        setContext(contextData)
        setScenarios(scenarioData)
        setLlmStatus(statusData)
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setSamples([
            'I need a dashboard for sales managers to track units sold from Salesforce within two weeks.',
            'Can you create a report showing delayed shipments by customer and region?',
            'We need to understand why some BIM tickets take much longer to resolve.',
          ])
        }
      })
    return () => controller.abort()
  }, [])

  function applyResponse(response: IntakeResponse, appendAssistant = true) {
    if (appendAssistant) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.assistant_message,
          mode: response.mode,
          contextUsed: response.context_used,
          questions: response.next_questions,
          llmProvider: response.llm_provider,
          llmModel: response.llm_model,
          llmRequestId: response.llm_request_id,
          llmLatencyMs: response.llm_latency_ms,
          fallbackReason: response.fallback_reason,
        },
      ])
    }
    if (response.llm_provider !== 'system') {
      setLlmStatus({
        configured: response.llm_provider === 'openai',
        provider: response.llm_provider,
        model: response.llm_model,
        message: response.fallback_reason ?? 'OpenAI API response completed successfully.',
      })
    }
    setIntake(response.intake)
    setTicket(response.ticket_preview)
    setTicketBundle(response.ticket_bundle_preview)
    setFieldMetadata(response.field_metadata)
    setRequirements(response.requirements_matrix)
    setAmbiguousFields(response.ambiguous_fields)
  }

  async function sendMessage(message: string) {
    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: message }
    setMessages((current) => [...current, userMessage])
    setLoading(true)
    setError(null)
    try {
      const response = await api.sendMessage(sessionId, message)
      applyResponse(response)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The assistant is unavailable.')
    } finally {
      setLoading(false)
    }
  }

  async function resetIntake() {
    setLoading(true)
    setError(null)
    try {
      await api.reset(sessionId)
      setMessages([GREETING])
      setIntake(null)
      setTicket(null)
      setTicketBundle(null)
      setFieldMetadata({})
      setRequirements([])
      setAmbiguousFields([])
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not reset the intake.')
    } finally {
      setLoading(false)
    }
  }

  async function updateField(field: string, value: string | boolean | string[] | null) {
    setSavingField(true)
    setError(null)
    try {
      applyResponse(await api.updateField(sessionId, field, value), false)
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : 'Could not update the requirement.'
      setError(message)
      throw requestError
    } finally {
      setSavingField(false)
    }
  }

  async function runScenario(scenarioId: string) {
    setRunningId(scenarioId)
    setStressError(null)
    try {
      setStressResult(await api.runStressTest(scenarioId))
    } catch (requestError) {
      setStressError(requestError instanceof Error ? requestError.message : 'Could not run the scenario.')
    } finally {
      setRunningId(null)
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true"><span>A</span></div>
          <div>
            <strong>AI BI Intake Assistant</strong>
            <span>CMU × Armada · Standalone prototype</span>
          </div>
        </div>

        <nav className="view-switcher" aria-label="Workspace views">
          <button className={view === 'intake' ? 'active' : ''} onClick={() => setView('intake')} type="button">
            <MessageSquareText size={15} /> Intake workspace
          </button>
          <button className={view === 'scenarios' ? 'active' : ''} onClick={() => setView('scenarios')} type="button">
            <FlaskConical size={15} /> Scenario lab
          </button>
        </nav>

        <div className="topbar-actions">
          <div className={`llm-status-chip ${llmStatus?.provider ?? 'checking'}`} title={llmStatus?.message ?? 'Checking backend AI configuration'}>
            <BrainCircuit size={14} />
            <span>
              {llmStatus?.provider === 'openai'
                ? `OpenAI · ${llmStatus.model ?? 'configured'}`
                : llmStatus?.provider === 'deterministic'
                  ? 'Deterministic fallback'
                  : 'Checking AI'}
            </span>
          </div>
          <div className="safety-chip"><ShieldCheck size={14} /><span>Mock Jira</span></div>
          <button className="context-button" onClick={() => setContextOpen(true)} type="button">
            <BookOpen size={15} /> Business context
          </button>
        </div>
      </header>

      <main>
        {view === 'intake' ? (
          <div className={`intake-workspace ${insightsOpen ? 'insights-open' : 'insights-collapsed'}`}>
            <ChatPanel
              error={error}
              loading={loading}
              messages={messages}
              onReset={resetIntake}
              onSend={sendMessage}
              samples={samples}
            />
            <InsightSidebar onOpenChange={setInsightsOpen} open={insightsOpen}>
              <div id="explainable-requirements">
                <RequirementsMatrix
                  ambiguousFields={ambiguousFields}
                  intake={intake}
                  metadata={fieldMetadata}
                  nodes={requirements}
                  onEdit={updateField}
                  saving={savingField}
                />
              </div>
              <div id="ticket-draft">
                <TicketPreviewCard bundle={ticketBundle} ticket={ticket} />
              </div>
            </InsightSidebar>
          </div>
        ) : (
          <StressTestPanel
            error={stressError}
            onRun={runScenario}
            result={stressResult}
            runningId={runningId}
            scenarios={scenarios}
          />
        )}
      </main>

      <ContextPanel context={context} onClose={() => setContextOpen(false)} open={contextOpen} />
    </div>
  )
}
