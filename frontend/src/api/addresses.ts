import { api } from './client'

export interface Address { id: string; label: string; recipient_name: string; phone: string; district_code: string; detail: string }

export const addressesApi = {
  list: () => api.get<Address[]>('/addresses'),
  create: (d: Omit<Address, 'id'>) => api.post<Address>('/addresses', d),
  update: (id: string, d: Partial<Omit<Address, 'id'>>) => api.patch<Address>(`/addresses/${id}`, d),
  remove: (id: string) => api.delete<void>(`/addresses/${id}`),
}