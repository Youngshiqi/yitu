<script setup lang="ts">
import { useAuthStore, type Role } from '../stores/auth'
import { useRoute } from 'vue-router'
const auth = useAuthStore()
const route = useRoute()

interface MenuItem { label: string; path: string; icon: string; roles: Role[] }

const ALL_MENU: MenuItem[] = [
  { label: '运单列表', path: '/shipments', icon: '📦', roles: ['CUSTOMER'] },
  { label: '创建运单', path: '/shipments/new', icon: '➕', roles: ['CUSTOMER'] },
  { label: '地址簿', path: '/addresses', icon: '📍', roles: ['CUSTOMER'] },
  { label: '通知中心', path: '/notifications', icon: '🔔', roles: ['CUSTOMER', 'COURIER', 'STATION_OPERATOR', 'OPERATIONS_ADMIN'] },
]

const items = ALL_MENU.filter(m => auth.user && m.roles.includes(auth.user.role))

const ROLES: Record<string, string> = {
  CUSTOMER: '客户', COURIER: '快递员', STATION_OPERATOR: '网点员', OPERATIONS_ADMIN: '运营', SYSTEM_ADMIN: '系统',
}

function isActive(path: string) {
  if (path === '/shipments') return route.path === '/shipments' || route.path.startsWith('/shipments/')
  return route.path === path || route.path.startsWith(path + '/')
}
</script>
<template>
  <aside :style="{
    width: 'var(--yitu-sidebar-w)', minHeight: '100vh',
    background: 'var(--yitu-ink-800)', color: '#fff',
    display: 'flex', flexDirection: 'column',
    position: 'fixed', left: 0, top: 0, bottom: 0, zIndex: 100,
  }">
    <!-- Logo -->
    <div style="padding: 20px 24px; border-bottom: 1px solid rgba(255,255,255,0.07);">
      <div style="font-size: 1.125rem; font-weight: 700; letter-spacing: 0.05em;">驿途</div>
      <div style="font-size: 0.625rem; color: rgba(255,255,255,0.35); margin-top: 2px; letter-spacing: 0.08em;">YITU LOGISTICS</div>
    </div>

    <!-- 用户身份 -->
    <div v-if="auth.user" style="margin: 12px; padding: 8px 14px; background: rgba(255,255,255,0.05); border-radius: 6px; font-size: 0.75rem; color: rgba(255,255,255,0.5);">
      {{ auth.user.display_name }}
      <span style="float: right;">{{ ROLES[auth.user.role] }}</span>
    </div>

    <!-- 导航 -->
    <nav style="flex: 1; padding: 8px;">
      <router-link v-for="item in items" :key="item.path" :to="item.path"
        :style="{
          display: 'flex', alignItems: 'center', gap: '10px',
          padding: '10px 14px', borderRadius: '6px',
          fontSize: '0.8125rem', fontWeight: 500,
          textDecoration: 'none', marginBottom: '2px',
          transition: 'all 0.12s ease',
          color: isActive(item.path) ? '#fff' : 'rgba(255,255,255,0.45)',
          background: isActive(item.path) ? 'rgba(255,255,255,0.08)' : 'transparent',
        }">
        <span>{{ item.icon }}</span> {{ item.label }}
      </router-link>
    </nav>
  </aside>
</template>