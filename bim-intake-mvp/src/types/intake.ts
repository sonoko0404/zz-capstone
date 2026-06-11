export type Urgency = 'Low' | 'Normal' | 'High' | 'Critical'

export interface IntakeForm {
  requesterName: string
  requesterEmail: string
  department: string
  affectedAsset: string
  problemStatement: string
  requestedSolution: string
  businessValue: string
  urgency: Urgency
  dueDate: string
  impact: string
  acceptanceCriteria: string
  contextNotes: string
}

export interface JiraDraft {
  summary: string
  description: string
  acceptanceCriteria: string[]
  suggestedPriority: string
  labels: string[]
  sourceChannel: 'New UI'
}

export interface StoredSubmission {
  id: string
  submittedAt: string
  form: IntakeForm
  draft: JiraDraft
  sourceTicketKey: string
  bimTicketKey: string
  displayStatus?: TicketDisplayStatus
  workflowStage?: WorkflowStage
}

export interface SubmissionResult {
  sourceTicketKey: string
  bimTicketKey: string
  linkedAt: string
  draft: JiraDraft
  storedCount: number
}

export type TicketDisplayStatus = 'Submitted' | 'Needs review' | 'Jira draft ready' | 'Ready for Jira'

export type WorkflowStage =
  | 'Request Received'
  | 'BIM Classification'
  | 'Info Completion'
  | 'Jira Draft'
  | 'PO/Admin Review'
  | 'Create ITO/BIM'
  | 'Link Tickets'
  | 'Status Sync/UAT'

export interface UserSession {
  email: string
  displayName: string
  loginAt: string
  role: 'user' | 'admin'
}
