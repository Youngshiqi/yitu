<script setup lang="ts">
const STATUS_LABELS: Record<string, string> = {
  PENDING_PAYMENT: '待支付', PENDING_PICKUP: '待揽收', PICKUP_ASSIGNED: '已派揽收',
  WAITING_FOR_DROPOFF: '等待自寄', PICKED_UP: '已揽收', AT_ORIGIN_STATION: '始发站',
  IN_LINEHAUL: '干线运输', AT_DESTINATION_STATION: '目的站', DELIVERY_ASSIGNED: '已派派送',
  OUT_FOR_DELIVERY: '派送中', WAITING_FOR_RECIPIENT_PICKUP: '等待自取', DELIVERED: '已签收',
  CANCELLED: '已取消', RETURN_APPROVED: '退回中', IN_RETURN: '退回运输', RETURNED: '已退回',
  OPEN: '待处理', ASSIGNED: '已分配', PROCESSING: '处理中',
  WAITING_FOR_CUSTOMER: '等待客户', RESOLVED: '已解决', CLOSED: '已关闭',
};
defineProps<{ status: string }>();
</script>
<template>
  <span class="status-badge" :class="status.toLowerCase()">{{ STATUS_LABELS[status] || status }}</span>
</template>