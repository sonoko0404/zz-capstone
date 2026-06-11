<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Back, DataAnalysis, Histogram, Operation, SwitchButton } from '@element-plus/icons-vue'
import { clearSession, getSession } from '../services/authService'

const router = useRouter()
const route = useRoute()
const session = computed(() => getSession())
const activeMenu = computed(() => route.path)

const menuItems = [
  { path: '/admin/queue', label: 'Intake Queue', icon: DataAnalysis },
  { path: '/admin/plan', label: 'Admin Plan', icon: Operation },
  { path: '/admin/workflow', label: 'Workflow', icon: Histogram },
]

function logout() {
  clearSession()
  router.replace('/login')
}

function switchToUserLogin() {
  clearSession()
  router.replace('/login')
}
</script>

<template>
  <el-container class="workbench-shell admin-workbench">
    <el-aside class="sidebar admin-sidebar" width="256px">
      <div class="brand-block">
        <div class="brand-mark admin-mark">AD</div>
        <div>
          <strong>BIM Admin</strong>
          <span>Review and routing console</span>
        </div>
      </div>

      <el-menu class="sidebar-menu" :default-active="activeMenu" router>
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-note">
        <span>Admin responsibility</span>
        <strong>Review, approve, and route</strong>
      </div>
    </el-aside>

    <el-container>
      <el-header class="app-header">
        <div>
          <p class="eyebrow">BI operations admin</p>
          <h1>{{ route.meta.title || 'Admin Console' }}</h1>
        </div>
        <div class="user-cluster">
          <el-button :icon="Back" @click="switchToUserLogin">User portal</el-button>
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
