import { api, generateIdempotencyKey } from './client';
export interface RecoveryView { id: string; action: string; status: string; reason: string; created_at: string; }
export interface RecoveryShipmentView { shipment_id: string; shipment_status: string; recovery: RecoveryView; refund_amount_cents: number; new_task_id: string | null; }
export const returnsApi = {
  cancel: (id: string, reason: string) => api.post<RecoveryShipmentView>(`/returns/shipments/${id}/cancel`, { reason }, { idempotencyKey: generateIdempotencyKey() }),
  redeliver: (id: string, reason: string) => api.post<RecoveryShipmentView>(`/returns/shipments/${id}/redeliver`, { reason }, { idempotencyKey: generateIdempotencyKey() }),
  convertToPickup: (id: string, reason: string) => api.post<RecoveryShipmentView>(`/returns/shipments/${id}/convert-to-pickup`, { reason }, { idempotencyKey: generateIdempotencyKey() }),
  approveReturn: (id: string, reason: string) => api.post<RecoveryShipmentView>(`/returns/shipments/${id}/approve-return`, { reason }, { idempotencyKey: generateIdempotencyKey() }),
  advanceReturn: (id: string, reason: string) => api.post<RecoveryShipmentView>(`/returns/shipments/${id}/advance-return`, { reason }, { idempotencyKey: generateIdempotencyKey() }),
};