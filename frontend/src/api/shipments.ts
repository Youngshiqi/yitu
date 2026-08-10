import { api, generateIdempotencyKey } from './client';
export type ShipmentStatus = 'PENDING_PAYMENT' | 'PENDING_PICKUP' | 'PICKUP_ASSIGNED' | 'WAITING_FOR_DROPOFF' | 'PICKED_UP' | 'AT_ORIGIN_STATION' | 'IN_LINEHAUL' | 'AT_DESTINATION_STATION' | 'DELIVERY_ASSIGNED' | 'OUT_FOR_DELIVERY' | 'WAITING_FOR_RECIPIENT_PICKUP' | 'DELIVERED' | 'CANCELLED' | 'RETURN_APPROVED' | 'IN_RETURN' | 'RETURNED';
export interface ShipmentView { id: string; shipment_no: string; owner_id: string; status: ShipmentStatus; }
export interface ShipmentListResponse { items: ShipmentView[]; total: number; limit: number; offset: number; }
export interface CreateShipmentDraft {
  sender_address_id: string | null; receiver_address_id: string | null;
  origin_station_id: string | null; destination_station_id: string | null;
  pickup_method: 'DOOR_PICKUP' | 'STATION_DROPOFF'; delivery_method: 'HOME_DELIVERY' | 'STATION_PICKUP';
}
export interface CreateShipmentCommand { draft: CreateShipmentDraft; status: 'PENDING_PAYMENT'; }
export interface TrackingEventView { id: string; shipment_id: string; event_type: string; message: string; created_at: string; }
export const shipmentsApi = {
  create: (d: CreateShipmentCommand) => api.post<ShipmentView>('/shipments', d, { idempotencyKey: generateIdempotencyKey() }),
  list: (params?: { status?: ShipmentStatus; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return api.get<ShipmentListResponse>(`/shipments${qs ? `?${qs}` : ''}`);
  },
  get: (id: string) => api.get<ShipmentView>(`/shipments/${id}`),
  confirmPayment: (id: string) => api.post<void>(`/shipments/${id}/confirm-payment`, {}, { idempotencyKey: generateIdempotencyKey() }),
  getTracking: (id: string) => api.get<TrackingEventView[]>(`/shipments/${id}/tracking`),
};