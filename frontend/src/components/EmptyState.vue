<script setup lang="ts">
defineProps<{ icon?: string; title: string; description?: string }>();
</script>
<template>
  <div class="empty-state">
    <div class="empty-state-icon">{{ icon || '📋' }}</div>
    <div class="empty-state-title">{{ title }}</div>
    <p v-if="description" style="font-size: 0.8125rem; max-width: 320px;">{{ description }}</p>
  </div>
</template>