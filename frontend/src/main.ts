import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/global.css'
import App from './App.vue'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
app.use(createPinia())
app.use(ElementPlus)

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
        { path: 'shipments', name: 'ShipmentList', component: () => import('./pages/customer/ShipmentList.vue') },
        { path: 'shipments/new', name: 'CreateShipment', component: () => import('./pages/customer/CreateShipment.vue') },
        { path: 'shipments/:id', name: 'ShipmentDetail', component: () => import('./pages/customer/ShipmentDetail.vue') },
        { path: 'addresses', name: 'AddressBook', component: () => import('./pages/customer/AddressBook.vue') },
        { path: 'notifications', name: 'Notifications', component: () => import('./pages/customer/Notifications.vue') },
      ],
    },
  ],
})

router.beforeEach((to, _from) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.token) return '/login'
  if (to.path === '/login' && auth.token) return '/shipments'
})

app.use(router)
app.mount('#app')