import { createRouter, createWebHistory } from 'vue-router'

import AdminLayout from './layouts/AdminLayout.vue'
import EngineeringLayout from './layouts/EngineeringLayout.vue'
import ResidentLayout from './layouts/ResidentLayout.vue'
import AdminDashboard from './views/AdminDashboard.vue'
import EngineeringDashboard from './views/EngineeringDashboard.vue'
import ResidentHome from './views/ResidentHome.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: ResidentLayout,
      children: [{ path: '', component: ResidentHome }],
    },
    {
      path: '/admin',
      component: AdminLayout,
      children: [{ path: '', component: AdminDashboard }],
    },
    {
      path: '/engineering',
      component: EngineeringLayout,
      children: [{ path: '', component: EngineeringDashboard }],
    },
  ],
})

export default router
