const BASE = '/api/v1'

export class ApiError extends Error {
  code: string; status: number; requestId: string; details: unknown
  constructor(code: string, message: string, status: number, requestId: string, details?: unknown) {
    super(message); this.name = 'ApiError'; this.code = code; this.status = status; this.requestId = requestId; this.details = details
  }
}

function token() { return localStorage.getItem('yitu_token') }

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const t = token(); if (t) headers['Authorization'] = `Bearer ${t}`
  const res = await fetch(`${BASE}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined })
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(data.code || 'UNKNOWN', data.message || '请求失败', res.status, data.request_id || '', data.details)
  return data as T
}

export const api = {
  get: <T>(p: string) => request<T>('GET', p),
  post: <T>(p: string, b?: unknown) => request<T>('POST', p, b),
  patch: <T>(p: string, b?: unknown) => request<T>('PATCH', p, b),
  delete: <T>(p: string) => request<T>('DELETE', p),
}