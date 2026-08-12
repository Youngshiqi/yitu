import { api } from './client'

export interface Station { id: string; code: string; name: string; district_code: string }

export const stationsApi = {
  list: (districtCode?: string) => api.get<Station[]>(`/stations${districtCode ? `?district_code=${districtCode}` : ''}`),
}