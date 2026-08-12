import axios from 'axios';
export const http = axios.create({ baseURL: '/api/v1', timeout: 12000 });
http.interceptors.request.use((config) => {
    const token = localStorage.getItem('yitu_token');
    if (token)
        config.headers.Authorization = `Bearer ${token}`;
    return config;
});
http.interceptors.response.use((response) => response, (error) => {
    if (error.response?.status === 401)
        localStorage.removeItem('yitu_token');
    return Promise.reject(error);
});
export async function login(login_name, password) {
    const { data } = await http.post('/auth/demo-login', { login_name, password });
    localStorage.setItem('yitu_token', data.access_token);
    return data;
}
export async function me() { return (await http.get('/auth/me')).data; }
export async function listShipments(params) { return (await http.get('/shipments', { params })).data; }
export async function getShipment(id) { return (await http.get(`/shipments/${id}`)).data; }
export async function tracking(id) { return (await http.get(`/shipments/${id}/tracking`)).data; }
export async function listAddresses() { return (await http.get('/addresses')).data; }
export async function createAddress(payload) { return (await http.post('/addresses', payload)).data; }
export async function listNotifications() { return (await http.get('/notifications')).data; }
export async function markNotificationRead(id) { return (await http.post(`/notifications/${id}/read`)).data; }
export async function listStations() { return (await http.get('/stations')).data; }
export async function createShipment(payload) { return (await http.post('/shipments', payload, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data; }
export async function createConversation(title) { return (await http.post('/agent/conversations', { title })).data; }
export async function listConversations() { return (await http.get('/agent/conversations')).data; }
export async function listMessages(id) { return (await http.get(`/agent/conversations/${id}/messages`)).data; }
export async function sendAgentMessage(id, content) { return (await http.post(`/agent/conversations/${id}/messages`, { content })).data; }
export async function getAgentDraft(id) { return (await http.get(`/agent/conversations/${id}/draft`)).data; }
export async function validateAgentDraft(id) { return (await http.post(`/agent/conversations/${id}/draft/validate`)).data; }
export async function issueAgentGrant(id) { return (await http.post(`/agent/conversations/${id}/grant`)).data; }
export async function consumeAgentGrant(id) { return (await http.post(`/agent/conversations/grants/${id}/consume`)).data; }
export async function listCourierTasks(shipment_id) { return (await http.get('/dispatch/tasks', { params: { shipment_id: shipment_id || undefined } })).data; }
export async function acceptCourierTask(id) { await http.post(`/dispatch/tasks/${id}/accept`); }
export async function confirmCourierPickup(id) { await http.post(`/dispatch/tasks/${id}/confirm-pickup`); }
export async function startCourierDelivery(shipmentId) { await http.post(`/dispatch/shipments/${shipmentId}/start-delivery`); }
export async function confirmCourierDelivery(shipmentId, signerName) { await http.post(`/dispatch/shipments/${shipmentId}/confirm-delivery`, { signer_name: signerName }); }
export async function reportException(payload) { return (await http.post('/exceptions', payload, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data; }
export async function listExceptions(params) { return (await http.get('/exceptions', { params })).data; }
export async function applyExceptionAction(id, action, reason) { return (await http.post(`/exceptions/${id}/${action}`, { reason: reason || undefined }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data; }
export async function resolveException(id, resolutionCode, reason) { return (await http.post(`/exceptions/${id}/resolve`, { resolution_code: resolutionCode, reason }, { headers: { 'Idempotency-Key': crypto.randomUUID() } })).data; }
export async function arriveDestination(shipmentId) { return (await http.post(`/dispatch/shipments/${shipmentId}/arrive-destination`)).data; }
export async function listSlaInstances(shipmentId) { return (await http.get(`/sla/shipments/${shipmentId}/instances`)).data; }
export async function listDeadLetters(params) { return (await http.get('/admin/dead-letters', { params })).data; }
export async function replayDeadLetter(id) { return (await http.post(`/admin/dead-letters/${id}/replay`)).data; }
export async function uploadKnowledgeDocument(file) { const body = new FormData(); body.append('file', file); return (await http.post('/knowledge/documents', body, { headers: { 'Content-Type': 'multipart/form-data' } })).data; }
export async function reviewKnowledgeDocument(id, payload) { return (await http.post(`/knowledge/documents/${id}/review`, payload)).data; }
export async function knowledgeAction(id, action) { return (await http.post(`/knowledge/documents/${id}/${action}`)).data; }
export async function searchKnowledge(query, category) { return (await http.get('/knowledge/search', { params: { query, category: category || undefined, limit: 10 } })).data; }
