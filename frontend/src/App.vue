<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, Bell, Box, ChatDotRound, Delete, Edit, Expand, Fold, Location, Plus, Search, Setting, User } from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'
import { consumeAgentGrant, createAddress, createConversation, createShipment, deleteAddress, deleteConversation, getAgentDraft, getShipment, issueAgentGrant, listAddresses, listConversations, listMessages, listNotifications, listRegions, listShipments, login, markNotificationRead, me, streamAgentMessage, tracking, updateAddress, validateAgentDraft, type Address, type AddressInput, type AgentConversation, type AgentMessage, type Notification, type Region, type Shipment } from './api'
import StationOperatorWorkspace from './StationOperatorWorkspace.vue'
import CourierWorkspace from './CourierWorkspace.vue'
import OperationsWorkspace from './OperationsWorkspace.vue'
import SystemAdminWorkspace from './SystemAdminWorkspace.vue'

const loggedIn = ref(Boolean(localStorage.getItem('yitu_token')))
const user = ref<{ display_name: string; role: string; station_id?: string | null } | null>(null)
const view = ref('shipments')
const loading = ref(false)
const shipments = ref<Shipment[]>([])
const total = ref(0)
const addresses = ref<Address[]>([])
const notifications = ref<Notification[]>([])
const selected = ref<any>(null)
const timeline = ref<any[]>([])
const page = ref(1)
const query = ref('')
const loginForm = ref({ login_name: 'customer.demo', password: 'YituDemo2026!' })
// 演示环境身份列表；正式用户名密码登录接入后可替换为后端用户搜索。
const loginAccounts = [
  { login_name: 'customer.demo', label: '客户 · customer.demo', role: 'CUSTOMER' },
  { login_name: 'courier.bijing.demo', label: '北京快递员 · courier.bijing.demo', role: 'COURIER' },
  { login_name: 'courier.shanghai.demo', label: '上海快递员 · courier.shanghai.demo', role: 'COURIER' },
  { login_name: 'operator.beijing.demo', label: '北京网点操作员 · operator.beijing.demo', role: 'STATION_OPERATOR' },
  { login_name: 'operator.shanghai.demo', label: '上海网点操作员 · operator.shanghai.demo', role: 'STATION_OPERATOR' },
  { login_name: 'operations.demo', label: '运营管理员 · operations.demo', role: 'OPERATIONS_ADMIN' },
  { login_name: 'system.demo', label: '系统管理员 · system.demo', role: 'SYSTEM_ADMIN' },
]
const addressDialog = ref(false)
const emptyAddress = (): AddressInput => ({ label: '常用地址', recipient_name: '', phone: '', province_region_id: '', city_region_id: '', district_region_id: '', detail: '' })
const addressForm = ref<AddressInput>(emptyAddress())
const editingAddressId = ref<string | null>(null)
const provinces = ref<Region[]>([])
const cities = ref<Region[]>([])
const districts = ref<Region[]>([])
const regionLoading = ref(false)
const shipmentForm = ref({ sender_address_id: '', receiver_address_id: '', pickup_method: 'DOOR_PICKUP', delivery_method: 'HOME_DELIVERY' })
const conversations = ref<AgentConversation[]>([])
const activeConversation = ref<AgentConversation | null>(null)
const agentMessages = ref<AgentMessage[]>([])
const agentDraft = ref<any>(null)
const agentInput = ref('')
const agentSending = ref(false)
const chatListCollapsed = ref(false)
const messagesContainer = ref<HTMLElement | null>(null)
const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true })
const defaultLinkOpen = markdown.renderer.rules.link_open ?? ((tokens, index, options, _environment, renderer) => renderer.renderToken(tokens, index, options))
markdown.renderer.rules.link_open = (tokens, index, options, environment, renderer) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, index, options, environment, renderer)
}

function renderMarkdown(content: string): string {
  return markdown.render(content)
}

// 新消息和流式增量到达后始终展示最新内容，避免用户手动拖动滚动条。
watch(agentMessages, async () => {
  await nextTick()
  const container = messagesContainer.value
  if (container) container.scrollTop = container.scrollHeight
}, { deep: true, flush: 'post' })

