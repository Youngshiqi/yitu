<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { exceptionsApi, type ExceptionView } from '../api/exceptions';
import { returnsApi } from '../api/returns';
import StatusBadge from '../components/StatusBadge.vue';
import ActionPanel from '../components/ActionPanel.vue';
import EmptyState from '../components/EmptyState.vue';
const route = useRoute();
const router = useRouter();
const id = route.params.id as string;
const exception = ref<ExceptionView | null>(null);
const loading = ref(true);
const actionLoading = ref(false);
async function fetchData() {
  loading.value = true;
  try { exception.value = await exceptionsApi.get(id); }
  catch (err) { console.error(err); }
  finally { loading.value = false; }
}
onMounted(fetchData);
const EXCEPTION_ACTIONS = [
  { label: '分配处理人', action: 'assign' },
  { label: '开始处理', action: 'start_processing' },
  { label: '标记已解决', action: 'resolve' },
  { label: '关闭工单', action: 'close' },
];
async function handleAction(action: string, reason?: string) {
  actionLoading.value = true;
  try {
    if (action === 'assign') await exceptionsApi.assign(id, '', '', reason || '');
    else if (action === 'start_processing') await exceptionsApi.startProcessing(id, reason);
    else if (action === 'resolve') await exceptionsApi.resolve(id, 'RESOLVED', reason);
    else if (action === 'close') await exceptionsApi.close(id, reason);
    await fetchData();
  } catch (err: any) { alert(err.message || '操作失败'); }
  finally { actionLoading.value = false; }
}
const RECOVERY_ACTIONS = [
  { label: '取消运单', action: 'cancel' },
  { label: '重派', action: 'redeliver' },
  { label: '转自取', action: 'convert_to_pickup' },
  { label: '退回', action: 'return' },
];
async function handleRecovery(action: string, reason?: string) {
  actionLoading.value = true;
  try {
    const sid = exception.value?.shipment_id;
    if (!sid) return;
    if (action === 'cancel') await returnsApi.cancel(sid, reason || '异常处理取消');
    else if (action === 'redeliver') await returnsApi.redeliver(sid, reason || '');
    else if (action === 'convert_to_pickup') await returnsApi.convertToPickup(sid, reason || '');
    else if (action === 'return') await returnsApi.approveReturn(sid, reason || '');
    await fetchData();
  } catch (err: any) { alert(err.message || '操作失败'); }
  finally { actionLoading.value = false; }
}
</script>
<template>
  <div class="page-container">
    <button class="btn btn-ghost btn-sm" @click="router.push('/exceptions')" style="margin-bottom: var(--space-md);">← 返回列表</button>
    <div v-if="loading" style="display: flex; justify-content: center; padding: var(--space-3xl);"><div class="loading-spinner" /></div>
    <template v-else-if="exception">
      <div class="card" style="padding: var(--space-xl); margin-bottom: var(--space-lg);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: var(--space-md);">
          <div>
            <div class="mono" style="font-size: 1.125rem; font-weight: 600; color: var(--color-primary-800); margin-bottom: 4px;">{{ exception.shipment_id }}</div>
            <div style="font-size: 0.75rem; color: var(--color-text-secondary);">{{ exception.case_type }} · {{ exception.severity }}</div>
          </div>
          <StatusBadge :status="exception.status" />
        </div>
        <div v-if="exception.description" style="margin-top: var(--space-md); font-size: 0.8125rem; color: var(--color-text-secondary); padding: var(--space-md); background: var(--color-surface-200); border-radius: var(--radius-md);">{{ exception.description }}</div>
      </div>
      <ActionPanel :actions="EXCEPTION_ACTIONS" @action="handleAction" title="异常处理" :loading="actionLoading" style="margin-bottom: var(--space-lg);" />
      <ActionPanel v-if="exception.shipment_id" :actions="RECOVERY_ACTIONS" @action="handleRecovery" title="恢复动作" :loading="actionLoading" style="margin-bottom: var(--space-lg);" />
    </template>
    <EmptyState v-else icon="⚠️" title="异常工单不存在" />
  </div>
</template>