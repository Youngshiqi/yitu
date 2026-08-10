import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia } from 'pinia'
import './styles/global.css'
import App from './App.vue'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'Login', component: () => import('./pages/Login.vue') },
    {
      path: '/',
      component: () => import('./components/Layout.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/shipments' },
        { path: 'shipments', name: 'ShipmentList', component: () => import('./pages/ShipmentList.vue') },
        { path: 'shipments/new', name: 'CreateShipment', component: () => import('./pages/CreateShipment.vue') },
        { path: 'shipments/:id', name: 'ShipmentDetail', component: () => import('./pages/ShipmentDetail.vue') },
        { path: 'notifications', name: 'Notifications', component: () => import('./pages/Notifications.vue') },
        { path: 'operations', name: 'Operations', component: () => import('./pages/OperationsConsole.vue') },
        { path: 'exceptions', name: 'ExceptionList', component: () => import('./pages/ExceptionList.vue') },
        { path: 'exceptions/:id', name: 'ExceptionDetail', component: () => import('./pages/ExceptionDetail.vue') },
        { path: 'admin/dead-letters', name: 'AdminDeadLetters', component: () => import('./pages/AdminDeadLetters.vue') },
      ],
    },
  ],
})

router.beforeEach((to, _from) => {
  const token = localStorage.getItem('yitu_token')
  if (to.meta.requiresAuth && !token) return '/login'
  if (to.path === '/login' && token) return '/shipments'
})

app.use(router)
app.mount('#app')