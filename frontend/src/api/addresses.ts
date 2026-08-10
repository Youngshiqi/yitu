export interface Address {
  id: string; label: string; recipient_name: string;
  phone: string; district_code: string; detail: string;
}
export type CreateAddressRequest = Omit<Address, 'id'>;

import { api } from './client';
export const addressesApi = {
  list: () => api.get<Address[]>('/addresses'),
  create: (d: CreateAddressRequest) => api.post<Address>('/addresses', d),
  update: (id: string, d: Partial<CreateAddressRequest>) => api.patch<Address>(`/addresses/${id}`, d),
  remove: (id: string) => api.delete<void>(`/addresses/${id}`),
};