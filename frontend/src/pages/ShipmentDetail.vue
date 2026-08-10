<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { shipmentsApi, type ShipmentView, type TrackingEventView } from '../api/shipments';
import { returnsApi } from '../api/returns';
import StatusBadge from '../components/StatusBadge.vue';
import ShipmentTimeline from '../components/ShipmentTimeline.vue';
import ActionPanel from '../components/ActionPanel.vue';
import EmptyState from '../components/EmptyState.vue';
import { useAuthStore } from '../stores/auth';
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const id = route.params.id as string;
const shipment = ref<ShipmentView | null>(null);
const tracking = ref<TrackingEventView[]>([]);
const loading = ref(true);
async function fetchData() {
  loading.value = true;
  try {
    const [s, t] = await Promise.all([shipmentsApi.get(id), shipmentsApi.getTracking(id)]);
    shipment.value = s; tracking.value = t;
  } catch (err) { console.error(err); }
  finally { loading.value = false; }
}
onMounted(fetchData);
async function handleAction(action: string, reason?: string) {
  try {
    if (action === 'confirm_payment') await shipmentsApi.confirmPayment(id);
    else if (action === 'cancel') await returnsApi.cancel(id, reason || '用户取消');
    await fetchData();
  } catch (err: any) { alert(err.message || '操作失败'); }
}
const isCustomer = auth.user?.role === 'CUSTOMER';
const customerActions = [];
if (shipment.value?.status === 'PENDING_PAYMENT') customerActions.push({ label: '确认支付', action: 'confirm_payment' });
if (shipment.value && ['PENDING_PAYMENT', 'PENDING_PICKUP', 'WAITING_FOR_DROPOFF'].includes(shipment.value.status))
  customerActions.push({ label: '取消运单', action: 'cancel', danger: true });
</script>
<template>
  <div class="page-container">
    <button class="btn btn-ghost btn-sm" @click="router.push('/shipments')" style="margin-bottom: var(--space-md);">← 返回列表</button>
    <div v-if="loading" style="display: flex; justify-content: center; padding: var(--space-3xl);"><div class="loading-spinner" /></div>
    <template v-else-if="shipment">
      <div class="card" style="padding: var(--space-xl); margin-bottom: var(--space-lg);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: var(--space-md);">
          <div>
            <div style="font-size: 0.75rem; color: var(--color-text-muted); margin-bottom: 4px; letter-spacing: 0.04em;">运单号</div>
            <div class="mono" style="font-size: 1.25rem; font-weight: 700; color: var(--color-primary-800);">{{ shipment.shipment_no }}</div>
          </div>
          <StatusBadge :status="shipment.status" />
        </div>
      </div>
      <ActionPanel v-if="isCustomer && customerActions.length" :actions="customerActions" @action="handleAction" title="可用操作" style="margin-bottom: var(--space-lg);" />
      <div class="card" style="padding: var(--space-xl);">
        <h3 style="font-size: 0.9375rem; font-weight: 600; margin-bottom: var(--space-lg); color: var(--color-text-secondary); letter-spacing: 0.02em;">物流生命线</h3>
        <ShipmentTimeline :events="tracking" :currentStatus="shipment.status" />
      </div>
    </template>
    <EmptyState v-else icon="📦" title="运单不存在" />
  </div>
</template>