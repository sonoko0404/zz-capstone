<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChatLineSquare, Connection, MagicStick, Warning } from '@element-plus/icons-vue'
import { getStoredSubmissions } from '../services/intakeService'
import type { StoredSubmission } from '../types/intake'

const submissions = ref<StoredSubmission[]>(getStoredSubmissions())
const selectedId = ref(submissions.value[0]?.id ?? '')
const selectedTicket = computed(() => submissions.value.find((ticket) => ticket.id === selectedId.value))

const cards = computed(() => {
  const missing = submissions.value.filter((item) => !item.form.impact || !item.form.acceptanceCriteria).length

  return [
    { label: 'New Requests', value: submissions.value.length, icon: ChatLineSquare, tone: 'primary' },
    { label: 'Missing Info', value: missing, icon: Warning, tone: 'warning' },
    { label: 'Draft Ready', value: submissions.value.length - missing, icon: MagicStick, tone: 'success' },
    { label: 'Ready for Jira', value: Math.max(submissions.value.length - missing - 1, 0), icon: Connection, tone: 'info' },
  ]
})

function formatDate(value: string) {
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}
</script>

<template>
  <section class="view-stack">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Admin queue</p>
        <h2>Review submitted BIM intake before Jira creation</h2>
      </div>
      <el-tag effect="dark" round>Human-in-the-loop MVP</el-tag>
    </div>

    <div class="metric-grid">
      <el-card v-for="card in cards" :key="card.label" class="metric-card" shadow="never">
        <div class="metric-icon" :class="card.tone">
          <el-icon><component :is="card.icon" /></el-icon>
        </div>
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
      </el-card>
    </div>

    <div class="tickets-grid">
      <el-card shadow="never">
        <template #header>
          <div>
            <p class="eyebrow">Request queue</p>
            <h2>Submitted tickets</h2>
          </div>
        </template>
        <el-empty v-if="submissions.length === 0" description="No user submissions yet." />
        <el-table v-else :data="submissions" highlight-current-row @row-click="(row: StoredSubmission) => (selectedId = row.id)">
          <el-table-column label="Linked draft" min-width="180">
            <template #default="{ row }">
              <strong>{{ row.sourceTicketKey }} -> {{ row.bimTicketKey }}</strong>
            </template>
          </el-table-column>
          <el-table-column label="Asset" prop="form.affectedAsset" min-width="200" />
          <el-table-column label="Review stage" min-width="170">
            <template #default="{ row }">
              <el-tag type="warning" effect="light">{{ row.workflowStage }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Submitted" width="150">
            <template #default="{ row }">{{ formatDate(row.submittedAt) }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div>
            <p class="eyebrow">Admin review duties</p>
            <h2>Selected intake</h2>
          </div>
        </template>
        <el-empty v-if="!selectedTicket" description="Select a submitted intake to review." />
        <template v-else>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="Requester">{{ selectedTicket.form.requesterEmail }}</el-descriptions-item>
            <el-descriptions-item label="Department">{{ selectedTicket.form.department }}</el-descriptions-item>
            <el-descriptions-item label="Priority">{{ selectedTicket.draft.suggestedPriority }}</el-descriptions-item>
            <el-descriptions-item label="Admin decision">Review draft, confirm missing info, then approve Jira creation.</el-descriptions-item>
          </el-descriptions>

          <div class="draft-panel">
            <h3>{{ selectedTicket.draft.summary }}</h3>
            <pre>{{ selectedTicket.draft.description }}</pre>
          </div>
        </template>
      </el-card>
    </div>
  </section>
</template>
