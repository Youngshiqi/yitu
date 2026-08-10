<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { notificationsApi } from '../api/notifications';
const router = useRouter();
const unreadCount = ref(0);
// 每 15 秒轮询一次未读数量
let timer: ReturnType<typeof setInterval>;
async function poll() {
  try { const data = await notificationsApi.list(true); unreadCount.value = data.length; } catch { /* 静默 */ }
}
poll();
timer = setInterval(poll, 15000);
import { onUnmounted } from 'vue';
onUnmounted(() => clearInterval(timer));
</script>
<template>
  <button class="notification-bell" @click="router.push('/notifications')" title="通知中心">
    🔔
    <span v-if="unreadCount > 0" class="badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
  </button>
</template>