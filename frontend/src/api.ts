import axios from 'axios'

export const http = axios.create({ baseURL: '/api/v1', timeout: 12000 })
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('yitu_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
http.interceptors.response.use((response) => response, (error) => {
  if (error.response?.status === 401 && !error.config?.url?.includes('/auth/demo-login')) {
    localStorage.removeItem('yitu_token')
    window.dispatchEvent(new Event('yitu-auth-expired'))
  }
  return Promise.reject(error)
})

export type Shipment = { id: string; shipment_no: string; owner_id: string; status: string; delivery_method: string; quote_id?: string; package_id?: string }
export type ShipmentDraftInput = { sender_address_id?: string; receiver_address_id?: string; origin_station_id?: string; destination_station_id?: string; pickup_method: string; delivery_method: string; quote_id?: string; package_category?: string; package_description?: string; estimated_weight_grams?: number; estimated_length_cm?: number; estimated_width_cm?: number; estimated_height_cm?: number; declared_value_cents?: number; special_instructions?: string }
export type Region = { id: string; name: string; level: 'PROVINCE' | 'CITY' | 'DISTRICT' }
export type ServiceType = 'HOME_PICKUP' | 'STATION_DROP_OFF' | 'HOME_DELIVERY' | 'STATION_PICKUP'
export type StationServiceArea = { province_region_id: string; city_region_id: string; district_region_id: string; district_code: string; district_name: string; province_name: string; city_name: string; service_types: ServiceType[] }
export type StationLite = { id: string; code: string; name: string }
export type AdminStation = { id: string; code: string; name: string; district_code: string; province_region_id: string; city_region_id: string; district_region_id: string; province_name: string; city_name: string; district_name: string; enabled: boolean; created_at: string; updated_at: string; service_areas: StationServiceArea[] }
export type StationInput = { code: string; name: string; district_region_id: string; service_areas: Array<{ district_region_id: string; service_types: ServiceType[] }> }
export type Address = { id: string; label?: string; recipient_name: string; phone: string; province_region_id: string; province_name: string; city_region_id: string; city_name: string; district_region_id: string; district_name: string; district_code: string; detail: string; full_address: string }
export type AddressInput = { label?: string; recipient_name: string; phone: string; province_region_id: string; city_region_id: string; district_region_id: string; detail: string }
export type Notification = { id: string; template_code: string; template_data: Record<string, unknown>; title: string; content: string; status: string; created_at: string; read_at?: string }
export type AgentConversation = { id: string; title?: string; status: string; created_at: string; updated_at: string }
export type AgentMessage = { id: string; conversation_id: string; role: 'user' | 'assistant' | 'tool' | 'system'; content: string; envelope?: Record<string, unknown>; created_at: string }
export type AgentStreamEvent =
  | { event: 'user_message'; data: AgentMessage }
  | { event: 'delta'; data: { content: string } }
  | { event: 'done'; data: AgentMessage }
  | { event: 'error'; data: { code: string; message: string } }
export type CourierTask = { id: string; shipment_id: string; task_type: 'PICKUP' | 'DELIVERY'; status: 'AVAILABLE' | 'ACCEPTED' | 'COMPLETED' | 'CANCELLED'; assignee_id?: string }
export type Quote = { id: string; total_cents: number; currency: string; line_items: Array<{ name: string; amount_cents: number }>; rule_version: string; created_at: string }
export type ExceptionCase = { id: string; shipment_id: string; case_type: string; severity: string; status: string; description: string; blocks_fulfillment: boolean; assigned_to?: string; opened_at: string }
export type DeadLetter = { id: string; event_id: string; event_type: string; business_id: string; attempts: number; last_error: string; failed_at: string; replayed_at?: string; suggested_action: string }
export type KnowledgeDocument = { id: string; filename: string; content_type: string; size_bytes: number; sha256: string; status: string; page_count?: number; error_message?: string; mineru_task_id?: string; created_at: string; updated_at: string; category?: string; published_at?: string }

// ---- 认证 ----
export async function login(login_name: string, password: string) {
  const { data } = await http.post('/auth/demo-login', { login_name, password })
  localStorage.setItem('yitu_token', data.access_token)
  return data
}
export async function me() { return (await http.get('/auth/me')).data }

// ---- 运单 ----
export async function listShipments(params?: Record<string, unknown>) { return (await http.get('/shipments', { params })).data }
export type ShipmentDetail = { shipment: Shipment; tracking: Array<{ id: string; message: string; occurred_at: string }>; paid_total_cents: number; eta_at?: string | null; promised_delivery_at?: string | null; sender_address?: Address; receiver_address?: Address; package?: { category: string; description: string; estimated_weight_grams: number; estimated_length_cm: number; estimated_width_cm: number; estimated_height_cm: number; declared_value_cents: number; special_instructions?: string | null; actual_weight_grams?: number | null; actual_length_cm?: number | null; actual_width_cm?: number | null; actual_height_cm?: number | null }; quote?: { id: string; rule_version: string; fee_items: Array<{ code: string; amount_cents: number }>; total_cents: number; billable_weight_grams: number } }
export async function getShipment(id: string): Promise<ShipmentDetail> {
  const { data } = await http.get(`/shipments/${id}`)
  // 兼容后端重启前的旧版扁平响应，避免详情页因缺少 shipment 节点崩溃。
  if (data && typeof data === 'object' && data.shipment) return data as ShipmentDetail
  return {
    shipment: data as Shipment,
    tracking: [],
    paid_total_cents: 0,
    eta_at: null,
    promised_delivery_at: null,
  }
}
export async function tracking(id: string) { return (await http.get(`/shipments/${id}/tracking`)).data }
export async function createShipment(payload: { draft: ShipmentDraftInput; status: string }) { return (await http.post('/shipments', payload, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function getLabel(id: string) { return (await http.get(`/shipments/${id}/label`)).data }
export async function resumeShipment(id: string, reason: string) { return (await http.post(`/shipments/${id}/resume`, { reason }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }

// ---- 地址 ----
export async function listAddresses() { return (await http.get('/addresses')).data as Address[] }
export async function createAddress(payload: AddressInput) { return (await http.post('/addresses', payload)).data as Address }
export async function updateAddress(id: string, payload: Partial<AddressInput>) { return (await http.patch(`/addresses/${id}`, payload)).data as Address }
export async function deleteAddress(id: string) { await http.delete(`/addresses/${id}`) }

// ---- 行政区划 ----
export async function listRegions(params: { level?: 'PROVINCE'; parent_id?: string }) { return (await http.get('/regions', { params })).data as { items: Region[] } }

// ---- 网点 ----
export async function listStations(params?: Record<string, unknown>) { return (await http.get('/stations', { params })).data as StationLite[] }
export async function listAdminStations(params?: Record<string, unknown>) { return (await http.get('/admin/stations', { params })).data as { items: AdminStation[]; total: number } }
export async function createAdminStation(payload: StationInput) { return (await http.post('/admin/stations', payload)).data as AdminStation }
export async function updateAdminStation(id: string, payload: StationInput) { return (await http.patch(`/admin/stations/${id}`, payload)).data as AdminStation }
export async function setAdminStationEnabled(id: string, enabled: boolean) { return (await http.post(`/admin/stations/${id}/${enabled ? 'enable' : 'disable'}`)).data as AdminStation }
export async function deleteAdminStation(id: string) { await http.delete(`/admin/stations/${id}`) }

// ---- 报价与支付 ----
export async function createQuote(payload: {
  origin_district_code: string; destination_district_code: string
  pickup_method: string; delivery_method: string
  actual_weight_grams: number; length_cm: number; width_cm: number; height_cm: number
  declared_value_cents?: number
}) { return (await http.post('/pricing/quotes', payload, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data as Quote }
export async function getQuote(id: string) { return (await http.get(`/pricing/quotes/${id}`)).data as Quote }
export async function payQuote(quoteId: string, payload: { shipment_id: string; amount_cents: number }) { return (await http.post(`/payments/quotes/${quoteId}/pay`, payload, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function paySupplement(quoteId: string, payload: { shipment_id: string; amount_cents: number }) { return (await http.post(`/payments/quotes/${quoteId}/supplement`, payload, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function confirmPayment(shipmentId: string) { return (await http.post(`/shipments/${shipmentId}/confirm-payment`)).data }
export async function confirmPickupWithReweigh(taskId: string, payload: { actual_weight_grams: number; actual_length_cm: number; actual_width_cm: number; actual_height_cm: number; remark?: string }) { return (await http.post(`/dispatch/tasks/${taskId}/confirm-pickup-with-reweigh`, payload)).data }

// ---- 通知 ----
export async function listNotifications() { return (await http.get('/notifications')).data as Notification[] }
export async function markNotificationRead(id: string) { return (await http.post(`/notifications/${id}/read`)).data }
export function notificationStreamUrl(cursor?: string): string { const base = '/api/v1/notifications/stream'; return cursor ? `${base}?cursor=${encodeURIComponent(cursor)}` : base }

// ---- AI Agent ----
export async function createConversation(title?: string) { return (await http.post('/agent/conversations', { title })).data as AgentConversation }
export async function listConversations() { return (await http.get('/agent/conversations')).data as AgentConversation[] }
export async function deleteConversation(id: string) { await http.delete(`/agent/conversations/${id}`) }
export async function listMessages(id: string) { return (await http.get(`/agent/conversations/${id}/messages`)).data as AgentMessage[] }
export async function sendAgentMessage(id: string, content: string) { return (await http.post(`/agent/conversations/${id}/messages`, { content })).data }
export async function* streamAgentMessage(id: string, content: string): AsyncGenerator<AgentStreamEvent> {
  const token = localStorage.getItem('yitu_token')
  const response = await fetch(`/api/v1/agent/conversations/${id}/messages/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ content }),
  })
  if (response.status === 401) {
    localStorage.removeItem('yitu_token')
    window.dispatchEvent(new Event('yitu-auth-expired'))
  }
  if (!response.ok || !response.body) throw new Error(`Agent stream failed: ${response.status}`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const event = frame.split('\n').find(line => line.startsWith('event:'))?.slice(6).trim()
      const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
      if (event && data) yield { event, data: JSON.parse(data) } as AgentStreamEvent
      boundary = buffer.indexOf('\n\n')
    }
    if (done) break
  }
}
export async function getAgentDraft(id: string) { return (await http.get(`/agent/conversations/${id}/draft`)).data }
export async function validateAgentDraft(id: string) { return (await http.post(`/agent/conversations/${id}/draft/validate`)).data }
export async function issueAgentGrant(id: string) { return (await http.post(`/agent/conversations/${id}/grant`)).data }
export async function consumeAgentGrant(id: string) { return (await http.post(`/agent/conversations/grants/${id}/consume`)).data }

// ---- 快递员任务 ----
export async function listCourierTasks(shipment_id?: string) { return (await http.get('/dispatch/tasks', { params: { shipment_id: shipment_id || undefined } })).data as CourierTask[] }
export async function acceptCourierTask(id: string) { await http.post(`/dispatch/tasks/${id}/accept`) }
export async function confirmCourierPickup(id: string) { await http.post(`/dispatch/tasks/${id}/confirm-pickup`) }
export async function startCourierDelivery(shipmentId: string) { await http.post(`/dispatch/shipments/${shipmentId}/start-delivery`) }
export async function confirmCourierDelivery(shipmentId: string, signerName: string) { await http.post(`/dispatch/shipments/${shipmentId}/confirm-delivery`, { signer_name: signerName }) }
export async function arriveDestination(shipmentId: string) { return (await http.post(`/dispatch/shipments/${shipmentId}/arrive-destination`)).data }

// ---- 网点操作 ----
export async function acceptDropoff(shipmentId: string) { return (await http.post(`/dispatch/shipments/${shipmentId}/accept-dropoff`)).data }
export async function confirmOriginArrival(shipmentId: string) { return (await http.post(`/dispatch/shipments/${shipmentId}/confirm-origin-arrival`)).data }
export async function dispatchLinehaul(shipmentId: string) { return (await http.post(`/dispatch/shipments/${shipmentId}/dispatch-linehaul`)).data }
export async function issuePickupCredential(shipmentId: string) { return (await http.post(`/dispatch/shipments/${shipmentId}/issue-pickup-credential`)).data }
export async function verifyStationPickup(shipmentId: string, code: string) { return (await http.post(`/dispatch/shipments/${shipmentId}/verify-station-pickup`, { code }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }

// ---- 异常 ----
export async function reportException(payload: { shipment_id: string; case_type: string; description: string; evidence_summary: Record<string, unknown> }) { return (await http.post('/exceptions', payload, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function listExceptions(params?: Record<string, unknown>) { return (await http.get('/exceptions', { params })).data as { items: ExceptionCase[]; total: number } }
export async function assignException(id: string, assignee_id: string) { return (await http.post(`/exceptions/${id}/assign`, { assignee_id }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function applyExceptionAction(id: string, action: 'start-processing' | 'wait-for-customer' | 'resume-processing' | 'close', reason?: string) { return (await http.post(`/exceptions/${id}/${action}`, { reason: reason || undefined }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function resolveException(id: string, resolutionCode: string, reason: string) { return (await http.post(`/exceptions/${id}/resolve`, { resolution_code: resolutionCode, reason }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function reassignExceptionTask(id: string, reason: string) { return (await http.post(`/exceptions/${id}/reassign-task`, { reason }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }

// ---- 返回与恢复 ----
export async function cancelShipment(id: string) { return (await http.post(`/returns/shipments/${id}/cancel`, {}, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function requestInterception(id: string) { return (await http.post(`/returns/shipments/${id}/request-interception`, {}, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function redeliverShipment(id: string, reason: string) { return (await http.post(`/returns/shipments/${id}/redeliver`, { reason }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function convertToPickup(id: string, reason: string) { return (await http.post(`/returns/shipments/${id}/convert-to-pickup`, { reason }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function approveReturn(id: string) { return (await http.post(`/returns/shipments/${id}/approve-return`, {}, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }
export async function advanceReturn(id: string) { return (await http.post(`/returns/shipments/${id}/advance-return`, {}, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data }

// ---- SLA ----
export async function listSlaInstances(shipmentId: string) { return (await http.get(`/sla/shipments/${shipmentId}/instances`)).data }

// ---- 死信 ----
export async function listDeadLetters(params?: Record<string, unknown>) { return (await http.get('/admin/dead-letters', { params })).data as DeadLetter[] }
export async function replayDeadLetter(id: string) { return (await http.post(`/admin/dead-letters/${id}/replay`)).data }

// ---- 知识库 ----
export async function listKnowledgeDocuments(params?: Record<string, unknown>) { return (await http.get('/knowledge/documents', { params })).data as KnowledgeDocument[] }
export async function uploadKnowledgeDocument(file: File) { const body = new FormData(); body.append('file', file); return (await http.post('/knowledge/documents', body, { headers: { 'Content-Type': 'multipart/form-data' } })).data as KnowledgeDocument }
export async function reviewKnowledgeDocument(id: string, payload: { category?: string; effective_from?: string; effective_to?: string }) { return (await http.post(`/knowledge/documents/${id}/review`, payload)).data as KnowledgeDocument }
export async function knowledgeAction(id: string, action: 'publish' | 'archive' | 'deactivate' | 'reparse') { return (await http.post(`/knowledge/documents/${id}/${action}`)).data as KnowledgeDocument }
export async function searchKnowledge(query: string, category?: string) { return (await http.get('/knowledge/search', { params: { query, category: category || undefined, limit: 10 } })).data as { items: Array<{ document_id: string; filename: string; category?: string; title?: string; section_path: string[]; content: string; page_start?: number; page_end?: number; score: number }> } }
