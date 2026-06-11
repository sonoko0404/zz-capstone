<script setup lang="ts">
import { computed, ref } from 'vue'
import { Document, Refresh } from '@element-plus/icons-vue'
import { getStoredSubmissions } from '../services/intakeService'
import type { StoredSubmission } from '../types/intake'

const submissions = ref<StoredSubmission[]>(getStoredSubmissions())
const selectedId = ref(submissions.value[0]?.id ?? '')
const selectedTicket = computed(() => submissions.value.find((ticket) => ticket.id === selectedId.value))

function refreshTickets() {
  submissions.value = getStoredSubmissions()
  selectedId.value = submissions.value[0]?.id ?? ''
}

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
        <p class="eyebrow">My tickets</p>
        <h2>Submitted request history</h2>
      </div>
      <el-button :icon="Refresh" @click="refreshTickets">Refresh</el-button>
    </div>

    <div class="tickets-grid">
      <el-card shadow="never">
        <el-empty v-if="submissions.length === 0" description="No submitted tickets yet." />
        <el-table v-else :data="submissions" highlight-current-row @row-click="(row: StoredSubmission) => (selectedId = row.id)">
          <el-table-column label="Linked tickets" min-width="180">
            <template #default="{ row }">
              <strong>{{ row.sourceTicketKey }} -> {{ row.bimTicketKey }}</strong>
            </template>
          </el-table-column>
          <el-table-column label="Asset" prop="form.affectedAsset" min-width="200" />
          <el-table-column label="Status" width="150">
            <template #default="{ row }">
              <el-tag type="success" effect="light">{{ row.displayStatus }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Submitted" width="150">
            <template #default="{ row }">{{ formatDate(row.submittedAt) }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-title-row">
            <div>
              <p class="eyebrow">Selected ticket</p>
              <h2>Detail preview</h2>
            </div>
            <el-icon class="card-title-icon"><Document /></el-icon>
          </div>
        </template>

        <el-empty v-if="!selectedTicket" description="Select a ticket to inspect the draft." />
        <template v-else>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="Source ticket">{{ selectedTicket.sourceTicketKey }}</el-descriptions-item>
            <el-descriptions-item label="BIM ticket">{{ selectedTicket.bimTicketKey }}</el-descriptions-item>
            <el-descriptions-item label="Workflow stage">{{ selectedTicket.workflowStage }}</el-descriptions-item>
            <el-descriptions-item label="Requester">{{ selectedTicket.form.requesterEmail }}</el-descriptions-item>
            <el-descriptions-item label="Priority">{{ selectedTicket.draft.suggestedPriority }}</el-descriptions-item>
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