const statusMap: Record<string, string> = {
  PENDING_PAYMENT: '待支付',
  PENDING_PICKUP: '待揽收',
  PICKUP_ASSIGNED: '已分配揽收',
  WAITING_FOR_DROPOFF: '等待客户自寄',
  PICKED_UP: '已揽收',
  AT_ORIGIN_STATION: '已到达始发网点',
  IN_LINEHAUL: '干线运输中',
  AT_DESTINATION_STATION: '已到达目标网点',
  DELIVERY_ASSIGNED: '已分配派送',
  OUT_FOR_DELIVERY: '派送中',
  WAITING_FOR_RECIPIENT_PICKUP: '等待客户自取',
  DELIVERED: '已签收',
  CANCELLED: '已取消',
  RETURN_REQUESTED: '已申请退回',
  RETURN_APPROVED: '退回已批准',
  RETURNING: '退回运输中',
  RETURNED_TO_ORIGIN_STATION: '已退回始发网点',
  RETURN_COMPLETED: '退回已完成',
}
const nav = computed(() => [
  { id: 'shipments', label: '我的运单', icon: Box },
  { id: 'create', label: '我要寄件', icon: Plus },
  { id: 'agent', label: 'AI 寄件助手', icon: ChatDotRound },
  { id: 'addresses', label: '地址簿', icon: Location },
  { id: 'notifications', label: '消息中心', icon: Bell, badge: notifications.value.filter(n => n.status !== 'READ').length },
])

