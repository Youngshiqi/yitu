import { api, generateIdempotencyKey } from './client';
export interface QuoteRequest {
  origin_district_code: string; destination_district_code: string;
  pickup_method: 'DOOR_PICKUP' | 'STATION_DROPOFF';
  delivery_method: 'HOME_DELIVERY' | 'STATION_PICKUP';
  actual_weight_grams: number; length_cm: number; width_cm: number; height_cm: number; declared_value_cents: number;
}
export interface QuoteLineItem { label: string; amount_cents: number; }
export interface QuoteView {
  id: string; owner_id: string; total_cents: number; chargeable_weight_grams: number;
  line_items: QuoteLineItem[]; rule_version: string; created_at: string; expires_at: string;
}
export const pricingApi = {
  createQuote: (d: QuoteRequest) => api.post<QuoteView>('/pricing/quotes', d, { idempotencyKey: generateIdempotencyKey() }),
  getQuote: (id: string) => api.get<QuoteView>(`/pricing/quotes/${id}`),
};