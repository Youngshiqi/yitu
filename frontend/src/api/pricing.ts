import { api } from './client'

export interface QuoteLineItem { label: string; amount_cents: number }
export interface QuoteView {
  id: string; total_cents: number; chargeable_weight_grams: number
  rule_version: string; line_items: QuoteLineItem[]
}

export const pricingApi = {
  createQuote: (d: {
    origin_district_code: string; destination_district_code: string
    pickup_method: string; delivery_method: string
    actual_weight_grams: number; length_cm: number; width_cm: number; height_cm: number
    declared_value_cents: number
  }) => api.post<QuoteView>('/pricing/quotes', d),
  getQuote: (id: string) => api.get<QuoteView>(`/pricing/quotes/${id}`),
}