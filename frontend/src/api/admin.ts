import { api } from './client';
export interface DeadLetterView { id: string; event_id: string; event_type: string; business_id: string; attempts: number; last_error: string; failed_at: string; replayed_at: string | null; suggested_action: string; }
export const adminApi = {
  listDeadLetters: (limit = 50, offset = 0) => api.get<DeadLetterView[]>(`/admin/dead-letters?limit=${limit}&offset=${offset}`),
  replayDeadLetter: (id: string) => api.post<{ dead_letter_id: string; event_id: string; status: string }>(`/admin/dead-letters/${id}/replay`),
};