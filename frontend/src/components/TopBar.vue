<script setup lang="ts">
import { useAuthStore } from '../stores/auth'
import { useRouter } from 'vue-router'
const auth = useAuthStore()
const router = useRouter()
function handleLogout() { auth.logout(); router.push('/login') }
</script>
<template>
  <header :style="{
    height: 'var(--yitu-topbar-h)', background: 'var(--yitu-white)',
    borderBottom: '1px solid var(--yitu-gray-200)',
    display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
    padding: '0 24px', gap: '16px',
    position: 'sticky', top: 0, zIndex: 50,
  }">
    <el-tag size="small" type="warning" effect="plain" round>DEMO</el-tag>
    <el-badge :value="0" :hidden="true">
      <el-button link @click="router.push('/notifications')" style="font-size: 1.25rem;">🔔</el-button>
    </el-badge>
    <span v-if="auth.user" style="font-size: 0.8125rem; color: var(--yitu-gray-500); font-weight: 500;">
      {{ auth.user.display_name }}
    </span>
    <el-button text size="small" @click="handleLogout">退出</el-button>
  </header>
</template>