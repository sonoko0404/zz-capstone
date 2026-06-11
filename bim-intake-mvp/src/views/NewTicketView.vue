<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElNotification } from 'element-plus'
import { Check, DocumentChecked, RefreshLeft } from '@element-plus/icons-vue'
import { getSession } from '../services/authService'
import { getStoredSubmissions, submitIntake } from '../services/intakeService'
import type { IntakeForm, SubmissionResult } from '../types/intake'
import {
  createJiraDraft,
  defaultIntakeForm,
  getCompletionScore,
  getFollowUpQuestions,
  isValidEmail,
  requiredFields,
  urgencyOptions,
} from '../utils/intakeDraft'

const session = getSession()
const form = reactive<IntakeForm>(defaultIntakeForm(session?.email ?? ''))
const submittedOnce = ref(false)
const isSubmitting = ref(false)
const result = ref<SubmissionResult | null>(null)
const storedCount = ref(getStoredSubmissions().length)

if (session?.displayName) {
  form.requesterName = session.displayName
}

const emailReady = computed(() => isValidEmail(form.requesterEmail))
const missingFields = computed(() =>
  requiredFields.filter((field) => String(form[field.key]).trim().length === 0),
)
const completionScore = computed(() => getCompletionScore(form))
const followUpQuestions = computed(() => getFollowUpQuestions(form, emailReady.value))
const draft = computed(() => createJiraDraft(form))
const canSubmit = computed(() => missingFields.value.length === 0 && emailReady.value)

function fieldError(key: keyof IntakeForm) {
  if (!submittedOnce.value) {
    return ''
  }

  if (key === 'requesterEmail' && !emailReady.value) {
    return form.requesterEmail.trim() ? 'Use a valid email address.' : 'Requester email is required.'
  }

  const field = requiredFields.find((item) => item.key === key)
  return field && !String(form[key]).trim() ? `${field.label} is required.` : ''
}

function resetForm() {
  Object.assign(form, defaultIntakeForm(session?.email ?? ''))
  if (session?.displayName) {
    form.requesterName = session.displayName
  }
  submittedOnce.value = false
  result.value = null
}

