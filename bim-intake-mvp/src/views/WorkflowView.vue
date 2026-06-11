<script setup lang="ts">
const workflowSteps = [
  {
    title: 'Request Received',
    description: 'Email and new UI submissions enter one intake record.',
  },
  {
    title: 'BIM Classification',
    description: 'Classifier decides whether the request belongs in the BIM flow.',
  },
  {
    title: 'Info Completion',
    description: 'Agent asks Karen-style follow-up questions for missing fields.',
  },
  {
    title: 'Jira Draft',
    description: 'Summary, description, priority, labels, and AC are generated.',
  },
  {
    title: 'PO/Admin Review',
    description: 'Human review approves or edits the draft before write actions.',
  },
  {
    title: 'Create ITO/BIM',
    description: 'Future Jira API creates customer-visible and BI execution tickets.',
  },
  {
    title: 'Link Tickets',
    description: 'Source and BIM tickets are linked for auditability.',
  },
  {
    title: 'Status Sync/UAT',
    description: 'BIM progress updates source tickets, UAT, and closure readiness.',
  },
]
</script>

<template>
  <section class="view-stack">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Workflow blueprint</p>
        <h2>What happens after a ticket is submitted</h2>
      </div>
      <el-tag type="success" effect="light" round>Planned Jira automation</el-tag>
    </div>

    <el-card shadow="never">
      <el-steps :active="3" align-center class="workflow-steps">
        <el-step v-for="step in workflowSteps" :key="step.title" :title="step.title" />
      </el-steps>
    </el-card>

    <div class="workflow-grid">
      <el-card v-for="(step, index) in workflowSteps" :key="step.title" class="workflow-card" shadow="never">
        <span class="step-number">{{ index + 1 }}</span>
        <h3>{{ step.title }}</h3>
        <p>{{ step.description }}</p>
      </el-card>
    </div>

    <el-card shadow="never">
      <template #header>
        <div>
          <p class="eyebrow">Implementation boundary</p>
          <h2>MVP versus future automation</h2>
        </div>
      </template>
      <el-table
        :data="[
          { capability: 'Submit structured BIM request', mvp: 'Implemented', future: 'Keep' },
          { capability: 'Generate Jira draft', mvp: 'Implemented locally', future: 'Reviewable draft API' },
          { capability: 'Create linked ITO/BIM tickets', mvp: 'Mock keys only', future: 'Jira API write action' },
          { capability: 'Status sync and UAT reminders', mvp: 'Planned screen', future: 'Jira listener and notification rules' },
        ]"
      >
        <el-table-column prop="capability" label="Capability" min-width="240" />
        <el-table-column prop="mvp" label="Current MVP" min-width="180" />
        <el-table-column prop="future" label="Future state" min-width="220" />
      </el-table>
    </el-card>
  </section>
</template>
