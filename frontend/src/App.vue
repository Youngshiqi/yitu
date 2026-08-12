<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowRight, Bell, Box, ChatDotRound, Location, Plus, Search, Setting, User } from '@element-plus/icons-vue'
import { consumeAgentGrant, createAddress, createConversation, createShipment, getAgentDraft, getShipment, issueAgentGrant, listAddresses, listConversations, listMessages, listNotifications, listShipments, listStations, login, markNotificationRead, me, sendAgentMessage, tracking, validateAgentDraft, type Address, type AgentConversation, type AgentMessage, type Notification, type Shipment } from './api'
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
const stations = ref<any[]>([])
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
  { login_name: 'operations.demo', label: '运营管理员 · operations.demo', role: 'OPERATIONS_ADMIN' },
  { login_name: 'system.demo', label: '系统管理员 · system.demo', role: 'SYSTEM_ADMIN' },
]
const addressDialog = ref(false)
const addressForm = ref<Omit<Address, 'id'>>({ label: '常用地址', recipient_name: '', phone: '', district_code: '', detail: '' })
const shipmentForm = ref({ sender_address_id: '', receiver_address_id: '', pickup_method: 'DOOR_PICKUP', delivery_method: 'HOME_DELIVERY' })
const conversations = ref<AgentConversation[]>([])
const activeConversation = ref<AgentConversation | null>(null)
const agentMessages = ref<AgentMessage[]>([])
const agentDraft = ref<any>(null)
const agentInput = ref('')
const agentSending = ref(false)

const statusMap: Record<string, string> = { PENDING_PAYMENT: '待支付', CREATED: '已创建', IN_TRANSIT: '运输中', OUT_FOR_DELIVERY: '派送中', DELIVERED: '已签收', AT_DESTINATION_STATION: '已到达网点' }
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
    const [ship, addr, station, notice, chats] = await Promise.all([listShipments({ limit: 20, offset: (page.value - 1) * 20 }), listAddresses(), listStations(), listNotifications(), listConversations()])
    shipments.value = ship.items ?? []; total.value = ship.total ?? 0; addresses.value = addr; stations.value = station; notifications.value = notice; conversations.value = chats
  } catch { ElMessage.error('数据加载失败，请确认后端服务已启动') } finally { loading.value = false }
}
async function doLogin() { try { await login(loginForm.value.login_name, loginForm.value.password); loggedIn.value = true; user.value = await me(); if (user.value?.role === 'CUSTOMER') await loadData() } catch { ElMessage.error('账号或密码错误') } }
function logout() { localStorage.removeItem('yitu_token'); loggedIn.value = false; user.value = null }
async function openShipment(item: Shipment) { selected.value = await getShipment(item.id); timeline.value = await tracking(item.id); view.value = 'detail' }
async function saveAddress() { try { await createAddress(addressForm.value); addressDialog.value = false; await loadData(); ElMessage.success('地址已保存') } catch { ElMessage.error('地址保存失败') } }
async function submitShipment() { try { await createShipment({ draft: shipmentForm.value, status: 'PENDING_PAYMENT' }); ElMessage.success('运单已创建'); view.value = 'shipments'; await loadData() } catch { ElMessage.error('请完善寄件信息') } }
async function openConversation(conversation?: AgentConversation) { try { activeConversation.value = conversation ?? await createConversation('智能寄件'); agentMessages.value = await listMessages(activeConversation.value.id); agentDraft.value = await getAgentDraft(activeConversation.value.id) } catch { ElMessage.error('AI 助手暂时不可用') } }
async function sendMessage() { const content = agentInput.value.trim(); if (!content || !activeConversation.value || agentSending.value) return; agentInput.value = ''; agentSending.value = true; try { const turn = await sendAgentMessage(activeConversation.value.id, content); agentMessages.value.push(turn.user_message, turn.assistant_message); agentDraft.value = await getAgentDraft(activeConversation.value.id) } catch { ElMessage.error('消息发送失败，请稍后重试') } finally { agentSending.value = false } }
async function validateDraft() { if (!activeConversation.value) return; try { const result = await validateAgentDraft(activeConversation.value.id); agentDraft.value = result.draft; ElMessage.success(`报价已生成：${(result.quote.total_cents / 100).toFixed(2)} 元`) } catch { ElMessage.warning('请先在对话中补充寄件信息') } }
async function confirmAgentShipment() { if (!activeConversation.value) return; try { const grant = await issueAgentGrant(activeConversation.value.id); await consumeAgentGrant(grant.id); ElMessage.success('运单已创建'); await loadData(); view.value = 'shipments' } catch { ElMessage.error('草稿尚未准备好，请重新确认报价') } }
async function readNotice(item: Notification) { if (item.status !== 'READ') { await markNotificationRead(item.id); item.status = 'READ' } }
onMounted(async () => { if (loggedIn.value) { try { user.value = await me(); if (user.value?.role === 'CUSTOMER') await loadData() } catch { logout() } } })
</script>

