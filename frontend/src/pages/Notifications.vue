<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { notificationsApi, type NotificationView } from '../api/notifications';
import { useSSE } from '../composables/useSSE';
import EmptyState from '../components/EmptyState.vue';
const notifications = ref<NotificationView[]>([]);
const loading = ref(true);
async function fetchNotifications() {
  loading.value = true;
  try {
    notifications.value = await notificationsApi.list();
  } catch (err) { console.error(err); }
  finally { loading.value = false; }
}
useSSE('notifications', (event) => {
  try {
    const n = JSON.parse(event.data);
    notifications.value.unshift(n);
  } catch {}
});
onMounted(fetchNotifications);
async function markRead(id: string) {
  try {
    await notificationsApi.markRead(id);
    const n = notifications.value.find(item => item.id === id);
    if (n) n.status = 'READ';
  } catch {}
}
</script>
<template>
  <div class="page-container">
    <h1 class="page-title">通知中心</h1>
    <div v-if="loading" style="display: flex; justify-content: center; padding: var(--space-3xl);"><div class="loading-spinner" /></div>
    <EmptyState v-else-if="notifications.length === 0" icon="🔔" title="暂无通知" description="运单状态变更时会收到通知" />
    <div v-else style="display: flex; flex-direction: column; gap: var(--space-xs);">
      <div v-for="n in notifications" :key="n.id" @click="markRead(n.id)"
        :style="{ background: n.status === 'UNREAD' ? 'var(--color-surface-200)' : 'var(--color-surface)', cursor: 'pointer' }"
        style="padding: var(--space-md) var(--space-lg); border-radius: var(--radius-md); transition: background 0.15s ease; border-left: 3px solid transparent;"
        :class="{ 'notification-unread': n.status === 'UNREAD' }">
        <div style="display: flex; justify-content: space-between; align-items: center; gap: var(--space-md);">
          <div style="flex: 1;">
            <div style="font-size: 0.8125rem; font-weight: 600; color: var(--color-text-primary); margin-bottom: 2px;">{{ n.title }}</div>
            <div style="font-size: 0.75rem; color: var(--color-text-secondary);">{{ n.content }}</div>
          </div>
          <div style="text-align: right; flex-shrink: 0;">
            <div style="font-size: 0.6875rem; color: var(--color-text-muted); white-space: nowrap;">{{ n.created_at }}</div>
            <div v-if="n.status === 'UNREAD'" style="width: 8px; height: 8px; border-radius: 50%; background: var(--color-amber); margin-left: auto; margin-top: 4px;" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.notification-unread { border-left-color: var(--color-amber) !important; }
</style>