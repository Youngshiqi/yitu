import axios from 'axios'

export const http = axios.create({ baseURL: '/api/v1', timeout: 12000 })
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('yitu_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
http.interceptors.response.use((response) => response, (error) => {
  if (error.response?.status === 401) localStorage.removeItem('yitu_token')
  return Promise.reject(error)
})

export type Shipment = { id: string; shipment_no: string; owner_id: string; status: string }
export type Address = { id: string; label?: string; recipient_name: string; phone: string; district_code: string; detail: string }
export type Notification = { id: string; title: string; content: string; status: string; created_at: string; read_at?: string }
export type AgentConversation = { id: string; title?: string; status: string; created_at: string; updated_at: string }
export type AgentMessage = { id: string; conversation_id: string; role: 'user' | 'assistant' | 'tool' | 'system'; content: string; envelope?: Record<string, unknown>; created_at: string }
export type CourierTask = { id: string; shipment_id: string; task_type: 'PICKUP' | 'DELIVERY'; status: 'AVAILABLE' | 'ACCEPTED' | 'COMPLETED' | 'CANCELLED'; assignee_id?: string }

export async function login(login_name: string, password: string) {
  const { data } = await http.post('/auth/demo-login', { login_name, password })
  localStorage.setItem('yitu_token', data.access_token)
  return data
}
export async function me() { return (await http.get('/auth/me')).data }
export async function listShipments(params?: Record<string, unknown>) { return (await http.get('/shipments', { params })).data }
export async function getShipment(id: string) { return (await http.get(`/shipments/${id}`)).data }
export async function tracking(id: string) { return (await http.get(`/shipments/${id}/tracking`)).data }
export async function listAddresses() { return (await http.get('/addresses')).data as Address[] }
export async function createAddress(payload: Omit<Address, 'id'>) { return (await http.post('/addresses', payload)).data }
export async function listNotifications() { return (await http.get('/notifications')).data as Notification[] }
export async function markNotificationRead(id: string) { return (await http.post(`/notifications/${id}/read`)).data }
export async function listStations() { return (await http.get('/stations')).data }
export async function createShipment(payload: unknown) { return (await http.post('/shipments', payload, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function createConversation(title?: string) { return (await http.post('/agent/conversations', { title })).data as AgentConversation }
export async function listConversations() { return (await http.get('/agent/conversations')).data as AgentConversation[] }
export async function listMessages(id: string) { return (await http.get(`/agent/conversations/${id}/messages`)).data as AgentMessage[] }
export async function sendAgentMessage(id: string, content: string) { return (await http.post(`/agent/conversations/${id}/messages`, { content })).data }
export async function getAgentDraft(id: string) { return (await http.get(`/agent/conversations/${id}/draft`)).data }
export async function validateAgentDraft(id: string) { return (await http.post(`/agent/conversations/${id}/draft/validate`)).data }
export async function issueAgentGrant(id: string) { return (await http.post(`/agent/conversations/${id}/grant`)).data }
export async function consumeAgentGrant(id: string) { return (await http.post(`/agent/conversations/grants/${id}/consume`)).data }
export async function listCourierTasks(shipment_id?: string) { return (await http.get('/dispatch/tasks', { params: { shipment_id: shipment_id || undefined } })).data as CourierTask[] }
export async function acceptCourierTask(id: string) { await http.post(`/dispatch/tasks/${id}/accept`) }
export async function confirmCourierPickup(id: string) { await http.post(`/dispatch/tasks/${id}/confirm-pickup`) }
export async function startCourierDelivery(shipmentId: string) { await http.post(`/dispatch/shipments/${shipmentId}/start-delivery`) }
export async function confirmCourierDelivery(shipmentId: string, signerName: string) { await http.post(`/dispatch/shipments/${shipmentId}/confirm-delivery`, { signer_name: signerName }) }
export async function reportException(payload: { shipment_id: string; case_type: string; description: string; evidence_summary: Record<string, unknown> }) { return (await http.post('/exceptions', payload, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export type ExceptionCase = { id: string; shipment_id: string; case_type: string; severity: string; status: string; description: string; blocks_fulfillment: boolean; assigned_to?: string; opened_at: string }
export async function listExceptions(params?: Record<string, unknown>) { return (await http.get('/exceptions', { params })).data as { items: ExceptionCase[]; total: number } }
export async function applyExceptionAction(id: string, action: 'start-processing' | 'wait-for-customer' | 'resume-processing' | 'close', reason?: string) { return (await http.post(`/exceptions/${id}/${action}`, { reason: reason || undefined }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function resolveException(id: string, resolutionCode: string, reason: string) { return (await http.post(`/exceptions/${id}/resolve`, { resolution_code: resolutionCode, reason }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function arriveDestination(shipmentId: string) { return (await http.post(`/dispatch/shipments/${shipmentId}/arrive-destination`)).data }
export async function listSlaInstances(shipmentId: string) { return (await http.get(`/sla/shipments/${shipmentId}/instances`)).data }
export type DeadLetter = { id: string; event_id: string; event_type: string; business_id: string; attempts: number; last_error: string; failed_at: string; replayed_at?: string; suggested_action: string }
export type KnowledgeDocument = { id: string; filename: string; content_type: string; size_bytes: number; sha256: string; status: string; page_count?: number; error_message?: string; mineru_task_id?: string; created_at: string; updated_at: string; category?: string; published_at?: string }
export async function listDeadLetters(params?: Record<string, unknown>) { return (await http.get('/admin/dead-letters', { params })).data as DeadLetter[] }
export async function replayDeadLetter(id: string) { return (await http.post(`/admin/dead-letters/${id}/replay`)).data }
export async function uploadKnowledgeDocument(file: File) { const body = new FormData(); body.append('file', file); return (await http.post('/knowledge/documents', body, { headers: { 'Content-Type': 'multipart/form-data' } })).data as KnowledgeDocument }
export async function reviewKnowledgeDocument(id: string, payload: { category?: string; effective_from?: string; effective_to?: string }) { return (await http.post(`/knowledge/documents/${id}/review`, payload)).data as KnowledgeDocument }
export async function knowledgeAction(id: string, action: 'publish' | 'archive' | 'deactivate' | 'reparse') { return (await http.post(`/knowledge/documents/${id}/${action}`)).data as KnowledgeDocument }
export async function searchKnowledge(query: string, category?: string) { return (await http.get('/knowledge/search', { params: { query, category: category || undefined, limit: 10 } })).data as { items: Array<{ document_id: string; filename: string; category?: string; title?: string; section_path: string[]; content: string; page_start?: number; page_end?: number; score: number }> } }
