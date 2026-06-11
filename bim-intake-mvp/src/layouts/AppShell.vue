<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataBoard,
  DocumentAdd,
  Files,
  Histogram,
  Operation,
  SwitchButton,
} from '@element-plus/icons-vue'
import { clearSession, getSession } from '../services/authService'

const router = useRouter()
const route = useRoute()
const session = computed(() => getSession())
const activeMenu = computed(() => route.path)

const menuItems = [
  { path: '/app/overview', label: 'Overview', icon: DataBoard },
  { path: '/app/new', label: 'New Ticket', icon: DocumentAdd },
  { path: '/app/tickets', label: 'My Tickets', icon: Files },
  { path: '/app/admin', label: 'Admin Plan', icon: Operation },
  { path: '/app/workflow', label: 'Workflow', icon: Histogram },
]

function logout() {
  clearSession()
  router.replace('/login')
}
</script>

<template>
  <el-container class="workbench-shell">
    <el-aside class="sidebar" width="248px">
      <div class="brand-block">
        <div class="brand-mark">BI</div>
        <div>
          <strong>BIM Intake</strong>
          <span>Product Owner Agent</span>
        </div>
      </div>

      <el-menu class="sidebar-menu" :default-active="activeMenu" router>
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-note">
        <span>Vercel-ready MVP</span>
        <strong>Frontend mock mode</strong>
      </div>
    </el-aside>

    <el-container>
      <el-header class="app-header">
        <div>
          <p class="eyebrow">BI Migration request portal</p>
          <h1>{{ route.meta.title || 'BIM Workbench' }}</h1>
        </div>
        <div class="user-cluster">
          <el-tag effect="plain" round>{{ session?.email }}</el-tag>
          <el-button :icon="SwitchButton" @click="logout">Logout</el-button>
        </div>
      </el-header>

      <el-main class="app-main">
        <RouterView v-slot="{ Component }">
          <Transition name="page-slide" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </el-main>
    </el-container>
  </el-container>
</template>
