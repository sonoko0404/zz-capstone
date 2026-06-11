import { createRouter, createWebHistory } from 'vue-router'
import { getSession } from '../services/authService'
import AppShell from '../layouts/AppShell.vue'
import LoginView from '../views/LoginView.vue'
import OverviewView from '../views/OverviewView.vue'
import NewTicketView from '../views/NewTicketView.vue'
import TicketsView from '../views/TicketsView.vue'
import AdminPlanView from '../views/AdminPlanView.vue'
import WorkflowView from '../views/WorkflowView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: () => (getSession() ? '/app/overview' : '/login'),
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { guestOnly: true },
    },
    {
      path: '/app',
      component: AppShell,
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/app/overview' },
        { path: 'overview', name: 'overview', component: OverviewView, meta: { title: 'Overview' } },
        { path: 'new', name: 'new-ticket', component: NewTicketView, meta: { title: 'New Ticket' } },
        { path: 'tickets', name: 'tickets', component: TicketsView, meta: { title: 'My Tickets' } },
        { path: 'admin', name: 'admin-plan', component: AdminPlanView, meta: { title: 'Admin Plan' } },
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
    return '/login'
  }

  if (to.meta.guestOnly && session) {
    return '/app/overview'
  }

  return true
})

export default router
