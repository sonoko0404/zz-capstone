import type {
  AttachmentListResponse,
  ContextSummary,
  IntakeResponse,
  JiraRuntimeStatus,
  LLMRuntimeStatus,
  ScenarioSummary,
  StressTestResult,
  TicketGenerationResponse,
} from '../types/intake'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(payload?.detail ?? `Request failed with status ${response.status}`)
  }
  return (await response.json()) as T
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  context: () => request<ContextSummary>('/api/context/summary'),
  llmStatus: () => request<LLMRuntimeStatus>('/api/llm/status'),
  jiraStatus: () => request<JiraRuntimeStatus>('/api/jira/status'),
  samples: async () => (await request<{ requests: string[] }>('/api/sample-requests')).requests,
  scenarios: async () =>
    (await request<{ scenarios: ScenarioSummary[] }>('/api/stress-test/scenarios')).scenarios,
  sendMessage: (sessionId: string, message: string) =>
    request<IntakeResponse>('/api/intake/message', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, message }),
    }),
  reset: (sessionId: string) =>
    request<{ session_id: string; status: string }>('/api/intake/reset', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    }),
  generateTicket: (sessionId: string) =>
    request<TicketGenerationResponse>('/api/intake/generate-ticket', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    }),
  updateField: (sessionId: string, field: string, value: string | boolean | string[] | null, confirmed = true) =>
    request<IntakeResponse>('/api/intake/field', {
      method: 'PATCH',
      body: JSON.stringify({ session_id: sessionId, field, value, confirmed }),
    }),
  uploadAttachment: async (sessionId: string, file: File) => {
    const body = new FormData()
    body.append('session_id', sessionId)
    body.append('file', file)
    const response = await fetch(`${API_BASE}/api/intake/attachments`, {
      method: 'POST',
      body,
    })
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null
      throw new Error(payload?.detail ?? `Upload failed with status ${response.status}`)
    }
    return (await response.json()) as AttachmentListResponse
  },
  removeAttachment: (sessionId: string, filename: string) =>
    request<AttachmentListResponse>('/api/intake/attachments', {
      method: 'DELETE',
      body: JSON.stringify({ session_id: sessionId, filename }),
    }),
  validationAction: (
    sessionId: string,
    action: 'submit' | 'approve' | 'reject',
    validatorName?: string,
    note?: string,
  ) => request<IntakeResponse>(`/api/intake/validation/${action}`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, validator_name: validatorName, note }),
  }),
  runStressTest: (scenarioId: string) =>
    request<StressTestResult>('/api/stress-test/run', {
      method: 'POST',
      body: JSON.stringify({ scenario_id: scenarioId }),
    }),
}