async function loadData() {
  if (!loggedIn.value) return
  loading.value = true
  try {
    const [ship, addr, notice, chats] = await Promise.all([listShipments({ limit: 20, offset: (page.value - 1) * 20 }), listAddresses(), listNotifications(), listConversations()])
    shipments.value = ship.items ?? []; total.value = ship.total ?? 0; addresses.value = addr; notifications.value = notice; conversations.value = chats
  } catch { ElMessage.error('数据加载失败，请确认后端服务已启动') } finally { loading.value = false }
}
async function doLogin() { try { await login(loginForm.value.login_name, loginForm.value.password); loggedIn.value = true; user.value = await me(); if (user.value?.role === 'CUSTOMER') await loadData() } catch { ElMessage.error('账号或密码错误') } }
function logout() { localStorage.removeItem('yitu_token'); loggedIn.value = false; user.value = null }
function handleAuthExpired() { loggedIn.value = false; user.value = null; ElMessage.warning('登录状态已失效，请重新登录') }
async function openShipment(item: Shipment) { selected.value = await getShipment(item.id); timeline.value = await tracking(item.id); view.value = 'detail' }
async function openAddressDialog() {
  editingAddressId.value = null; addressForm.value = emptyAddress(); cities.value = []; districts.value = []; addressDialog.value = true; regionLoading.value = true
  try { provinces.value = (await listRegions({ level: 'PROVINCE' })).items } catch { ElMessage.error('行政区划加载失败') } finally { regionLoading.value = false }
}
async function editAddress(address: Address) {
  editingAddressId.value = address.id
  addressForm.value = { label: address.label, recipient_name: address.recipient_name, phone: address.phone, province_region_id: address.province_region_id, city_region_id: address.city_region_id, district_region_id: address.district_region_id, detail: address.detail }
  addressDialog.value = true; regionLoading.value = true
  try {
    const [provinceResult, cityResult, districtResult] = await Promise.all([listRegions({ level: 'PROVINCE' }), listRegions({ parent_id: address.province_region_id }), listRegions({ parent_id: address.city_region_id })])
    provinces.value = provinceResult.items; cities.value = cityResult.items; districts.value = districtResult.items
  } catch { ElMessage.error('行政区划加载失败') } finally { regionLoading.value = false }
}
async function removeAddress(address: Address) {
  try {
    await ElMessageBox.confirm(`确定删除“${address.label || address.full_address}”吗？`, '删除地址', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
    await deleteAddress(address.id)
    if (shipmentForm.value.sender_address_id === address.id) shipmentForm.value.sender_address_id = ''
    if (shipmentForm.value.receiver_address_id === address.id) shipmentForm.value.receiver_address_id = ''
    addresses.value = addresses.value.filter(item => item.id !== address.id)
    ElMessage.success('地址已删除')
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error.response?.data?.message || '地址删除失败')
  }
}
async function changeProvince(value: string) {
  addressForm.value.city_region_id = ''; addressForm.value.district_region_id = ''; cities.value = []; districts.value = []
  if (!value) return
  regionLoading.value = true
  try { cities.value = (await listRegions({ parent_id: value })).items } catch { ElMessage.error('城市列表加载失败') } finally { regionLoading.value = false }
}
async function changeCity(value: string) {
  addressForm.value.district_region_id = ''; districts.value = []
  if (!value) return
  regionLoading.value = true
  try { districts.value = (await listRegions({ parent_id: value })).items } catch { ElMessage.error('区县列表加载失败') } finally { regionLoading.value = false }
}
async function saveAddress() {
  const form = addressForm.value
  if (!form.recipient_name || !form.phone || !form.province_region_id || !form.city_region_id || !form.district_region_id || !form.detail) { ElMessage.warning('请完整填写联系人、省市区和详细地址'); return }
  try {
    if (editingAddressId.value) await updateAddress(editingAddressId.value, form)
    else await createAddress(form)
    addressDialog.value = false; await loadData(); ElMessage.success(editingAddressId.value ? '地址已更新' : '地址已保存')
  } catch (error: any) { ElMessage.error(error.response?.data?.message || '地址保存失败') }
}
async function submitShipment() {
  const form = shipmentForm.value
  if (!form.sender_address_id) { ElMessage.warning('请选择寄件地址'); return }
  if (!form.receiver_address_id) { ElMessage.warning('请选择收件地址'); return }
  const draft = {
    sender_address_id: form.sender_address_id,
    receiver_address_id: form.receiver_address_id,
    pickup_method: 'DOOR_PICKUP',
    delivery_method: 'HOME_DELIVERY',
  }
  try { await createShipment({ draft, status: 'PENDING_PAYMENT' }); ElMessage.success('运单已创建'); view.value = 'shipments'; await loadData() } catch (error: any) { ElMessage.error(error.response?.data?.message || error.response?.data?.detail?.[0]?.msg || '运单创建失败') }
}
function startNewConversation() {
  const now = new Date().toISOString()
  activeConversation.value = { id: '', status: 'LOCAL', created_at: now, updated_at: now }
  agentMessages.value = []
  agentDraft.value = null
  agentInput.value = ''
}
async function openConversation(conversation: AgentConversation) {
  try {
    activeConversation.value = conversation
    agentMessages.value = await listMessages(conversation.id)
    agentDraft.value = await getAgentDraft(conversation.id)
  } catch { ElMessage.error('AI 助手暂时不可用') }
}
async function removeConversation(conversation: AgentConversation) {
  try {
    await ElMessageBox.confirm(`确定删除会话“${conversation.title || '未命名会话'}”吗？删除后无法恢复。`, '删除会话', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await deleteConversation(conversation.id)
    conversations.value = conversations.value.filter(item => item.id !== conversation.id)
    if (activeConversation.value?.id === conversation.id) {
      activeConversation.value = null
      agentMessages.value = []
      agentDraft.value = null
    }
    ElMessage.success('会话已删除')
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error.response?.data?.message || '会话删除失败')
  }
}
async function sendMessage() {
  const content = agentInput.value.trim()
  if (!content || !activeConversation.value || agentSending.value) return
  const createdAt = new Date().toISOString()
  const temporaryUserId = `local-user-${crypto.randomUUID()}`
  const temporaryAssistantId = `local-assistant-${crypto.randomUUID()}`
  const userMessage: AgentMessage = { id: temporaryUserId, conversation_id: activeConversation.value.id, role: 'user', content, created_at: createdAt }
  const assistantMessage: AgentMessage = { id: temporaryAssistantId, conversation_id: activeConversation.value.id, role: 'assistant', content: '', created_at: createdAt }
  agentInput.value = ''
  agentMessages.value.push(userMessage, assistantMessage)
  agentSending.value = true
  let completed = false
  try {
    if (!activeConversation.value.id) {
      activeConversation.value = await createConversation()
      userMessage.conversation_id = activeConversation.value.id
      assistantMessage.conversation_id = activeConversation.value.id
    }
    const conversationId = activeConversation.value.id
    for await (const event of streamAgentMessage(conversationId, content)) {
      if (event.event === 'user_message') {
        const index = agentMessages.value.findIndex(item => item.id === temporaryUserId)
        if (index >= 0) agentMessages.value[index] = event.data
      } else if (event.event === 'delta') {
        const message = agentMessages.value.find(item => item.id === temporaryAssistantId)
        if (message) message.content += event.data.content
      } else if (event.event === 'done') {
        const index = agentMessages.value.findIndex(item => item.id === temporaryAssistantId)
        if (index >= 0) agentMessages.value[index] = event.data
        completed = true
      } else {
        throw new Error(event.data.message)
      }
    }
    if (!completed) throw new Error('AI 回复流意外结束')
    agentDraft.value = await getAgentDraft(conversationId)
    conversations.value = await listConversations()
    activeConversation.value = conversations.value.find(item => item.id === conversationId) ?? activeConversation.value
  } catch (error: any) {
    const message = agentMessages.value.find(item => item.id === temporaryAssistantId)
    if (message) message.content = error.message || 'AI 服务暂时不可用，请稍后重试'
    ElMessage.error(error.message || '消息发送失败，请稍后重试')
  } finally {
    if (activeConversation.value?.id) conversations.value = await listConversations().catch(() => conversations.value)
    agentSending.value = false
  }
}
async function validateDraft() { if (!activeConversation.value) return; try { const result = await validateAgentDraft(activeConversation.value.id); agentDraft.value = result.draft; ElMessage.success(`报价已生成：${(result.quote.total_cents / 100).toFixed(2)} 元`) } catch { ElMessage.warning('请先在对话中补充寄件信息') } }
async function confirmAgentShipment() { if (!activeConversation.value) return; try { const grant = await issueAgentGrant(activeConversation.value.id); await consumeAgentGrant(grant.id); ElMessage.success('运单已创建'); await loadData(); view.value = 'shipments' } catch { ElMessage.error('草稿尚未准备好，请重新确认报价') } }
async function readNotice(item: Notification) { if (item.status !== 'READ') { await markNotificationRead(item.id); item.status = 'READ' } }
onMounted(async () => { window.addEventListener('yitu-auth-expired', handleAuthExpired); if (loggedIn.value) { try { user.value = await me(); if (user.value?.role === 'CUSTOMER') await loadData() } catch { logout() } } })
onBeforeUnmount(() => window.removeEventListener('yitu-auth-expired', handleAuthExpired))
</script>

