<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Connection, Finished, Lock, Message } from '@element-plus/icons-vue'
import { ElNotification } from 'element-plus'
import { loginWithEmail } from '../services/authService'
import { isValidEmail } from '../utils/intakeDraft'

const router = useRouter()
const isLoading = ref(false)
const form = reactive({ email: '' })
const emailReady = computed(() => isValidEmail(form.email))

async function submitLogin() {
  if (!emailReady.value) {
    ElNotification.warning({
      title: 'Email required',
      message: 'Enter a valid company email to open the intake workbench.',
    })
    return
  }

  isLoading.value = true

  try {
    await loginWithEmail(form.email)
    router.replace('/app/overview')
  } catch (error) {
    ElNotification.error({
      title: 'Login failed',
      message: error instanceof Error ? error.message : 'Unable to create session.',
    })
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-hero">
      <div class="login-copy">
        <el-tag effect="dark" round>New UI intake channel</el-tag>
        <h1>BIM request intake without the email handoff mess</h1>
        <p>
          Submit structured BI requests, generate Jira-ready drafts, and keep ITO and BIM work linked from the start.
        </p>
        <div class="login-proof">
          <span><el-icon><Finished /></el-icon> Jira draft preview</span>
          <span><el-icon><Connection /></el-icon> Linked ticket plan</span>
          <span><el-icon><Lock /></el-icon> Mock auth boundary</span>
        </div>
      </div>

      <el-card class="login-card" shadow="always">
        <template #header>
          <div class="card-title-row">
            <div>
              <p class="eyebrow">Email sign in</p>
              <h2>Open BIM Workbench</h2>
            </div>
            <el-icon class="card-title-icon"><Message /></el-icon>
          </div>
        </template>

        <el-form label-position="top" @submit.prevent="submitLogin">
          <el-form-item label="Work email" :error="form.email && !emailReady ? 'Use a valid email address.' : ''">
            <el-input
              v-model="form.email"
              size="large"
              type="email"
              placeholder="name@company.com"
              :prefix-icon="Message"
              @keyup.enter="submitLogin"
            />
          </el-form-item>

          <el-button
            class="full-width"
            size="large"
            type="primary"
            :icon="ArrowRight"
            :loading="isLoading"
            @click="submitLogin"
          >
            Continue
          </el-button>
        </el-form>

        <el-alert
          class="login-alert"
          title="MVP mode"
          type="info"
          description="No password is required. The session is stored locally until a real auth API is configured."
          show-icon
          :closable="false"
        />
      </el-card>
    </section>
  </main>
</template>
