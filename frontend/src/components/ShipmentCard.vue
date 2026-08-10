<script setup lang="ts">
import type { ShipmentView } from '../api/shipments';
import StatusBadge from './StatusBadge.vue';
defineProps<{ shipment: ShipmentView }>();
const emit = defineEmits<{ click: [id: string] }>();
</script>
<template>
  <div class="card" style="padding: var(--space-lg); cursor: pointer; display: flex; flex-direction: column; gap: var(--space-md); transition: box-shadow 0.15s, transform 0.15s;"
    @click="emit('click', shipment.id)"
    @mouseenter="(e: MouseEvent) => { const el = e.currentTarget as HTMLElement; el.style.boxShadow = 'var(--shadow-md)'; el.style.transform = 'translateY(-1px)'; }"
    @mouseleave="(e: MouseEvent) => { const el = e.currentTarget as HTMLElement; el.style.boxShadow = 'var(--shadow-sm)'; el.style.transform = 'none'; }">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <span class="mono" style="font-size: 0.9375rem; font-weight: 600; color: var(--color-primary-800);">{{ shipment.shipment_no }}</span>
      <StatusBadge :status="shipment.status" />
    </div>
  </div>
</template>