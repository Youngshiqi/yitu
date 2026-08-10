<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { adminApi, type DeadLetterView } from '../api/admin';
import EmptyState from '../components/EmptyState.vue';
const deadLetters = ref<DeadLetterView[]>([]);
const loading = ref(true);
const replaying = ref<string | null>(null);
const replayResult = ref<{ id: string; success: boolean } | null>(null);
async function fetchData() {
  loading.value = true;
  try { deadLetters.value = await adminApi.listDeadLetters(); }
  catch (err) { console.error(err); }
  finally { loading.value = false; }
}
onMounted(fetchData);
async function handleReplay(id: string) {
  replaying.value = id;
  replayResult.value = null;
  try {
    const result = await adminApi.replayDeadLetter(id);
    replayResult.value = { id, success: !!result };
    await fetchData();
  } catch (err: any) { replayResult.value = { id, success: false }; }
  finally { replaying.value = null; }
}
</script>
<template>
  <div class="page-container">
    <h1 class="page-title">死信管理</h1>
    <div v-if="loading" style="display: flex; justify-content: center; padding: var(--space-3xl);"><div class="loading-spinner" /></div>
    <EmptyState v-else-if="deadLetters.length === 0" icon="📮" title="无死信" description="当前没有死信消息" />
    <div v-else style="display: flex; flex-direction: column; gap: var(--space-sm);">
      <div v-for="d in deadLetters" :key="d.id" class="card" style="padding: var(--space-lg);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: var(--space-md);">
          <div style="flex: 1; min-width: 0;">
            <div class="mono" style="font-size: 0.75rem; color: var(--color-text-muted); margin-bottom: 4px;">{{ d.id }}</div>
            <div style="font-size: 0.8125rem; color: var(--color-text-primary); margin-bottom: 4px;">{{ d.event_type }}</div>
            <div style="font-size: 0.6875rem; color: var(--color-red);">{{ d.last_error }}</div>
          </div>
          <div style="display: flex; flex-direction: column; align-items: flex-end; gap: var(--space-xs);">
            <span style="font-size: 0.6875rem; color: var(--color-text-muted);">{{ d.failed_at }}</span>
            <button class="btn btn-amber btn-sm" :disabled="replaying === d.id"
              @click="handleReplay(d.id)">{{ replaying === d.id ? '重放中...' : '🔄 重放' }}</button>
            <span v-if="replayResult?.id === d.id" :style="{ fontSize: '0.6875rem', color: replayResult.success ? 'var(--color-green)' : 'var(--color-red)' }">{{ replayResult.success ? '✓ 重放成功' : '✗ 重放失败' }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>