async function handleSubmit() {
  submittedOnce.value = true
  result.value = null

  if (!canSubmit.value) {
    ElNotification.warning({
      title: 'Missing required details',
      message: 'Complete the required intake fields before creating a Jira draft.',
    })
    return
  }

  isSubmitting.value = true

  try {
    result.value = await submitIntake({ ...form }, draft.value)
    storedCount.value = getStoredSubmissions().length
    ElNotification.success({
      title: 'Draft created',
      message: `${result.value.sourceTicketKey} linked to ${result.value.bimTicketKey}`,
    })
  } catch (error) {
    ElNotification.error({
      title: 'Submission failed',
      message: error instanceof Error ? error.message : 'Unable to submit this request.',
    })
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <section class="view-stack">
    <div class="section-heading">
      <div>
        <p class="eyebrow">New ticket</p>
        <h2>Structured BIM request form</h2>
      </div>
      <el-progress class="completion-ring" type="dashboard" :percentage="completionScore" :width="82" />
    </div>

    <div class="new-ticket-grid">
      <el-card class="form-card" shadow="never">
        <el-form label-position="top" @submit.prevent="handleSubmit">
          <div class="form-grid">
            <el-form-item label="Requester name" :error="fieldError('requesterName')">
              <el-input v-model="form.requesterName" size="large" placeholder="Requester name" />
            </el-form-item>
            <el-form-item label="Requester email" :error="fieldError('requesterEmail')">
              <el-input v-model="form.requesterEmail" size="large" type="email" placeholder="name@company.com" />
            </el-form-item>
            <el-form-item label="Department" :error="fieldError('department')">
              <el-input v-model="form.department" size="large" placeholder="Revenue Operations" />
            </el-form-item>
            <el-form-item label="Urgency">
              <el-select v-model="form.urgency" size="large" class="full-width">
                <el-option v-for="option in urgencyOptions" :key="option" :label="option" :value="option" />
              </el-select>
            </el-form-item>
          </div>

          <el-form-item label="Affected report, dashboard, dataset, or workflow" :error="fieldError('affectedAsset')">
            <el-input v-model="form.affectedAsset" size="large" placeholder="Monthly Margin Dashboard" />
          </el-form-item>

          <el-form-item label="Problem statement" :error="fieldError('problemStatement')">
            <el-input
              v-model="form.problemStatement"
              type="textarea"
              :rows="4"
              placeholder="Describe the business problem, not just the requested solution."
            />
          </el-form-item>

          <el-form-item label="Business value" :error="fieldError('businessValue')">
            <el-input
              v-model="form.businessValue"
              type="textarea"
              :rows="3"
              placeholder="Decision, risk, cost, revenue, or customer outcome this work supports."
            />
          </el-form-item>

          <div class="form-grid">
            <el-form-item label="Requested solution">
              <el-input v-model="form.requestedSolution" size="large" placeholder="Optional" />
            </el-form-item>
            <el-form-item label="Needed by">
              <el-date-picker
                v-model="form.dueDate"
                size="large"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="Select date"
                class="full-width"
              />
            </el-form-item>
          </div>

          <el-form-item label="Impact">
            <el-input
              v-model="form.impact"
              type="textarea"
              :rows="3"
              placeholder="Number of users, reports, decisions, period close timing, or blocked work."
            />
          </el-form-item>

          <el-form-item label="Acceptance criteria">
            <el-input
              v-model="form.acceptanceCriteria"
              type="textarea"
              :rows="3"
              placeholder="One measurable outcome per line."
            />
          </el-form-item>

          <el-form-item label="Additional context or attachment notes">
            <el-input
              v-model="form.contextNotes"
              type="textarea"
              :rows="3"
              placeholder="Links, screenshots, source systems, or sample rows."
            />
          </el-form-item>

          <el-alert
            v-if="result"
            class="success-pop"
            type="success"
            show-icon
            :closable="false"
            :title="`${result.sourceTicketKey} linked to ${result.bimTicketKey}`"
            description="The mock submission is saved locally and ready for PO/Admin review."
          />

          <div class="form-actions">
            <el-button :icon="RefreshLeft" size="large" @click="resetForm">Clear</el-button>
            <el-button type="primary" :icon="Check" size="large" :loading="isSubmitting" @click="handleSubmit">
              Submit request
            </el-button>
          </div>
        </el-form>
      </el-card>

      <aside class="preview-stack">
        <el-card shadow="never">
          <template #header>
            <div class="card-title-row">
              <div>
                <p class="eyebrow">Follow-up queue</p>
                <h2>Missing information</h2>
              </div>
              <el-tag round>{{ followUpQuestions.length }}</el-tag>
            </div>
          </template>
          <el-empty v-if="followUpQuestions.length === 0" description="Ready for draft review." />
          <ul v-else class="question-list">
            <li v-for="question in followUpQuestions" :key="question">{{ question }}</li>
          </ul>
        </el-card>

        <el-card shadow="never">
          <template #header>
            <div class="card-title-row">
              <div>
                <p class="eyebrow">Jira artifact preview</p>
                <h2>BIM draft</h2>
              </div>
              <el-tag type="warning" round>{{ draft.suggestedPriority }}</el-tag>
            </div>
          </template>

          <el-descriptions :column="1" border>
            <el-descriptions-item label="Summary">{{ draft.summary }}</el-descriptions-item>
            <el-descriptions-item label="Source">{{ draft.sourceChannel }}</el-descriptions-item>
            <el-descriptions-item label="Labels">
              <div class="tag-row">
                <el-tag v-for="label in draft.labels" :key="label" effect="plain">{{ label }}</el-tag>
              </div>
            </el-descriptions-item>
          </el-descriptions>

          <div class="draft-panel">
            <h3>Description</h3>
            <pre>{{ draft.description }}</pre>
          </div>

          <div class="draft-panel">
            <h3>Acceptance criteria</h3>
            <ul>
              <li v-for="item in draft.acceptanceCriteria" :key="item">{{ item }}</li>
            </ul>
          </div>
        </el-card>

        <el-card shadow="never">
          <div class="mini-stat">
            <el-icon><DocumentChecked /></el-icon>
            <span>{{ storedCount }} local mock submission{{ storedCount === 1 ? '' : 's' }}</span>
          </div>
        </el-card>
      </aside>
    </div>
  </section>
</template>
