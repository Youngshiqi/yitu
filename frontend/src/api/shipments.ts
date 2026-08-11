import { api } from './client'

export type ShipmentStatus =
  'PENDING_PAYMENT' | 'PENDING_PICKUP' | 'PICKUP_ASSIGNED' | 'WAITING_FOR_DROPOFF' |
  'PICKED_UP' | 'AT_ORIGIN_STATION' | 'IN_LINEHAUL' | 'AT_DESTINATION_STATION' |
  'DELIVERY_ASSIGNED' | 'OUT_FOR_DELIVERY' | 'WAITING_FOR_RECIPIENT_PICKUP' |
  'DELIVERED' | 'CANCELLED' | 'RETURN_APPROVED' | 'IN_RETURN' | 'RETURNED'

export interface ShipmentView {
  id: string; shipment_no: string; owner_id: string; status: ShipmentStatus
}

export interface ShipmentListResponse {
  items: ShipmentView[]; total: number; limit: number; offset: number
}

export interface TrackingEventView {
  id: string; shipment_id: string; event_type: string; label: string
  description: string | null; occurred_at: string; location: string | null
}

export const shipmentsApi = {
  create: (d: { draft: Record<string, unknown>; status: string }) =>
    api.post<ShipmentView>('/shipments', d),
  list: (params?: { status?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams()
    if (params?.status) q.set('status', params.status)
    if (params?.limit) q.set('limit', String(params.limit))
    if (params?.offset) q.set('offset', String(params.offset))
    const qs = q.toString()
    return api.get<ShipmentListResponse>(`/shipments${qs ? `?${qs}` : ''}`)
  },
  get: (id: string) => api.get<ShipmentView>(`/shipments/${id}`),
  getTracking: (id: string) => api.get<TrackingEventView[]>(`/shipments/${id}/tracking`),
  confirmPayment: (id: string) => api.post<void>(`/shipments/${id}/confirm-payment`),
  getLabel: (id: string) => api.get<{ shipment_no: string; barcode: string; qr_query_token: string }>(`/shipments/${id}/label`),
}