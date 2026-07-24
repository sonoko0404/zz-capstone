import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Bot, Database, HelpCircle, RotateCcw, Send, Sparkles, UserRound, Zap } from 'lucide-react'
import type { ChatMessage } from '../types/intake'
import { SampleRequestButtons } from './SampleRequestButtons'
import { messageMatchesEvidence } from './requirementsReview'

interface ChatPanelProps {
  messages: ChatMessage[]
  samples: string[]
  loading: boolean
  error: string | null
  onSend: (message: string) => Promise<void>
  onReset: () => Promise<void>
  evidenceFocus?: { text: string; requestId: number } | null
}

export function ChatPanel({
  messages,
  samples,
  loading,
  error,
  onSend,
  onReset,
  evidenceFocus,
}: ChatPanelProps) {
  const [draft, setDraft] = useState('')
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const messageRefs = useRef<Record<string, HTMLElement | null>>({})

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages, loading])

  useEffect(() => {
    if (!evidenceFocus) return
    const match = messages.find((message) => messageMatchesEvidence(message.content, evidenceFocus.text))
    if (!match) return
    const element = messageRefs.current[match.id]
    setHighlightedMessageId(match.id)
    element?.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      block: 'center',
    })
    const timer = window.setTimeout(() => setHighlightedMessageId(null), 2200)
    return () => window.clearTimeout(timer)
  }, [evidenceFocus, messages])

  async function submit(event?: FormEvent) {
    event?.preventDefault()
    const message = draft.trim()
    if (!message || loading) return
    setDraft('')
    await onSend(message)
  }

  function appendSuggestedReply(reply: string) {
    const trimmed = draft.trim()
    const next = !trimmed
      ? reply
      : trimmed.endsWith(',')
        ? `${trimmed} ${reply}`
        : `${trimmed}, ${reply}`
    setDraft(next)
    requestAnimationFrame(() => {
      const field = composerRef.current
      if (!field) return
      field.focus()
      field.setSelectionRange(next.length, next.length)
    })
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submit()
    }
  }

  return (
    <section className="panel chat-panel" aria-labelledby="chat-title">
      <header className="panel-header chat-header">
        <div>
          <div className="eyebrow"><Sparkles size={13} /> Guided intake</div>
          <h2 id="chat-title">Shape the request together</h2>
        </div>
        <button className="icon-button text-button" onClick={() => void onReset()} type="button">
          <RotateCcw aria-hidden="true" size={15} />
          New intake
        </button>
      </header>

      <div className="chat-body" aria-live="polite">
        {messages.map((message) => (
          <article
            className={`message-row ${message.role}${highlightedMessageId === message.id ? ' evidence-highlight' : ''}`}
            key={message.id}
            ref={(element) => {
              messageRefs.current[message.id] = element
            }}
          >
            <div className="message-avatar" aria-hidden="true">
              {message.role === 'assistant' ? <Bot size={17} /> : <UserRound size={17} />}
            </div>
            <div className="message-content">
              <div className="message-meta">
                {message.role === 'assistant' ? 'BI intake assistant' : 'You'}
                {message.mode === 'draft_ticket' && <span className="message-status">Draft ready</span>}
                {message.role === 'assistant' && message.llmProvider && (
                  <span className={`provider-badge ${message.llmProvider}`}>
                    {message.llmProvider === 'openai'
                      ? 'OpenAI API'
                      : message.llmProvider === 'claude'
                        ? 'Claude'
                        : message.llmProvider === 'deterministic'
                          ? 'Fallback'
                          : 'Guardrail'}
                  </span>
                )}
              </div>
              <p>{message.content}</p>
              {(message.llmProvider === 'openai' || message.llmProvider === 'claude') && (
                <div className="llm-trace" title={message.llmRequestId ?? undefined}>
                  <Zap size={12} />
                  <span>{message.llmModel ?? 'model'}</span>
                  {message.llmLatencyMs !== null && message.llmLatencyMs !== undefined && <span>{message.llmLatencyMs} ms</span>}
                  {message.llmRequestId && <code>{message.llmRequestId.slice(-10)}</code>}
                </div>
              )}
              {message.llmProvider === 'deterministic' && message.fallbackReason && (
                <div className="fallback-warning" role="status">
                  <AlertTriangle size={13} />
                  <span><strong>LLM fallback:</strong> {message.fallbackReason}</span>
                </div>
              )}
              {message.contextUsed && message.contextUsed.length > 0 && (
                <details className="context-evidence">
                  <summary><Database size={13} /> Context used</summary>
                  <ul>
                    {message.contextUsed.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </details>
              )}
              {message.role === 'assistant' && message.questions && message.questions.length > 0 && (
                <div className="question-stack">
                  {message.questions.map((question) => (
                    <div className="question-card" key={`${message.id}-${question.field}`}>
                      <strong>{question.question}</strong>
                      <details>
                        <summary><HelpCircle size={12} /> Why this matters</summary>
                        <p>{question.rationale}</p>
                      </details>
                      <div className="reply-chips">
                        {question.suggested_replies.map((reply) => (
                          <button
                            disabled={loading}
                            key={reply}
                            onClick={() => appendSuggestedReply(reply)}
                            type="button"
                          >
                            {reply}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </article>
        ))}
        {messages.length === 1 && (
          <SampleRequestButtons samples={samples} disabled={loading} onSelect={(sample) => void onSend(sample)} />
        )}
        {loading && (
          <div className="message-row assistant loading-message">
            <div className="message-avatar"><Bot size={17} /></div>
            <div className="thinking-dots" aria-label="Assistant is analyzing the intake">
              <span /> <span /> <span />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <footer className="composer-wrap">
        {error && <div className="inline-error" role="alert">{error}</div>}
        <form className="composer" onSubmit={submit}>
          <textarea
            aria-label="Describe your BI request"
            disabled={loading}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe the decision, audience, data, or report you need…"
            ref={composerRef}
            rows={2}
            value={draft}
          />
          <button className="send-button" disabled={!draft.trim() || loading} type="submit">
            <Send aria-hidden="true" size={17} />
            Send
          </button>
        </form>
        <p className="composer-note">
          Click suggested replies to add them here · Separate answers with commas · Enter to send
        </p>
      </footer>
    </section>
  )
}
