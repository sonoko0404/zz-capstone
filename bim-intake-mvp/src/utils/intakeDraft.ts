import type { IntakeForm, JiraDraft, Urgency } from '../types/intake'

export const urgencyOptions: Urgency[] = ['Low', 'Normal', 'High', 'Critical']

export const requiredFields: Array<{ key: keyof IntakeForm; label: string; question: string }> = [
  {
    key: 'requesterName',
    label: 'Requester name',
    question: 'Who should BI contact for requirements and UAT?',
  },
  {
    key: 'requesterEmail',
    label: 'Requester email',
    question: 'What email should receive customer-visible ITO updates?',
  },
  {
    key: 'department',
    label: 'Department',
    question: 'Which business department owns this request?',
  },
  {
    key: 'affectedAsset',
    label: 'Affected report or asset',
    question: 'Which report, dashboard, dataset, or workflow is affected?',
  },
  {
    key: 'problemStatement',
    label: 'Problem statement',
    question: 'What problem needs to be solved, in business terms?',
  },
  {
    key: 'businessValue',
    label: 'Business value',
    question: 'What decision, risk, cost, or customer outcome depends on this work?',
  },
  {
    key: 'urgency',
    label: 'Urgency',
    question: 'How urgent is the request compared with normal sprint work?',
  },
]

export const completenessFields: Array<keyof IntakeForm> = [
  'requesterName',
  'requesterEmail',
  'department',
  'affectedAsset',
  'problemStatement',
  'businessValue',
  'urgency',
  'impact',
  'dueDate',
  'acceptanceCriteria',
]

export function defaultIntakeForm(email = ''): IntakeForm {
  return {
    requesterName: '',
    requesterEmail: email,
    department: '',
    affectedAsset: '',
    problemStatement: '',
    requestedSolution: '',
    businessValue: '',
    urgency: 'Normal',
    dueDate: '',
    impact: '',
    acceptanceCriteria: '',
    contextNotes: '',
  }
}

export function createJiraDraft(form: IntakeForm): JiraDraft {
  const asset = form.affectedAsset.trim() || 'BIM request'
  const problem = form.problemStatement.trim() || 'New BIM intake request'
  const generatedAcceptanceCriteria = form.acceptanceCriteria
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)

  return {
    summary: `${asset}: ${shorten(problem, 72)}`,
    description: [
      `Problem: ${problem}`,
      `Business value: ${form.businessValue.trim() || 'Needs confirmation'}`,
      `Requested solution: ${form.requestedSolution.trim() || 'Not specified by requester'}`,
      `Affected asset: ${asset}`,
      `Impact: ${form.impact.trim() || 'Needs follow-up'}`,
      `Requester: ${form.requesterName.trim() || 'Unknown'} (${form.requesterEmail.trim() || 'No email'})`,
      `Department: ${form.department.trim() || 'Unknown'}`,
      `Due date: ${form.dueDate || 'No fixed date'}`,
      `Context: ${form.contextNotes.trim() || 'No additional context provided'}`,
    ].join('\n'),
    acceptanceCriteria:
      generatedAcceptanceCriteria.length > 0
        ? generatedAcceptanceCriteria
        : [
            'BI team confirms the affected asset and scope with the requester.',
            'Updated report, dataset, or workflow addresses the stated business problem.',
            'Requester validates the output during UAT before closure.',
          ],
    suggestedPriority: suggestPriority(form.urgency, form.impact),
    labels: ['bim-intake', 'source-new-ui', normalizeLabel(asset), normalizeLabel(form.department)],
    sourceChannel: 'New UI',
  }
}

export function getCompletionScore(form: IntakeForm) {
  const completed = completenessFields.filter((field) => String(form[field]).trim().length > 0).length
  return Math.round((completed / completenessFields.length) * 100)
}

export function getFollowUpQuestions(form: IntakeForm, isEmailValid: boolean) {
  const questions = requiredFields
    .filter((field) => String(form[field.key]).trim().length === 0)
    .map((field) => field.question)

  if (form.requesterEmail.trim() && !isEmailValid) {
    questions.push('Can you provide a valid requester email address?')
  }

  if (!form.acceptanceCriteria.trim()) {
    questions.push('How will the requester know the BIM work is complete and acceptable?')
  }

  if (!form.impact.trim()) {
    questions.push('How many users, reports, or business decisions are affected?')
  }

  return questions
}

export function isValidEmail(email: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
}

function shorten(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}...` : value
}

function normalizeLabel(value: string) {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')

  return normalized || 'needs-triage'
}

function suggestPriority(urgency: Urgency, impact: string) {
  const impactText = impact.toLowerCase()

  if (urgency === 'Critical' || impactText.includes('executive') || impactText.includes('blocked')) {
    return 'Highest'
  }

  if (urgency === 'High' || impactText.includes('many') || impactText.includes('month-end')) {
    return 'High'
  }

  if (urgency === 'Low') {
    return 'Low'
  }

  return 'Medium'
}
