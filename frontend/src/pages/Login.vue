<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'

const auth = useAuthStore()
const router = useRouter()

const DEMO = [
  { login: 'customer.demo', label: '客户', role: 'CUSTOMER', desc: '下单、支付、查件', color: '#5c7c99' },
  { login: 'courier.bijing.demo', label: '北京快递员', role: 'COURIER', desc: '揽收、派送', color: '#2e7d32' },
  { login: 'courier.shanghai.demo', label: '上海快递员', role: 'COURIER', desc: '揽收、派送', color: '#2e7d32' },
  { login: 'operator.beijing.demo', label: '北京网点员', role: 'STATION_OPERATOR', desc: '入站、干线', color: '#e8a838' },
  { login: 'operator.shanghai.demo', label: '上海网点员', role: 'STATION_OPERATOR', desc: '到站、自取', color: '#e8a838' },
  { login: 'operations.demo', label: '运营管理员', role: 'OPERATIONS_ADMIN', desc: '异常、SLA', color: '#d94040' },
  { login: 'system.demo', label: '系统管理员', role: 'SYSTEM_ADMIN', desc: '死信、配置', color: '#6a1b9a' },
]

const password = ref('YituDemo2026!')
const active = ref('')

const REDIRECT: Record<string, string> = {
  CUSTOMER: '/shipments', COURIER: '/operations', STATION_OPERATOR: '/operations',
  OPERATIONS_ADMIN: '/operations', SYSTEM_ADMIN: '/admin/dead-letters',
}

async function handleLogin(loginName: string) {
  active.value = loginName
  try {
    await auth.login(loginName, password.value)
    router.push(REDIRECT[auth.user?.role || 'CUSTOMER'] || '/shipments')
  } catch {
    ElMessage.error(auth.error || '登录失败')
  }
}
</script>
<template>
  <div :style="{
    minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: 'linear-gradient(160deg, #1a2332 0%, #0d1520 100%)', padding: '32px',
  }">
    <div style="width: 100%; max-width: 720px;">
      <!-- 品牌 -->
      <div style="text-align: center; margin-bottom: 48px;">
        <div style="font-size: 2.5rem; font-weight: 700; color: #fff; letter-spacing: 0.08em;">驿途</div>
        <div style="font-size: 0.6875rem; color: rgba(255,255,255,0.3); letter-spacing: 0.12em; margin-top: 6px;">YITU SMART LOGISTICS</div>
        <div style="margin-top: 16px; display: inline-block; padding: 3px 14px; border-radius: 100px; background: rgba(255,255,255,0.06); color: var(--yitu-amber-light); font-size: 0.6875rem; font-weight: 600; letter-spacing: 0.04em;">演示环境</div>
      </div>

      <!-- 角色卡片 -->
      <div :style="{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '10px' }">
        <button
          v-for="a in DEMO" :key="a.login"
          @click="handleLogin(a.login)"
          :disabled="auth.loading"
          :style="{
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px',
            padding: '20px 16px', borderRadius: '10px', color: '#fff', cursor: 'pointer',
            transition: 'all 0.18s ease', border: '1px solid',
            background: active === a.login ? 'rgba(255,255,255,0.12)' : 'rgba(255,255,255,0.04)',
            borderColor: active === a.login ? a.color : 'rgba(255,255,255,0.06)',
          }">
          <span style="font-size: 0.9375rem; font-weight: 700;">{{ a.label }}</span>
          <span style="font-size: 0.625rem; opacity: 0.4; font-family: var(--yitu-mono);">{{ a.login }}</span>
          <span style="font-size: 0.6875rem; opacity: 0.55;">{{ a.desc }}</span>
        </button>
      </div>

      <!-- 密码 -->
      <div style="margin-top: 20px; display: flex; gap: 8px; justify-content: center;">
        <el-input
          v-model="password" type="password" show-password
          :style="{ width: '260px', '--el-fill-color-blank': 'rgba(255,255,255,0.06)', '--el-border-color': 'rgba(255,255,255,0.1)', '--el-text-color': '#fff', '--el-input-placeholder-color': 'rgba(255,255,255,0.25)' }"
          placeholder="演示密码" />
      </div>

      <p style="text-align: center; margin-top: 24px; color: rgba(255,255,255,0.25); font-size: 0.6875rem;">
        选择角色即可登录 · 演示密码：YituDemo2026!
      </p>
    </div>
  </div>
</template>