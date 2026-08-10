<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { shipmentsApi, type ShipmentView, type ShipmentStatus } from '../api/shipments';
import ShipmentCard from '../components/ShipmentCard.vue';
import EmptyState from '../components/EmptyState.vue';
const router = useRouter();
const shipments = ref<ShipmentView[]>([]);
const total = ref(0);
const loading = ref(true);
const statusFilter = ref<ShipmentStatus | ''>('');
const offset = ref(0);
const limit = 20;
const STATUS_FILTERS = [
  { label: '全部', value: '' }, { label: '待支付', value: 'PENDING_PAYMENT' },
  { label: '待揽收', value: 'PENDING_PICKUP' }, { label: '运输中', value: 'IN_LINEHAUL' },
  { label: '派送中', value: 'OUT_FOR_DELIVERY' }, { label: '已签收', value: 'DELIVERED' },
  { label: '已取消', value: 'CANCELLED' },
];
async function fetchData(filter: ShipmentStatus | '', pageOffset: number) {
  loading.value = true;
  try {
    const data = await shipmentsApi.list({ status: filter || undefined, limit, offset: pageOffset });
    shipments.value = data.items;
    total.value = data.total;
  } catch (err) { console.error(err); }
  finally { loading.value = false; }
}
function handleFilter(s: ShipmentStatus | '') { statusFilter.value = s; offset.value = 0; fetchData(s, 0); }
onMounted(() => fetchData('', 0));
</script>
<template>
  <div class="page-container">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-lg);">
      <h1 class="page-title" style="margin-bottom: 0;">我的运单</h1>
      <button class="btn btn-amber" @click="router.push('/shipments/new')">➕ 创建运单</button>
    </div>
    <div style="display: flex; gap: var(--space-sm); margin-bottom: var(--space-lg); flex-wrap: wrap;">
      <button v-for="f in STATUS_FILTERS" :key="f.value"
        :class="['btn btn-sm', statusFilter === f.value ? 'btn-primary' : 'btn-ghost']"
        @click="handleFilter(f.value as ShipmentStatus | '')">{{ f.label }}</button>
    </div>
    <div v-if="loading" style="display: flex; justify-content: center; padding: var(--space-3xl);"><div class="loading-spinner" /></div>
    <EmptyState v-else-if="shipments.length === 0" icon="📦" title="暂无运单" description="创建你的第一个运单" />
    <div v-else style="display: flex; flex-direction: column; gap: var(--space-sm);">
      <ShipmentCard v-for="s in shipments" :key="s.id" :shipment="s" @click="(id: string) => router.push(`/shipments/${id}`)" />
    </div>
    <div v-if="total > limit" style="display: flex; justify-content: center; gap: var(--space-sm); margin-top: var(--space-lg);">
      <button class="btn btn-ghost btn-sm" :disabled="offset === 0" @click="offset -= limit; fetchData(statusFilter, offset);">← 上一页</button>
      <span style="font-size: 0.8125rem; color: var(--color-text-secondary); padding: 4px 12px;">{{ Math.floor(offset / limit) + 1 }} / {{ Math.ceil(total / limit) }}</span>
      <button class="btn btn-ghost btn-sm" :disabled="offset + limit >= total" @click="offset += limit; fetchData(statusFilter, offset);">下一页 →</button>
    </div>
  </div>
</template>