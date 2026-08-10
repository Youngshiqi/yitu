import { api, generateIdempotencyKey } from './client';
export type ExceptionType = 'PICKUP_FAILED' | 'ADDRESS_ERROR' | 'RECIPIENT_UNREACHABLE' | 'REFUSED' | 'DAMAGE' | 'WEIGHT_MISMATCH' | 'STATION_DELAY' | 'SUSPECTED_LOSS' | 'WAITING_FOR_SUPPLEMENT';
export type ExceptionStatus = 'OPEN' | 'ASSIGNED' | 'PROCESSING' | 'WAITING_FOR_CUSTOMER' | 'RESOLVED' | 'CLOSED';
export interface ExceptionView {
  id: string; shipment_id: string; case_type: ExceptionType; severity: string;
  status: ExceptionStatus; description: string; assigned_to: string | null;
  responsible_station_id: string | null; blocks_fulfillment: boolean;
  opened_at: string; resolved_at: string | null; closed_at: string | null;
}
export interface ExceptionListResponse { items: ExceptionView[]; total: number; limit: number; offset: number; }
export const exceptionsApi = {
  create: (d: { shipment_id: string; case_type: ExceptionType; description: string; evidence_summary?: Record<string, unknown> }) =>
    api.post<ExceptionView>('/exceptions', d, { idempotencyKey: generateIdempotencyKey() }),
  list: (params?: Record<string, string | number | boolean>) => {
    const q = new URLSearchParams();
    if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '') q.set(k, String(v)); });
    const qs = q.toString();
    return api.get<ExceptionListResponse>(`/exceptions${qs ? `?${qs}` : ''}`);
  },
  get: (id: string) => api.get<ExceptionView>(`/exceptions/${id}`),
  assign: (id: string, assigneeId: string, stationId: string, reason?: string) =>
    api.post<ExceptionView>(`/exceptions/${id}/assign`, { assignee_id: assigneeId, responsible_station_id: stationId, reason }, { idempotencyKey: generateIdempotencyKey() }),
  startProcessing: (id: string, reason?: string) =>
    api.post<ExceptionView>(`/exceptions/${id}/start-processing`, { reason }, { idempotencyKey: generateIdempotencyKey() }),
  resolve: (id: string, resolutionCode: string, reason?: string) =>
    api.post<ExceptionView>(`/exceptions/${id}/resolve`, { resolution_code: resolutionCode, reason }, { idempotencyKey: generateIdempotencyKey() }),
  close: (id: string, reason?: string) =>
    api.post<ExceptionView>(`/exceptions/${id}/close`, { reason }, { idempotencyKey: generateIdempotencyKey() }),
};