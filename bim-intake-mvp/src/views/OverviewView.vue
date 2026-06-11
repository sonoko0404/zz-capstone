<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CircleCheck, Files, MagicStick, Plus, Warning } from '@element-plus/icons-vue'
import { getStoredSubmissions } from '../services/intakeService'

const router = useRouter()
const submissions = ref(getStoredSubmissions())

const metrics = computed(() => {
  const total = submissions.value.length
  const missingInfo = submissions.value.filter((item) => !item.form.impact || !item.form.acceptanceCriteria).length
  const draftReady = submissions.value.filter((item) => item.displayStatus === 'Jira draft ready').length

  return [
    { label: 'Submitted tickets', value: total, icon: Files, tone: 'blue' },
    { label: 'Need follow-up', value: missingInfo, icon: Warning, tone: 'amber' },
    { label: 'Draft ready', value: draftReady, icon: MagicStick, tone: 'teal' },
    { label: 'Linked mock pairs', value: total, icon: CircleCheck, tone: 'green' },
  ]
})

const latestTickets = computed(() => submissions.value.slice(0, 4))
</script>

<template>
  <section class="view-stack">
    <div class="hero-panel">
      <div>
        <p class="eyebrow">Operations snapshot</p>
        <h2>One intake layer for clean BIM handoff</h2>
        <p>
          Start with structured request capture, then move toward classification, missing-info follow-up, Jira draft approval,
          and linked ITO/BIM creation.
        </p>
      </div>
      <el-button type="primary" size="large" :icon="Plus" @click="router.push('/app/new')">
        New ticket
      </el-button>
    </div>

    <div class="metric-grid">
      <el-card v-for="metric in metrics" :key="metric.label" class="metric-card" shadow="never">
        <div class="metric-icon" :class="metric.tone">
          <el-icon><component :is="metric.icon" /></el-icon>
        </div>
        <span>{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
      </el-card>
    </div>

    <div class="content-grid">
      <el-card shadow="never">
        <template #header>
          <div class="card-title-row">
            <div>
              <p class="eyebrow">Recent activity</p>
              <h2>Latest submitted tickets</h2>
            </div>
            <el-button text @click="router.push('/app/tickets')">View all</el-button>
          </div>
        </template>

        <el-empty v-if="latestTickets.length === 0" description="No mock tickets submitted yet." />
        <div v-else class="ticket-list">
          <article v-for="ticket in latestTickets" :key="ticket.id" class="ticket-row">
            <div>
              <strong>{{ ticket.form.affectedAsset }}</strong>
              <span>{{ ticket.sourceTicketKey }} -> {{ ticket.bimTicketKey }}</span>
            </div>
            <el-tag type="success" effect="light">{{ ticket.displayStatus }}</el-tag>
          </article>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div>
            <p class="eyebrow">Next operating model</p>
            <h2>After submission</h2>
          </div>
        </template>
        <el-timeline>
          <el-timeline-item timestamp="1" type="primary">Classify as BIM-related request</el-timeline-item>
          <el-timeline-item timestamp="2" type="warning">Ask for missing report, value, impact, and UAT details</el-timeline-item>
          <el-timeline-item timestamp="3" type="success">Generate Jira draft and linked ticket plan</el-timeline-item>
          <el-timeline-item timestamp="4">Admin or PO approves before real Jira creation</el-timeline-item>
        </el-timeline>
      </el-card>
    </div>
  </section>
</template>
