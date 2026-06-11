import type { IntakeForm, JiraDraft, StoredSubmission, SubmissionResult } from '../types/intake'

const STORAGE_KEY = 'bim-intake-submissions'

function readStoredSubmissions(): StoredSubmission[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    const submissions = raw ? (JSON.parse(raw) as StoredSubmission[]) : []
    return submissions.map(withDisplayDefaults)
  } catch {
    return []
  }
}

function withDisplayDefaults(submission: StoredSubmission): StoredSubmission {
  return {
    ...submission,
    displayStatus: submission.displayStatus ?? 'Jira draft ready',
    workflowStage: submission.workflowStage ?? 'PO/Admin Review',
  }
}

function writeStoredSubmissions(submissions: StoredSubmission[]) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(submissions))
}

function nextTicketKey(prefix: 'ITO' | 'BIM', currentCount: number) {
  return `${prefix}-${String(10001 + currentCount).padStart(5, '0')}`
}

export function getStoredSubmissions() {
  return readStoredSubmissions()
}

export async function submitIntake(form: IntakeForm, draft: JiraDraft): Promise<SubmissionResult> {
  const apiUrl = import.meta.env.VITE_INTAKE_API_URL?.trim()
  const submittedAt = new Date().toISOString()
  const payload = { form, draft, submittedAt }

  if (apiUrl) {
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })

    if (!response.ok) {
      throw new Error(`Intake API failed with ${response.status}`)
    }

    return (await response.json()) as SubmissionResult
  }

  await new Promise((resolve) => window.setTimeout(resolve, 450))

  const existing = readStoredSubmissions()
  const sourceTicketKey = nextTicketKey('ITO', existing.length)
  const bimTicketKey = nextTicketKey('BIM', existing.length)
  const stored: StoredSubmission = {
    id: crypto.randomUUID(),
    submittedAt,
    form,
    draft,
    sourceTicketKey,
    bimTicketKey,
    displayStatus: 'Submitted',
    workflowStage: 'Request Received',
  }

  writeStoredSubmissions([stored, ...existing].slice(0, 12))

  return {
    sourceTicketKey,
    bimTicketKey,
    linkedAt: submittedAt,
    draft,
    storedCount: existing.length + 1,
  }
}
