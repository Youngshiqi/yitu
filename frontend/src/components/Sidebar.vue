<script setup lang="ts">
import { useAuthStore, type Role } from '../stores/auth';
import { useRoute } from 'vue-router';
const auth = useAuthStore();
const route = useRoute();
interface MenuItem { label: string; path: string; icon: string; roles: Role[]; }
const MENU: MenuItem[] = [
  { label: '运单列表', path: '/shipments', icon: '📦', roles: ['CUSTOMER'] },
  { label: '创建运单', path: '/shipments/new', icon: '➕', roles: ['CUSTOMER'] },
  { label: '通知中心', path: '/notifications', icon: '🔔', roles: ['CUSTOMER','COURIER','STATION_OPERATOR','OPERATIONS_ADMIN'] },
  { label: '履约操作台', path: '/operations', icon: '🔀', roles: ['COURIER','STATION_OPERATOR','OPERATIONS_ADMIN'] },
  { label: '异常工单', path: '/exceptions', icon: '⚠', roles: ['CUSTOMER','COURIER','STATION_OPERATOR','OPERATIONS_ADMIN'] },
  { label: '死信管理', path: '/admin/dead-letters', icon: '🛡', roles: ['SYSTEM_ADMIN'] },
];
const items = MENU.filter((m) => auth.user && m.roles.includes(auth.user.role));
const roleLabel: Record<string, string> = { CUSTOMER: '客户', COURIER: '快递员', STATION_OPERATOR: '网点员', OPERATIONS_ADMIN: '运营', SYSTEM_ADMIN: '系统' };
</script>
<template>
  <aside style="width: var(--sidebar-width); min-height: 100vh; background: var(--color-primary-800); color: var(--color-text-inverse); display: flex; flex-direction: column; position: fixed; left: 0; top: 0; bottom: 0; z-index: 100;">
    <div style="padding: var(--space-lg); border-bottom: 1px solid rgba(255,255,255,0.08);">
      <div style="font-size: 1.125rem; font-weight: 700; letter-spacing: 0.04em;">驿途</div>
      <div style="font-size: 0.6875rem; color: var(--color-surface-400); margin-top: 2px; letter-spacing: 0.06em;">YITU LOGISTICS</div>
    </div>
    <div v-if="auth.user" style="margin: var(--space-md); padding: var(--space-sm) var(--space-md); background: rgba(255,255,255,0.06); border-radius: var(--radius-sm); font-size: 0.75rem; color: var(--color-surface-400);">
      {{ auth.user.display_name }}
      <span style="float: right; opacity: 0.7;">{{ roleLabel[auth.user.role] }}</span>
    </div>
    <nav style="flex: 1; padding: var(--space-sm);">
      <router-link v-for="item in items" :key="item.path" :to="item.path"
        style="display: flex; align-items: center; gap: var(--space-sm); padding: 10px var(--space-md); border-radius: var(--radius-md); font-size: 0.875rem; font-weight: 500; text-decoration: none; margin-bottom: 2px; transition: all 0.12s ease;"
        :style="{ color: route.path === item.path || (item.path !== '/' && route.path.startsWith(item.path)) ? '#fff' : 'var(--color-surface-400)', background: route.path === item.path || (item.path !== '/' && route.path.startsWith(item.path)) ? 'rgba(255,255,255,0.08)' : 'transparent' }">
        <span>{{ item.icon }}</span> {{ item.label }}
      </router-link>
    </nav>
  </aside>
</template>