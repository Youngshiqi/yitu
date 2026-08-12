<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { notificationsApi, type NotificationView } from '../../api/notifications'

const notifications = ref<NotificationView[]>([])
const loading = ref(true)
const unread = ref(0)
let es: EventSource | null = null

async function fetchData() {
  loading.value = true
  try {
    notifications.value = await notificationsApi.list()
    unread.value = notifications.value.filter(n => n.status === 'UNREAD').length
  } catch (err) { console.error(err) }
  finally { loading.value = false }
}

function connectSSE() {
  const token = localStorage.getItem('yitu_token')
  es = new EventSource(`/api/v1/notifications/stream?token=${token}`)
  es.addEventListener('notification', (e) => {
    try {
      const n = JSON.parse(e.data) as NotificationView
      notifications.value.unshift(n)
      unread.value++
    } catch {}
  })
  es.onerror = () => { /* 自动重连 */ }
}

onMounted(() => { fetchData(); connectSSE() })
onUnmounted(() => { if (es) es.close() })

async function markRead(n: NotificationView) {
  if (n.status === 'READ') return
  try {
    await notificationsApi.markRead(n.id)
    n.status = 'READ'
    unread.value = Math.max(0, unread.value - 1)
  } catch {}
}
</script>
<template>
  <div class="page-wrap">
    <div class="page-header">
      <h1 class="page-title">通知中心</h1>
      <el-tag v-if="unread > 0" type="danger" round>{{ unread }} 条未读</el-tag>
    </div>

    <div v-if="loading" style="display: flex; justify-content: center; padding: 64px 0;">
      <el-icon class="is-loading" :size="28" />
    </div>

    <div v-else-if="notifications.length === 0" class="empty-wrap">
      <div class="empty-icon">🔔</div>
      <div class="empty-title">暂无通知</div>
      <div class="empty-desc">运单状态变更时你将收到通知</div>
    </div>

    <div v-else style="display: flex; flex-direction: column; gap: 6px;">
      <div
        v-for="n in notifications" :key="n.id"
        @click="markRead(n)"
        :style="{
          padding: '14px 20px', borderRadius: '8px', cursor: 'pointer',
          transition: 'background 0.15s ease',
          borderLeft: '3px solid',
          borderColor: n.status === 'UNREAD' ? 'var(--yitu-amber)' : 'transparent',
          background: n.status === 'UNREAD' ? 'var(--yitu-amber-bg)' : 'var(--yitu-white)',
        }">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;">
          <div style="flex: 1; min-width: 0;">
            <div style="font-size: 0.8125rem; font-weight: 600; color: var(--yitu-ink-800); margin-bottom: 4px;">
              {{ n.title }}
            </div>
            <div style="font-size: 0.75rem; color: var(--yitu-gray-500); line-height: 1.5;">
              {{ n.content }}
            </div>
          </div>
          <div style="text-align: right; flex-shrink: 0;">
            <div style="font-size: 0.6875rem; color: var(--yitu-gray-400); white-space: nowrap;">
              {{ n.created_at }}
            </div>
            <div v-if="n.status === 'UNREAD'"
              style="width: 8px; height: 8px; border-radius: 50%; background: var(--yitu-amber); margin-left: auto; margin-top: 6px;" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>