<script setup lang="ts">
import type { TrackingEventView } from '../api/shipments';
const props = defineProps<{ events: TrackingEventView[]; currentStatus: string }>();

function nodeClass(status: string, i: number, total: number): string {
  if (i < total - 1) return 'completed';
  if (['DELIVERED', 'CANCELLED', 'RETURNED'].includes(status) && i === total - 1) return 'completed';
  if (['CANCELLED', 'RETURN_APPROVED', 'IN_RETURN'].includes(status)) return 'exception';
  return 'active';
}

function eventLabel(type: string): string {
  const labels: Record<string, string> = {
    confirm_payment: '支付确认', 'shipment.created': '运单创建', accept: '已接单',
    confirm_pickup: '已揽收', accept_dropoff: '客户自寄到站', confirm_origin_arrival: '始发站验收',
    dispatch_linehaul: '干线发车', arrive_destination: '目的站到达', issue_pickup_credential: '签发自取码',
    start_delivery: '开始派送', confirm_delivery: '已签收', verify_station_pickup: '网点自取核销',
    cancel: '运单取消', approve_return: '批准退回', advance_return: '推进退回',
    convert_to_pickup: '转为自取', redeliver: '重新派送', SHIPMENT_RESUMED: '履约已恢复',
  };
  return labels[type] || type;
}
</script>
<template>
  <div v-if="events.length === 0" class="empty-state" style="padding: var(--space-xl);">
    <div class="empty-state-icon">📋</div>
    <div class="empty-state-title">暂无轨迹记录</div>
  </div>
  <div v-else class="timeline">
    <div v-for="(event, i) in events" :key="event.id" class="timeline-node">
      <div class="timeline-dot" :class="nodeClass(currentStatus, i, events.length)" />
      <div class="timeline-content">
        <span class="timeline-label">{{ eventLabel(event.event_type) }}</span>
        <span class="timeline-time">{{ new Date(event.created_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) }}</span>
        <span class="timeline-desc">{{ event.message }}</span>
      </div>
    </div>
  </div>
</template>