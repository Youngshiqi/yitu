import { api } from './client'

export interface NotificationView {
  id: string; template_code: string; title: string; content: string
  status: 'UNREAD' | 'READ'; created_at: string; read_at: string | null
}

export const notificationsApi = {
  list: (unreadOnly?: boolean) =>
    api.get<NotificationView[]>(`/notifications${unreadOnly ? '?unread_only=true' : ''}`),
  markRead: (id: string) => api.post<NotificationView>(`/notifications/${id}/read`),
}