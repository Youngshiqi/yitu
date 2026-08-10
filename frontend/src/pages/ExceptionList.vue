<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { exceptionsApi, type ExceptionView, type ExceptionStatus } from '../api/exceptions';
import StatusBadge from '../components/StatusBadge.vue';
import EmptyState from '../components/EmptyState.vue';
const router = useRouter();
const exceptions = ref<ExceptionView[]>([]);
const total = ref(0);
const loading = ref(true);
const statusFilter = ref<ExceptionStatus | ''>('');
const offset = ref(0);
const limit = 20;
const STATUS_FILTERS = [
  { label: '全部', value: '' }, { label: '待处理', value: 'OPEN' },
  { label: '处理中', value: 'PROCESSING' }, { label: '等待客户', value: 'WAITING_FOR_CUSTOMER' },
  { label: '已解决', value: 'RESOLVED' }, { label: '已关闭', value: 'CLOSED' },
];
async function fetchData() {
  loading.value = true;
  try {
    const params: Record<string, string | number | boolean> = { limit, offset: offset.value };
    if (statusFilter.value) params.status = statusFilter.value;
    const data = await exceptionsApi.list(params);
    exceptions.value = data.items; total.value = data.total;
  } catch (err) { console.error(err); }
  finally { loading.value = false; }
}
function handleFilter(s: ExceptionStatus | '') { statusFilter.value = s; offset.value = 0; fetchData(); }
onMounted(() => fetchData());
</script>
<template>
  <div class="page-container">
    <h1 class="page-title">异常工单</h1>
    <div style="display: flex; gap: var(--space-sm); margin-bottom: var(--space-lg); flex-wrap: wrap;">
      <button v-for="f in STATUS_FILTERS" :key="f.value"
        :class="['btn btn-sm', statusFilter === f.value ? 'btn-primary' : 'btn-ghost']"
        @click="handleFilter(f.value as ExceptionStatus | '')">{{ f.label }}</button>
    </div>
    <div v-if="loading" style="display: flex; justify-content: center; padding: var(--space-3xl);"><div class="loading-spinner" /></div>
    <EmptyState v-else-if="exceptions.length === 0" icon="✅" title="无异常工单" description="当前没有异常工单" />
    <div v-else style="display: flex; flex-direction: column; gap: var(--space-sm);">
      <div v-for="e in exceptions" :key="e.id" class="card" style="padding: var(--space-lg); cursor: pointer;"
        @click="router.push(`/exceptions/${e.id}`)">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: var(--space-md);">
          <div>
            <div class="mono" style="font-size: 0.875rem; font-weight: 600; color: var(--color-primary-800); margin-bottom: 4px;">{{ e.shipment_id }}</div>
            <div style="font-size: 0.75rem; color: var(--color-text-secondary);">{{ e.case_type }} · {{ e.severity }}</div>
          </div>
          <StatusBadge :status="e.status" />
        </div>
      </div>
    </div>
    <div v-if="total > limit" style="display: flex; justify-content: center; gap: var(--space-sm); margin-top: var(--space-lg);">
      <button class="btn btn-ghost btn-sm" :disabled="offset === 0" @click="offset -= limit; fetchData();">← 上一页</button>
      <span style="font-size: 0.8125rem; color: var(--color-text-secondary); padding: 4px 12px;">{{ Math.floor(offset / limit) + 1 }} / {{ Math.ceil(total / limit) }}</span>
      <button class="btn btn-ghost btn-sm" :disabled="offset + limit >= total" @click="offset += limit; fetchData();">下一页 →</button>
    </div>
  </div>
</template>