<template>
  <div v-if="!loggedIn" class="login-page">
    <div class="login-art"><div class="eyebrow">YITU LOGISTICS / 2026</div><h1>把每一次<br><em>寄托</em>送到。</h1><p>从下单、交接到签收，一处掌握完整轨迹。</p><div class="route-line"><span>广州</span><ArrowRight /><span>上海</span></div></div>
    <el-card class="login-card" shadow="never"><div class="brand-mark">Y</div><h2>欢迎回来</h2><p class="muted">选择身份进入对应工作台</p><el-form @submit.prevent="doLogin" @keyup.enter="doLogin"><el-form-item label="登录身份"><el-select v-model="loginForm.login_name" size="large" class="full-input" filterable><el-option v-for="account in loginAccounts" :key="account.login_name" :label="account.label" :value="account.login_name"><div class="login-option"><span>{{ account.label }}</span><small>{{ account.role }}</small></div></el-option></el-select></el-form-item><el-form-item label="密码"><el-input v-model="loginForm.password" type="password" show-password size="large" /></el-form-item><el-button type="primary" size="large" class="full-btn" @click="doLogin">进入工作台 <ArrowRight /></el-button></el-form><div class="login-note">演示环境统一密码：YituDemo2026!</div></el-card>
  </div>
  <CourierWorkspace v-else-if="user?.role === 'COURIER'" :user="user" @logout="logout" />
  <OperationsWorkspace v-else-if="user?.role === 'OPERATIONS_ADMIN'" :user="user" @logout="logout" />
  <SystemAdminWorkspace v-else-if="user?.role === 'SYSTEM_ADMIN'" :user="user" @logout="logout" />
  <div v-else class="app-shell">
    <aside class="sidebar"><div class="logo"><span>Y</span><div>Yitu<small>物流工作台</small></div></div><div class="workspace-label">客户工作区</div><nav><button v-for="item in nav" :key="item.id" :class="{ active: view === item.id }" @click="view = item.id"><component :is="item.icon" /><span>{{ item.label }}</span><b v-if="item.badge">{{ item.badge }}</b></button></nav><div class="sidebar-foot"><el-button text @click="logout"><Setting /> 退出登录</el-button></div></aside>
    <main class="main"><header class="topbar"><div><div class="crumb">客户中心 <span>/</span> {{ nav.find(n => n.id === view)?.label ?? '运单详情' }}</div><h1>{{ view === 'detail' ? '运单详情' : nav.find(n => n.id === view)?.label }}</h1></div><div class="top-actions"><el-input v-model="query" placeholder="搜索运单号" :prefix-icon="Search" clearable /><el-avatar :size="34">{{ user?.display_name?.slice(0, 1) }}</el-avatar><span class="user-name">{{ user?.display_name || '演示客户' }}</span></div></header>
      <section v-loading="loading" class="content">
        <div v-if="view === 'shipments'" class="page-block"><div class="section-head"><div><p class="section-kicker">TRACKING OVERVIEW</p><h2>最近运单</h2></div><el-button type="primary" @click="view = 'create'"><Plus /> 新建寄件</el-button></div><div class="stat-strip"><div><small>全部运单</small><strong>{{ total }}</strong></div><div><small>运输中</small><strong>{{ shipments.filter(s => s.status === 'IN_TRANSIT').length }}</strong></div><div><small>待支付</small><strong>{{ shipments.filter(s => s.status === 'PENDING_PAYMENT').length }}</strong></div></div><el-table :data="shipments.filter(s => !query || s.shipment_no.includes(query))" class="shipment-table" @row-click="openShipment"><el-table-column prop="shipment_no" label="运单号" min-width="190"><template #default="{ row }"><span class="shipment-no">{{ row.shipment_no }}</span></template></el-table-column><el-table-column prop="status" label="状态"><template #default="{ row }"><el-tag :type="row.status === 'DELIVERED' ? 'success' : row.status === 'PENDING_PAYMENT' ? 'warning' : 'primary'" effect="light">{{ statusMap[row.status] || row.status }}</el-tag></template></el-table-column><el-table-column label="操作" width="100"><template #default="{ row }"><el-button text type="primary" @click.stop="openShipment(row)">查看 <ArrowRight /></el-button></template></el-table-column></el-table><el-pagination v-if="total > 20" v-model:current-page="page" layout="prev, pager, next" :total="total" @current-change="loadData" /></div>
        <div v-else-if="view === 'create'" class="page-block narrow"><div class="section-head"><div><p class="section-kicker">NEW SHIPMENT</p><h2>创建寄件</h2></div></div><el-card shadow="never" class="form-card"><el-form label-position="top"><el-form-item label="寄件地址"><el-select v-model="shipmentForm.sender_address_id" placeholder="选择寄件地址" filterable><el-option v-for="a in addresses" :key="a.id" :label="`${a.recipient_name} · ${a.detail}`" :value="a.id" /></el-select></el-form-item><el-form-item label="收件地址"><el-select v-model="shipmentForm.receiver_address_id" placeholder="选择收件地址" filterable><el-option v-for="a in addresses" :key="a.id" :label="`${a.recipient_name} · ${a.detail}`" :value="a.id" /></el-select></el-form-item><div class="form-grid"><el-form-item label="寄件方式"><el-radio-group v-model="shipmentForm.pickup_method"><el-radio-button value="DOOR_PICKUP">上门取件</el-radio-button><el-radio-button value="STATION_DROPOFF">网点寄件</el-radio-button></el-radio-group></el-form-item><el-form-item label="派送方式"><el-radio-group v-model="shipmentForm.delivery_method"><el-radio-button value="HOME_DELIVERY">送货上门</el-radio-button><el-radio-button value="STATION_PICKUP">网点自提</el-radio-button></el-radio-group></el-form-item></div><el-button type="primary" size="large" @click="submitShipment">创建运单 <ArrowRight /></el-button></el-form></el-card></div>
        <div v-else-if="view === 'agent'" class="agent-page"><aside class="chat-list"><div class="section-head"><div><p class="section-kicker">ASSISTANT</p><h2>智能寄件</h2></div><el-button circle type="primary" :icon="Plus" @click="openConversation()" /></div><button v-for="chat in conversations" :key="chat.id" :class="['chat-item', { active: activeConversation?.id === chat.id }]" @click="openConversation(chat)"><ChatDotRound /><span>{{ chat.title || '未命名会话' }}<small>{{ new Date(chat.updated_at).toLocaleDateString('zh-CN') }}</small></span></button><el-empty v-if="!conversations.length" description="开始一次智能寄件" /></aside><section class="chat-window"><div v-if="activeConversation" class="chat-body"><div class="chat-intro"><div class="agent-orb"><ChatDotRound /></div><h3>你好，我是 Yitu 寄件助手</h3><p>告诉我寄件和收件城市、物品重量，我会帮你准备运单草稿并计算报价。</p></div><div class="messages"><div v-for="message in agentMessages" :key="message.id" :class="['message', message.role]"><div class="message-bubble">{{ message.content }}</div></div></div><div class="chat-composer"><el-input v-model="agentInput" type="textarea" :rows="2" resize="none" placeholder="例如：帮我从广州寄一箱衣服到上海" @keydown.enter.exact.prevent="sendMessage" /><el-button type="primary" :loading="agentSending" :icon="ArrowRight" @click="sendMessage" /></div></div><div v-else class="chat-empty"><div class="agent-orb"><ChatDotRound /></div><h3>用对话完成寄件</h3><p>从地址、重量到报价确认，Yitu 助手会一步步帮你完成。</p><el-button type="primary" @click="openConversation()">开始新对话</el-button></div></section><aside class="draft-panel"><div class="section-kicker">SHIPMENT DRAFT</div><h3>运单草稿</h3><div v-if="agentDraft" class="draft-content"><el-tag :type="agentDraft.status === 'READY_FOR_CONFIRMATION' ? 'success' : 'warning'">{{ agentDraft.status === 'READY_FOR_CONFIRMATION' ? '待确认' : '信息补充中' }}</el-tag><dl><div v-for="(value, key) in agentDraft.payload" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></div></dl><el-button v-if="agentDraft.status !== 'READY_FOR_CONFIRMATION'" class="full-btn" @click="validateDraft">生成报价</el-button><el-button v-else type="primary" class="full-btn" @click="confirmAgentShipment">确认并创建运单</el-button></div><el-empty v-else description="对话后自动生成" /></aside></div>
        <div v-else-if="view === 'addresses'" class="page-block"><div class="section-head"><div><p class="section-kicker">ADDRESS BOOK</p><h2>地址簿</h2></div><el-button type="primary" @click="addressDialog = true"><Plus /> 新增地址</el-button></div><div class="address-grid"><el-card v-for="a in addresses" :key="a.id" shadow="never" class="address-card"><div class="address-label">{{ a.label || '常用地址' }}</div><strong>{{ a.recipient_name }} <span>{{ a.phone }}</span></strong><p>{{ a.detail }}</p><small>{{ a.district_code }}</small></el-card></div></div>
        <div v-else-if="view === 'notifications'" class="page-block"><div class="section-head"><div><p class="section-kicker">NOTIFICATIONS</p><h2>消息中心</h2></div></div><div class="notice-list"><div v-for="n in notifications" :key="n.id" :class="['notice', { unread: n.status !== 'READ' }]" @click="readNotice(n)"><div class="notice-dot"></div><div><strong>{{ n.title }}</strong><p>{{ n.content }}</p><time>{{ new Date(n.created_at).toLocaleString('zh-CN') }}</time></div></div><el-empty v-if="!notifications.length" description="暂无消息" /></div></div>
        <div v-else class="page-block"><el-button text @click="view = 'shipments'">← 返回运单</el-button><div v-if="selected" class="detail-layout"><div class="detail-main"><p class="section-kicker">SHIPMENT DETAIL</p><h2>{{ selected.shipment?.shipment_no || selected.shipment_no }}</h2><el-tag type="primary">{{ statusMap[selected.shipment?.status || selected.status] || selected.shipment?.status }}</el-tag><div class="timeline"><div v-for="event in timeline" :key="event.id" class="timeline-item"><div class="timeline-dot"></div><div><strong>{{ event.message }}</strong><time>{{ new Date(event.occurred_at).toLocaleString('zh-CN') }}</time></div></div><el-empty v-if="!timeline.length" description="暂无轨迹" /></div></div><aside class="detail-side"><el-card shadow="never"><small>当前状态</small><h3>{{ statusMap[selected.shipment?.status || selected.status] || '处理中' }}</h3><el-button type="primary" class="full-btn">联系在线客服</el-button></el-card></aside></div></div>
      </section>
    </main>
    <el-dialog v-model="addressDialog" title="新增地址" width="480px"><el-form label-position="top"><el-form-item label="标签"><el-input v-model="addressForm.label" /></el-form-item><el-form-item label="收件人"><el-input v-model="addressForm.recipient_name" /></el-form-item><el-form-item label="手机号"><el-input v-model="addressForm.phone" /></el-form-item><el-form-item label="行政区编码"><el-input v-model="addressForm.district_code" /></el-form-item><el-form-item label="详细地址"><el-input v-model="addressForm.detail" /></el-form-item></el-form><template #footer><el-button @click="addressDialog = false">取消</el-button><el-button type="primary" @click="saveAddress">保存地址</el-button></template></el-dialog>
  </div>
</template>
