<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Key, Message, UserFilled } from '@element-plus/icons-vue'
import { ElNotification } from 'element-plus'
import { loginWithEmail } from '../services/authService'
import { isValidEmail } from '../utils/intakeDraft'

const router = useRouter()
const isLoading = ref(false)
const form = reactive({ email: '' })
const emailReady = computed(() => isValidEmail(form.email))

async function submitAdminLogin() {
  if (!emailReady.value) {
    ElNotification.warning({
      title: 'Admin email required',
      message: 'Enter a valid email to open the admin console.',
    })
    return
  }

  isLoading.value = true

  try {
    await loginWithEmail(form.email, 'admin')
    router.replace('/admin/queue')
  } catch (error) {
    ElNotification.error({
      title: 'Admin login failed',
      message: error instanceof Error ? error.message : 'Unable to create admin session.',
    })
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main class="login-page admin-login-page">
    <router-link class="corner-link" to="/login">User login</router-link>
    <section class="login-hero admin-login-hero">
      <div class="login-copy">
        <el-tag effect="dark" round>Admin console</el-tag>
        <h1>Review intake quality before Jira automation runs</h1>
        <p>
          Admins classify requests, request missing information, approve Jira drafts, and monitor linked ITO/BIM handoff.
        </p>
        <div class="login-proof">
          <span><el-icon><UserFilled /></el-icon> Intake queue</span>
          <span><el-icon><Key /></el-icon> Approval boundary</span>
          <span><el-icon><Message /></el-icon> Follow-up ownership</span>
        </div>
      </div>

      <el-card class="login-card" shadow="always">
        <template #header>
          <div class="card-title-row">
            <div>
              <p class="eyebrow">Admin email sign in</p>
              <h2>Open Admin Console</h2>
            </div>
            <el-icon class="card-title-icon"><Key /></el-icon>
          </div>
        </template>

        <el-form label-position="top" @submit.prevent="submitAdminLogin">
          <el-form-item label="Admin email" :error="form.email && !emailReady ? 'Use a valid email address.' : ''">
            <el-input
              v-model="form.email"
              size="large"
              type="email"
              placeholder="admin@company.com"
              :prefix-icon="Message"
              @keyup.enter="submitAdminLogin"
            />
          </el-form-item>

          <el-button
            class="full-width"
            size="large"
            type="primary"
            :icon="ArrowRight"
            :loading="isLoading"
            @click="submitAdminLogin"
          >
            Continue as admin
          </el-button>
        </el-form>

        <el-alert
          class="login-alert"
          title="Prototype access"
          type="warning"
          description="Admin login is email-only for MVP. Real permissions should be enforced by the future auth API."
          show-icon
          :closable="false"
        />
      </el-card>
    </section>
  </main>
</template>