<template>
  <div v-if="!loggedIn" class="login-page">
    <div class="login-art"><div class="eyebrow">YITU LOGISTICS / 2026</div><h1>把每一次<br><em>寄托</em>送到。</h1><p>从下单、交接到签收，一处掌握完整轨迹。</p><div class="route-line"><span>广州</span><ArrowRight /><span>上海</span></div></div>
    <el-card class="login-card" shadow="never"><div class="brand-mark">Y</div><h2>欢迎回来</h2><p class="muted">选择身份进入对应工作台</p><el-form @submit.prevent="doLogin" @keyup.enter="doLogin"><el-form-item label="登录身份"><el-select v-model="loginForm.login_name" size="large" class="full-input" filterable><el-option v-for="account in loginAccounts" :key="account.login_name" :label="account.label" :value="account.login_name"><div class="login-option"><span>{{ account.label }}</span><small>{{ account.role }}</small></div></el-option></el-select></el-form-item><el-form-item label="密码"><el-input v-model="loginForm.password" type="password" show-password size="large" /></el-form-item><el-button type="primary" size="large" class="full-btn" @click="doLogin">进入工作台 <ArrowRight /></el-button></el-form><div class="login-note">演示环境统一密码：YituDemo2026!</div></el-card>
  </div>
  <CourierWorkspace v-else-if="user?.role === 'COURIER'" :user="user" @logout="logout" />
  <StationOperatorWorkspace v-else-if="user?.role === 'STATION_OPERATOR'" :user="user" @logout="logout" />
  <OperationsWorkspace v-else-if="user?.role === 'OPERATIONS_ADMIN'" :user="user" @logout="logout" />
  <SystemAdminWorkspace v-else-if="user?.role === 'SYSTEM_ADMIN'" :user="user" @logout="logout" />
  <div v-else class="app-shell">
    <aside class="sidebar"><div class="logo"><span>Y</span><div>Yitu<small>物流工作台</small></div></div><div class="workspace-label">客户工作区</div><nav><button v-for="item in nav" :key="item.id" :class="{ active: view === item.id }" @click="view = item.id"><component :is="item.icon" /><span>{{ item.label }}</span><b v-if="item.badge">{{ item.badge }}</b></button></nav><div class="sidebar-foot"><el-button text @click="logout"><Setting /> 退出登录</el-button></div></aside>
    <main class="main"><header class="topbar"><div><div class="crumb">客户中心 <span>/</span> {{ nav.find(n => n.id === view)?.label ?? '运单详情' }}</div><h1>{{ view === 'detail' ? '运单详情' : nav.find(n => n.id === view)?.label }}</h1></div><div class="top-actions"><el-input v-model="query" placeholder="搜索运单号" :prefix-icon="Search" clearable /><el-avatar :size="34">{{ user?.display_name?.slice(0, 1) }}</el-avatar><span class="user-name">{{ user?.display_name || '演示客户' }}</span></div></header>
      <section v-loading="loading" class="content">
        <div v-if="view === 'shipments'" class="page-block"><div class="section-head"><div><p class="section-kicker">TRACKING OVERVIEW</p><h2>最近运单</h2></div><el-button type="primary" @click="view = 'create'"><Plus /> 新建寄件</el-button></div><div class="stat-strip"><div><small>全部运单</small><strong>{{ total }}</strong></div><div><small>运输中</small><strong>{{ shipments.filter(s => ['IN_LINEHAUL', 'OUT_FOR_DELIVERY'].includes(s.status)).length }}</strong></div><div><small>待支付</small><strong>{{ shipments.filter(s => s.status === 'PENDING_PAYMENT').length }}</strong></div></div><el-table :data="shipments.filter(s => !query || s.shipment_no.includes(query))" class="shipment-table" @row-click="openShipment"><el-table-column prop="shipment_no" label="运单号" min-width="190"><template #default="{ row }"><span class="shipment-no">{{ row.shipment_no }}</span></template></el-table-column><el-table-column prop="status" label="状态"><template #default="{ row }"><el-tag :type="row.status === 'DELIVERED' ? 'success' : row.status === 'PENDING_PAYMENT' ? 'warning' : row.status === 'CANCELLED' ? 'danger' : 'primary'" effect="light">{{ statusMap[row.status] || row.status }}</el-tag></template></el-table-column><el-table-column label="操作" width="100"><template #default="{ row }"><el-button text type="primary" @click.stop="openShipment(row)">查看 <ArrowRight /></el-button></template></el-table-column></el-table><el-pagination v-if="total > 20" v-model:current-page="page" layout="prev, pager, next" :total="total" @current-change="loadData" /></div>
        <div v-else-if="view === 'create'" class="page-block narrow"><div class="section-head"><div><p class="section-kicker">NEW SHIPMENT</p><h2>创建寄件</h2></div></div><el-card shadow="never" class="form-card"><el-form label-position="top"><div class="form-grid"><el-form-item label="寄件方式"><el-tag type="success" size="large">上门取件</el-tag></el-form-item><el-form-item label="派送方式"><el-tag type="success" size="large">送货上门</el-tag></el-form-item></div><el-form-item label="寄件地址"><el-select v-model="shipmentForm.sender_address_id" placeholder="选择寄件地址" filterable><el-option v-for="a in addresses" :key="a.id" :label="`${a.recipient_name} · ${a.full_address}`" :value="a.id" /></el-select></el-form-item><el-form-item label="收件地址"><el-select v-model="shipmentForm.receiver_address_id" placeholder="选择收件地址" filterable><el-option v-for="a in addresses" :key="a.id" :label="`${a.recipient_name} · ${a.full_address}`" :value="a.id" /></el-select></el-form-item><div class="service-tip">当前仅支持上门取件和送货上门；所选区县必须已有服务网点。</div><el-button type="primary" size="large" @click="submitShipment">创建运单 <ArrowRight /></el-button></el-form></el-card></div>
        <div v-else-if="view === 'agent'" :class="['agent-page', { 'chat-list-collapsed': chatListCollapsed }]">
          <aside :class="['chat-list', { collapsed: chatListCollapsed }]">
            <el-button v-if="chatListCollapsed" class="chat-expand" text :icon="Expand" title="展开会话列表" @click="chatListCollapsed = false" />
            <template v-else>
              <div class="section-head"><div><p class="section-kicker">ASSISTANT</p><h2>智能寄件</h2></div><div class="chat-list-actions"><el-button circle text :icon="Fold" title="收起会话列表" @click="chatListCollapsed = true" /><el-button circle type="primary" :icon="Plus" title="新建会话" @click="startNewConversation" /></div></div>
              <div v-for="chat in conversations" :key="chat.id" :class="['chat-item', { active: activeConversation?.id === chat.id }]" @click="openConversation(chat)">
                <span>{{ chat.title || '未命名会话' }}<small>{{ new Date(chat.updated_at).toLocaleDateString('zh-CN') }}</small></span>
                <el-button class="chat-delete" circle text type="danger" :icon="Delete" @click.stop="removeConversation(chat)" />
              </div>
              <el-empty v-if="!conversations.length" description="开始一次智能寄件" />
            </template>
          </aside>
          <section class="chat-window"><div v-if="activeConversation" class="chat-body"><div class="chat-intro"><div class="agent-orb"><ChatDotRound /></div><h3>你好，我是 Yitu 寄件助手</h3><p>告诉我寄件和收件城市、物品重量，我会帮你准备运单草稿并计算报价。</p></div><div ref="messagesContainer" class="messages"><div v-for="message in agentMessages" :key="message.id" :class="['message', message.role]"><div v-if="message.role === 'assistant'" class="message-bubble markdown-body" v-html="renderMarkdown(message.content)" /><div v-else class="message-bubble">{{ message.content }}</div></div></div><div class="chat-composer"><el-input v-model="agentInput" type="textarea" :rows="2" resize="none" placeholder="例如：帮我从广州寄一箱衣服到上海" @keydown.enter.exact.prevent="sendMessage" /><el-button type="primary" :loading="agentSending" :icon="ArrowRight" @click="sendMessage" /></div></div><div v-else class="chat-empty"><div class="agent-orb"><ChatDotRound /></div><h3>用对话完成寄件</h3><p>从地址、重量到报价确认，Yitu 助手会一步步帮你完成。</p><el-button type="primary" @click="startNewConversation">开始新对话</el-button></div></section>
          <aside class="draft-panel"><div class="section-kicker">SHIPMENT DRAFT</div><h3>运单草稿</h3><div v-if="agentDraft" class="draft-content"><el-tag :type="agentDraft.status === 'READY_FOR_CONFIRMATION' ? 'success' : 'warning'">{{ agentDraft.status === 'READY_FOR_CONFIRMATION' ? '待确认' : '信息补充中' }}</el-tag><dl><div v-for="(value, key) in agentDraft.payload" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></div></dl><el-button v-if="agentDraft.status !== 'READY_FOR_CONFIRMATION'" class="full-btn" @click="validateDraft">生成报价</el-button><el-button v-else type="primary" class="full-btn" @click="confirmAgentShipment">确认并创建运单</el-button></div><el-empty v-else description="对话后自动生成" /></aside>
        </div>
        <div v-else-if="view === 'addresses'" class="page-block"><div class="section-head"><div><p class="section-kicker">ADDRESS BOOK</p><h2>地址簿</h2></div><el-button type="primary" @click="openAddressDialog"><Plus /> 新增地址</el-button></div><div class="address-grid"><el-card v-for="a in addresses" :key="a.id" shadow="never" class="address-card"><div class="address-card-head"><div class="address-label">{{ a.label || '常用地址' }}</div><div class="address-actions"><el-button text type="primary" :icon="Edit" @click="editAddress(a)">编辑</el-button><el-button text type="danger" :icon="Delete" @click="removeAddress(a)">删除</el-button></div></div><strong>{{ a.recipient_name }} <span>{{ a.phone }}</span></strong><p>{{ a.full_address }}</p><small>{{ a.province_name }} · {{ a.city_name }} · {{ a.district_name }}</small></el-card></div></div>
        <div v-else-if="view === 'notifications'" class="page-block"><div class="section-head"><div><p class="section-kicker">NOTIFICATIONS</p><h2>消息中心</h2></div></div><div class="notice-list"><div v-for="n in notifications" :key="n.id" :class="['notice', { unread: n.status !== 'READ' }]" @click="readNotice(n)"><div class="notice-dot"></div><div><strong>{{ n.title }}</strong><p>{{ n.content }}</p><time>{{ new Date(n.created_at).toLocaleString('zh-CN') }}</time></div></div><el-empty v-if="!notifications.length" description="暂无消息" /></div></div>
        <div v-else class="page-block"><el-button text @click="view = 'shipments'">← 返回运单</el-button><div v-if="selected" class="detail-layout"><div class="detail-main"><p class="section-kicker">SHIPMENT DETAIL</p><h2>{{ selected.shipment?.shipment_no || selected.shipment_no }}</h2><el-tag type="primary">{{ statusMap[selected.shipment?.status || selected.status] || selected.shipment?.status }}</el-tag><div class="timeline"><div v-for="event in timeline" :key="event.id" class="timeline-item"><div class="timeline-dot"></div><div><strong>{{ event.message }}</strong><time>{{ new Date(event.occurred_at).toLocaleString('zh-CN') }}</time></div></div><el-empty v-if="!timeline.length" description="暂无轨迹" /></div></div><aside class="detail-side"><el-card shadow="never"><small>当前状态</small><h3>{{ statusMap[selected.shipment?.status || selected.status] || '处理中' }}</h3><el-button type="primary" class="full-btn">联系在线客服</el-button></el-card></aside></div></div>
      </section>
    </main>
    <el-dialog v-model="addressDialog" :title="editingAddressId ? '编辑地址' : '新增地址'" width="560px"><el-form label-position="top" v-loading="regionLoading"><div class="form-grid"><el-form-item label="标签"><el-input v-model="addressForm.label" placeholder="例如：家、公司" /></el-form-item><el-form-item label="联系人"><el-input v-model="addressForm.recipient_name" /></el-form-item></div><el-form-item label="手机号"><el-input v-model="addressForm.phone" /></el-form-item><div class="region-grid"><el-form-item label="省"><el-select v-model="addressForm.province_region_id" filterable placeholder="请选择省份" @change="changeProvince"><el-option v-for="item in provinces" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="市"><el-select v-model="addressForm.city_region_id" filterable placeholder="请选择城市" :disabled="!addressForm.province_region_id" @change="changeCity"><el-option v-for="item in cities" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="区 / 县"><el-select v-model="addressForm.district_region_id" filterable placeholder="请选择区县" :disabled="!addressForm.city_region_id"><el-option v-for="item in districts" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item></div><el-form-item label="详细地址"><el-input v-model="addressForm.detail" type="textarea" :rows="2" placeholder="街道、门牌号、小区及楼栋信息" /></el-form-item></el-form><template #footer><el-button @click="addressDialog = false">取消</el-button><el-button type="primary" @click="saveAddress">{{ editingAddressId ? '保存修改' : '保存地址' }}</el-button></template></el-dialog>
  </div>
