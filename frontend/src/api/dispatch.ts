import { api, generateIdempotencyKey } from './client';
export interface TaskView { id: string; shipment_id: string; task_type: string; status: string; assignee_id: string | null; }
export const dispatchApi = {
  listTasks: (shipmentId?: string) => api.get<TaskView[]>(`/dispatch/tasks${shipmentId ? `?shipment_id=${shipmentId}` : ''}`),
  acceptTask: (id: string) => api.post<void>(`/dispatch/tasks/${id}/accept`, {}, { idempotencyKey: generateIdempotencyKey() }),
  confirmPickup: (id: string) => api.post<void>(`/dispatch/tasks/${id}/confirm-pickup`, {}, { idempotencyKey: generateIdempotencyKey() }),
  acceptDropoff: (id: string) => api.post<void>(`/dispatch/shipments/${id}/accept-dropoff`, {}, { idempotencyKey: generateIdempotencyKey() }),
  confirmOriginArrival: (id: string) => api.post<void>(`/dispatch/shipments/${id}/confirm-origin-arrival`, {}, { idempotencyKey: generateIdempotencyKey() }),
  dispatchLinehaul: (id: string) => api.post<void>(`/dispatch/shipments/${id}/dispatch-linehaul`, {}, { idempotencyKey: generateIdempotencyKey() }),
  arriveDestination: (id: string) => api.post<void>(`/dispatch/shipments/${id}/arrive-destination`, {}, { idempotencyKey: generateIdempotencyKey() }),
  startDelivery: (id: string) => api.post<void>(`/dispatch/shipments/${id}/start-delivery`, {}, { idempotencyKey: generateIdempotencyKey() }),
  confirmDelivery: (id: string, signer: string) => api.post<void>(`/dispatch/shipments/${id}/confirm-delivery`, { signer_name: signer }, { idempotencyKey: generateIdempotencyKey() }),
  issuePickupCredential: (id: string) => api.post<void>(`/dispatch/shipments/${id}/issue-pickup-credential`, {}, { idempotencyKey: generateIdempotencyKey() }),
  verifyStationPickup: (id: string, code: string) => api.post<void>(`/dispatch/shipments/${id}/verify-station-pickup`, { code }, { idempotencyKey: generateIdempotencyKey() }),
};