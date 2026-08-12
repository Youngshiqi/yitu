<script setup lang="ts">
import { useAuthStore } from '../stores/auth'
import Sidebar from './Sidebar.vue'
import TopBar from './TopBar.vue'
const auth = useAuthStore()
</script>
<template>
  <div v-if="!auth.token" style="display: flex; justify-content: center; padding: 64px;">
    <el-icon class="is-loading" :size="32" />
  </div>
  <div v-else style="display: flex; min-height: 100vh;">
    <Sidebar />
    <div style="margin-left: var(--yitu-sidebar-w); flex: 1; display: flex; flex-direction: column; min-width: 0;">
      <TopBar />
      <main style="flex: 1; background: var(--yitu-paper);"><router-view /></main>
    </div>
  </div>
</template>