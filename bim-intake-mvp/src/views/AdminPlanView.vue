<script setup lang="ts">
import { CircleCheck, Connection, DataAnalysis, EditPen, MagicStick, Warning } from '@element-plus/icons-vue'

const queueCards = [
  { label: 'New Requests', value: 8, icon: EditPen, type: 'primary' },
  { label: 'Missing Info', value: 3, icon: Warning, type: 'warning' },
  { label: 'Draft Ready', value: 5, icon: MagicStick, type: 'success' },
  { label: 'Ready for Jira', value: 2, icon: Connection, type: 'info' },
]

const responsibilities = [
  'Classify incoming email/UI requests as BIM or non-BIM.',
  'Trigger follow-up questions when report, impact, value, or acceptance criteria are incomplete.',
  'Review generated summary, description, labels, priority, and acceptance criteria.',
  'Approve creation of linked ITO and BIM Jira issues once Jira API access is enabled.',
  'Monitor status sync, UAT feedback, and closure readiness across both Jira records.',
]
</script>

<template>
  <section class="view-stack">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Admin prototype</p>
        <h2>Operational console plan</h2>
      </div>
      <el-tag effect="dark" round>Static MVP</el-tag>
    </div>

    <div class="metric-grid">
      <el-card v-for="card in queueCards" :key="card.label" class="metric-card" shadow="never">
        <div class="metric-icon" :class="card.type">
          <el-icon><component :is="card.icon" /></el-icon>
        </div>
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
      </el-card>
    </div>

    <div class="content-grid">
      <el-card shadow="never">
        <template #header>
          <div class="card-title-row">
            <div>
              <p class="eyebrow">Admin responsibilities</p>
              <h2>Human-in-the-loop controls</h2>
            </div>
            <el-icon class="card-title-icon"><DataAnalysis /></el-icon>
          </div>
        </template>
        <el-timeline>
          <el-timeline-item v-for="item in responsibilities" :key="item" type="primary">
            {{ item }}
          </el-timeline-item>
        </el-timeline>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div>
            <p class="eyebrow">Phase plan</p>
            <h2>From static console to Jira automation</h2>
          </div>
        </template>
        <el-steps direction="vertical" :active="1">
          <el-step title="MVP" description="Static queue summary, form review, and process explanation." />
          <el-step title="Phase 2" description="Editable local queue: assign owner, mark missing info, approve draft." />
          <el-step title="Phase 3" description="Jira API creates ITO and BIM issues, then validates the link." />
          <el-step title="Phase 4" description="Status sync, UAT prompts, closure guardrails, and release summaries." />
        </el-steps>
        <el-alert
          class="spaced-alert"
          title="Admin actions are intentionally non-destructive in this MVP."
          type="info"
          :closable="false"
          show-icon
        />
      </el-card>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="card-title-row">
          <div>
            <p class="eyebrow">Traceability goal</p>
            <h2>Every business request gets a linked execution record</h2>
          </div>
          <el-icon class="card-title-icon success"><CircleCheck /></el-icon>
        </div>
      </template>
      <p class="body-copy">
        The admin console should prevent orphan BIM tickets by requiring a source ITO/SCP link or an explicit internal-work
        exception before the request reaches sprint planning.
      </p>
    </el-card>
  </section>
</template>
