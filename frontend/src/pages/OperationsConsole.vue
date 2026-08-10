<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { dispatchApi, type TaskView } from '../api/dispatch';
import { exceptionsApi, type ExceptionView } from '../api/exceptions';
import StatusBadge from '../components/StatusBadge.vue';
import EmptyState from '../components/EmptyState.vue';
import { useAuthStore } from '../stores/auth';
const auth = useAuthStore();
const tasks = ref<TaskView[]>([]);
const loading = ref(true);
const activeTab = ref<'tasks' | 'exceptions'>('tasks');
const exceptions = ref<ExceptionView[]>([]);
const exceptionLoading = ref(false);
const actionLoading = ref<string | null>(null);
async function fetchTasks() {
  loading.value = true;
  try { tasks.value = await dispatchApi.listTasks(); }
  catch (err) { console.error(err); }
  finally { loading.value = false; }
}
async function fetchExceptions() {
  if (exceptions.value.length > 0) return;
  exceptionLoading.value = true;
  try { const data = await exceptionsApi.list({ limit: 50 }); exceptions.value = data.items; }
  catch (err) { console.error(err); }
  finally { exceptionLoading.value = false; }
}
onMounted(() => { fetchTasks(); fetchExceptions(); });
async function doAction(taskId: string, action: string) {
  actionLoading.value = taskId;
  try {
    if (action === 'accept') await dispatchApi.acceptTask(taskId);
    else if (action === 'confirm_pickup') await dispatchApi.confirmPickup(taskId);
    else if (action === 'accept_dropoff') await dispatchApi.acceptDropoff(taskId);
    else if (action === 'confirm_origin_arrival') await dispatchApi.confirmOriginArrival(taskId);
    else if (action === 'dispatch_linehaul') await dispatchApi.dispatchLinehaul(taskId);
    else if (action === 'arrive_destination') await dispatchApi.arriveDestination(taskId);
    else if (action === 'start_delivery') await dispatchApi.startDelivery(taskId);
    else if (action === 'confirm_delivery') await dispatchApi.confirmDelivery(taskId, '签收人');
    else if (action === 'issue_pickup_credential') await dispatchApi.issuePickupCredential(taskId);
    else if (action === 'verify_station_pickup') await dispatchApi.verifyStationPickup(taskId, '');
    await fetchTasks();
  } catch (err: any) { alert(err.message || '操作失败'); }
  finally { actionLoading.value = null; }
}
const TASK_ACTIONS: Record<string, { label: string; action: string }[]> = {
  'PENDING_ACCEPTANCE': [{ label: '接受任务', action: 'accept' }],
  'ASSIGNED': [{ label: '确认揽收', action: 'confirm_pickup' }, { label: '接受自寄', action: 'accept_dropoff' }],
  'PICKED_UP': [{ label: '确认始发站到达', action: 'confirm_origin_arrival' }],
  'AT_ORIGIN_STATION': [{ label: '发干线', action: 'dispatch_linehaul' }],
  'IN_TRANSIT': [{ label: '确认目的站到达', action: 'arrive_destination' }],
  'AT_DESTINATION_STATION': [{ label: '开始派送', action: 'start_delivery' }, { label: '发自取码', action: 'issue_pickup_credential' }],
  'OUT_FOR_DELIVERY': [{ label: '确认签收', action: 'confirm_delivery' }],
  'AWAITING_PICKUP': [{ label: '核销自取', action: 'verify_station_pickup' }],
};
</script>
<template>
  <div class="page-container">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-lg);">
      <h1 class="page-title" style="margin-bottom: 0;">履约操作台</h1>
      <span style="font-size: 0.75rem; color: var(--color-text-muted); padding: 4px 12px; background: var(--color-surface-200); border-radius: 100px;">{{ auth.user?.display_name }}</span>
    </div>
    <div style="display: flex; gap: var(--space-sm); margin-bottom: var(--space-lg);">
      <button :class="['btn btn-sm', activeTab === 'tasks' ? 'btn-primary' : 'btn-ghost']" @click="activeTab = 'tasks'">📋 任务列表</button>
      <button :class="['btn btn-sm', activeTab === 'exceptions' ? 'btn-primary' : 'btn-ghost']" @click="activeTab = 'exceptions'">⚠️ 异常工单</button>
    </div>

    <!-- 任务列表 -->
    <div v-if="activeTab === 'tasks'">
      <div v-if="loading" style="display: flex; justify-content: center; padding: var(--space-3xl);"><div class="loading-spinner" /></div>
      <EmptyState v-else-if="tasks.length === 0" icon="📋" title="暂无任务" description="当前没有待处理的履约任务" />
      <div v-else style="display: flex; flex-direction: column; gap: var(--space-sm);">
        <div v-for="t in tasks" :key="t.id" class="card" style="padding: var(--space-lg);">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: var(--space-md);">
            <div>
              <div class="mono" style="font-size: 0.875rem; font-weight: 600; color: var(--color-primary-800); margin-bottom: 4px;">{{ t.shipment_id }}</div>
              <div style="font-size: 0.75rem; color: var(--color-text-secondary);">{{ t.task_type }}</div>
            </div>
            <div style="display: flex; align-items: center; gap: var(--space-sm);">
              <StatusBadge :status="t.status" />
              <button v-for="act in (TASK_ACTIONS[t.status] || [])" :key="act.action"
                :class="['btn btn-sm', act.action === 'accept' ? 'btn-primary' : 'btn-amber']"
                :disabled="actionLoading === t.id"
                @click="doAction(t.id, act.action)">{{ actionLoading === t.id ? '处理中...' : act.label }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 异常工单 -->
    <div v-if="activeTab === 'exceptions'">
      <div v-if="exceptionLoading" style="display: flex; justify-content: center; padding: var(--space-3xl);"><div class="loading-spinner" /></div>
      <EmptyState v-else-if="exceptions.length === 0" icon="✅" title="无异常" description="当前没有异常工单" />
      <div v-else style="display: flex; flex-direction: column; gap: var(--space-sm);">
        <div v-for="e in exceptions" :key="e.id" class="card" style="padding: var(--space-lg);">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: var(--space-md);">
            <div>
              <div class="mono" style="font-size: 0.875rem; font-weight: 600; color: var(--color-primary-800); margin-bottom: 4px;">{{ e.shipment_id }}</div>
              <div style="font-size: 0.75rem; color: var(--color-text-secondary);">{{ e.case_type }} · {{ e.severity }}</div>
            </div>
            <StatusBadge :status="e.status" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>