/* API Client —— 统一封装 fetch，注入 token，处理错误 */

const BASE_URL = '/api/v1';

export class ApiError extends Error {
  code: string;
  status: number;
  requestId: string;
  details: unknown;

  constructor(code: string, message: string, status: number, requestId: string, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.requestId = requestId;
    this.details = details;
  }
}

function getToken(): string | null {
  return localStorage.getItem('yitu_token');
}

async function request<T>(method: string, path: string, body?: unknown, opts?: { idempotencyKey?: string }): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (opts?.idempotencyKey) headers['Idempotency-Key'] = opts.idempotencyKey;

  const res = await fetch(`${BASE_URL}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });

  if (res.status === 204) return undefined as T;

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(data.code || 'UNKNOWN', data.message || '请求失败', res.status, data.request_id || '', data.details);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown, opts?: { idempotencyKey?: string }) => request<T>('POST', path, body, opts),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
};

export function generateIdempotencyKey(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}