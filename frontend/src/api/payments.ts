import { api } from './client'

export const paymentsApi = {
  pay: (quoteId: string, shipmentId: string, amountCents: number) =>
    api.post(`/payments/quotes/${quoteId}/pay`, { shipment_id: shipmentId, amount_cents: amountCents }),
}