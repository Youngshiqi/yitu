<script setup lang="ts">
import { useAuthStore } from '../stores/auth';
import Sidebar from './Sidebar.vue';
import TopBar from './TopBar.vue';
const auth = useAuthStore();
</script>
<template>
  <div v-if="!auth.token" style="display: flex; justify-content: center; padding: var(--space-3xl);">
    <div class="loading-spinner" />
  </div>
  <div v-else style="display: flex; min-height: 100vh;">
    <Sidebar />
    <div style="margin-left: var(--sidebar-width); flex: 1; display: flex; flex-direction: column;">
      <TopBar />
      <main style="flex: 1;"><router-view /></main>
    </div>
  </div>
</template>