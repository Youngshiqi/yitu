<script setup lang="ts">
import { useAuthStore } from '../stores/auth';
import { useRouter } from 'vue-router';
import NotificationBell from './NotificationBell.vue';
const auth = useAuthStore();
const router = useRouter();
function handleLogout() { auth.logout(); router.push('/login'); }
</script>
<template>
  <header style="height: var(--topbar-height); background: var(--color-bg-card); border-bottom: 1px solid rgba(0,0,0,0.06); display: flex; align-items: center; justify-content: flex-end; padding: 0 var(--space-xl); gap: var(--space-md); position: sticky; top: 0; z-index: 50;">
    <span style="font-size: 0.6875rem; padding: 2px 8px; border-radius: 100px; background: var(--color-amber-light); color: var(--color-primary-800); font-weight: 600; letter-spacing: 0.04em;">DEMO</span>
    <NotificationBell v-if="auth.user" />
    <div v-if="auth.user" style="display: flex; align-items: center; gap: var(--space-sm);">
      <span style="font-size: 0.8125rem; color: var(--color-text-secondary); font-weight: 500;">{{ auth.user.display_name }}</span>
      <button class="btn btn-ghost btn-sm" @click="handleLogout" title="退出登录">🚪</button>
    </div>
  </header>
</template>