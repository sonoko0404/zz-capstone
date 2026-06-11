import { createRouter, createWebHistory } from 'vue-router'
import { getSession } from '../services/authService'
import AppShell from '../layouts/AppShell.vue'
import AdminShell from '../layouts/AdminShell.vue'
import LoginView from '../views/LoginView.vue'
import AdminLoginView from '../views/AdminLoginView.vue'
import OverviewView from '../views/OverviewView.vue'
import NewTicketView from '../views/NewTicketView.vue'
import TicketsView from '../views/TicketsView.vue'
import AdminQueueView from '../views/AdminQueueView.vue'
import AdminPlanView from '../views/AdminPlanView.vue'
import WorkflowView from '../views/WorkflowView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: () => {
        const session = getSession()
        return session?.role === 'admin' ? '/admin/queue' : session ? '/app/overview' : '/login'
      },
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { guestOnly: true },
    },
    {
      path: '/admin/login',
      name: 'admin-login',
      component: AdminLoginView,
      meta: { guestOnly: true, adminLogin: true },
    },
    {
      path: '/app',
      component: AppShell,
      meta: { requiresAuth: true, role: 'user' },
      children: [
        { path: '', redirect: '/app/overview' },
        { path: 'overview', name: 'overview', component: OverviewView, meta: { title: 'Overview' } },
        { path: 'new', name: 'new-ticket', component: NewTicketView, meta: { title: 'New Ticket' } },
        { path: 'tickets', name: 'tickets', component: TicketsView, meta: { title: 'My Tickets' } },
      ],
    },
    {
      path: '/admin',
      component: AdminShell,
      meta: { requiresAuth: true, role: 'admin' },
      children: [
        { path: '', redirect: '/admin/queue' },
        { path: 'queue', name: 'admin-queue', component: AdminQueueView, meta: { title: 'Intake Queue' } },
        { path: 'plan', name: 'admin-plan', component: AdminPlanView, meta: { title: 'Admin Plan' } },
        { path: 'workflow', name: 'workflow', component: WorkflowView, meta: { title: 'Workflow' } },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

router.beforeEach((to) => {
  const session = getSession()

  if (to.meta.requiresAuth && !session) {
    return to.meta.role === 'admin' ? '/admin/login' : '/login'
  }

  if (to.meta.role === 'admin' && session?.role !== 'admin') {
    return '/admin/login'
  }

  if (to.meta.role === 'user' && session?.role === 'admin') {
    return '/admin/queue'
  }

  if (to.meta.guestOnly && session) {
    const isAdminLogin = Boolean(to.meta.adminLogin)

    if (isAdminLogin && session.role !== 'admin') {
      return true
    }

    if (!isAdminLogin && session.role !== 'user') {
      return true
    }

    return session.role === 'admin' ? '/admin/queue' : '/app/overview'
  }

  return true
})

export default router