</template>

<style scoped>
.chat-item span {
  flex: 1;
  min-width: 0;
}

.agent-page.chat-list-collapsed {
  grid-template-columns: 52px minmax(360px, 1fr) 250px;
}

.chat-list.collapsed {
  padding: 16px 8px;
}

.chat-list-actions {
  display: flex;
  align-items: center;
  gap: 3px;
}

.chat-list-actions .el-button + .el-button {
  margin-left: 0;
}

.chat-expand {
  width: 100%;
  min-height: 38px;
}

.chat-delete {
  flex: 0 0 auto;
  margin: -6px -7px 0 0;
}

.markdown-body :deep(> :first-child) {
  margin-top: 0;
}

.markdown-body :deep(> :last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(p),
.markdown-body :deep(ul),
.markdown-body :deep(ol),
.markdown-body :deep(blockquote),
.markdown-body :deep(pre) {
  margin: 0 0 10px;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
}

.markdown-body :deep(li + li) {
  margin-top: 4px;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 14px 0 7px;
  line-height: 1.35;
}

.markdown-body :deep(h1) { font-size: 19px; }
.markdown-body :deep(h2) { font-size: 17px; }
.markdown-body :deep(h3),
.markdown-body :deep(h4) { font-size: 15px; }

.markdown-body :deep(code) {
  padding: 2px 5px;
  background: #dce5df;
  font: 12px 'DM Mono', monospace;
}

.markdown-body :deep(pre) {
  overflow-x: auto;
  padding: 12px;
  background: #1d2528;
  color: #e9eee9;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
  color: inherit;
}

.markdown-body :deep(blockquote) {
  padding-left: 12px;
  border-left: 3px solid #d5b878;
  color: #64736b;
}

.markdown-body :deep(a) {
  color: #35685a;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.address-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.address-card-head .address-label {
  margin-top: 9px;
}

.address-actions {
  display: flex;
  gap: 2px;
}

.address-actions .el-button + .el-button {
  margin-left: 0;
}

.service-tip {
  margin: -2px 0 18px;
  color: #7c8982;
  font-size: 12px;
}
</style>
