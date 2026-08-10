<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';
const auth = useAuthStore();
const router = useRouter();
const DEMO_ACCOUNTS = [
  { login: 'customer.demo', label: '客户', role: 'CUSTOMER', desc: '下单、支付、查件' },
  { login: 'courier.bijing.demo', label: '北京快递员', role: 'COURIER', desc: '揽收、派送' },
  { login: 'courier.shanghai.demo', label: '上海快递员', role: 'COURIER', desc: '揽收、派送' },
  { login: 'operator.beijing.demo', label: '北京网点员', role: 'STATION_OPERATOR', desc: '入站、干线' },
  { login: 'operator.shanghai.demo', label: '上海网点员', role: 'STATION_OPERATOR', desc: '到站、自取' },
  { login: 'operations.demo', label: '运营管理员', role: 'OPERATIONS_ADMIN', desc: '异常、SLA' },
  { login: 'system.demo', label: '系统管理员', role: 'SYSTEM_ADMIN', desc: '死信、配置' },
];
const password = ref('YituDemo2026!');
const selectedLogin = ref('');
async function handleLogin(loginName: string) {
  selectedLogin.value = loginName;
  try {
    await auth.login(loginName, password.value);
    const routes: Record<string, string> = { CUSTOMER: '/shipments', COURIER: '/operations', STATION_OPERATOR: '/operations', OPERATIONS_ADMIN: '/operations', SYSTEM_ADMIN: '/admin/dead-letters' };
    router.push(routes[auth.user?.role || 'CUSTOMER'] || '/shipments');
  } catch { /* store 已处理 */ }
}
</script>
<template>
  <div style="min-height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, var(--color-primary-800) 0%, var(--color-primary-900) 100%); padding: var(--space-xl);">
    <div style="width: 100%; max-width: 680px;">
      <div style="text-align: center; margin-bottom: var(--space-2xl);">
        <div style="font-size: 2.5rem; font-weight: 700; color: #fff; letter-spacing: 0.06em;">驿途</div>
        <div style="font-size: 0.75rem; color: var(--color-surface-400); letter-spacing: 0.08em; margin-top: 4px;">YITU SMART LOGISTICS</div>
        <div style="margin-top: var(--space-lg); display: inline-block; padding: 4px 14px; border-radius: 100px; background: rgba(255,255,255,0.08); color: var(--color-amber-light); font-size: 0.6875rem; font-weight: 600; letter-spacing: 0.04em;">演示环境</div>
      </div>
      <div v-if="auth.error" style="background: var(--color-red); color: #fff; padding: var(--space-md); border-radius: var(--radius-md); margin-bottom: var(--space-lg); font-size: 0.875rem; text-align: center;">{{ auth.error }}</div>
      <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--space-sm);">
        <button v-for="account in DEMO_ACCOUNTS" :key="account.login"
          @click="handleLogin(account.login)" :disabled="auth.loading"
          :style="{ background: selectedLogin === account.login ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.06)', border: selectedLogin === account.login ? '1px solid var(--color-amber)' : '1px solid rgba(255,255,255,0.08)' }"
          style="display: flex; flex-direction: column; align-items: center; gap: var(--space-xs); padding: var(--space-lg) var(--space-md); border-radius: var(--radius-lg); color: #fff; cursor: pointer; transition: all 0.15s ease;">
          <span style="font-size: 0.9375rem; font-weight: 700;">{{ account.label }}</span>
          <span style="font-size: 0.6875rem; opacity: 0.5; font-family: var(--font-mono);">{{ account.login }}</span>
          <span style="font-size: 0.6875rem; opacity: 0.6;">{{ account.desc }}</span>
        </button>
      </div>
      <div style="margin-top: var(--space-lg); display: flex; gap: var(--space-sm); justify-content: center;">
        <input type="password" v-model="password" placeholder="演示密码"
          style="width: 240px; padding: 10px 16px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12); border-radius: var(--radius-md); color: #fff; font-size: 0.875rem;" />
      </div>
      <p style="text-align: center; margin-top: var(--space-xl); color: var(--color-surface-500); font-size: 0.75rem;">选择角色即可登录 · 演示密码：YituDemo2026!</p>
    </div>
  </div>
</template>