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
  AttachmentDraft,
  ChatMessage,
  ContextSummary,
  IntakeData,
  IntakeResponse,
  FieldMetadata,
  JiraRuntimeStatus,
  JiraTicketBundlePreview,
  LLMRuntimeStatus,
  ScenarioSummary,
  StressTestResult,
  TicketPreview,
  RequirementNode,
  ValidationState,
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
  const [completionScore, setCompletionScore] = useState(0)
  const [readyForTicket, setReadyForTicket] = useState(false)
  const [validationReady, setValidationReady] = useState(false)
  const [validationState, setValidationState] = useState<ValidationState>('gathering')
  const [evidenceFocus, setEvidenceFocus] = useState<{ text: string; requestId: number } | null>(null)
  const [samples, setSamples] = useState<string[]>([])
  const [context, setContext] = useState<ContextSummary | null>(null)
  const [llmStatus, setLlmStatus] = useState<LLMRuntimeStatus | null>(null)
  const [jiraStatus, setJiraStatus] = useState<JiraRuntimeStatus | null>(null)
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([])
  const [stressResult, setStressResult] = useState<StressTestResult | null>(null)
  const [contextOpen, setContextOpen] = useState(false)
  const [insightsOpen, setInsightsOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [creatingTicket, setCreatingTicket] = useState(false)
  const [uploadingAttachment, setUploadingAttachment] = useState(false)
  const [pendingAttachments, setPendingAttachments] = useState<AttachmentDraft[]>([])
  const [savingField, setSavingField] = useState(false)
  const [runningId, setRunningId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stressError, setStressError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([api.samples(), api.context(), api.scenarios(), api.llmStatus(), api.jiraStatus()])
      .then(([sampleData, contextData, scenarioData, statusData, jiraStatusData]) => {
        if (controller.signal.aborted) return
        setSamples(sampleData)
        setContext(contextData)
        setScenarios(scenarioData)
        setLlmStatus(statusData)
        setJiraStatus(jiraStatusData)
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
        configured: response.llm_provider === 'openai' || response.llm_provider === 'claude',
        provider: response.llm_provider,
        model: response.llm_model,
        message: response.fallback_reason ?? 'LLM response completed successfully.',
      })
    }
    setIntake(response.intake)
    setTicket(response.ticket_preview)
    setTicketBundle(response.ticket_bundle_preview)
    if (response.pending_attachments) setPendingAttachments(response.pending_attachments)
    setFieldMetadata(response.field_metadata)
    setRequirements(response.requirements_matrix)
    setAmbiguousFields(response.ambiguous_fields)
    setCompletionScore(response.completion_score)
    setReadyForTicket(response.ready_for_ticket)
    setValidationReady(response.validation_ready)
    setValidationState(response.validation_state)
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
      setPendingAttachments([])
      setFieldMetadata({})
      setRequirements([])
      setAmbiguousFields([])
      setCompletionScore(0)
      setReadyForTicket(false)
      setValidationReady(false)
      setValidationState('gathering')
      setEvidenceFocus(null)
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

  async function createTicketsInJira() {
    setCreatingTicket(true)
    setError(null)
    try {
      const preview = await api.generateTicket(sessionId)
      setTicket(preview.ticket_preview)
      setTicketBundle(preview.ticket_bundle_preview)
      if (preview.pending_attachments) setPendingAttachments(preview.pending_attachments)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not create Jira tickets.')
    } finally {
      setCreatingTicket(false)
    }
  }

  async function uploadAttachmentFiles(files: FileList | File[]) {
    setUploadingAttachment(true)
    setError(null)
    try {
      let latest = pendingAttachments
      for (const file of Array.from(files)) {
        const response = await api.uploadAttachment(sessionId, file)
        latest = response.attachments
        if (response.ticket_preview) setTicket(response.ticket_preview)
        if (response.ticket_bundle_preview) setTicketBundle(response.ticket_bundle_preview)
      }
      setPendingAttachments(latest)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not upload the attachment.')
    } finally {
      setUploadingAttachment(false)
    }
  }

  async function removePendingAttachment(filename: string) {
    setUploadingAttachment(true)
    setError(null)
    try {
      const response = await api.removeAttachment(sessionId, filename)
      setPendingAttachments(response.attachments)
      if (response.ticket_preview) setTicket(response.ticket_preview)
      if (response.ticket_bundle_preview) setTicketBundle(response.ticket_bundle_preview)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not remove the attachment.')
    } finally {
      setUploadingAttachment(false)
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
                : llmStatus?.provider === 'claude'
                  ? `Claude · ${llmStatus.model ?? 'configured'}`
                  : llmStatus?.provider === 'deterministic'
                    ? 'Deterministic fallback'
                    : 'Checking AI'}
            </span>
          </div>
          <div className="safety-chip" title={jiraStatus?.message ?? 'Checking Jira configuration'}>
            <ShieldCheck size={14} />
            <span>{jiraStatus?.provider === 'real' ? 'Real Jira enabled' : jiraStatus?.provider === 'mock' ? 'Mock Jira' : 'Checking Jira'}</span>
          </div>
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
              evidenceFocus={evidenceFocus}
            />
            <InsightSidebar onOpenChange={setInsightsOpen} open={insightsOpen}>
              <div id="explainable-requirements">
                <RequirementsMatrix
                  ambiguousFields={ambiguousFields}
                  completionScore={completionScore}
                  hasDraft={Boolean(ticketBundle)}
                  intake={intake}
                  metadata={fieldMetadata}
                  nodes={requirements}
                  onEdit={updateField}
                  onViewEvidence={(evidence) => setEvidenceFocus({
                    text: evidence,
                    requestId: Date.now(),
                  })}
                  readyForTicket={readyForTicket}
                  saving={savingField}
                  validationReady={validationReady}
                  validationState={validationState}
                />
              </div>
              <div id="ticket-draft">
                <TicketPreviewCard
                  bundle={ticketBundle}
                  creating={creatingTicket}
                  jiraProvider={jiraStatus?.provider ?? 'mock'}
                  onCreateInJira={createTicketsInJira}
                  onRemoveAttachment={removePendingAttachment}
                  onUploadFiles={uploadAttachmentFiles}
                  pendingAttachments={pendingAttachments}
                  ticket={ticket}
                  uploading={uploadingAttachment}
                />
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
