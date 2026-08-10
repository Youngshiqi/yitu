<script setup lang="ts">
import { ref } from 'vue';
interface ActionItem { label: string; action: string; danger?: boolean; }
const props = defineProps<{ actions: ActionItem[]; title?: string }>();
const emit = defineEmits<{ action: [action: string, reason?: string] }>();
const loading = ref<string | null>(null);
const reason = ref('');
const showReason = ref<string | null>(null);

async function handleAction(action: string) {
  loading.value = action;
  try {
    emit('action', action, reason.value || undefined);
    showReason.value = null;
    reason.value = '';
  } finally {
    loading.value = null;
  }
}
</script>
<template>
  <div class="card" style="padding: var(--space-lg);">
    <h3 v-if="title" style="font-size: 0.9375rem; font-weight: 600; margin-bottom: var(--space-md); color: var(--color-text-secondary);">{{ title }}</h3>
    <div style="display: flex; flex-wrap: wrap; gap: var(--space-sm);">
      <button v-for="act in actions" :key="act.action"
        :class="['btn btn-sm', act.danger ? 'btn-red' : 'btn-primary']"
        :disabled="loading !== null"
        @click="['cancel','redeliver','convert_to_pickup','approve_return','advance_return'].includes(act.action) ? showReason = act.action : handleAction(act.action)">
        {{ loading === act.action ? '...' : act.label }}
      </button>
    </div>
    <div v-if="showReason" style="margin-top: var(--space-md); display: flex; gap: var(--space-sm); align-items: flex-end;">
      <div class="form-group" style="flex: 1;">
        <label class="form-label">操作原因</label>
        <input class="form-input" v-model="reason" placeholder="请输入操作原因" />
      </div>
      <button class="btn btn-amber btn-sm" @click="handleAction(showReason)" :disabled="!reason || loading !== null">确认</button>
      <button class="btn btn-ghost btn-sm" @click="showReason = null; reason = '';">取消</button>
    </div>
  </div>
</template>