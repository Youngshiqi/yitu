import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { api, ApiError } from '../api/client';

export type Role = 'CUSTOMER' | 'COURIER' | 'STATION_OPERATOR' | 'OPERATIONS_ADMIN' | 'SYSTEM_ADMIN';

export interface CurrentUser {
  id: string;
  display_name: string;
  role: Role;
  station_id: string | null;
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null);
  const token = ref<string | null>(localStorage.getItem('yitu_token'));
  const loading = ref(false);
  const error = ref<string | null>(null);

  const isLoggedIn = computed(() => !!token.value && !!user.value);

  async function login(loginName: string, password: string) {
    loading.value = true;
    error.value = null;
    try {
      const data = await api.post<{ access_token: string; token_type: string }>('/auth/demo-login', {
        login_name: loginName,
        password,
      });
      localStorage.setItem('yitu_token', data.access_token);
      token.value = data.access_token;
      await fetchMe();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : '登录失败';
      error.value = msg;
      throw err;
    } finally {
      loading.value = false;
    }
  }

  function logout() {
    localStorage.removeItem('yitu_token');
    user.value = null;
    token.value = null;
    error.value = null;
  }

  async function fetchMe() {
    if (!token.value) return;
    try {
      user.value = await api.get<CurrentUser>('/auth/me');
    } catch {
      localStorage.removeItem('yitu_token');
      user.value = null;
      token.value = null;
    }
  }

  return { user, token, loading, error, isLoggedIn, login, logout, fetchMe };
});