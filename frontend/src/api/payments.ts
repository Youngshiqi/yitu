import { api, generateIdempotencyKey } from './client';
export interface PaymentTransactionView {
  id: string; shipment_id: string | null; transaction_type: string; status: string; amount_cents: number; created_at: string;
}
export const paymentsApi = {
  pay: (quoteId: string, shipmentId: string, amountCents: number) =>
    api.post<PaymentTransactionView>(`/payments/quotes/${quoteId}/pay`, { shipment_id: shipmentId, amount_cents: amountCents }, { idempotencyKey: generateIdempotencyKey() }),
};